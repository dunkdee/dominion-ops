#!/usr/bin/env python3
"""Validate the repo-native Dominion Founder Oversight and Evidence Control layer."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "governance" / "founder_oversight_contract.json"
MISSION_SCHEMA = ROOT / "governance" / "schemas" / "founder_mission_record.schema.json"
EVIDENCE_SCHEMA = ROOT / "governance" / "schemas" / "founder_evidence_record.schema.json"
MISSION_EXAMPLE = ROOT / "runtime" / "examples" / "founder_oversight_mission.example.json"
EVIDENCE_EXAMPLE = ROOT / "runtime" / "examples" / "founder_oversight_evidence.example.json"

TRUTH_STATES = {"VERIFIED", "INFERRED", "UNKNOWN", "BLOCKED"}
HOLD_STATES = {
    "tiktok": "DISABLED",
    "trading_and_markov": "PAPER_ONLY",
    "wix": "RECORD_ONLY",
    "payments": "NOT_AUTHORIZED",
    "publications": "NOT_AUTHORIZED",
    "customer_contact": "NOT_AUTHORIZED",
    "credential_changes": "NOT_AUTHORIZED",
    "production_service_changes": "NOT_AUTHORIZED",
}
LANE_STATES = {
    "intelligence": "governed_reasoning_only",
    "context_memory": "governed_memory_only",
    "execution": "dormant_by_default",
    "verification": "read_only",
    "impact_revenue": "draft_only",
}


class OversightValidationError(ValueError):
    """Raised when an oversight invariant fails."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise OversightValidationError(message)


