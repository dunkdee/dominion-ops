#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

PROTOCOL_VERSION = "2026-07-28"
LEGACY_PROTOCOL_VERSION = "2025-06-18"
SERVER_NAME = "dominion-mcp-cli"
SERVER_VERSION = "1.0.0"
MAX_BODY_BYTES = 1_048_576
MAX_RESPONSE_BYTES = 1_048_576
REGISTRY_PATH = Path(os.getenv("DOMINION_MCP_REGISTRY", Path(__file__).with_name("connector_registry.json")))
STATE_DIR = Path(os.getenv("DOMINION_MCP_STATE_DIR", str(Path.home() / ".dominion/mcp-cli")))


class ConnectorError(RuntimeError):
    pass


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        raise ConnectorError(f"redirect_not_allowed:{code}")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


def load_registry(path: Path = REGISTRY_PATH) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError) as exc:
        raise ConnectorError(f"registry_unavailable:{type(exc).__name__}") from exc
    if not isinstance(data, dict) or data.get("schema") != "dominion-mcp-connector-registry-v1":
        raise ConnectorError("registry_schema_invalid")
    if data.get("default_mode") != "deny":
        raise ConnectorError("registry_must_fail_closed")
    if data.get("external_mutation_enabled") is not False:
        raise ConnectorError("external_mutation_must_be_disabled")
    connectors = data.get("connectors")
    if not isinstance(connectors, dict) or not connectors:
        raise ConnectorError("registry_connectors_missing")
    for connector_id, spec in connectors.items():
        if not re.fullmatch(r"[a-z0-9][a-z0-9_.-]{1,79}", connector_id):
            raise ConnectorError(f"connector_id_invalid:{connector_id}")
        if not isinstance(spec, dict):
            raise ConnectorError(f"connector_spec_invalid:{connector_id}")
        if spec.get("effect") != "read_only":
            raise ConnectorError(f"connector_effect_not_allowed:{connector_id}")
        if spec.get("adapter") not in {"http_get", "exec", "file_read"}:
            raise ConnectorError(f"connector_adapter_invalid:{connector_id}")
    return data


def public_registry(registry: dict[str, Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for connector_id in sorted(registry["connectors"]):
        spec = registry["connectors"][connector_id]
        result.append(
            {
                "id": connector_id,
                "title": str(spec.get("title") or connector_id),
                "description": str(spec.get("description") or ""),
                "adapter": spec["adapter"],
                "effect": spec["effect"],
                "classification": str(spec.get("classification") or "internal"),
            }
        )
    return result


def _validated_params(spec: dict[str, Any], supplied: Any) -> dict[str, str]:
    if supplied in (None, {}):
        supplied = {}
    if not isinstance(supplied, dict):
        raise ConnectorError("params_must_be_object")
    allowed = spec.get("allowed_params", {})
    if not isinstance(allowed, dict):
        raise ConnectorError("connector_allowed_params_invalid")
    unknown = sorted(set(supplied) - set(allowed))
    if unknown:
        raise ConnectorError(f"params_not_allowed:{','.join(unknown)}")
    result: dict[str, str] = {}
    for key, value in supplied.items():
        text = str(value)
        rule = allowed.get(key, {})
        if not isinstance(rule, dict):
            raise ConnectorError(f"param_rule_invalid:{key}")
        max_length = int(rule.get("max_length", 256))
        if len(text) > max_length:
            raise ConnectorError(f"param_too_long:{key}")
        pattern = str(rule.get("pattern", r"^[A-Za-z0-9._:/@+ -]*$"))
        if not re.fullmatch(pattern, text):
            raise ConnectorError(f"param_pattern_rejected:{key}")
        result[key] = text
    return result


def _http_get(spec: dict[str, Any], params: dict[str, str]) -> dict[str, Any]:
    target = str(spec.get("target") or "")
    parsed = urllib.parse.urlsplit(target)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ConnectorError("http_target_invalid")
    query_keys = spec.get("query_params", {})
    if not isinstance(query_keys, dict):
        raise ConnectorError("query_param_map_invalid")
    mapped: dict[str, str] = {}
    for incoming, outgoing in query_keys.items():
        if incoming in params:
            mapped[str(outgoing)] = params[incoming]
    query = urllib.parse.urlencode(mapped)
    url = urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path, query or parsed.query, parsed.fragment))
    timeout = max(1, min(int(spec.get("timeout_seconds", 5)), 20))
    request = urllib.request.Request(url, method="GET", headers={"Accept": "application/json,text/plain;q=0.8"})
    opener = urllib.request.build_opener(NoRedirect)
    try:
        with opener.open(request, timeout=timeout) as response:
            raw = response.read(MAX_RESPONSE_BYTES + 1)
            if len(raw) > MAX_RESPONSE_BYTES:
                raise ConnectorError("response_too_large")
            content_type = response.headers.get("Content-Type", "")
            text = raw.decode("utf-8", errors="replace")
            payload: Any = text
            if "json" in content_type.lower() or text.lstrip().startswith(("{", "[")):
                try:
                    payload = json.loads(text)
                except ValueError:
                    payload = text
            return {"status": int(response.status), "content_type": content_type, "body": payload}
    except urllib.error.HTTPError as exc:
        raise ConnectorError(f"http_status:{exc.code}") from exc
    except urllib.error.URLError as exc:
        raise ConnectorError(f"http_unreachable:{type(exc.reason).__name__}") from exc


