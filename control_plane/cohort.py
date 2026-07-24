"""Fail-closed validation for controlled shadow-mode agent cohorts.

The validator prepares an assignment report only. It never mutates the agent
registry, changes lifecycle state, starts a runtime, or grants production
permissions.
"""

from __future__ import annotations

import re
from typing import Any

from .canonical import sha256_json

ID_PATTERN = re.compile(r"^[a-z][a-z0-9_-]{2,63}$")
REQUIRED_BLOCKED_ACTIONS = {
    "merge_to_main",
    "deploy_production",
    "publish_external_content",
    "contact_customer_or_claimant",
    "spend_or_move_money",
    "sign_file_or_submit_legal_document",
    "reactivate_suspended_or_retired_agent",
}
REQUIRED_FIELDS = {
    "cohort_id",
    "mode",
    "owner",
    "objective",
    "entry_evidence",
    "shared_prohibited_actions",
    "exit_criteria",
    "assignments",
}


def validate_shadow_cohort(
    manifest: dict[str, Any],
    registry: dict[str, Any],
    tool_catalog: dict[str, Any],
    activation_gates: dict[str, Any],
) -> dict[str, Any]:
    if not isinstance(manifest, dict):
        raise TypeError("cohort manifest must be an object")

    errors: list[str] = []
    warnings: list[str] = []
    missing = sorted(REQUIRED_FIELDS - set(manifest))
    errors.extend(f"missing_field:{field}" for field in missing)

    cohort_id = manifest.get("cohort_id")
    if not isinstance(cohort_id, str) or not ID_PATTERN.fullmatch(cohort_id):
        errors.append("invalid_cohort_id")
    if manifest.get("mode") != "SHADOW":
        errors.append("cohort_mode_must_be_shadow")
    if activation_gates.get("mode") != "shadow_only":
        errors.append("runtime_not_shadow_only")
    if activation_gates.get("external_execution_enabled") is not False:
        errors.append("external_execution_must_be_disabled")
    if activation_gates.get("registry_mutation_enabled") is not False:
        errors.append("registry_mutation_must_be_disabled")
    if manifest.get("owner") != "human_overseer":
        errors.append("human_overseer_must_own_cohort")

    entry_evidence = manifest.get("entry_evidence", [])
    if not isinstance(entry_evidence, list) or not entry_evidence or not all(
        isinstance(item, str) and item for item in entry_evidence
    ):
        errors.append("entry_evidence_must_be_nonempty_string_list")

    exit_criteria = manifest.get("exit_criteria", [])
    if not isinstance(exit_criteria, list) or not exit_criteria or not all(
        isinstance(item, str) and item for item in exit_criteria
    ):
        errors.append("exit_criteria_must_be_nonempty_string_list")

    prohibited = manifest.get("shared_prohibited_actions", [])
    if not isinstance(prohibited, list) or not all(isinstance(item, str) for item in prohibited):
        errors.append("shared_prohibited_actions_must_be_string_list")
        prohibited_set: set[str] = set()
    else:
        prohibited_set = set(prohibited)
    missing_blocks = sorted(REQUIRED_BLOCKED_ACTIONS - prohibited_set)
    errors.extend(f"missing_prohibited_action:{item}" for item in missing_blocks)

    agents = {
        item.get("id"): item
        for item in registry.get("agents", [])
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    tools = {
        item.get("id"): item
        for item in tool_catalog.get("tools", [])
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    if tool_catalog.get("default_behavior") != "deny":
        errors.append("tool_catalog_must_be_default_deny")

    assignments = manifest.get("assignments", [])
    if not isinstance(assignments, list) or not assignments:
        errors.append("assignments_must_be_nonempty_list")
        assignments = []

    seen_agents: set[str] = set()
    assignment_reports: list[dict[str, Any]] = []
    for index, assignment in enumerate(assignments):
        assignment_errors: list[str] = []
        if not isinstance(assignment, dict):
            errors.append(f"assignment_{index}_must_be_object")
            continue
        agent_id = assignment.get("agent_id")
        if not isinstance(agent_id, str) or agent_id not in agents:
            assignment_errors.append("unknown_agent")
            agent = None
        else:
            agent = agents[agent_id]
            if agent_id in seen_agents:
                assignment_errors.append("duplicate_agent_assignment")
            seen_agents.add(agent_id)
            if agent.get("state") in {"SUSPENDED", "RETIRED"}:
                assignment_errors.append("agent_not_eligible")

        duties = assignment.get("duties", [])
        if not isinstance(duties, list) or not duties or not all(isinstance(item, str) for item in duties):
            assignment_errors.append("duties_must_be_nonempty_string_list")
            duties_set: set[str] = set()
        else:
            duties_set = set(duties)
        if agent is not None:
            permission_set = set(agent.get("permissions", []))
            for duty in sorted(duties_set - permission_set):
                assignment_errors.append(f"duty_not_registered:{duty}")

        tool_allowlist = assignment.get("tool_allowlist", [])
        if not isinstance(tool_allowlist, list) or not tool_allowlist or not all(
            isinstance(item, str) for item in tool_allowlist
        ):
            assignment_errors.append("tool_allowlist_must_be_nonempty_string_list")
            tool_allowlist = []
        if "*" in tool_allowlist:
            assignment_errors.append("wildcard_tool_forbidden")
        for tool_id in tool_allowlist:
            tool = tools.get(tool_id)
            if tool is None:
                assignment_errors.append(f"unknown_tool:{tool_id}")
                continue
            if "SHADOW" not in tool.get("allowed_modes", []):
                assignment_errors.append(f"tool_not_allowed_in_shadow:{tool_id}")
            if tool.get("external_effect") not in {"none", "read_only"}:
                assignment_errors.append(f"external_effect_tool_forbidden:{tool_id}")

        data_classes = assignment.get("data_classification", [])
        if not isinstance(data_classes, list) or not data_classes:
            assignment_errors.append("data_classification_must_be_nonempty_list")
        elif not set(data_classes).issubset({"PUBLIC", "INTERNAL", "CONFIDENTIAL", "RESTRICTED"}):
            assignment_errors.append("invalid_data_classification")

        if assignment.get("escalates_to") not in agents:
            assignment_errors.append("unknown_escalation_target")
        if assignment.get("lifecycle_change_requested") is not False:
            assignment_errors.append("lifecycle_change_forbidden")

        assignment_reports.append(
            {
                "agent_id": agent_id,
                "eligible": not assignment_errors,
                "errors": sorted(set(assignment_errors)),
                "state_unchanged": True,
                "production_authority_granted": False,
            }
        )
        errors.extend(f"assignment:{agent_id}:{item}" for item in assignment_errors)

    if len(assignments) > 12:
        warnings.append("large_initial_cohort_review_recommended")

    status = "REJECTED" if errors else "ELIGIBLE_FOR_SHADOW_ASSIGNMENT_REVIEW"
    result = {
        "cohort_id": cohort_id,
        "manifest_hash": sha256_json(manifest),
        "status": status,
        "mode": "SHADOW_ONLY",
        "errors": sorted(set(errors)),
        "warnings": sorted(set(warnings)),
        "assignment_reports": assignment_reports,
        "registry_mutated": False,
        "agents_promoted": False,
        "runtime_started": False,
        "external_execution_authorized": False,
    }
    result["report_hash"] = sha256_json(result)
    return result
