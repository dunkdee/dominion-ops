#!/usr/bin/env python3
"""Fail-closed validation for the staged ethical revenue/impact pipeline."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
ERRORS: list[str] = []

REQUIRED_FALSE_AUTHORITIES = {
    "external_execution_authorized",
    "money_movement_authorized",
    "publication_authorized",
    "customer_or_prospect_contact_authorized",
    "pricing_authorized",
    "credential_change_authorized",
}
EXPECTED_VERTICAL_MODES = {
    "commerce_fulfillment": "record_only",
    "content_traffic": "draft_only",
    "analytics_services": "shadow_only",
}
EXPECTED_STAGES = ["measure", "draft", "human_approval", "record_outcomes"]
EXPECTED_TRUTH_STATES = ["VERIFIED", "INFERRED", "UNKNOWN", "BLOCKED"]


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


def main() -> int:
    constitution_path = ROOT / "governance" / "SYSTEM_CONSTITUTION.md"
    verticals_path = ROOT / "governance" / "verticals.json"
    contract_path = ROOT / "revenue" / "impact_pipeline" / "contract.json"

    for path in (constitution_path, verticals_path, contract_path):
        require(path.is_file(), f"missing required file: {path.relative_to(ROOT)}")
    if ERRORS:
        return report()

    constitution = constitution_path.read_text(encoding="utf-8")
    require("Human final authority" in constitution, "constitution must retain human final authority")
    require("Revenue does not override law or safety" in constitution, "constitution must retain revenue safety rule")

    verticals = load_json(verticals_path)
    contract = load_json(contract_path)

    require(contract.get("status") == "STAGED_NOT_ACTIVATED", "pipeline must remain staged")
    require(
        contract.get("promotion_status") == "No pipeline stage promotes a vertical, authorizes an action, or changes a runtime setting.",
        "pipeline must not claim activation authority",
    )

    authority = contract.get("authority", {})
    require(isinstance(authority, dict), "authority must be an object")
    require(authority.get("human_final_authority") == "human_overseer", "human final authority must be preserved")
    require(authority.get("default_behavior") == "deny", "default behavior must be deny")
    for field in REQUIRED_FALSE_AUTHORITIES:
        require(authority.get(field) is False, f"{field} must remain false")

    scope = contract.get("scope", {})
    require(isinstance(scope, dict), "scope must be an object")
    contract_modes = scope.get("allowed_vertical_modes", {})
    require(contract_modes == EXPECTED_VERTICAL_MODES, "pipeline modes must remain Wix record-only, content draft-only, analytics shadow-only")

    by_id = {
        item.get("id"): item
        for item in verticals.get("verticals", [])
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    for vertical_id, expected_mode in EXPECTED_VERTICAL_MODES.items():
        require(vertical_id in by_id, f"missing governed vertical: {vertical_id}")
        require(by_id.get(vertical_id, {}).get("mode") == expected_mode, f"{vertical_id} mode does not match governed registry")

    forbidden = set(scope.get("forbidden_actions", []))
    for action in (
        "publish_external_content",
        "schedule_external_content",
        "contact_prospect_or_customer",
        "accept_client_data",
        "send_proposal",
        "set_or_change_price",
        "enable_checkout",
        "process_or_move_money",
        "create_paid_spend",
        "change_credentials",
        "change_production_configuration",
        "claim_unverified_revenue_or_impact",
    ):
        require(action in forbidden, f"forbidden action missing: {action}")

    workflow = contract.get("workflow", [])
    require(isinstance(workflow, list), "workflow must be a list")
    stages = [item.get("stage") for item in workflow if isinstance(item, dict)]
    require(stages == EXPECTED_STAGES, "workflow stage order is incorrect")
    for item in workflow:
        if not isinstance(item, dict):
            ERRORS.append("each workflow item must be an object")
            continue
        require(item.get("external_effects") is False, f"{item.get('stage')} must have no external effects")
    approval = next((item for item in workflow if isinstance(item, dict) and item.get("stage") == "human_approval"), {})
    require(approval.get("agent_may_approve") is False, "agents may not approve pipeline actions")

    require(contract.get("truth_states") == EXPECTED_TRUTH_STATES, "truth states must be canonical")
    required_fields = set(contract.get("minimum_record_fields", []))
    for field in (
        "mission_id",
        "truth_state",
        "evidence_references",
        "facts",
        "assumptions",
        "unknowns",
        "limitations",
        "approval_reference",
        "follow_up_owner",
    ):
        require(field in required_fields, f"minimum record field missing: {field}")

    invariants = contract.get("safety_invariants", {})
    require(isinstance(invariants, dict), "safety_invariants must be an object")
    for field in (
        "external_actions_must_be_empty",
        "paid_spend_must_be_zero",
        "money_moved_must_be_false",
        "published_content_must_be_false",
        "prospects_or_customers_contacted_must_be_false",
        "credentials_changed_must_be_false",
        "production_changed_must_be_false",
        "raw_sensitive_data_forbidden",
        "unreviewed_self_modification_forbidden",
    ):
        require(invariants.get(field) is True, f"safety invariant missing or disabled: {field}")

    return report()


def report() -> int:
    if ERRORS:
        print("Ethical revenue/impact pipeline validation FAILED:")
        for error in ERRORS:
            print(f" - {error}")
        return 1
    print("Ethical revenue/impact pipeline validation PASSED")
    print("Verified staged-only scope, approval gate, truthful records, and zero external effects.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
