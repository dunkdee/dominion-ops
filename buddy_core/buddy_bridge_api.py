#!/usr/bin/env python3
from flask import Flask, request, jsonify
import hmac
import json
import os
import re
import sys
import threading
from pathlib import Path
from urllib.parse import urlparse

import requests

try:
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=Path.home() / "buddy_core" / ".env")
    load_dotenv(dotenv_path=Path.home() / "conductor" / ".env")
    load_dotenv(dotenv_path=Path.home() / ".env")
except ImportError:
    pass


def _bootstrap_canonical_repo_root() -> Path | None:
    """Expose canonical repo packages to the standalone Buddy runtime.

    Production starts Buddy Bridge from ``~/buddy_core`` while governed shared
    engines live under the canonical ``~/dominion-ops`` repository. Resolve only
    an explicitly configured root or that canonical owner location, and add it
    before importing shared modules.
    """
    candidates: list[Path] = []
    configured = os.getenv("DOMINION_REPO_ROOT", "").strip()
    if configured:
        candidates.append(Path(configured).expanduser())
    candidates.append(Path.home() / "dominion-ops")

    for candidate in candidates:
        try:
            resolved = candidate.resolve(strict=True)
        except (OSError, RuntimeError):
            continue
        if not resolved.is_dir():
            continue
        if not (resolved / "apps" / "revenue_engine").is_dir():
            continue
        root = str(resolved)
        if root not in sys.path:
            sys.path.insert(0, root)
        return resolved
    return None


DOMINION_REPO_ROOT = _bootstrap_canonical_repo_root()

from core.capability_health import audit_capabilities
from core.operator import get_operator
from core.revenue_runtime import (
    MAX_PAYLOAD_BYTES,
    run_compounding_payload,
    run_fast_cash_payload,
)

app = Flask(__name__)

BASE = Path.home() / "buddy_core"
LOG = BASE / "buddy_bridge.log"
DEALS = BASE / "scored_deals.json"
BUDDY_WEB_TOKEN = os.getenv("BUDDY_WEB_TOKEN", "").strip()
MCP_BASE_URL = os.getenv("BUDDY_MCP_BASE_URL", "http://127.0.0.1:8390").rstrip("/")
MCP_PROTOCOL_VERSION = "2026-07-28"
MAX_MCP_REQUEST_BYTES = 65_536
MAX_LOG_BYTES = max(1_048_576, int(os.getenv("BUDDY_BRIDGE_MAX_LOG_BYTES", "5242880")))
LOG_BACKUPS = max(1, min(int(os.getenv("BUDDY_BRIDGE_LOG_BACKUPS", "3")), 10))


def _rotate_log() -> None:
    try:
        if not LOG.exists() or LOG.stat().st_size < MAX_LOG_BYTES:
            return
        oldest = Path(f"{LOG}.{LOG_BACKUPS}")
        if oldest.exists():
            oldest.unlink()
        for index in range(LOG_BACKUPS - 1, 0, -1):
            source = Path(f"{LOG}.{index}")
            if source.exists():
                source.replace(Path(f"{LOG}.{index + 1}"))
        LOG.replace(Path(f"{LOG}.1"))
    except OSError:
        # Logging must never take Buddy offline.
        return


def log(x):
    try:
        BASE.mkdir(parents=True, exist_ok=True)
        _rotate_log()
        with LOG.open("a", encoding="utf-8") as f:
            f.write(str(x)[:4000] + "\n")
    except OSError:
        return


def _authorized(req) -> bool:
    """Fail closed. Accept the same bearer token as Buddy web or X-Buddy-Token."""
    if not BUDDY_WEB_TOKEN:
        return False
    supplied = req.headers.get("X-Buddy-Token", "").strip()
    if supplied and hmac.compare_digest(supplied, BUDDY_WEB_TOKEN):
        return True
    auth = req.headers.get("Authorization", "")
    expected = f"Bearer {BUDDY_WEB_TOKEN}"
    return bool(auth) and hmac.compare_digest(auth, expected)


def _mcp_base() -> str:
    parsed = urlparse(MCP_BASE_URL)
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise RuntimeError("MCP endpoint must remain loopback-only")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise RuntimeError("MCP endpoint format rejected")
    return MCP_BASE_URL


