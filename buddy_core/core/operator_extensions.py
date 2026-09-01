"""Runtime extensions for BuddyOperator.

This module adds concrete capability executors without weakening the base
operator's plan validation or external-action boundaries. It is installed by
``core.__init__`` for every BuddyOperator instance.
"""
from __future__ import annotations

import json
import re
import uuid
from pathlib import Path
from typing import Any, Callable

try:
    from core.capability_health import audit_capabilities
    from core import mcp_client
    from core.self_heal import diagnose, repair_safe
except ImportError:
    from buddy_core.core.capability_health import audit_capabilities
    from buddy_core.core import mcp_client
    from buddy_core.core.self_heal import diagnose, repair_safe

ROOT = Path(__file__).resolve().parents[1]
EXTENSION_FILE = ROOT / "config" / "capability_extensions.json"


class OperatorExtensionError(RuntimeError):
    pass


def _load_extensions() -> list[dict[str, Any]]:
    try:
        data = json.loads(EXTENSION_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError) as exc:
        raise OperatorExtensionError(f"capability_extensions_unavailable:{type(exc).__name__}") from exc
    if data.get("schema") != "dominion-buddy-capability-extensions-v1":
        raise OperatorExtensionError("capability_extensions_schema_invalid")
    caps = data.get("capabilities")
    if not isinstance(caps, list):
        raise OperatorExtensionError("capability_extensions_invalid")
    return [c for c in caps if isinstance(c, dict) and c.get("enabled", True)]


def _capability_health_executor(operator: Any) -> Callable[[str, dict], tuple[Any, list]]:
    def execute(instruction: str, context: dict):
        result = audit_capabilities(operator)
        evidence = [{
            "type": "capability_health",
            "status": result.get("status"),
            "registered_enabled": result.get("registered_enabled"),
            "native_connected": result.get("native_connected"),
            "mcp_status": (result.get("mcp") or {}).get("status"),
        }]
        return result, evidence
    return execute


def _self_diagnose_executor(operator: Any) -> Callable[[str, dict], tuple[Any, list]]:
    def execute(instruction: str, context: dict):
        result = diagnose()
        evidence = [{
            "type": "self_diagnosis",
            "observed_at": result.get("observed_at"),
            "healthy": result.get("healthy"),
            "issue_count": len(result.get("issues", [])),
            "mcp_connectors_registered": (result.get("mcp_connectors") or {}).get("registered"),
            "mcp_connectors_failed": (result.get("mcp_connectors") or {}).get("failed"),
        }]
        return result, evidence
    return execute


def _self_repair_executor(operator: Any) -> Callable[[str, dict], tuple[Any, list]]:
    def execute(instruction: str, context: dict):
        result = repair_safe()
        status = str(result.get("status") or "BLOCKED")
        evidence = [{
            "type": "self_heal_receipt",
            "status": status,
            "receipt": result.get("receipt"),
            "authorization_id": result.get("authorization_id"),
        }]
        if status not in {"HEALTHY", "REPAIRED"}:
            unresolved = (result.get("after") or result.get("before") or {}).get("issues", [])
            raise OperatorExtensionError(
                f"self_heal_{status.lower()}:unresolved={len(unresolved)} receipt={result.get('receipt','')}"
            )
        return result, evidence
    return execute


def _mcp_list_executor(operator: Any) -> Callable[[str, dict], tuple[Any, list]]:
    def execute(instruction: str, context: dict):
        health = mcp_client.health()
        result = mcp_client.list_connectors()
        evidence = [{
            "type": "mcp_registry",
            "service": health.get("service"),
            "version": health.get("version"),
            "connector_count": len(result.get("connectors", [])),
            "external_mutation_enabled": result.get("external_mutation_enabled"),
        }]
        return result, evidence
    return execute


def _extract_connector_id(instruction: str, available: list[dict[str, Any]]) -> str:
    ids = [str(item.get("id", "")) for item in available if item.get("id")]
    lowered = (instruction or "").lower()
    for connector_id in ids:
        if connector_id.lower() in lowered:
            return connector_id
    exact = (instruction or "").strip()
    if exact in ids:
        return exact
    match = re.search(r"\bconnector_id\s*=\s*([a-z0-9][a-z0-9_.-]{1,79})\b", lowered)
    if match and match.group(1) in ids:
        return match.group(1)
    raise OperatorExtensionError(
        "connector id not identified from instruction; list connectors first and name one registered connector"
    )


