"""Loopback-only client for Dominion's governed MCP connector fabric."""
from __future__ import annotations

import json
import os
import re
import uuid
from typing import Any

import requests

PROTOCOL_VERSION = "2026-07-28"
BASE_URL = os.getenv("BUDDY_MCP_BASE_URL", "http://127.0.0.1:8390").rstrip("/")


class MCPClientError(RuntimeError):
    pass


def _assert_loopback() -> None:
    if not (BASE_URL.startswith("http://127.0.0.1:") or BASE_URL.startswith("http://localhost:")):
        raise MCPClientError("MCP endpoint must remain loopback-only")


def health(timeout: float = 4.0) -> dict[str, Any]:
    _assert_loopback()
    response = requests.get(f"{BASE_URL}/health", timeout=timeout)
    response.raise_for_status()
    data = response.json()
    if data.get("status") != "ok" or data.get("service") != "dominion-mcp-cli":
        raise MCPClientError("MCP health contract failed")
    if data.get("external_mutation_enabled") is not False:
        raise MCPClientError("MCP mutation must remain disabled")
    if data.get("binding") != "loopback-only":
        raise MCPClientError("MCP binding contract failed")
    return data


def list_connectors(timeout: float = 4.0) -> dict[str, Any]:
    _assert_loopback()
    response = requests.get(f"{BASE_URL}/connectors", timeout=timeout)
    response.raise_for_status()
    data = response.json()
    if not isinstance(data.get("connectors"), list):
        raise MCPClientError("MCP connector list invalid")
    if data.get("external_mutation_enabled") is not False:
        raise MCPClientError("MCP mutation must remain disabled")
    return data


def invoke(connector_id: str, params: dict[str, Any] | None = None, timeout: float = 25.0) -> dict[str, Any]:
    _assert_loopback()
    if not re.fullmatch(r"[a-z0-9][a-z0-9_.-]{1,79}", connector_id or ""):
        raise MCPClientError("invalid connector id")
    payload = {
        "jsonrpc": "2.0",
        "id": uuid.uuid4().hex,
        "method": "tools/call",
        "params": {
            "name": "dominion_connector_invoke",
            "arguments": {"connector_id": connector_id, "params": params or {}},
        },
    }
    response = requests.post(
        f"{BASE_URL}/mcp",
        headers={
            "Content-Type": "application/json",
            "MCP-Protocol-Version": PROTOCOL_VERSION,
            "Mcp-Method": "tools/call",
            "Mcp-Name": "dominion_connector_invoke",
        },
        data=json.dumps(payload),
        timeout=timeout,
    )
    response.raise_for_status()
    body = response.json()
    if body.get("error"):
        raise MCPClientError(str(body["error"].get("message") or "MCP RPC error"))
    result = body.get("result") or {}
    if result.get("isError") is True:
        structured = result.get("structuredContent") or {}
        raise MCPClientError(str(structured.get("error") or "connector invocation failed"))
    structured = result.get("structuredContent")
    if not isinstance(structured, dict) or structured.get("status") != "PASS":
        raise MCPClientError("connector result contract failed")
    return structured


__all__ = ["MCPClientError", "health", "list_connectors", "invoke"]