def _mcp_connectors() -> dict:
    response = requests.get(f"{_mcp_base()}/connectors", timeout=5)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict) or payload.get("external_mutation_enabled") is not False:
        raise RuntimeError("MCP connector registry failed read-only invariant")
    connectors = payload.get("connectors")
    if not isinstance(connectors, list):
        raise RuntimeError("MCP connector registry malformed")
    return payload


def _mcp_invoke(connector_id: str, params: dict | None = None) -> dict:
    connector_id = (connector_id or "").strip()
    if not re.fullmatch(r"[a-z0-9][a-z0-9_.-]{1,79}", connector_id):
        raise ValueError("invalid connector_id")
    params = params or {}
    if not isinstance(params, dict):
        raise TypeError("params must be an object")
    arguments = {"connector_id": connector_id, "params": params}
    encoded = json.dumps(arguments, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if len(encoded) > MAX_MCP_REQUEST_BYTES:
        raise ValueError("MCP request too large")

    # Verify the selected connector is present in the current read-only registry
    # before asking MCP to invoke it. The MCP server independently re-validates.
    registry = _mcp_connectors()
    allowed = {
        item.get("id")
        for item in registry.get("connectors", [])
        if isinstance(item, dict) and item.get("effect") == "read_only"
    }
    if connector_id not in allowed:
        raise ValueError("connector not registered as read-only")

    rpc = {
        "jsonrpc": "2.0",
        "id": "buddy-bridge",
        "method": "tools/call",
        "params": {
            "name": "dominion_connector_invoke",
            "arguments": arguments,
        },
    }
    response = requests.post(
        f"{_mcp_base()}/mcp",
        json=rpc,
        headers={
            "MCP-Protocol-Version": MCP_PROTOCOL_VERSION,
            "Mcp-Method": "tools/call",
            "Mcp-Name": "dominion_connector_invoke",
        },
        timeout=25,
    )
    response.raise_for_status()
    envelope = response.json()
    if not isinstance(envelope, dict) or "result" not in envelope:
        raise RuntimeError("MCP response malformed")
    result = envelope["result"]
    if not isinstance(result, dict):
        raise RuntimeError("MCP result malformed")
    if result.get("isError") is True:
        detail = result.get("structuredContent") or {"error": "connector failed"}
        raise RuntimeError(json.dumps(detail, ensure_ascii=False)[:500])
    structured = result.get("structuredContent")
    if not isinstance(structured, dict) or structured.get("status") != "PASS":
        raise RuntimeError("MCP connector did not return PASS evidence")
    return structured


def _governed_revenue_request(runner, lane: str):
    if not _authorized(request):
        return jsonify(error="unauthorized"), 401
    if request.content_length is not None and request.content_length > MAX_PAYLOAD_BYTES:
        return jsonify(status="BLOCKED", error="payload_too_large"), 413
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify(status="BLOCKED", error="JSON object required"), 400
    try:
        result = runner(payload)
        log(
            f"[REVENUE_{lane}] publication_state=DRAFT_SHADOW "
            f"review_hold={result.get('review_hold', False)}"
        )
        return jsonify(result)
    except (KeyError, TypeError, ValueError) as exc:
        log(f"[REVENUE_{lane}_BLOCKED] {type(exc).__name__}")
        return jsonify(
            status="BLOCKED",
            publication_state="DRAFT_SHADOW",
            error=type(exc).__name__,
            detail=str(exc)[:400],
        ), 400
    except Exception as exc:
        log(f"[REVENUE_{lane}_ERROR] {type(exc).__name__}")
        return jsonify(
            status="BLOCKED",
            publication_state="DRAFT_SHADOW",
            error=type(exc).__name__,
        ), 500


@app.get("/health")
def health():
    return jsonify(
        ok=True,
        service="buddy_bridge",
        port=5052,
        operator="v2",
        canonical_repo=bool(DOMINION_REPO_ROOT),
    )


@app.get("/webhook/buddy/capabilities")
def buddy_capabilities():
    if not _authorized(request):
        return jsonify(error="unauthorized"), 401
    try:
        report = audit_capabilities(get_operator())
        return jsonify(report), 200 if report.get("status") == "HEALTHY" else 503
    except Exception as exc:
        log(f"[CAPABILITY_AUDIT_ERROR] {type(exc).__name__}")
        return jsonify(status="DEGRADED", error=type(exc).__name__), 503


@app.get("/webhook/buddy/connectors")
def buddy_connectors():
    if not _authorized(request):
        return jsonify(error="unauthorized"), 401
    try:
        return jsonify(_mcp_connectors())
    except Exception as exc:
        log(f"[MCP_LIST_ERROR] {type(exc).__name__}")
        return jsonify(status="BLOCKED", error=type(exc).__name__), 503


@app.post("/webhook/buddy/connectors/invoke")
def buddy_connector_invoke():
    if not _authorized(request):
        return jsonify(error="unauthorized"), 401
    if request.content_length is not None and request.content_length > MAX_MCP_REQUEST_BYTES:
        return jsonify(status="BLOCKED", error="payload_too_large"), 413
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify(status="BLOCKED", error="JSON object required"), 400
    try:
        result = _mcp_invoke(payload.get("connector_id", ""), payload.get("params"))
        log(f"[MCP_INVOKE] connector={result.get('connector_id')} status={result.get('status')}")
        return jsonify(result)
    except (KeyError, TypeError, ValueError) as exc:
        log(f"[MCP_INVOKE_BLOCKED] {type(exc).__name__}")
        return jsonify(status="BLOCKED", error=type(exc).__name__, detail=str(exc)[:300]), 400
    except Exception as exc:
        log(f"[MCP_INVOKE_ERROR] {type(exc).__name__}")
        return jsonify(status="BLOCKED", error=type(exc).__name__), 503


@app.post("/webhook/wholesale/trigger")
def wholesale_trigger():
    data = request.get_json(silent=True) or {}
    states = data.get("states", ["FL", "TX", "GA", "NC", "OH"])
    dry_run = bool(data.get("dry_run", False))

    def run_log():
        log(f"[WHOLESALE] states={states} dry_run={dry_run}")

    threading.Thread(target=run_log, daemon=True).start()
    return jsonify(status="started", states=states, dry_run=dry_run)


@app.get("/webhook/wholesale/deals")
def wholesale_deals():
    if not DEALS.exists():
        return jsonify(deals=[], count=0)
    try:
        rows = json.loads(DEALS.read_text(encoding="utf-8"))
    except Exception as e:
        return jsonify(error=str(e), deals=[], count=0), 500

    hot = []
    for d in rows:
        try:
            fee = float(d.get("assignment_fee_est", d.get("profit", 0)) or 0)
        except Exception:
            fee = 0
        if fee >= 10000:
            hot.append(d)
    return jsonify(deals=hot, count=len(hot))


@app.post("/webhook/wholesale/notify")
def wholesale_notify():
    data = request.get_json(silent=True) or {}
    message = data.get("message", "")
    log("[N8N] " + str(message))
    return jsonify(status="ok")


@app.post("/webhook/buddy/command")
def buddy_command():
    if not _authorized(request):
        return jsonify(error="unauthorized"), 401
    data = request.get_json(silent=True) or {}
    command = (data.get("command") or "").strip()
    if not command:
        return jsonify(error="no command"), 400
    session_id = (data.get("session_id") or "bridge").strip()[:120]
    simulate = bool(data.get("simulate", False))
    try:
        result = get_operator().handle(command, session_id=session_id, simulate=simulate)
        log(f"[COMMAND] status={result.get('status')} mission={result.get('mission_id','none')}")
        return jsonify(result)
    except Exception as exc:
        log(f"[COMMAND_ERROR] {type(exc).__name__}")
        return jsonify(status="BLOCKED", error=type(exc).__name__), 500


@app.post("/webhook/buddy/revenue/fast-cash")
def buddy_revenue_fast_cash():
    """Return a governed FAST CASH DRAFT_SHADOW package; never publish."""
    return _governed_revenue_request(run_fast_cash_payload, "FAST_CASH")


@app.post("/webhook/buddy/revenue/compounding")
def buddy_revenue_compounding():
    """Return a governed COMPOUNDING DRAFT_SHADOW result; never publish."""
    return _governed_revenue_request(run_compounding_payload, "COMPOUNDING")


@app.post("/webhook/conductor")
def conductor_webhook():
    data = request.get_json(silent=True) or {}
    log("[CONDUCTOR] " + json.dumps(data, ensure_ascii=False))
    return jsonify(status="received", service="buddy_bridge", route="conductor")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5052)
