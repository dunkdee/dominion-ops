from __future__ import annotations

import json
import os
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from ipaddress import ip_address, ip_network
from typing import Any
from urllib import error, request


OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
NEMOTRON_MODEL = os.getenv("NEMOTRON_MODEL", "nemotron-3-nano:4b")
LISTEN_HOST = os.getenv("NEMOTRON_LISTEN_HOST", "0.0.0.0")
LISTEN_PORT = int(os.getenv("NEMOTRON_LISTEN_PORT", "11435"))
UPSTREAM_TIMEOUT_SECONDS = int(os.getenv("NEMOTRON_TIMEOUT_SECONDS", "300"))

DOMINION_CHARTER = """You are Nemotron, Dominion's primary reasoning layer and a member of one coordinated enterprise AI family.
The Founder retains final authority. Never represent yourself or another agent as outranking the Founder.
Operate as one ecosystem with parallel specialist lanes coordinated through Dominion Command Center and Conductor.
Start with precision, then move quickly. Separate verified facts, inferences, proposals, and completed actions.
Optimize for truthful, measurable real-world impact, durable workflows, closed loops, and shared Dominion memory.
Never claim work is complete without evidence. Identify the objective, next action, verification gate, and memory update.
Payments, credential changes, public publishing, and live trading require their own explicit authorization.
Do not expose private chain-of-thought. Return concise conclusions, checks, and useful evidence instead.
"""


def _json_request(method: str, url: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method=method,
    )
    with request.urlopen(req, timeout=UPSTREAM_TIMEOUT_SECONDS) as response:
        parsed = json.loads(response.read().decode("utf-8"))
    if not isinstance(parsed, dict):
        raise ValueError("upstream returned a non-object JSON response")
    return parsed


def _available_models() -> list[str]:
    payload = _json_request("GET", f"{OLLAMA_BASE_URL}/api/tags")
    return [str(item.get("name")) for item in payload.get("models", []) if item.get("name")]


class Handler(BaseHTTPRequestHandler):
    server_version = "DominionNemotron/1.0"

    def _send(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0 or length > 1_000_000:
            raise ValueError("invalid request body size")
        parsed = json.loads(self.rfile.read(length).decode("utf-8"))
        if not isinstance(parsed, dict):
            raise ValueError("request body must be a JSON object")
        return parsed

    def _client_allowed(self) -> bool:
        client = ip_address(self.client_address[0])
        return client.is_loopback or client in ip_network("172.16.0.0/12")

    def do_GET(self) -> None:  # noqa: N802
        if not self._client_allowed():
            self._send(403, {"error": {"message": "client network not authorized", "type": "forbidden"}})
            return
        try:
            models = _available_models()
            available = NEMOTRON_MODEL in models
        except (error.URLError, TimeoutError, ValueError, json.JSONDecodeError):
            models, available = [], False

        if self.path == "/health":
            self._send(
                200 if available else 503,
                {
                    "status": "ok" if available else "degraded",
                    "service": "dominion-nemotron",
                    "model": NEMOTRON_MODEL,
                    "model_available": available,
                    "founder_authority": "final",
                    "ecosystem": "dominion",
                },
            )
            return
        if self.path == "/v1/models":
            data = [{"id": name, "object": "model", "owned_by": "dominion"} for name in models]
            self._send(200, {"object": "list", "data": data})
            return
        self._send(404, {"error": {"message": "not found", "type": "not_found"}})

    def do_POST(self) -> None:  # noqa: N802
        if not self._client_allowed():
            self._send(403, {"error": {"message": "client network not authorized", "type": "forbidden"}})
            return
        if self.path != "/v1/chat/completions":
            self._send(404, {"error": {"message": "not found", "type": "not_found"}})
            return
        try:
            payload = self._read_json()
            messages = payload.get("messages")
            if not isinstance(messages, list) or not messages:
                raise ValueError("messages must be a non-empty array")
            upstream = {
                "model": NEMOTRON_MODEL,
                "messages": [{"role": "system", "content": DOMINION_CHARTER}, *messages],
                "stream": False,
                "think": False,
                "keep_alive": "10m",
                "options": {
                    "temperature": float(payload.get("temperature", 0.2)),
                    "num_ctx": 4096,
                },
            }
            result = _json_request("POST", f"{OLLAMA_BASE_URL}/api/chat", upstream)
            content = str((result.get("message") or {}).get("content") or "").strip()
            if not content:
                raise ValueError("Nemotron returned no final answer")
            normalized = {
                "id": f"chatcmpl-dominion-{int(time.time() * 1000)}",
                "object": "chat.completion",
                "created": int(time.time()),
                "model": NEMOTRON_MODEL,
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": content},
                        "finish_reason": result.get("done_reason") or "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": int(result.get("prompt_eval_count") or 0),
                    "completion_tokens": int(result.get("eval_count") or 0),
                    "total_tokens": int(result.get("prompt_eval_count") or 0) + int(result.get("eval_count") or 0),
                },
            }
            self._send(200, normalized)
        except (ValueError, json.JSONDecodeError) as exc:
            self._send(400, {"error": {"message": str(exc), "type": "invalid_request"}})
        except (error.URLError, TimeoutError) as exc:
            self._send(502, {"error": {"message": f"Nemotron upstream unavailable: {exc}", "type": "upstream"}})

    def log_message(self, format: str, *args: object) -> None:
        return


if __name__ == "__main__":
    ThreadingHTTPServer((LISTEN_HOST, LISTEN_PORT), Handler).serve_forever()
