#!/usr/bin/env python3
"""Fail closed when dormant Dominion specialist-lane contracts drift from governance."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "governance" / "specialist_lane_contracts.json"
SCHEMA = ROOT / "governance" / "specialist_lane_contracts.schema.json"
CANONICAL_TRUTH_STATES = ["VERIFIED", "INFERRED", "UNKNOWN", "BLOCKED"]
REQUIRED_LANES = {
    "research_strategy",
    "content_distribution",
    "operations_customer_support",
    "revenue_lead_workflow",
    "security_quality_verification",
}
GLOBAL_PROHIBITIONS = {
    "independent_external_action",
    "external_publication",
    "customer_or_claimant_contact",
    "spend_or_move_money",
    "credential_or_secret_access",
    "production_deployment",
    "live_trading",
    "self_activation",
    "self_modification",
    "authority_or_budget_expansion",
}
REQUIRED_MEMORY = {
    "evidence": "Dominion-Brain/08-Evidence/",
    "decisions": "Dominion-Brain/12-Decisions/",
    "learning": "Dominion-Brain/13-Learning/",
    "current_state": "Dominion-Brain/14-Daily-State/",
}


class ContractError(ValueError):
    """Raised for a specialist-lane governance violation."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ContractError(message)


def load(path: Path) -> dict[str, Any]:
    require(path.is_file(), f"missing required file: {path.relative_to(ROOT)}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ContractError(f"invalid JSON in {path.relative_to(ROOT)}: {exc}") from exc
    require(isinstance(value, dict), f"{path.relative_to(ROOT)} root must be an object")
    return value


def validate_kpis(lane_id: str, kpis: Any) -> None:
    require(isinstance(kpis, list) and kpis, f"{lane_id}: kpi_interface must be non-empty")
    ids: set[str] = set()
    for kpi in kpis:
        require(isinstance(kpi, dict), f"{lane_id}: each KPI must be an object")
        metric_id = kpi.get("id")
        require(isinstance(metric_id, str) and metric_id, f"{lane_id}: KPI id missing")
        require(metric_id not in ids, f"{lane_id}: duplicate KPI id {metric_id}")
        ids.add(metric_id)
        require(kpi.get("truth_state") in CANONICAL_TRUTH_STATES, f"{lane_id}/{metric_id}: noncanonical truth state")
        require(kpi.get("baseline_required") is True, f"{lane_id}/{metric_id}: baseline must be required before promotion")
        require(kpi.get("target_state") == "BASELINE_REQUIRED", f"{lane_id}/{metric_id}: target must not claim an unmeasured outcome")
        require(kpi.get("cadence") in {"per_mission", "daily", "weekly", "monthly"}, f"{lane_id}/{metric_id}: invalid cadence")
        require(isinstance(kpi.get("definition"), str) and kpi["definition"].strip(), f"{lane_id}/{metric_id}: definition missing")
        require(isinstance(kpi.get("evidence_source"), str) and kpi["evidence_source"].strip(), f"{lane_id}/{metric_id}: evidence source missing")


def validate_packet(lane_id: str, label: str, packet: Any) -> None:
    require(isinstance(packet, dict), f"{lane_id}: {label} must be an object")
    fields = packet.get("required_fields")
    require(isinstance(fields, list) and fields, f"{lane_id}: {label}.required_fields must be non-empty")
    require(packet.get("truth_state_required") is True, f"{lane_id}: {label} must require truth states")
    require(packet.get("secrets_permitted") is False, f"{lane_id}: {label} may not permit secrets")


def validate_lane(lane: Any, all_prohibitions: set[str]) -> str:
    require(isinstance(lane, dict), "each lane must be an object")
    lane_id = lane.get("id")
    require(isinstance(lane_id, str) and lane_id, "lane id missing")
    require(lane.get("lifecycle_state") == "REGISTERED", f"{lane_id}: lifecycle state must remain REGISTERED")
    require(lane.get("activation_state") == "DORMANT", f"{lane_id}: activation state must remain DORMANT")
    require(lane.get("budget_usd") == 0, f"{lane_id}: budget must remain zero")
    require(lane.get("owner") == "coordinator", f"{lane_id}: coordinator must own routing")
    require(lane.get("approval_gate") == "human_overseer_recorded_approval", f"{lane_id}: Founder approval gate missing")
    require(lane.get("independent_verifier") == "sentinel", f"{lane_id}: independent verifier must be sentinel")

    prohibited = lane.get("prohibited_actions")
    require(isinstance(prohibited, list), f"{lane_id}: prohibited_actions must be a list")
    missing_prohibitions = all_prohibitions - set(prohibited)
    require(not missing_prohibitions, f"{lane_id}: missing prohibitions {sorted(missing_prohibitions)}")
    require("approve_own_proposal" in prohibited if lane_id == "security_quality_verification" else True, f"{lane_id}: verifier cannot approve its own proposal")

    allowed = lane.get("allowed_internal_actions")
    require(isinstance(allowed, list) and allowed, f"{lane_id}: allowed_internal_actions must be non-empty")
    for action in allowed:
        require("external" not in action and "publish" not in action and "contact" not in action and "spend" not in action, f"{lane_id}: allowed action is not internal: {action}")

    validate_packet(lane_id, "input_contract", lane.get("input_contract"))
    validate_packet(lane_id, "output_contract", lane.get("output_contract"))

    memory = lane.get("shared_memory")
    require(isinstance(memory, dict), f"{lane_id}: shared_memory must be an object")
    home = memory.get("agent_home")
    require(isinstance(home, str) and home.startswith("Dominion-Brain/04-Agents/"), f"{lane_id}: invalid Obsidian agent home")
    for key, destination in REQUIRED_MEMORY.items():
        require(memory.get(key) == destination, f"{lane_id}: {key} memory destination must be {destination}")

    validate_kpis(lane_id, lane.get("kpi_interface"))
    requirements = lane.get("promotion_requirements")
    require(isinstance(requirements, list) and requirements, f"{lane_id}: promotion_requirements must be non-empty")
    return lane_id


def main() -> int:
    try:
        schema = load(SCHEMA)
        contract = load(CONTRACT)
        require(schema.get("title") == "Dominion Dormant Specialist Lane Contracts", "schema title drift")
        require(contract.get("schema_version") == "1.0.0", "contract schema version must be 1.0.0")
        require(contract.get("authority") == "human_overseer", "human overseer must retain final authority")
        require(contract.get("activation_default") == "DORMANT", "specialist lanes must default to DORMANT")
        require(contract.get("budget_default_usd") == 0, "specialist lanes must default to zero budget")
        require(contract.get("truth_states") == CANONICAL_TRUTH_STATES, "truth states must be canonical")
        require(set(contract.get("global_prohibitions", [])) == GLOBAL_PROHIBITIONS, "global prohibitions drift")
        memory = contract.get("shared_memory")
        require(isinstance(memory, dict), "shared memory contract missing")
        require(memory.get("policy_source") == "GitHub versioned governance and contracts", "GitHub must remain policy source")
        require(memory.get("operational_memory") == "Obsidian Dominion-Brain", "Obsidian must remain operational memory")
        for key, destination in {
            "evidence_destination": REQUIRED_MEMORY["evidence"],
            "decision_destination": REQUIRED_MEMORY["decisions"],
            "learning_destination": REQUIRED_MEMORY["learning"],
        }.items():
            require(memory.get(key) == destination, f"shared memory {key} must be {destination}")

        lanes = contract.get("lanes")
        require(isinstance(lanes, list), "lanes must be a list")
        lane_ids = {validate_lane(lane, GLOBAL_PROHIBITIONS) for lane in lanes}
        require(lane_ids == REQUIRED_LANES, f"lane roster must be exactly {sorted(REQUIRED_LANES)}")
    except ContractError as exc:
        print(f"SPECIALIST LANE CONTRACTS: FAIL — {exc}", file=sys.stderr)
        return 1

    print(f"SPECIALIST LANE CONTRACTS: PASS — {len(REQUIRED_LANES)} dormant lanes validated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
