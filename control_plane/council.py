"""Independent Five Council review aggregation."""

from __future__ import annotations

from typing import Any

from .canonical import sha256_json

APPROVALS = {"APPROVE", "APPROVE_WITH_CONDITIONS"}
VALID_STATES = APPROVALS | {"VETO", "HOLD", "ABSTAIN"}


class CouncilError(ValueError):
    """Raised when council records are malformed or inconsistent."""


def aggregate_council_decision(
    proposal: dict[str, Any],
    reviews: list[dict[str, Any]],
    *,
    risk: str,
    council_policy: dict[str, Any],
    human_approval: dict[str, Any] | None = None,
) -> dict[str, Any]:
    proposal_hash = sha256_json(proposal)
    council_defs = council_policy.get("councils", [])
    known_councils = {item.get("id"): item for item in council_defs if isinstance(item, dict)}
    threshold = council_policy.get("thresholds", {}).get(risk)
    if not isinstance(threshold, dict):
        raise CouncilError(f"unknown risk threshold: {risk}")

    by_council: dict[str, dict[str, Any]] = {}
    for review in reviews:
        if not isinstance(review, dict):
            raise CouncilError("each review must be an object")
        council_id = review.get("council_id")
        if council_id not in known_councils:
            raise CouncilError(f"unknown council: {council_id}")
        if council_id in by_council:
            raise CouncilError(f"duplicate council review: {council_id}")
        if review.get("proposal_hash") != proposal_hash:
            raise CouncilError(f"proposal hash mismatch for council: {council_id}")
        if review.get("decision") not in VALID_STATES:
            raise CouncilError(f"invalid decision for council: {council_id}")
        if not review.get("evidence"):
            raise CouncilError(f"missing evidence for council: {council_id}")
        if not review.get("rationale"):
            raise CouncilError(f"missing rationale for council: {council_id}")
        by_council[council_id] = review

    vetoes = sorted(council_id for council_id, review in by_council.items() if known_councils[council_id].get("veto") is True and review.get("decision") == "VETO")
    holds = sorted(council_id for council_id, review in by_council.items() if review.get("decision") == "HOLD")
    approvals = sorted(council_id for council_id, review in by_council.items() if review.get("decision") in APPROVALS)
    required = int(threshold.get("required_approvals", 0))
    missing_councils = sorted(set(known_councils) - set(by_council))

    if vetoes:
        final_state = "VETO"
        reasons = ["independent_veto"]
    elif holds:
        final_state = "HOLD"
        reasons = ["council_hold"]
    elif len(approvals) < required:
        final_state = "HOLD"
        reasons = ["approval_threshold_not_met"]
    elif threshold.get("human_required") is True and not (isinstance(human_approval, dict) and human_approval.get("approved") is True and human_approval.get("approver") == "human_overseer" and human_approval.get("evidence")):
        final_state = "HOLD"
        reasons = ["human_approval_required"]
    else:
        final_state = "APPROVE"
        reasons = ["council_threshold_met"]

    result = {
        "proposal_hash": proposal_hash,
        "risk": risk,
        "decision": final_state,
        "reasons": reasons,
        "approvals": approvals,
        "vetoes": vetoes,
        "holds": holds,
        "missing_councils": missing_councils,
        "required_approvals": required,
        "human_approval_recorded": bool(isinstance(human_approval, dict) and human_approval.get("approved") is True),
        "reviews": [by_council[key] for key in sorted(by_council)],
    }
    result["decision_hash"] = sha256_json(result)
    return result
