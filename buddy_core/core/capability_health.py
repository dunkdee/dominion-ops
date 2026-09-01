"""Truthful capability-health inspection for Buddy.

This module does not grant authority. It reports whether declared capabilities
have real executors and whether the governed MCP read-only connector fabric is
reachable. External capabilities without an execution adapter are reported as
BOUNDARY_ONLY rather than pretending they are operational.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import requests

ROOT = Path(__file__).resolve().parents[1]
CAPABILITY_FILE = ROOT / "config" / "capability_registry.json"
MCP_BASE_URL = os.getenv("BUDDY_MCP_BASE_URL", "http://127.0.0.1:8390").rstrip("/")


class CapabilityHealthError(RuntimeError):
    pass


def _load_registry() -> dict[str, Any]:
    try:
        data = json.loads(CAPABILITY_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError) as exc:
        raise CapabilityHealthError(f"capability_registry_unavailable:{type(exc).__name__}") from exc
    caps = data.get("capabilities")
    if not isinstance(caps, list) or not caps:
        raise CapabilityHealthError("capability_registry_invalid")
    return data


def _loopback_url(url: str) -> bool:
    return url.startswith("http://127.0.0.1:") or url.startswith("http://localhost:")


def _mcp_health(timeout: float = 4.0) -> dict[str, Any]:
    if not _loopback_url(MCP_BASE_URL + "/"):
        return {"status": "BLOCKED", "reason": "mcp_url_must_be_loopback"}
    try:
        health_response = requests.get(f"{MCP_BASE_URL}/health", timeout=timeout)
        health_response.raise_for_status()
        health = health_response.json()
        connector_response = requests.get(f"{MCP_BASE_URL}/connectors", timeout=timeout)
        connector_response.raise_for_status()
        connectors = connector_response.json()
    except (requests.RequestException, ValueError, TypeError) as exc:
        return {"status": "UNAVAILABLE", "reason": type(exc).__name__}

    listed = connectors.get("connectors", []) if isinstance(connectors, dict) else []
    healthy = (
        isinstance(health, dict)
        and health.get("status") == "ok"
        and health.get("service") == "dominion-mcp-cli"
        and health.get("external_mutation_enabled") is False
        and health.get("binding") == "loopback-only"
        and isinstance(listed, list)
        and int(health.get("connector_count", -1)) == len(listed)
    )
    return {
        "status": "HEALTHY" if healthy else "DEGRADED",
        "service": health.get("service") if isinstance(health, dict) else None,
        "version": health.get("version") if isinstance(health, dict) else None,
        "connector_count": len(listed),
        "connectors": [
            {
                "id": item.get("id"),
                "effect": item.get("effect"),
                "adapter": item.get("adapter"),
            }
            for item in listed
            if isinstance(item, dict)
        ],
        "external_mutation_enabled": (
            health.get("external_mutation_enabled") if isinstance(health, dict) else None
        ),
    }


def audit_capabilities(operator: Any | None = None) -> dict[str, Any]:
    """Return a fail-visible capability inventory.

    `operator` is optional so CI can validate the registry without starting the
    full runtime. When supplied, native executor declarations are checked
    against the operator's actual executor map.
    """
    registry = _load_registry()
    capabilities = [c for c in registry["capabilities"] if c.get("enabled", True)]
    ids = [str(c.get("id", "")) for c in capabilities]
    duplicates = sorted({cap_id for cap_id in ids if cap_id and ids.count(cap_id) > 1})
    malformed = []
    native_missing = []
    boundary_only = []
    connected_native = []

    executors = getattr(operator, "_executors", {}) if operator is not None else None
    for cap in capabilities:
        cap_id = str(cap.get("id", ""))
        executor = str(cap.get("executor", ""))
        classification = str(cap.get("classification", ""))
        auth_required = bool(cap.get("auth_required", False))
        if not cap_id or not executor:
            malformed.append(cap_id or "<missing-id>")
            continue
        if executor.startswith("native:"):
            if executors is None:
                connected_native.append({"id": cap_id, "executor": executor, "status": "DECLARED"})
            elif executor in executors:
                connected_native.append({"id": cap_id, "executor": executor, "status": "CONNECTED"})
            else:
                native_missing.append({"id": cap_id, "executor": executor})
        elif executor.startswith("external:"):
            if auth_required and classification in {"privileged_write", "destructive"}:
                boundary_only.append({"id": cap_id, "executor": executor, "status": "BOUNDARY_ONLY"})
            else:
                malformed.append(cap_id)
        else:
            malformed.append(cap_id)

    mcp = _mcp_health()
    blocking_gaps = []
    if duplicates:
        blocking_gaps.append("duplicate_capability_ids")
    if malformed:
        blocking_gaps.append("malformed_capabilities")
    if native_missing:
        blocking_gaps.append("native_executor_missing")
    if mcp.get("status") != "HEALTHY":
        blocking_gaps.append("mcp_unhealthy")

    return {
        "schema": "dominion-buddy-capability-health-v1",
        "registry_version": registry.get("version"),
        "registered_enabled": len(capabilities),
        "native_connected": len(connected_native),
        "boundary_only": len(boundary_only),
        "duplicates": duplicates,
        "malformed": malformed,
        "native_missing": native_missing,
        "native": connected_native,
        "external_boundaries": boundary_only,
        "mcp": mcp,
        "blocking_gaps": blocking_gaps,
        "status": "HEALTHY" if not blocking_gaps else "DEGRADED",
        "truth_rule": (
            "A registered name is not treated as an operational capability until its "
            "executor and required runtime service are connected and verifiable."
        ),
    }


__all__ = ["CapabilityHealthError", "audit_capabilities"]
