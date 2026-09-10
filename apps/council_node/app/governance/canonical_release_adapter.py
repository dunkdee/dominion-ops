"""Bridge Council Node review state into Dominion's canonical final-release evaluator.

This module does not create approvals. It preserves Council order, validates reviewer
identity at the boundary, reports the next missing review, and delegates the final
release decision to ``control_plane.final_release.evaluate_final_release`` so Council
Node cannot become a second governance authority.
"""
from __future__ import annotations

from typing import Any

from control_plane.final_release import evaluate_final_release

COUNCIL_ORDER: tuple[str, ...] = (
    "truth_evidence",
    "law_governance",
    "security_risk",
    "engineering_reliability",
    "business_human_impact",
)


def ordered_missing_reviews(council_reviews: list[dict[str, Any]]) -> list[str]:
    """Return missing Council IDs in constitutional order.

    Duplicate or unknown identities are rejected instead of being silently accepted.
    """
    seen: set[str] = set()
    for review in council_reviews:
        council_id = review.get("council_id") if isinstance(review, dict) else None
        if council_id not in COUNCIL_ORDER:
            raise ValueError(f"unknown council identity: {council_id!r}")
        if council_id in seen:
            raise ValueError(f"duplicate council identity: {council_id}")
        seen.add(council_id)
    return [council_id for council_id in COUNCIL_ORDER if council_id not in seen]


def next_review_action(council_reviews: list[dict[str, Any]]) -> dict[str, Any]:
    """Describe the next governance action without fabricating a reviewer decision."""
    missing = ordered_missing_reviews(council_reviews)
    if missing:
        return {
            "status": "HOLD",
            "next_council": missing[0],
            "missing_councils": missing,
            "action": f"dispatch_independent_review:{missing[0]}",
        }
    return {
        "status": "READY_FOR_FINAL_EVALUATION",
        "next_council": None,
        "missing_councils": [],
        "action": "evaluate_canonical_final_release",
    }


def evaluate_canonical_release(
    *,
    release_request: dict[str, Any],
    human_authorization: dict[str, Any],
    council_reviews: list[dict[str, Any]],
    final_release_policy: dict[str, Any],
    council_policy: dict[str, Any],
    activation_gates: dict[str, Any],
) -> dict[str, Any]:
    """Run the one canonical final-release evaluator after ordered identity checks."""
    ordered_missing_reviews(council_reviews)
    return evaluate_final_release(
        release_request=release_request,
        human_authorization=human_authorization,
        council_reviews=council_reviews,
        final_release_policy=final_release_policy,
        council_policy=council_policy,
        activation_gates=activation_gates,
    )