def _mcp_invoke_executor(operator: Any) -> Callable[[str, dict], tuple[Any, list]]:
    def execute(instruction: str, context: dict):
        registry = mcp_client.list_connectors()
        connectors = registry.get("connectors", [])
        connector_id = _extract_connector_id(instruction, connectors)
        result = mcp_client.invoke(connector_id, {})
        evidence = [{
            "type": "mcp_connector_receipt",
            "connector_id": connector_id,
            "status": result.get("status"),
            "elapsed_ms": result.get("elapsed_ms"),
        }]
        return result, evidence
    return execute


def _build_direct_plan(operator: Any, objective: str, steps: list[tuple[str, str]], kind: str) -> dict:
    return {
        "mission_id": "mission_" + uuid.uuid4().hex[:12],
        "objective": objective,
        "kind": kind,
        "evidence_policy": None,
        "created_at": None,
        "conversation_context": "",
        "steps": [operator._step(capability, instruction) for capability, instruction in steps],
        "completion_rule": "Execute standing-authorized internal work and verify from real evidence.",
    }


def _wrap_handle(operator: Any) -> None:
    if getattr(operator, "_dominion_handle_extended", False):
        return
    original = operator.handle

    def extended_handle(
        message: str,
        *,
        session_id: str = "default",
        simulate: bool = False,
        conversation_context: str | None = None,
    ):
        text = (message or "").strip()
        lower = text.lower()

        capability_phrases = (
            "capability audit",
            "check your capabilities",
            "check capabilities",
            "what capabilities are connected",
            "what tools are connected",
            "are your capabilities working",
        )
        diagnose_phrases = (
            "diagnose yourself",
            "check yourself",
            "self diagnose",
            "self-diagnose",
            "what is wrong with you",
            "what's wrong with you",
            "diagnose the system",
        )
        repair_phrases = (
            "fix yourself",
            "repair yourself",
            "self heal",
            "self-heal",
            "heal yourself",
            "repair the system",
            "fix the system",
            "fix everything you can",
            "repair everything you can",
        )

        if any(phrase in lower for phrase in capability_phrases):
            plan = _build_direct_plan(
                operator,
                text,
                [("system.capability_health", "Audit all registered and extended Buddy capabilities against real executors and MCP runtime health.")],
                "capability_health",
            )
            if simulate:
                return {"status": "PLANNED", "objective": text, "plan": plan, "response": operator._plan_summary(plan)}
            return operator.execute(plan, session_id=session_id)

        if any(phrase in lower for phrase in repair_phrases):
            plan = _build_direct_plan(
                operator,
                text,
                [
                    ("system.self_diagnose", "Diagnose Buddy and every registered governed Dominion runtime connector before any mutation."),
                    ("system.self_repair", "Apply only standing-authorized allowlisted service/container/source repair recipes, verify all governed runtime signals, and roll back failed source repairs."),
                    ("system.capability_health", "Re-audit capability health after repair so unresolved gaps remain visible."),
                ],
                "self_heal",
            )
            if simulate:
                return {"status": "PLANNED", "objective": text, "plan": plan, "response": operator._plan_summary(plan)}
            return operator.execute(plan, session_id=session_id)

        if any(phrase in lower for phrase in diagnose_phrases):
            plan = _build_direct_plan(
                operator,
                text,
                [("system.self_diagnose", "Diagnose Buddy and every registered governed Dominion runtime connector without mutation.")],
                "self_diagnose",
            )
            if simulate:
                return {"status": "PLANNED", "objective": text, "plan": plan, "response": operator._plan_summary(plan)}
            return operator.execute(plan, session_id=session_id)

        return original(
            text,
            session_id=session_id,
            simulate=simulate,
            conversation_context=conversation_context,
        )

    operator.handle = extended_handle
    operator._dominion_handle_extended = True


def install_operator_extensions(operator: Any) -> Any:
    """Install reviewed extensions idempotently on one BuddyOperator instance."""
    if getattr(operator, "_dominion_extensions_installed", False):
        return operator

    for cap in _load_extensions():
        cap_id = str(cap.get("id", ""))
        if not cap_id:
            raise OperatorExtensionError("capability extension missing id")
        if cap_id in operator.capabilities:
            raise OperatorExtensionError(f"duplicate capability extension:{cap_id}")
        operator.capabilities[cap_id] = cap

    operator._executors.update(
        {
            "native:capability_health": _capability_health_executor(operator),
            "native:self_diagnose": _self_diagnose_executor(operator),
            "native:self_repair": _self_repair_executor(operator),
            "native:mcp_list": _mcp_list_executor(operator),
            "native:mcp_invoke": _mcp_invoke_executor(operator),
        }
    )
    _wrap_handle(operator)
    operator._dominion_extensions_installed = True
    return operator


__all__ = ["OperatorExtensionError", "install_operator_extensions"]
