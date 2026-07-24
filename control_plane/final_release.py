"""Fail-closed final release evaluator with the Five Council as the last affirmative gate."""
from __future__ import annotations

from typing import Any

from .canonical import sha256_json

APPROVALS = {"APPROVE", "APPROVE_WITH_CONDITIONS"}


def _hash_without(record: dict[str, Any], field: str) -> str:
    return sha256_json({key: value for key, value in record.items() if key != field})


def evaluate_final_release(
    *,
    release_request: dict[str, Any],
    human_authorization: dict[str, Any],
    council_reviews: list[dict[str, Any]],
    final_release_policy: dict[str, Any],
    council_policy: dict[str, Any],
    activation_gates: dict[str, Any],
) -> dict[str, Any]:
    """Evaluate one release request without performing the released action."""
    if not isinstance(release_request, dict):
        raise TypeError("release_request must be an object")
    if not isinstance(human_authorization, dict):
        raise TypeError("human_authorization must be an object")
    if not isinstance(council_reviews, list):
        raise TypeError("council_reviews must be a list")

    errors: list[str] = []
    reasons: list[str] = []
    request_hash = _hash_without(release_request, "release_request_hash")
    if release_request.get("release_request_hash") != request_hash:
        errors.append("release_request_hash_mismatch")

    release_class = release_request.get("release_class")
    if release_class not in set(final_release_policy.get("consequential_release_classes", [])):
        errors.append("release_class_not_governed")

    readiness = release_request.get("technical_readiness")
    if not isinstance(readiness, dict) or readiness.get("ready") is not True:
        errors.append("technical_readiness_not_verified")
    else:
        reasons.append("technical_readiness_verified")

    approval_hash = _hash_without(human_authorization, "approval_hash")
    if human_authorization.get("approval_hash") != approval_hash:
        errors.append("human_authorization_hash_mismatch")
    if human_authorization.get("approved") is not True:
        errors.append("human_authorization_missing")
    if human_authorization.get("approver") != "human_overseer":
        errors.append("invalid_human_approver")
    if human_authorization.get("approval_id") != release_request.get("human_authorization_id"):
        errors.append("human_authorization_id_mismatch")
    if human_authorization.get("approval_hash") != release_request.get("human_authorization_hash"):
        errors.append("human_authorization_binding_mismatch")

    human_sequence = human_authorization.get("authorization_sequence")
    if not isinstance(human_sequence, int) or human_sequence < 1:
        errors.append("invalid_human_authorization_sequence")
    elif release_request.get("human_authorization_sequence") != human_sequence:
        errors.append("human_authorization_sequence_mismatch")
    elif not errors:
        reasons.append("human_scope_authorization_recorded")

    council_defs = council_policy.get("councils", [])
    expected_councils = {
        item.get("id")
        for item in council_defs
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    by_council: dict[str, dict[str, Any]] = {}
    vetoes: list[str] = []
    holds: list[str] = []
    approvals: list[str] = []
    conditions: set[str] = set()
    max_review_sequence = human_sequence if isinstance(human_sequence, int) else 0

    for review in council_reviews:
        if not isinstance(review, dict):
            errors.append("invalid_council_review")
            continue
        council_id = review.get("council_id")
        if council_id not in expected_councils:
            errors.append("unknown_council")
            continue
        if council_id in by_council:
            errors.append("duplicate_council_review")
            continue
        by_council[council_id] = review

        if review.get("review_hash") != _hash_without(review, "review_hash"):
            errors.append(f"review_hash_mismatch:{council_id}")
        if review.get("release_request_hash") != request_hash:
            errors.append(f"review_request_mismatch:{council_id}")
        if review.get("independent") is not True:
            errors.append(f"review_not_independent:{council_id}")

        review_sequence = review.get("review_sequence")
        if not isinstance(review_sequence, int) or not isinstance(human_sequence, int) or review_sequence <= human_sequence:
            errors.append(f"review_not_after_human_authorization:{council_id}")
        elif review_sequence > max_review_sequence:
            max_review_sequence = review_sequence

        decision = review.get("decision")
        if decision in APPROVALS:
            approvals.append(council_id)
        elif decision == "VETO":
            vetoes.append(council_id)
        elif decision == "HOLD":
            holds.append(council_id)
        else:
            errors.append(f"non_approving_final_review:{council_id}")

        for condition in review.get("conditions", []):
            if isinstance(condition, str) and condition:
                conditions.add(condition)

    missing_councils = sorted(expected_councils - set(by_council))
    if missing_councils:
        errors.append("missing_council_reviews")
    if vetoes:
        errors.append("council_veto")
    if holds:
        errors.append("council_hold")
    if set(approvals) != expected_councils:
        errors.append("unanimous_council_approval_not_met")

    if not errors:
        reasons.append("unanimous_final_council_approval")
        decision = "FINAL_RELEASE_APPROVED"
    elif vetoes:
        decision = "VETO"
    else:
        decision = "HOLD"

    external_execution_authorized = (
        decision == "FINAL_RELEASE_APPROVED"
        and release_request.get("external_effects") is True
        and activation_gates.get("external_execution_enabled") is True
    )
    trial_activation_authorized = (
        external_execution_authorized
        and release_request.get("release_class") == "trial_activation"
    )

    result = {
        "decision_id": f"final_decision_{release_request.get('release_request_id')}",
        "release_request_id": release_request.get("release_request_id"),
        "release_request_hash": request_hash,
        "human_authorization_id": human_authorization.get("approval_id"),
        "human_authorization_hash": human_authorization.get("approval_hash"),
        "human_authorization_sequence": human_sequence,
        "council_decision_sequence": max_review_sequence + 1,
        "decision": decision,
        "reasons": reasons,
        "errors": sorted(set(errors)),
        "approved_scope": release_request.get("scope") if decision == "FINAL_RELEASE_APPROVED" else None,
        "approvals": sorted(approvals),
        "vetoes": sorted(vetoes),
        "holds": sorted(holds),
        "missing_councils": missing_councils,
        "conditions": sorted(conditions),
        "trial_activation_authorized": trial_activation_authorized,
        "external_execution_authorized": external_execution_authorized,
        "final_affirmative_gate": final_release_policy.get("final_affirmative_gate"),
    }
    result["decision_hash"] = sha256_json(result)
    return result
