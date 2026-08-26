import os
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("API_KEY", "test-key")
os.environ.setdefault("AUDIT_HMAC_KEY", "test-audit-key")
os.environ.setdefault("RADAH_SHARED_SECRET", "test-radah-key")
os.environ.setdefault("REQUIRE_RADAH_SIGNATURE", "false")

from app.models import OpportunityIn
from app.scoring import expected_rpv, opportunity_score, recommendation


def sample(**overrides):
    data = dict(
        name="Healthcare Accessibility",
        slug="healthcare-accessibility",
        demand=8.5,
        buyer_intent=9.2,
        urgency=9.5,
        competition=5.5,
        scalability=9.0,
        defensibility=8.5,
        execution_ease=7.5,
        payout=400.0,
        conversion_rate=0.025,
    )
    data.update(overrides)
    return OpportunityIn(**data)


def test_expected_rpv():
    assert expected_rpv(sample()) == 10.0


def test_score_is_bounded():
    s = opportunity_score(sample())
    assert 0 <= s <= 10


def test_recommendation():
    assert recommendation(7.0) == "ATTACK"
    assert recommendation(5.0) == "TEST"
    assert recommendation(4.99) == "PASS"