def load_json(path: Path) -> dict[str, Any]:
    require(path.is_file(), f"missing required file: {path.relative_to(ROOT)}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise OversightValidationError(f"invalid JSON in {path.relative_to(ROOT)}: {exc}") from exc
    require(isinstance(value, dict), f"{path.relative_to(ROOT)} must contain an object")
    return value


def validate_schema(schema: dict[str, Any], expected_version: str, required: set[str], label: str) -> None:
    require(schema.get("type") == "object", f"{label}: root type must be object")
    require(schema.get("additionalProperties") is False, f"{label}: unknown fields must be rejected")
    require(set(schema.get("required", [])) == required, f"{label}: required fields drifted")
    properties = schema.get("properties", {})
    require(isinstance(properties, dict), f"{label}: properties must be object")
    require(properties.get("schema_version", {}).get("const") == expected_version, f"{label}: schema version mismatch")
    truth = properties.get("truth_state", {})
    require(set(truth.get("enum", [])) == TRUTH_STATES, f"{label}: truth states drifted")


def validate_example(example: dict[str, Any], schema: dict[str, Any], label: str) -> None:
    required = set(schema["required"])
    require(set(example) == set(schema["properties"]), f"{label}: example fields must match schema properties")
    require(required.issubset(example), f"{label}: missing required fields")
    require(example["schema_version"] == schema["properties"]["schema_version"]["const"], f"{label}: schema version mismatch")
    require(example["truth_state"] in TRUTH_STATES, f"{label}: invalid truth state")
    for key in ("mission_id", "evidence_id"):
        if key in example:
            require(isinstance(example[key], str) and example[key], f"{label}: {key} must be a non-empty string")


def validate_contract(contract: dict[str, Any]) -> None:
    require(contract.get("schema_version") == "dominion-founder-oversight-contract-v1", "contract schema_version mismatch")
    authority = contract.get("authority", {})
    require(authority.get("default_behavior") == "deny", "contract must default deny")
    require(authority.get("autonomous_authority_expansion") is False, "authority expansion must remain prohibited")
    require(authority.get("runtime_authority_granted_by_this_contract") is False, "contract must not grant runtime authority")
    require(set(contract.get("truth_states", [])) == TRUTH_STATES, "truth states must be exact")
    require(contract.get("protected_holds") == HOLD_STATES, "protected holds drifted")

    lanes = contract.get("lanes", {})
    require(set(lanes) == set(LANE_STATES), "lane set drifted")
    for lane, expected_state in LANE_STATES.items():
        record = lanes[lane]
        require(record.get("state") == expected_state, f"{lane}: state must remain {expected_state}")
        require(isinstance(record.get("allowed"), list) and record["allowed"], f"{lane}: allowed scope missing")
        require(isinstance(record.get("prohibited"), list) and record["prohibited"], f"{lane}: prohibited scope missing")

    evidence = contract.get("evidence", {})
    required_evidence_fields = {
        "evidence_id", "mission_id", "timestamp", "actor", "source", "artifact_references",
        "result", "truth_state", "risks_and_limitations", "next_action", "redaction_status", "policy_version",
    }
    require(set(evidence.get("required_fields", [])) == required_evidence_fields, "evidence record fields drifted")
    evidence_text = " ".join(evidence.get("requirements", []))
    for prohibited in ("secrets", "credentials", "private keys", "tokens", "raw customer records"):
        require(prohibited in evidence_text, f"evidence protections missing: {prohibited}")

    approvals = set(contract.get("required_founder_approval_actions", []))
    for action in (
        "merge_to_main", "deploy_production", "publish_external_content", "contact_customer_or_claimant",
        "spend_or_move_money", "enable_live_trading", "change_credentials",
    ):
        require(action in approvals, f"Founder approval action missing: {action}")


def validate(root: Path = ROOT) -> dict[str, int]:
    global ROOT, CONTRACT, MISSION_SCHEMA, EVIDENCE_SCHEMA, MISSION_EXAMPLE, EVIDENCE_EXAMPLE
    ROOT = root.resolve()
    CONTRACT = ROOT / "governance" / "founder_oversight_contract.json"
    MISSION_SCHEMA = ROOT / "governance" / "schemas" / "founder_mission_record.schema.json"
    EVIDENCE_SCHEMA = ROOT / "governance" / "schemas" / "founder_evidence_record.schema.json"
    MISSION_EXAMPLE = ROOT / "runtime" / "examples" / "founder_oversight_mission.example.json"
    EVIDENCE_EXAMPLE = ROOT / "runtime" / "examples" / "founder_oversight_evidence.example.json"

    contract = load_json(CONTRACT)
    mission_schema = load_json(MISSION_SCHEMA)
    evidence_schema = load_json(EVIDENCE_SCHEMA)
    mission_example = load_json(MISSION_EXAMPLE)
    evidence_example = load_json(EVIDENCE_EXAMPLE)

    validate_contract(contract)
    validate_schema(
        mission_schema, "dominion-founder-mission-record-v1",
        {"schema_version", "mission_id", "title", "objective", "status", "truth_state", "initiating_event",
         "verified_facts", "unknowns_and_assumptions", "lane_assignments", "risk_level", "required_approvals",
         "verification_gate", "stop_conditions", "rollback_conditions", "memory_destination",
         "evidence_references", "policy_version"},
        "mission schema",
    )
    validate_schema(
        evidence_schema, "dominion-founder-evidence-record-v1",
        {"schema_version", "evidence_id", "mission_id", "timestamp", "actor", "source", "artifact_references",
         "result", "truth_state", "risks_and_limitations", "next_action", "redaction_status", "policy_version"},
        "evidence schema",
    )
    validate_example(mission_example, mission_schema, "mission example")
    validate_example(evidence_example, evidence_schema, "evidence example")
    require(mission_example["status"] == "PLANNED", "example must not claim execution")
    require(mission_example["truth_state"] == "UNKNOWN", "example must not claim runtime state")
    require(evidence_example["truth_state"] == "UNKNOWN", "example evidence must not claim runtime state")
    return {"lanes": len(contract["lanes"]), "protected_holds": len(HOLD_STATES), "schemas": 2}


def main() -> int:
    try:
        result = validate()
    except OversightValidationError as exc:
        print(f"FOUNDER OVERSIGHT: FAIL — {exc}", file=sys.stderr)
        return 1
    print(f"FOUNDER OVERSIGHT: PASS — {result['lanes']} bounded lanes, {result['protected_holds']} protected holds, {result['schemas']} schemas")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
