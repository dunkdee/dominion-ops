"""Dominion Revenue Engine — deterministic, evidence-bound revenue intelligence.

This package is intentionally simulation-only. It ranks opportunities, manages
affiliate evidence, drafts site architecture, reviews content, aggregates
revenue facts, and proposes one-variable learning changes. It performs no
network I/O and grants no production authority.
"""

from .engine import (
    AffiliateRegistry,
    RevenueLedger,
    build_site_plan,
    decision_receipt,
    propose_single_change,
    rank_opportunities,
    review_content,
    score_opportunity,
)
from .models import (
    AffiliateProgram,
    EvidenceState,
    Opportunity,
    ProgramStatus,
    RevenueEvent,
)

__all__ = [
    "AffiliateProgram",
    "AffiliateRegistry",
    "EvidenceState",
    "Opportunity",
    "ProgramStatus",
    "RevenueEvent",
    "RevenueLedger",
    "build_site_plan",
    "decision_receipt",
    "propose_single_change",
    "rank_opportunities",
    "review_content",
    "score_opportunity",
]
