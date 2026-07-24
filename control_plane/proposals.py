"""Canonical proposal envelopes and independently bound council reviews."""

from __future__ import annotations

import re
from typing import Any

from .canonical import sha256_json
from .council import aggregate_council_decision

ID_PATTERN = re.compile(r"^[a-z][a-z0-9_-]{2,95}$")
VALID_REVIEW_DECISIONS = {"APPROVE", "APPROVE_WITH_CONDITIONS", "VETO", "HOLD", "ABSTAIN"}
REQUIRED_PROPOSAL_FIELDS = {
    "proposal_id",
    "proposer_id",
    "objective",
    "requested_action",
    "risk",
    "evidence",
    "assumptions",
    "unknowns",
    "rollback_plan",
    "success_criteria",
    "external_effects",
}


def prepare_proposal_envelope(
    proposal: dict[str, Any],
    registry: dict[str, Any],
    authority: dict[str, Any],
    activation_gates: dict[str, Any],
) -> dict[str, Any]:
    if not isinstance(proposal, dict):
        raise TypeError("proposal must be an object")

    errors: list[str] = []
    missing = sorted(REQUIRED_PROPOSAL_FIELDS - set(proposal))
    errors.extend(f"missing_field:{field}" for field in missing)

    proposal_id = proposal.get("proposal_id")
    if not isinstance(proposal_id, str) or not ID_PATTERN.fullmatch(proposal_id):
        errors.append("invalid_proposal_id")

    agents = {
        item.get("id"): item
        for item in registry.get("agents", [])
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    proposer = agents.get(proposal.get("proposer_id"))
    if proposer is None:
        errors.append("unknown_proposer")
    elif proposer.get("state") in {"SUSPENDED", "RETIRED"}:
        errors.append("proposer_not_active")

    actions = {
        item.get("id"): item
        for item in authority.get("actions", [])
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    action = actions.get(proposal.get("requested_action"))
    if action is None:
        errors.append("unknown_requested_action")
    else:
        if proposal.get("risk") != action.get("risk"):
            errors.append("risk_does_not_match_authority")
        if proposer is not None and proposer.get("role") not in action.get("allowed_roles", []):
            errors.append("proposer_role_not_authorized_for_action")

    for field in ("evidence", "success_criteria"):
        value = proposal.get(field, [])
        if not isinstance(value, list) or not value or not all(isinstance(item, str) and item for item in value):
            errors.append(f"{field}_must_be_nonempty_string_list")
    for field in ("assumptions", "unknowns"):
        value = proposal.get(field, [])
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            errors.append(f"{field}_must_be_string_list")

    rollback_plan = proposal.get("rollback_plan")
    if not isinstance(rollback_plan, dict) or not rollback_plan.get("trigger") or not rollback_plan.get("procedure"):
        errors.append("rollback_plan_incomplete")

    if proposal.get("external_effects") is not False:
        errors.append("shadow_proposal_must_have_no_external_effects")
    if activation_gates.get("external_execution_enabled") is not False:
        errors.append("external_execution_gate_must_be_disabled")
    if activation_gates.get("mode") != "shadow_only":
        errors.append("runtime_not_shadow_only")

    proposal_hash = sha256_json(proposal)
    result = {
        "proposal_id": proposal_id,
        "proposal_hash": proposal_hash,
        "proposal": proposal,
        "status": "REJECTED" if errors else "READY_FOR_INDEPENDENT_COUNCIL_REVIEW",
        "errors": sorted(set(errors)),
        "external_execution_authorized": False,
        "proposal_mutated": False,
    }
    result["envelope_hash"] = sha256_json(result)
    return result


def bind_council_review(
    envelope: dict[str, Any],
    review: dict[str, Any],
    registry: dict[str, Any],
    council_policy: dict[str, Any],
) -> dict[str, Any]:
    if not isinstance(envelope, dict) or envelope.get("status") != "READY_FOR_INDEPENDENT_COUNCIL_REVIEW":
        raise ValueError("proposal envelope is not reviewable")
    if not isinstance(review, dict):
        raise TypeError("review must be an object")

    errors: list[str] = []
    councils = {
        item.get("id"): item
        for item in council_policy.get("councils", [])
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    agents = {
        item.get("id"): item
        for item in registry.get("agents", [])
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }

    council_id = review.get("council_id")
    reviewer_id = review.get("reviewer_agent_id")
    council = councils.get(council_id)
    reviewer = agents.get(reviewer_id)
    if council is None:
        errors.append("unknown_council")
    if reviewer is None:
        errors.append("unknown_reviewer")
    elif reviewer.get("role") != council_id:
        errors.append("reviewer_role_does_not_match_council")
    if reviewer_id == envelope.get("proposal", {}).get("proposer_id"):
        errors.append("proposer_cannot_review_own_proposal")
    if review.get("decision") not in VALID_REVIEW_DECISIONS:
        errors.append("invalid_review_decision")

    evidence = review.get("evidence", [])
    if not isinstance(evidence, list) or not evidence or not all(isinstance(item, str) and item for item in evidence):
        errors.append("review_evidence_must_be_nonempty_string_list")
    rationale = review.get("rationale")
    if not isinstance(rationale, str) or not rationale.strip():
        errors.append("review_rationale_required")
    conditions = review.get("conditions", [])
    if not isinstance(conditions, list) or not all(isinstance(item, str) for item in conditions):
        errors.append("conditions_must_be_string_list")

    bound = {
        "proposal_id": envelope.get("proposal_id"),
        "proposal_hash": envelope.get("proposal_hash"),
        "council_id": council_id,
        "reviewer_agent_id": reviewer_id,
        "decision": review.get("decision"),
        "evidence": evidence if isinstance(evidence, list) else [],
        "rationale": rationale,
        "conditions": conditions if isinstance(conditions, list) else [],
        "independent": reviewer_id != envelope.get("proposal", {}).get("proposer_id"),
        "status": "REJECTED" if errors else "BOUND",
        "errors": sorted(set(errors)),
    }
    bound["review_hash"] = sha256_json(bound)
    return bound


def aggregate_bound_reviews(
    envelope: dict[str, Any],
    bound_reviews: list[dict[str, Any]],
    *,
    council_policy: dict[str, Any],
    human_approval: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if envelope.get("status") != "READY_FOR_INDEPENDENT_COUNCIL_REVIEW":
        raise ValueError("proposal envelope is not reviewable")
    normalized: list[dict[str, Any]] = []
    for review in bound_reviews:
        if review.get("status") != "BOUND":
            raise ValueError("all reviews must be successfully bound")
        expected_hash = sha256_json({key: value for key, value in review.items() if key != "review_hash"})
        if review.get("review_hash") != expected_hash:
            raise ValueError("bound review hash mismatch")
        if review.get("proposal_hash") != envelope.get("proposal_hash"):
            raise ValueError("bound review proposal mismatch")
        normalized.append(
            {
                "council_id": review.get("council_id"),
                "proposal_hash": sha256_json(envelope),
                "decision": review.get("decision"),
                "evidence": ";".join(review.get("evidence", [])),
                "rationale": review.get("rationale"),
            }
        )

    result = aggregate_council_decision(
        envelope,
        normalized,
        risk=envelope.get("proposal", {}).get("risk"),
        council_policy=council_policy,
        human_approval=human_approval,
    )
    result["bound_proposal_hash"] = envelope.get("proposal_hash")
    result["external_execution_authorized"] = False
    result["decision_hash"] = sha256_json({key: value for key, value in result.items() if key != "decision_hash"})
    return result