def _exec(spec: dict[str, Any], params: dict[str, str]) -> dict[str, Any]:
    argv_template = spec.get("argv")
    if not isinstance(argv_template, list) or not argv_template or not all(isinstance(x, str) and x for x in argv_template):
        raise ConnectorError("exec_argv_invalid")
    argv: list[str] = []
    for token in argv_template:
        try:
            rendered = token.format_map(params)
        except KeyError as exc:
            raise ConnectorError(f"required_param_missing:{exc.args[0]}") from exc
        argv.append(rendered)
    timeout = max(1, min(int(spec.get("timeout_seconds", 5)), 20))
    try:
        cp = subprocess.run(argv, shell=False, check=False, capture_output=True, text=True, timeout=timeout, env={"PATH": os.environ.get("PATH", "/usr/bin:/bin")})
    except (OSError, subprocess.SubprocessError) as exc:
        raise ConnectorError(f"exec_failed:{type(exc).__name__}") from exc
    stdout = cp.stdout[:MAX_RESPONSE_BYTES]
    stderr = cp.stderr[:8192]
    return {"returncode": cp.returncode, "stdout": stdout, "stderr": stderr}


def _file_read(spec: dict[str, Any], params: dict[str, str]) -> dict[str, Any]:
    root = Path(str(spec.get("root") or "")).expanduser().resolve()
    relative = params.get("path", str(spec.get("path") or ""))
    if not relative:
        raise ConnectorError("file_path_missing")
    candidate = (root / relative).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ConnectorError("file_path_escape") from exc
    if not candidate.is_file() or candidate.is_symlink():
        raise ConnectorError("file_unavailable")
    raw = candidate.read_bytes()
    if len(raw) > min(int(spec.get("max_bytes", 262144)), MAX_RESPONSE_BYTES):
        raise ConnectorError("file_too_large")
    return {"path": str(candidate.relative_to(root)), "text": raw.decode("utf-8", errors="replace")}


def write_receipt(connector_id: str, args: dict[str, Any], status: str, elapsed_ms: int, detail: str = "") -> None:
    try:
        receipts = STATE_DIR / "receipts"
        receipts.mkdir(parents=True, exist_ok=True, mode=0o700)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
        path = receipts / f"{stamp}-{connector_id}-{uuid.uuid4().hex[:8]}.json"
        payload = {
            "schema": "dominion-mcp-connector-receipt-v1",
            "observed_at": utc_now(),
            "connector_id": connector_id,
            "status": status,
            "elapsed_ms": elapsed_ms,
            "arguments_sha256": sha256_json(args),
            "detail": detail[:160],
        }
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.chmod(path, 0o600)
    except OSError:
        return


