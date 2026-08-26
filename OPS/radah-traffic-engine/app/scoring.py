from __future__ import annotations
from .models import OpportunityIn


def expected_rpv(o: OpportunityIn) -> float:
    return round(o.payout * o.conversion_rate, 4)


def opportunity_score(o: OpportunityIn) -> float:
    """
    Conservative economic ranking. This is advisory only.
    RADAH remains the sole authorization gate.
    """
    rpv = expected_rpv(o)
    revenue_score = min(10.0, rpv * 2.0)

    gross = (
        o.buyer_intent * 0.22 +
        o.demand * 0.17 +
        o.urgency * 0.15 +
        revenue_score * 0.18 +
        o.scalability * 0.11 +
        o.defensibility * 0.10 +
        o.execution_ease * 0.07
    )
    penalty = o.competition * 0.16
    return round(max(0.0, min(10.0, gross - penalty)), 3)


def recommendation(score: float) -> str:
    if score >= 7:
        return "ATTACK"
    if score >= 5:
        return "TEST"
    return "PASS"
