#!/usr/bin/env python3
"""Validate Stage 7 revenue manifesto, wave discipline, and vertical contracts."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ERRORS: list[str] = []


def require(condition: bool, message: str) -> None:
    if not condition:
        ERRORS.append(message)


def load(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        ERRORS.append(f"cannot load {path.relative_to(ROOT)}: {exc}")
        return {}
    require(isinstance(value, dict), f"{path.relative_to(ROOT)} must contain an object")
    return value if isinstance(value, dict) else {}


def main() -> int:
    required = [
        "governance/DOMINION_REVENUE_MANIFESTO.md",
        "governance/revenue_vertical_activation_plan.json",
        "governance/schemas/revenue_vertical_activation_plan.schema.json",
        "revenue/verticals/wix_store.json",
        "revenue/verticals/kdp_publishing.json",
        "revenue/verticals/analytics_services.json",
        "architecture/STAGE7_REVENUE_VERTICAL_ACTIVATION.md",
        "tests/test_control_plane_stage7.py",
    ]
    for item in required:
        require((ROOT / item).is_file(), f"missing required file: {item}")

    plan = load(ROOT / "governance/revenue_vertical_activation_plan.json")
    require(plan.get("status") == "READY_FOR_HUMAN_WAVE_APPROVAL", "plan must remain human-gated")
    require(plan.get("mode") == "SHADOW_PLANNING", "plan mode must remain shadow planning")
    require(plan.get("revenue_vertical_activation_enabled") is False, "revenue wave may not self-activate")
    require(plan.get("million_dollar_outcome_is_target_not_forecast") is True, "large outcome must be a target, not a forecast")
    wave = plan.get("current_wave", {})
    require(wave.get("primary_verticals") == ["commerce_fulfillment", "kdp_publishing"], "Wave 1 primary vertical order is incorrect")
    require(wave.get("support_verticals") == ["analytics_services"], "Wave 1 support vertical is incorrect")
    require(wave.get("activation_status") == "NOT_ACTIVATED", "Wave 1 must not be marked active")
    require(plan.get("activation_sequence", [])[:3] == ["commerce_fulfillment", "kdp_publishing", "analytics_services"], "revenue activation sequence is incorrect")
    for field in ("external_execution_authorized", "pricing_authorized", "publication_authorized", "money_movement_authorized"):
        require(plan.get(field) is False, f"{field} must remain false")

    registry = load(ROOT / "governance/verticals.json")
    verticals = registry.get("verticals", [])
    ids = [item.get("id") for item in verticals]
    priorities = [item.get("priority") for item in verticals]
    require(len(ids) == len(set(ids)), "vertical ids must be unique")
    require(len(priorities) == len(set(priorities)), "vertical priorities must be unique")
    require(ids[:3] == ["commerce_fulfillment", "kdp_publishing", "analytics_services"], "registry must prioritize Wix, KDP, then analytics")
    require(priorities[:3] == [1, 2, 3], "top revenue priorities must be 1, 2, and 3")

    gates = load(ROOT / "governance/runtime_activation_gates.json")
    require(gates.get("stage") == 7, "activation stage must be 7")
    require(gates.get("mode") == "shadow_only", "runtime must remain shadow_only")
    require(gates.get("external_execution_enabled") is False, "external execution must remain disabled")
    require(gates.get("revenue_vertical_activation_enabled") is False, "revenue activation must remain disabled")
    require(gates.get("maximum_parallel_primary_revenue_verticals") == 2, "wave capacity must be two primary verticals")
    blocked = set(gates.get("blocked_capabilities", []))
    for capability in (
        "unverified_revenue_claim",
        "kdp_publication_without_rights_review",
        "wix_go_live_without_checkout_evidence",
        "activate_revenue_wave_without_human_approval",
    ):
        require(capability in blocked, f"missing blocked capability: {capability}")

    contracts = {
        "commerce_fulfillment": load(ROOT / "revenue/verticals/wix_store.json"),
        "kdp_publishing": load(ROOT / "revenue/verticals/kdp_publishing.json"),
        "analytics_services": load(ROOT / "revenue/verticals/analytics_services.json"),
    }
    for expected_id, contract in contracts.items():
        require(contract.get("vertical_id") == expected_id, f"{expected_id} contract id mismatch")
        require(contract.get("external_execution_authorized") is False, f"{expected_id} may not authorize execution")
        require(contract.get("revenue_verified") is False, f"{expected_id} may not claim verified revenue")
        require(bool(contract.get("launch_gates")), f"{expected_id} launch gates are missing")
        require(bool(contract.get("current_blockers")), f"{expected_id} blockers are missing")
        require(bool(contract.get("human_approvals")), f"{expected_id} human approvals are missing")
        require(bool(contract.get("prohibited_actions")), f"{expected_id} prohibited actions are missing")

    wix = contracts["commerce_fulfillment"]
    require("existing_wix_isolation_diagnosis_not_closed" in wix.get("current_blockers", []), "Wix isolation blocker must remain explicit")
    require("checkout_succeeds_with_controlled_test_purchase" in wix.get("launch_gates", []), "Wix checkout evidence gate is missing")

    kdp = contracts["kdp_publishing"]
    require("no_canonical_kdp_title_inventory_in_repository" in kdp.get("current_blockers", []), "KDP inventory unknown must remain explicit")
    require("publish_without_rights_review" in kdp.get("prohibited_actions", []), "KDP rights control is missing")
    require("autonomous_kdp_upload_or_publication" in kdp.get("prohibited_actions", []), "KDP autonomous publication must be blocked")

    analytics = contracts["analytics_services"]
    require("sell_raw_personal_data" in analytics.get("prohibited_actions", []), "raw personal data sale must be prohibited")
    require("represent_estimates_as_verified_revenue" in analytics.get("prohibited_actions", []), "estimated revenue claims must be prohibited")
    require(analytics.get("pricing_status") == "UNSET_REQUIRES_HUMAN_APPROVAL", "analytics pricing must remain human-gated")

    schema = load(ROOT / "governance/schemas/revenue_vertical_activation_plan.schema.json")
    require(schema.get("additionalProperties") is False, "activation plan schema must reject unknown fields")

    if ERRORS:
        print("Dominion Stage 7 validation FAILED:")
        for error in ERRORS:
            print(f" - {error}")
        return 1
    print("Dominion Stage 7 validation PASSED")
    print(f"Validated {len(required)} Stage 7 contracts and documents.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
