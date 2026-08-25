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
    cluster_keywords,
    decision_receipt,
    plan_email_capture,
    propose_single_change,
    rank_opportunities,
    review_content,
    run_compounding_lane,
    run_fast_cash_lane,
    score_opportunity,
)
from .models import (
    ActionDecision,
    AffiliateProgram,
    ApprovedProgramSnapshot,
    CampaignAsset,
    CompoundingLaneResult,
    ContentDraft,
    DecisionReceipt,
    DraftInput,
    EmailCapturePlan,
    EvidenceState,
    FastCashCampaignPackage,
    KeywordCluster,
    KeywordEvidence,
    LearningProposal,
    MetricSnapshot,
    Opportunity,
    ProgramStatus,
    RevenueEvent,
    SitePlan,
)

__all__ = [
    "ActionDecision",
    "AffiliateProgram",
    "AffiliateRegistry",
    "ApprovedProgramSnapshot",
    "CampaignAsset",
    "CompoundingLaneResult",
    "ContentDraft",
    "DecisionReceipt",
    "DraftInput",
    "EmailCapturePlan",
    "EvidenceState",
    "FastCashCampaignPackage",
    "KeywordCluster",
    "KeywordEvidence",
    "LearningProposal",
    "MetricSnapshot",
    "Opportunity",
    "ProgramStatus",
    "RevenueEvent",
    "RevenueLedger",
    "SitePlan",
    "build_site_plan",
    "cluster_keywords",
    "decision_receipt",
    "plan_email_capture",
    "propose_single_change",
    "rank_opportunities",
    "review_content",
    "run_compounding_lane",
    "run_fast_cash_lane",
    "score_opportunity",
]
