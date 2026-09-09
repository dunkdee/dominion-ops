from __future__ import annotations

import pytest

from apps.council_node.app.governance.canonical_release_adapter import (
    COUNCIL_ORDER,
    next_review_action,
    ordered_missing_reviews,
)


def _reviews(*councils: str) -> list[dict]:
    return [{"council_id": council_id} for council_id in councils]


def test_missing_reviews_follow_constitutional_order():
    reviews = _reviews("truth_evidence", "security_risk")
    assert ordered_missing_reviews(reviews) == [
        "law_governance",
        "engineering_reliability",
        "business_human_impact",
    ]


def test_next_action_dispatches_first_missing_council():
    action = next_review_action(_reviews("truth_evidence"))
    assert action["status"] == "HOLD"
    assert action["next_council"] == "law_governance"
    assert action["action"] == "dispatch_independent_review:law_governance"


def test_all_reviews_advance_to_canonical_final_evaluation():
    action = next_review_action(_reviews(*COUNCIL_ORDER))
    assert action == {
        "status": "READY_FOR_FINAL_EVALUATION",
        "next_council": None,
        "missing_councils": [],
        "action": "evaluate_canonical_final_release",
    }


def test_unknown_identity_fails_closed():
    with pytest.raises(ValueError, match="unknown council identity"):
        ordered_missing_reviews(_reviews("truth_evidence", "shadow_council"))


def test_duplicate_identity_fails_closed():
    with pytest.raises(ValueError, match="duplicate council identity"):
        ordered_missing_reviews(_reviews("truth_evidence", "truth_evidence"))
