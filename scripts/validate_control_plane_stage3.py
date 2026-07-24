#!/usr/bin/env python3
"""Validate Stage 3 shadow-mode control-plane contracts and safety boundaries."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from control_plane.cohort import REQUIRED_BLOCKED_ACTIONS, validate_shadow_cohort
from control_plane.proposals import prepare_proposal_envelope
from control_plane.shadow_revenue import run_shadow_revenue_experiment

ERRORS: list[str] = []
REQUIRED_FILES = [
    ROOT / "control_plane" / "cohort.py",
    ROOT / "control_plane" / "proposals.py",
    ROOT / "control_plane" / "shadow_revenue.py",
    ROOT / "governance" / "tool_catalog.json",
    ROOT / "governance" / "runtime_activation_gates.json",
    ROOT / "governance" / "schemas" / "agent_cohort.schema.json",
    ROOT / "governance" / "schemas" / "proposal_envelope.schema.json",
    ROOT / "governance" / "schemas" / "bound_council_review.schema.json",
    ROOT / "governance" / "schemas" / "shadow_revenue_experiment.schema.json",
    ROOT / "governance" / "schemas" / "tool_catalog.schema.json",
    ROOT / "agents" / "cohorts" / "stage3_core_shadow.json",
    ROOT / "runtime" / "examples" / "stage3_proposal.json",
    ROOT / "runtime" / "examples" / "shadow_revenue_experiment.json",
    ROOT / "tests" / "test_control_plane_stage3.py",
    ROOT / "architecture" / "STAGE3_SHADOW_OPERATIONS.md",
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


def validate_gates(gates: dict[str, Any]) -> None:
    require(gates.get("stage") == 3, "activation stage must be 3")
    require(gates.get("mode") == "shadow_only", "runtime mode must be shadow_only")
    require(gates.get("external_execution_enabled") is False, "external execution must remain disabled")
    require(gates.get("registry_mutation_enabled") is False, "registry mutation must remain disabled")
    require(REQUIRED_BLOCKED_ACTIONS.issubset(set(gates.get("blocked_actions", []))), "critical blocked actions are incomplete")
    blocked_capabilities = set(gates.get("blocked_capabilities", []))
    for capability in ("start_obsidian_runtime", "start_browser_agents", "live_customer_contact", "live_financial_execution", "production_deployment"):
        require(capability in blocked_capabilities, f"blocked capability missing: {capability}")


def validate_schemas() -> None:
    for name in (
        "agent_cohort.schema.json",
        "proposal_envelope.schema.json",
        "bound_council_review.schema.json",
        "shadow_revenue_experiment.schema.json",
        "tool_catalog.schema.json",
    ):
        schema = load_json(ROOT / "governance" / "schemas" / name)
        require(schema.get("additionalProperties") is False, f"{name} must reject unknown fields")


def validate_cohort_smoke() -> None:
    result = validate_shadow_cohort(
        load_json(ROOT / "agents" / "cohorts" / "stage3_core_shadow.json"),
        load_json(ROOT / "agents" / "registry.json"),
        load_json(ROOT / "governance" / "tool_catalog.json"),
        load_json(ROOT / "governance" / "runtime_activation_gates.json"),
    )
    require(result.get("status") == "ELIGIBLE_FOR_SHADOW_ASSIGNMENT_REVIEW", "core cohort must pass shadow validation")
    require(result.get("registry_mutated") is False, "cohort validation may not mutate registry")
    require(result.get("agents_promoted") is False, "cohort validation may not promote agents")
    require(result.get("runtime_started") is False, "cohort validation may not start runtimes")


def validate_proposal_smoke() -> None:
    result = prepare_proposal_envelope(
        load_json(ROOT / "runtime" / "examples" / "stage3_proposal.json"),
        load_json(ROOT / "agents" / "registry.json"),
        load_json(ROOT / "governance" / "authority_matrix.json"),
        load_json(ROOT / "governance" / "runtime_activation_gates.json"),
    )
    require(result.get("status") == "READY_FOR_INDEPENDENT_COUNCIL_REVIEW", "example proposal must be reviewable")
    require(result.get("external_execution_authorized") is False, "proposal preparation cannot authorize execution")


def validate_shadow_revenue_smoke() -> None:
    result = run_shadow_revenue_experiment(load_json(ROOT / "runtime" / "examples" / "shadow_revenue_experiment.json"))
    require(result.get("mode") == "SHADOW_ONLY", "shadow revenue mode is invalid")
    require(result.get("decision") == "TEST_ONLY", "synthetic fixture must remain TEST_ONLY")
    require(result.get("external_actions") == [], "shadow revenue may not create external actions")
    require(result.get("money_moved") is False, "shadow revenue may not move money")
    require(result.get("customers_contacted") is False, "shadow revenue may not contact customers")
    require(result.get("promotion_authorized") is False, "shadow revenue may not authorize promotion")


def main() -> int:
    validate_files()
    gates = load_json(ROOT / "governance" / "runtime_activation_gates.json")
    validate_gates(gates)
    validate_schemas()
    validate_cohort_smoke()
    validate_proposal_smoke()
    validate_shadow_revenue_smoke()
    if ERRORS:
        print("Dominion Stage 3 validation FAILED:")
        for error in ERRORS:
            print(f" - {error}")
        return 1
    print("Dominion Stage 3 validation PASSED")
    print(f"Validated {len(REQUIRED_FILES)} Stage 3 contracts and components.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
