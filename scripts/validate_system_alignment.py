#!/usr/bin/env python3
"""Fail-closed validation for Dominion system role and workflow alignment."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "governance" / "system_components.json"
CONTRACT = ROOT / "docs" / "DOMINION_SYSTEM_ALIGNMENT_V1.md"
FINAL_POLICY = ROOT / "governance" / "final_release_policy.json"
COUNCIL_POLICY = ROOT / "governance" / "five_council_policy.json"
ALLOWED_STATES = {"DONE", "IN_PROGRESS", "BLOCKED", "UNKNOWN", "PARKED"}

REQUIRED_COMPONENTS = {
    "founder", "five_council", "conductor", "buddy", "dominion_brain",
    "command_center", "dominion_publisher", "content_engine", "voltedge_wix",
    "n8n", "specialist_agents", "orion_alpha",
}
EXPECTED_EXCLUSIVE_ROLES = {
    "governance_final_gate": "five_council",
    "orchestration": "conductor",
    "operator_interface": "buddy",
    "operational_memory": "dominion_brain",
    "operator_observability": "command_center",
    "publishing_control_plane": "dominion_publisher",
    "commerce_boundary": "voltedge_wix",
}
EXPECTED_AUTHORITY_CLASSES = {
    "founder": "scope_and_priority",
    "five_council": "final_affirmative_gate",
    "conductor": "route_bounded_work",
    "buddy": "intent_to_governed_capability",
    "dominion_brain": "verified_coordination_memory",
    "command_center": "read_and_control_surface",
    "dominion_publisher": "approved_publication_execution",
    "content_engine": "draft_and_transform",
    "voltedge_wix": "catalog_checkout_order_truth",
    "n8n": "execute_declared_workflows",
    "specialist_agents": "evidence_and_recommendation",
    "orion_alpha": "paper_only_market_intelligence",
}
EXPECTED_SCHEDULER_OWNERS = {
    "founder": None,
    "five_council": None,
    "conductor": "conductor",
    "buddy": None,
    "dominion_brain": None,
    "command_center": None,
    "dominion_publisher": "dominion_publisher",
    "content_engine": None,
    "voltedge_wix": None,
    "n8n": "n8n",
    "specialist_agents": None,
    "orion_alpha": "orion_alpha",
}
EXPECTED_PIPELINE_OWNERS = {
    "production_release": "conductor",
    "traffic_revenue": "dominion_publisher",
    "platform_binding": "dominion_publisher",
    "commerce": "voltedge_wix",
    "research_knowledge": "specialist_agents",
    "paper_trading": "orion_alpha",
}
EXPECTED_PRECEDENCE = [
    "github",
    "runtime",
    "publisher_runtime_receipts",
    "provider_receipts",
    "command_center",
    "dominion_brain",
]
REQUIRED_CONTRACT_MARKERS = (
    "# Dominion System Alignment Contract v1",
    "Authority model: RADAH MEMSHALAH",
    "Dominion is one governed system with many specialized lanes.",
    "A lane is not DONE until the full execution loop closes.",
    "GitHub: versioned law, code, schemas, workflows, release policy, approved configuration descriptors.",
    "Foundation VM/runtime: live service/runtime truth.",
    "Publisher/runtime databases and immutable receipts: publication/job/account state.",
    "Commerce/platform providers: provider-native order, traffic, account, and publication evidence.",
    "Command Center: operator view of canonical state; never an independent truth producer.",
    "Obsidian / Dominion-Brain: operational memory and coordination layer synchronized from verified truth; never permitted to overrule GitHub/runtime evidence.",
)


class AlignmentFailure(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AlignmentFailure(message)


def load(path: Path) -> dict[str, Any]:
    require(path.is_file(), f"missing required file: {path.relative_to(ROOT)}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise AlignmentFailure(f"invalid JSON in {path.relative_to(ROOT)}: {exc}") from exc
    require(isinstance(value, dict), f"{path.relative_to(ROOT)} root must be an object")
    return value


def validate_contract() -> None:
    require(CONTRACT.is_file(), "missing alignment contract")
    text = CONTRACT.read_text(encoding="utf-8")
    require(text.strip(), "alignment contract must not be empty")
    for marker in REQUIRED_CONTRACT_MARKERS:
        require(marker in text, f"alignment contract invariant missing: {marker}")


def validate() -> tuple[int, int]:
    validate_contract()
    registry = load(REGISTRY)
    final_policy = load(FINAL_POLICY)
    council_policy = load(COUNCIL_POLICY)

    require(registry.get("schema_version") == 1, "system component schema_version must be 1")
    require(registry.get("authority_model") == "RADAH_MEMSHALAH", "authority model drift")
    require(registry.get("source_of_truth_precedence") == EXPECTED_PRECEDENCE, "source-of-truth precedence drift")

    require(final_policy.get("final_affirmative_gate") == "five_council", "final release gate drift")
    require(final_policy.get("default_behavior") == "deny", "final release policy must fail closed")
    final_release = council_policy.get("final_release", {})
    require(final_release.get("final_affirmative_gate") == "five_council", "council final gate drift")
    require(final_release.get("unanimous_approval_required") is True, "unanimous council approval must remain required")
    require(final_release.get("hold_or_missing_review_blocks_release") is True, "missing review/HOLD must block release")

    components = registry.get("components")
    require(isinstance(components, list) and components, "components must be a non-empty list")
    required = {
        "id", "role", "authority_class", "owner", "source_of_truth", "lifecycle_state",
        "scheduler_owner", "writes_external_state", "requires_receipt_for_side_effect",
    }
    by_id: dict[str, dict[str, Any]] = {}
    role_owners: dict[str, str] = {}

    for component in components:
        require(isinstance(component, dict), "component entries must be objects")
        missing = required - component.keys()
        require(not missing, f"component missing fields: {sorted(missing)}")
        cid = component["id"]
        require(isinstance(cid, str) and cid, "component id must be non-empty")
        require(cid not in by_id, f"duplicate component id: {cid}")
        by_id[cid] = component
        require(component["lifecycle_state"] in ALLOWED_STATES, f"{cid}: invalid lifecycle_state")
        require(isinstance(component["owner"], str) and component["owner"], f"{cid}: owner required")
        require(isinstance(component["source_of_truth"], str) and component["source_of_truth"], f"{cid}: source_of_truth required")
        require(type(component["writes_external_state"]) is bool, f"{cid}: writes_external_state must be boolean")
        require(type(component["requires_receipt_for_side_effect"]) is bool, f"{cid}: requires_receipt_for_side_effect must be boolean")
        if component["writes_external_state"]:
            require(component["requires_receipt_for_side_effect"] is True, f"{cid}: external side effects require receipts")
        role = component["role"]
        require(isinstance(role, str) and role, f"{cid}: role required")
        require(role not in role_owners, f"duplicate canonical role authority: {role}")
        role_owners[role] = cid

    require(set(by_id) == REQUIRED_COMPONENTS, "canonical component set drift")
    for cid, expected_authority in EXPECTED_AUTHORITY_CLASSES.items():
        require(by_id[cid]["authority_class"] == expected_authority, f"{cid}: authority_class drift")
    for cid, expected_scheduler in EXPECTED_SCHEDULER_OWNERS.items():
        require(by_id[cid]["scheduler_owner"] == expected_scheduler, f"{cid}: scheduler_owner drift")
        if expected_scheduler is not None:
            require(expected_scheduler in by_id, f"{cid}: scheduler owner must be canonical component")

    exclusive = registry.get("exclusive_roles")
    require(exclusive == EXPECTED_EXCLUSIVE_ROLES, "exclusive role mapping drift")
    for role, expected_component in EXPECTED_EXCLUSIVE_ROLES.items():
        require(by_id[expected_component]["role"] == role, f"exclusive role {role} owner mismatch")

    require(by_id["dominion_publisher"]["role"] == "publishing_control_plane", "Publisher must remain canonical publishing control plane")
    require(by_id["dominion_brain"]["role"] == "operational_memory", "Dominion Brain must remain canonical operational memory")
    require(by_id["command_center"]["role"] == "operator_observability", "Command Center must remain an observability/control surface")
    require(by_id["orion_alpha"]["authority_class"] == "paper_only_market_intelligence", "Orion/Alpha must remain paper-only here")

    pipelines = registry.get("mission_pipelines")
    require(isinstance(pipelines, list) and pipelines, "mission_pipelines must be a non-empty list")
    pipeline_ids: set[str] = set()
    for pipeline in pipelines:
        require(isinstance(pipeline, dict), "pipeline entries must be objects")
        pid = pipeline.get("id")
        owner = pipeline.get("owner")
        require(isinstance(pid, str) and pid, "pipeline id required")
        require(pid not in pipeline_ids, f"duplicate mission pipeline: {pid}")
        pipeline_ids.add(pid)
        require(pid in EXPECTED_PIPELINE_OWNERS, f"unexpected mission pipeline: {pid}")
        require(owner == EXPECTED_PIPELINE_OWNERS[pid], f"{pid}: canonical pipeline owner drift")
        require(owner in by_id, f"{pid}: unknown pipeline owner {owner}")
        require(pipeline.get("requires_closed_loop") is True, f"{pid}: closed-loop requirement must be true")

    require(set(EXPECTED_PIPELINE_OWNERS) == pipeline_ids, "canonical mission pipeline set drift")
    return len(components), len(pipelines)


def main() -> int:
    try:
        component_count, pipeline_count = validate()
    except AlignmentFailure as exc:
        print(f"SYSTEM ALIGNMENT: FAIL — {exc}", file=sys.stderr)
        return 1
    print(f"SYSTEM ALIGNMENT: PASS — {component_count} components, {pipeline_count} mission pipelines")
    print("RADAH_MEMSHALAH=PASS")
    print("FAIL_CLOSED_GOVERNANCE=PASS")
    print("ONE_BRAIN_ALIGNMENT=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