def invoke_connector(connector_id: str, supplied_params: Any = None, registry: dict[str, Any] | None = None) -> dict[str, Any]:
    registry = registry or load_registry()
    spec = registry["connectors"].get(connector_id)
    if not isinstance(spec, dict):
        raise ConnectorError("connector_not_registered")
    if spec.get("effect") != "read_only":
        raise ConnectorError("external_or_mutating_effect_denied")
    params = _validated_params(spec, supplied_params)
    started = time.monotonic()
    try:
        adapter = spec["adapter"]
        if adapter == "http_get":
            result = _http_get(spec, params)
        elif adapter == "exec":
            result = _exec(spec, params)
        elif adapter == "file_read":
            result = _file_read(spec, params)
        else:
            raise ConnectorError("adapter_not_supported")
        elapsed = int((time.monotonic() - started) * 1000)
        write_receipt(connector_id, params, "PASS", elapsed)
        return {"connector_id": connector_id, "status": "PASS", "elapsed_ms": elapsed, "result": result}
    except ConnectorError as exc:
        elapsed = int((time.monotonic() - started) * 1000)
        write_receipt(connector_id, params, "FAIL", elapsed, str(exc))
        raise


def tools_list() -> list[dict[str, Any]]:
    return [
        {
            "name": "dominion_connectors_list",
            "title": "List Dominion connectors",
            "description": "List the governed read-only connector registry available through the Dominion MCP CLI server.",
            "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        },
        {
            "name": "dominion_connector_invoke",
            "title": "Invoke a governed Dominion connector",
            "description": "Invoke one registered connector. Targets are fixed by the reviewed registry; arbitrary URLs and shell commands are not accepted.",
            "inputSchema": {
                "type": "object",
                "properties": {"connector_id": {"type": "string", "minLength": 2, "maxLength": 80}, "params": {"type": "object"}},
                "required": ["connector_id"],
                "additionalProperties": False,
            },
        },
    ]


def server_meta() -> dict[str, Any]:
    return {"io.modelcontextprotocol/serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION}}


def rpc_result(request_id: Any, result: dict[str, Any]) -> dict[str, Any]:
    result = dict(result)
    meta = result.get("_meta") if isinstance(result.get("_meta"), dict) else {}
    result["_meta"] = {**meta, **server_meta()}
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def rpc_error(request_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message, "data": {"_meta": server_meta()}}}


def handle_rpc(message: Any) -> dict[str, Any] | None:
    if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
        return rpc_error(message.get("id") if isinstance(message, dict) else None, -32600, "Invalid Request")
    request_id = message.get("id")
    method = message.get("method")
    params = message.get("params", {})
    if method == "notifications/initialized":
        return None
    if method == "server/discover":
        return rpc_result(
            request_id,
            {
                "resultType": "complete",
                "supportedVersions": [PROTOCOL_VERSION, LEGACY_PROTOCOL_VERSION],
                "capabilities": {"tools": {"listChanged": False}},
                "instructions": "Use only registered Dominion connectors. All launch connectors are read-only and fail closed.",
                "ttlMs": 60000,
                "cacheScope": "private",
            },
        )
    if method == "initialize":
        return rpc_result(
            request_id,
            {
                "protocolVersion": LEGACY_PROTOCOL_VERSION,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
                "instructions": "Legacy compatibility mode. Prefer MCP 2026-07-28 server/discover.",
            },
        )
    if method == "ping":
        return rpc_result(request_id, {})
    if method == "tools/list":
        return rpc_result(request_id, {"tools": tools_list(), "ttlMs": 60000, "cacheScope": "private"})
    if method == "tools/call":
        if not isinstance(params, dict):
            return rpc_error(request_id, -32602, "Invalid params")
        name = params.get("name")
        arguments = params.get("arguments") or {}
        try:
            if name == "dominion_connectors_list":
                registry = load_registry()
                payload = {"connectors": public_registry(registry), "external_mutation_enabled": False, "registry_sha256": sha256_json(registry)}
            elif name == "dominion_connector_invoke":
                if not isinstance(arguments, dict) or not isinstance(arguments.get("connector_id"), str):
                    return rpc_error(request_id, -32602, "connector_id is required")
                payload = invoke_connector(arguments["connector_id"], arguments.get("params"))
            else:
                return rpc_error(request_id, -32601, "Tool not found")
            text = json.dumps(payload, ensure_ascii=False, sort_keys=True)
            return rpc_result(request_id, {"content": [{"type": "text", "text": text}], "structuredContent": payload, "isError": False})
        except ConnectorError as exc:
            payload = {"status": "FAIL", "error": str(exc)}
            return rpc_result(request_id, {"content": [{"type": "text", "text": json.dumps(payload)}], "structuredContent": payload, "isError": True})
    return rpc_error(request_id, -32601, "Method not found")


def health_payload() -> dict[str, Any]:
    registry = load_registry()
    return {
        "status": "ok",
        "service": SERVER_NAME,
        "version": SERVER_VERSION,
        "protocol": PROTOCOL_VERSION,
        "registry_schema": registry["schema"],
        "registry_sha256": sha256_json(registry),
        "connector_count": len(registry["connectors"]),
        "external_mutation_enabled": False,
        "binding": "loopback-only",
        "time": utc_now(),
    }


class Handler(BaseHTTPRequestHandler):
    server_version = "DominionMCP/1.0"

    def log_message(self, fmt: str, *args: Any) -> None:
        sys.stderr.write(f"mcp-http {self.address_string()} {fmt % args}\n")

    def _json(self, status: int, payload: Any) -> None:
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self) -> None:  # noqa: N802
        try:
            if self.path == "/health":
                self._json(200, health_payload())
                return
            if self.path == "/connectors":
                registry = load_registry()
                self._json(200, {"connectors": public_registry(registry), "external_mutation_enabled": False})
                return
            self._json(404, {"error": "not_found"})
        except ConnectorError as exc:
            self._json(503, {"status": "error", "error": str(exc)})

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/mcp":
            self._json(404, {"error": "not_found"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self._json(400, rpc_error(None, -32700, "Invalid Content-Length"))
            return
        if length <= 0 or length > MAX_BODY_BYTES:
            self._json(413, rpc_error(None, -32700, "Request body size rejected"))
            return
        try:
            message = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            self._json(400, rpc_error(None, -32700, "Parse error"))
            return
        method = message.get("method") if isinstance(message, dict) else None
        protocol = self.headers.get("MCP-Protocol-Version", "")
        header_method = self.headers.get("Mcp-Method", "")
        header_name = self.headers.get("Mcp-Name", "")
        if protocol == PROTOCOL_VERSION:
            if header_method != method:
                self._json(400, rpc_error(message.get("id"), -32020, "Mcp-Method header mismatch"))
                return
            expected_name = ""
            if method == "tools/call" and isinstance(message.get("params"), dict):
                expected_name = str(message["params"].get("name") or "")
            if expected_name and header_name != expected_name:
                self._json(400, rpc_error(message.get("id"), -32020, "Mcp-Name header mismatch"))
                return
        elif method not in {"initialize", "notifications/initialized"}:
            self._json(400, rpc_error(message.get("id") if isinstance(message, dict) else None, -32001, "Unsupported or missing MCP-Protocol-Version"))
            return
        response = handle_rpc(message)
        if response is None:
            self.send_response(204)
            self.end_headers()
            return
        self._json(200, response)


def run_stdio() -> int:
    for raw in sys.stdin:
        raw = raw.strip()
        if not raw:
            continue
        try:
            message = json.loads(raw)
            response = handle_rpc(message)
        except ValueError:
            response = rpc_error(None, -32700, "Parse error")
        if response is not None:
            sys.stdout.write(json.dumps(response, ensure_ascii=False, separators=(",", ":")) + "\n")
            sys.stdout.flush()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Governed Dominion MCP CLI connector server")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--stdio", action="store_true", help="serve newline-delimited JSON-RPC over stdin/stdout")
    mode.add_argument("--http", action="store_true", help="serve loopback MCP/health HTTP")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8390)
    args = parser.parse_args()
    load_registry()
    if args.stdio:
        return run_stdio()
    if args.host not in {"127.0.0.1", "::1", "localhost"}:
        raise SystemExit("MCP HTTP binding must remain loopback-only")
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    try:
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
