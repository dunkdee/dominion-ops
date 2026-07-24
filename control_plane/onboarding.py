"""Fail-closed agent candidate admission checks.

This module validates candidates but never mutates the canonical registry or
promotes an agent. Promotion remains a separate reviewed repository change.
"""

from __future__ import annotations

import re
from typing import Any

from .canonical import sha256_json

ID_PATTERN = re.compile(r"^[a-z][a-z0-9_-]{2,63}$")
FORBIDDEN_REQUESTS = {
    "deploy_production",
    "merge_to_main",
    "publish_external_content",
    "contact_customer_or_claimant",
    "spend_or_move_money",
    "sign_file_or_submit_legal_document",
    "read_or_export_secret_values",
    "expand_own_permissions",
    "reactivate_suspended_or_retired_agent",
}
REQUIRED_FIELDS = {
    "id",
    "role",
    "purpose",
    "owner",
    "requested_actions",
    "prohibited_actions",
    "input_contract",
    "output_contract",
    "success_metrics",
    "failure_modes",
    "data_classification",
    "tool_allowlist",
    "escalates_to",
}


def validate_candidate(candidate: dict[str, Any], registry: dict[str, Any], authority: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    if not isinstance(candidate, dict):
        raise TypeError("candidate must be an object")

    missing = sorted(REQUIRED_FIELDS - set(candidate))
    errors.extend(f"missing_field:{field}" for field in missing)
    candidate_id = candidate.get("id")
    if not isinstance(candidate_id, str) or not ID_PATTERN.fullmatch(candidate_id):
        errors.append("invalid_agent_id")

    existing_ids = {item.get("id") for item in registry.get("agents", []) if isinstance(item, dict)}
    if candidate_id in existing_ids:
        errors.append("duplicate_agent_id")

    requested = candidate.get("requested_actions", [])
    if not isinstance(requested, list) or not all(isinstance(item, str) for item in requested):
        errors.append("requested_actions_must_be_string_list")
        requested = []
    if "*" in requested:
        errors.append("wildcard_action_forbidden")

    known_actions = {item.get("id") for item in authority.get("actions", []) if isinstance(item, dict)}
    unknown = sorted(set(requested) - known_actions)
    errors.extend(f"unknown_action:{action}" for action in unknown)
    forbidden = sorted(set(requested) & FORBIDDEN_REQUESTS)
    errors.extend(f"stage2_action_forbidden:{action}" for action in forbidden)

    tools = candidate.get("tool_allowlist", [])
    if not isinstance(tools, list) or not all(isinstance(item, str) for item in tools):
        errors.append("tool_allowlist_must_be_string_list")
    elif "*" in tools:
        errors.append("wildcard_tool_forbidden")

    for list_field in ("prohibited_actions", "success_metrics", "failure_modes"):
        value = candidate.get(list_field, [])
        if not isinstance(value, list) or not value:
            errors.append(f"{list_field}_must_be_nonempty_list")

    for contract_field in ("input_contract", "output_contract"):
        value = candidate.get(contract_field)
        if not isinstance(value, dict) or not value:
            errors.append(f"{contract_field}_must_be_nonempty_object")

    if candidate.get("data_classification") not in {"PUBLIC", "INTERNAL", "CONFIDENTIAL", "RESTRICTED"}:
        errors.append("invalid_data_classification")
    if candidate.get("owner") != "human_overseer":
        warnings.append("human_overseer_not_declared_as_owner")

    status = "REJECTED" if errors else "ELIGIBLE_FOR_SPEC_REVIEW"
    result = {
        "candidate_id": candidate_id,
        "candidate_hash": sha256_json(candidate),
        "status": status,
        "initial_state": "REGISTERED" if not errors else None,
        "errors": sorted(set(errors)),
        "warnings": sorted(set(warnings)),
        "registry_mutated": False,
        "production_authority_granted": False,
    }
    result["report_hash"] = sha256_json(result)
    return result
