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


def validate() -> tuple[int, int]:
    require(CONTRACT.is_file(), "missing alignment contract")
    registry = load(REGISTRY)
    final_policy = load(FINAL_POLICY)
    council_policy = load(COUNCIL_POLICY)

    require(registry.get("schema_version") == 1, "system component schema_version must be 1")
    require(registry.get("authority_model") == "RADAH_MEMSHALAH", "authority model drift")
    require(
        registry.get("source_of_truth_precedence")
        == ["github", "runtime", "provider_receipts", "command_center", "dominion_brain"],
        "source-of-truth precedence drift",
    )

    # Governance policy must still declare Five Council as the final affirmative gate.
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
        if component["writes_external_state"]:
            require(component["requires_receipt_for_side_effect"] is True, f"{cid}: external side effects require receipts")
        role = component["role"]
        require(role not in role_owners, f"duplicate canonical role authority: {role}")
        role_owners[role] = cid

    exclusive = registry.get("exclusive_roles")
    require(isinstance(exclusive, dict) and exclusive, "exclusive_roles must be defined")
    for role, expected_component in exclusive.items():
        require(expected_component in by_id, f"exclusive role {role} points to unknown component {expected_component}")
        require(by_id[expected_component]["role"] == role, f"exclusive role {role} owner mismatch")

    # Safety boundaries that must never drift silently.
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
        require(owner in by_id, f"{pid}: unknown pipeline owner {owner}")
        require(pipeline.get("requires_closed_loop") is True, f"{pid}: closed-loop requirement must be true")

    required_pipelines = {
        "production_release", "traffic_revenue", "platform_binding",
        "commerce", "research_knowledge", "paper_trading",
    }
    require(required_pipelines == pipeline_ids, "canonical mission pipeline set drift")

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
