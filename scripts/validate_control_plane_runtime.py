#!/usr/bin/env python3
"""Validate Stage 2 control-plane runtime contracts and fail-closed behavior."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from control_plane.governor import Governor, GovernorPaths
from control_plane.ledger import AppendOnlyLedger
from control_plane.onboarding import FORBIDDEN_REQUESTS
from control_plane.revenue_simulation import simulate_revenue_funnel

ERRORS: list[str] = []

REQUIRED_FILES = [
    ROOT / "control_plane" / "__init__.py",
    ROOT / "control_plane" / "canonical.py",
    ROOT / "control_plane" / "governor.py",
    ROOT / "control_plane" / "ledger.py",
    ROOT / "control_plane" / "council.py",
    ROOT / "control_plane" / "onboarding.py",
    ROOT / "control_plane" / "revenue_simulation.py",
    ROOT / "control_plane" / "cli.py",
    ROOT / "scripts" / "control_plane.py",
    ROOT / "tests" / "test_control_plane_runtime.py",
    ROOT / "governance" / "runtime_activation_gates.json",
    ROOT / "governance" / "schemas" / "action_request.schema.json",
    ROOT / "governance" / "schemas" / "policy_decision.schema.json",
    ROOT / "governance" / "schemas" / "council_review.schema.json",
    ROOT / "governance" / "schemas" / "agent_candidate.schema.json",
    ROOT / "governance" / "schemas" / "revenue_scenario.schema.json",
    ROOT / "architecture" / "CONTROL_PLANE_RUNTIME.md",
]


def require(condition: bool, message: str) -> None:
    if not condition:
        ERRORS.append(message)


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        ERRORS.append(f"cannot load {path.relative_to(ROOT)}: {exc}")
        return {}
    require(isinstance(value, dict), f"{path.relative_to(ROOT)} must contain an object")
    return value if isinstance(value, dict) else {}


def validate_files() -> None:
    for path in REQUIRED_FILES:
        require(path.is_file(), f"missing required file: {path.relative_to(ROOT)}")


def validate_activation_gates(gates: dict[str, Any]) -> None:
    require(gates.get("mode") == "simulation_only", "runtime mode must remain simulation_only")
    blocked = set(gates.get("blocked_actions", []))
    required = {
        "deploy_production",
        "publish_external_content",
        "contact_customer_or_claimant",
        "spend_or_move_money",
        "sign_file_or_submit_legal_document",
        "reactivate_suspended_or_retired_agent",
    }
    require(required.issubset(blocked), "runtime activation gates do not block all critical execution")
    require(bool(gates.get("promotion_requirements")), "promotion requirements must be non-empty")


def validate_schemas() -> None:
    for path in ROOT.glob("governance/schemas/*.schema.json"):
        schema = load_json(path)
        if path.name in {
            "action_request.schema.json",
            "policy_decision.schema.json",
            "council_review.schema.json",
            "agent_candidate.schema.json",
            "revenue_scenario.schema.json",
        }:
            require(schema.get("additionalProperties") is False, f"{path.name} must reject unknown fields")


def validate_governor_smoke() -> None:
    governor = Governor(
        GovernorPaths(
            authority=ROOT / "governance" / "authority_matrix.json",
            registry=ROOT / "agents" / "registry.json",
            council=ROOT / "governance" / "five_council_policy.json",
            activation_gates=ROOT / "governance" / "runtime_activation_gates.json",
        )
    )
    unknown = governor.evaluate({
        "actor_id": "research",
        "action_id": "not_registered",
        "evidence": ["smoke-test"],
        "satisfied_constraints": [],
        "legal_status": "NOT_APPLICABLE",
        "council_approvals": [],
    })
    require(unknown.get("decision") == "DENY", "unknown actions must be denied")
    require(unknown.get("execution_authorized") is False, "denied action cannot authorize execution")

    blocked = governor.evaluate({
        "actor_id": "human_overseer",
        "action_id": "deploy_production",
        "evidence": ["smoke-test"],
        "satisfied_constraints": [],
        "legal_status": "RESOLVED",
        "council_approvals": [],
    })
    require(blocked.get("decision") == "HOLD", "production deployment must remain held in Stage 2")


def validate_ledger_smoke() -> None:
    with tempfile.TemporaryDirectory() as temp:
        ledger = AppendOnlyLedger(Path(temp) / "ledger.jsonl")
        ledger.append(event_type="validation", actor="sentinel", payload={"result": "pass"}, timestamp="2026-01-01T00:00:00+00:00")
        verification = ledger.verify()
        require(verification.get("valid") is True, "ledger verification must pass")
        require(verification.get("record_count") == 1, "ledger must contain one smoke record")


def validate_revenue_smoke() -> None:
    scenario = load_json(ROOT / "runtime" / "examples" / "revenue_scenario.json")
    result = simulate_revenue_funnel(scenario)
    require(result.get("mode") == "SIMULATION_ONLY", "revenue runner must be simulation-only")
    require(result.get("external_actions") == [], "revenue simulation may not create external actions")
    require(result.get("money_moved") is False, "revenue simulation may not move money")
    require(result.get("customers_contacted") is False, "revenue simulation may not contact customers")


def validate_onboarding_boundaries() -> None:
    required = {
        "deploy_production",
        "merge_to_main",
        "publish_external_content",
        "contact_customer_or_claimant",
        "spend_or_move_money",
        "expand_own_permissions",
    }
    require(required.issubset(FORBIDDEN_REQUESTS), "agent onboarding forbidden-action set is incomplete")


def main() -> int:
    validate_files()
    gates = load_json(ROOT / "governance" / "runtime_activation_gates.json")
    validate_activation_gates(gates)
    validate_schemas()
    validate_governor_smoke()
    validate_ledger_smoke()
    validate_revenue_smoke()
    validate_onboarding_boundaries()

    if ERRORS:
        print("Dominion Stage 2 runtime validation FAILED:")
        for error in ERRORS:
            print(f" - {error}")
        return 1

    print("Dominion Stage 2 runtime validation PASSED")
    print(f"Validated {len(REQUIRED_FILES)} required runtime contracts and components.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
