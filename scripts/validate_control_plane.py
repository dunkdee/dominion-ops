#!/usr/bin/env python3
"""Validate Dominion control-plane governance using only the Python standard library."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

FILES = {
    "constitution": ROOT / "governance" / "SYSTEM_CONSTITUTION.md",
    "authority": ROOT / "governance" / "authority_matrix.json",
    "council": ROOT / "governance" / "five_council_policy.json",
    "incident": ROOT / "governance" / "incident_learning_policy.json",
    "legal": ROOT / "governance" / "legal_evidence_policy.json",
    "registry": ROOT / "agents" / "registry.json",
    "report_schema": ROOT / "agents" / "schemas" / "agent_report.schema.json",
    "incident_schema": ROOT / "governance" / "schemas" / "incident_record.schema.json",
    "architecture": ROOT / "architecture" / "CONTROL_PLANE.md",
    "incident_runbook": ROOT / "operations" / "INCIDENT_RESPONSE.md",
}

ERRORS: list[str] = []


def require(condition: bool, message: str) -> None:
    if not condition:
        ERRORS.append(message)


def load_json(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            value = json.load(handle)
    except FileNotFoundError:
        ERRORS.append(f"missing required file: {path.relative_to(ROOT)}")
        return {}
    except json.JSONDecodeError as exc:
        ERRORS.append(f"invalid JSON in {path.relative_to(ROOT)}: {exc}")
        return {}

    require(isinstance(value, dict), f"{path.relative_to(ROOT)} must contain a JSON object")
    return value if isinstance(value, dict) else {}


def validate_required_files() -> None:
    for path in FILES.values():
        require(path.is_file(), f"missing required file: {path.relative_to(ROOT)}")

    if FILES["constitution"].is_file():
        text = FILES["constitution"].read_text(encoding="utf-8")
        for phrase in (
            "Evidence before assertion",
            "No autonomous authority expansion",
            "Human final authority",
            "Five Council",
            "Incident-learning rule",
        ):
            require(phrase in text, f"constitution missing required principle: {phrase}")


def validate_authority(authority: dict[str, Any]) -> None:
    require(authority.get("default_behavior") == "deny", "authority default_behavior must be deny")
    require(authority.get("human_final_authority") == "human_overseer", "human_overseer must remain final authority")

    risk_levels = authority.get("risk_levels", {})
    require(
        set(risk_levels) == {"low", "moderate", "high", "critical", "prohibited"},
        "authority risk levels are incomplete",
    )
    require(
        risk_levels.get("critical", {}).get("human_approval_required") is True,
        "critical actions must require human approval",
    )
    require(
        risk_levels.get("prohibited", {}).get("action") == "reject",
        "prohibited actions must reject",
    )

    actions = authority.get("actions", [])
    require(isinstance(actions, list) and bool(actions), "authority actions must be a non-empty list")
    ids = [action.get("id") for action in actions if isinstance(action, dict)]
    require(len(ids) == len(set(ids)), "authority action ids must be unique")

    by_id = {action.get("id"): action for action in actions if isinstance(action, dict)}
    for required_action in (
        "deploy_production",
        "spend_or_move_money",
        "read_or_export_secret_values",
        "expand_own_permissions",
        "reactivate_suspended_or_retired_agent",
    ):
        require(required_action in by_id, f"authority action missing: {required_action}")

    for action_id in ("read_or_export_secret_values", "expand_own_permissions"):
        require(
            by_id.get(action_id, {}).get("allowed_roles") == [],
            f"{action_id} must have no agent role allowance",
        )


def validate_council(council: dict[str, Any], authority: dict[str, Any]) -> None:
    councils = council.get("councils", [])
    require(isinstance(councils, list) and len(councils) == 5, "exactly five councils are required")

    ids = {item.get("id") for item in councils if isinstance(item, dict)}
    expected = {
        "truth_evidence",
        "law_governance",
        "security_risk",
        "engineering_reliability",
        "business_human_impact",
    }
    require(ids == expected, "five council domains do not match the constitution")

    veto = {
        item.get("id")
        for item in councils
        if isinstance(item, dict) and item.get("veto") is True
    }
    require(
        {"law_governance", "security_risk"}.issubset(veto),
        "law and security councils must retain veto authority",
    )

    thresholds = council.get("thresholds", {})
    require(
        thresholds.get("critical", {}).get("required_approvals") == 5,
        "critical decisions require all five council approvals",
    )
    require(
        thresholds.get("critical", {}).get("human_required") is True,
        "critical decisions require human approval",
    )
    require(
        authority.get("independent_veto_domains") == ["law_governance", "security_risk"],
        "authority veto domains must match council policy",
    )


def validate_incident(incident: dict[str, Any]) -> None:
    gates = incident.get("closure_gates", {})
    for gate in (
        "root_cause_required",
        "control_change_required",
        "regression_test_required",
        "verification_required",
        "recurrence_monitor_required",
    ):
        require(gates.get(gate) is True, f"incident closure gate must be true: {gate}")

    modification = incident.get("self_modification", {})
    require(
        modification.get("agent_may_activate") is False,
        "agents may not activate their own policy changes",
    )
    require(
        modification.get("requires_version_control") is True,
        "incident-learning changes must be version controlled",
    )
    require("CLOSED" in incident.get("lifecycle", []), "incident lifecycle must include CLOSED")


def validate_legal(legal: dict[str, Any]) -> None:
    require(legal.get("default_legal_status") == "UNRESOLVED", "legal default must be UNRESOLVED")
    fail_closed = set(legal.get("fail_closed_statuses", []))
    require(
        {"CONFLICTED", "UNRESOLVED", "REQUIRES_COUNSEL"}.issubset(fail_closed),
        "legal fail-closed statuses are incomplete",
    )
    require(
        legal.get("hold_response") == {"legal_status": "UNRESOLVED", "action": "HOLD"},
        "legal hold response must be deterministic",
    )


def validate_registry(registry: dict[str, Any], council: dict[str, Any]) -> None:
    agents = registry.get("agents", [])
    require(isinstance(agents, list) and bool(agents), "agent registry must be non-empty")

    ids = [agent.get("id") for agent in agents if isinstance(agent, dict)]
    require(len(ids) == len(set(ids)), "agent ids must be unique")

    allowed_states = set(registry.get("allowed_lifecycle_states", []))
    required_states = {
        "REGISTERED",
        "SIMULATION",
        "SHADOW",
        "CANARY",
        "LIMITED_PRODUCTION",
        "PRODUCTION",
        "SUSPENDED",
        "RETIRED",
    }
    require(required_states.issubset(allowed_states), "agent lifecycle states are incomplete")

    roles = {agent.get("role") for agent in agents if isinstance(agent, dict)}
    council_roles = {
        item.get("id")
        for item in council.get("councils", [])
        if isinstance(item, dict)
    }
    require(council_roles.issubset(roles), "each council domain must have a registered agent role")

    by_id = {agent.get("id"): agent for agent in agents if isinstance(agent, dict)}
    for required_agent in ("human_overseer", "governor", "revenue_operations"):
        require(required_agent in by_id, f"required agent missing: {required_agent}")

    for agent in agents:
        if not isinstance(agent, dict):
            ERRORS.append("each registry agent must be an object")
            continue

        agent_id = agent.get("id", "<unknown>")
        for field in (
            "id",
            "role",
            "purpose",
            "state",
            "permissions",
            "prohibited_actions",
            "evidence_required",
            "escalates_to",
        ):
            require(field in agent, f"agent {agent_id} missing field: {field}")

        require(agent.get("state") in allowed_states, f"agent {agent_id} has invalid lifecycle state")
        permissions = agent.get("permissions", [])
        require(isinstance(permissions, list), f"agent {agent_id} permissions must be a list")
        require("*" not in permissions, f"agent {agent_id} may not have wildcard permissions")
        require(agent.get("evidence_required") is True, f"agent {agent_id} must require evidence")

        if agent.get("role") != "human_overseer":
            require(
                "approve_production" not in permissions,
                f"agent {agent_id} may not approve production",
            )
            require(
                "approve_financial" not in permissions,
                f"agent {agent_id} may not approve financial actions",
            )


def validate_schemas(report_schema: dict[str, Any], incident_schema: dict[str, Any]) -> None:
    require(
        report_schema.get("additionalProperties") is False,
        "agent report schema must reject unknown fields",
    )
    truth_states = (
        report_schema.get("properties", {})
        .get("truth_state", {})
        .get("enum", [])
    )
    require(
        truth_states == ["VERIFIED", "INFERRED", "UNKNOWN", "BLOCKED"],
        "agent report truth states must be canonical",
    )

    require(
        incident_schema.get("additionalProperties") is False,
        "incident schema must reject unknown fields",
    )
    required = set(incident_schema.get("required", []))
    require(
        {"root_cause", "regression_tests", "verification", "recurrence_monitor"}.issubset(required),
        "incident schema closure evidence fields are incomplete",
    )


def main() -> int:
    validate_required_files()

    authority = load_json(FILES["authority"])
    council = load_json(FILES["council"])
    incident = load_json(FILES["incident"])
    legal = load_json(FILES["legal"])
    registry = load_json(FILES["registry"])
    report_schema = load_json(FILES["report_schema"])
    incident_schema = load_json(FILES["incident_schema"])

    validate_authority(authority)
    validate_council(council, authority)
    validate_incident(incident)
    validate_legal(legal)
    validate_registry(registry, council)
    validate_schemas(report_schema, incident_schema)

    if ERRORS:
        print("Dominion control-plane validation FAILED:")
        for error in ERRORS:
            print(f" - {error}")
        return 1

    print("Dominion control-plane validation PASSED")
    print(f"Validated {len(FILES)} required contracts and documents.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
