from __future__ import annotations

import hashlib
import json
import re
from decimal import Decimal, ROUND_HALF_UP
from typing import Iterable

from .models import (
    AffiliateProgram,
    ContentReview,
    DecisionReceipt,
    EvidenceState,
    LearningProposal,
    MetricSnapshot,
    Opportunity,
    ProgramStatus,
    RevenueEvent,
    ScoredOpportunity,
    SitePage,
    SitePlan,
    normalize_evidence_refs,
)
from .policy import evaluate_action


_SCORE_QUANTUM = Decimal("0.01")
_RATE_QUANTUM = Decimal("0.0001")

_WEIGHTS = {
    "buyer_intent": Decimal("0.25"),
    "demand": Decimal("0.20"),
    "competition_inverse": Decimal("0.15"),
    "economics": Decimal("0.15"),
    "evidence": Decimal("0.10"),
    "zero_capital_fit": Decimal("0.10"),
    "original_value_fit": Decimal("0.05"),
}

_EVIDENCE_SCORE = {
    EvidenceState.VERIFIED: Decimal("1.0"),
    EvidenceState.INFERRED: Decimal("0.55"),
    EvidenceState.UNKNOWN: Decimal("0.0"),
}

_GUARANTEED_INCOME_PATTERNS = (
    re.compile(r"\bguaranteed?\s+(?:income|money|earnings?|profit|revenue)\b", re.I),
    re.compile(r"\byou\s+(?:will|cannot fail to)\s+(?:make|earn)\b", re.I),
    re.compile(r"\bcannot\s+lose\s+money\b", re.I),
)

_UNSUPPORTED_EXPERIENCE_PATTERNS = (
    re.compile(r"\b(?:we|i)\s+(?:personally\s+)?tested\b", re.I),
    re.compile(r"\b(?:we|i)\s+(?:personally\s+)?used\b", re.I),
    re.compile(r"\bour\s+hands[- ]on\s+test\b", re.I),
)


def _d(value: float) -> Decimal:
    return Decimal(str(value))


def score_opportunity(opportunity: Opportunity) -> ScoredOpportunity:
    components = {
        "buyer_intent": _d(opportunity.buyer_intent),
        "demand": _d(opportunity.demand),
        "competition_inverse": Decimal("1") - _d(opportunity.competition),
        "economics": _d(opportunity.economics),
        "evidence": _EVIDENCE_SCORE[opportunity.evidence_state],
        "zero_capital_fit": _d(opportunity.zero_capital_fit),
        "original_value_fit": _d(opportunity.original_value_fit),
    }
    raw = sum(components[key] * weight for key, weight in _WEIGHTS.items())
    score = (raw * Decimal("100")).quantize(_SCORE_QUANTUM, rounding=ROUND_HALF_UP)
    score = min(Decimal("100.00"), max(Decimal("0.00"), score))
    strongest = max(components, key=lambda key: (components[key], key))
    weakest = min(components, key=lambda key: (components[key], key))
    reason = (
        f"Strongest factor={strongest}; largest constraint={weakest}; "
        f"evidence={opportunity.evidence_state.value}."
    )
    return ScoredOpportunity(opportunity=opportunity, score=score, rank_reason=reason)


def rank_opportunities(opportunities: Iterable[Opportunity]) -> tuple[ScoredOpportunity, ...]:
    scored = [score_opportunity(item) for item in opportunities]
    evidence_priority = {
        EvidenceState.VERIFIED: 0,
        EvidenceState.INFERRED: 1,
        EvidenceState.UNKNOWN: 2,
    }
    return tuple(
        sorted(
            scored,
            key=lambda item: (
                -item.score,
                evidence_priority[item.opportunity.evidence_state],
                item.opportunity.opportunity_id,
            ),
        )
    )


class AffiliateRegistry:
    """In-memory evidence registry. It never enrolls programs or calls a network."""

    def __init__(self) -> None:
        self._programs: dict[str, AffiliateProgram] = {}

    def register(self, program: AffiliateProgram) -> None:
        self._programs[program.program_id] = program

    def get(self, program_id: str) -> AffiliateProgram:
        try:
            return self._programs[program_id]
        except KeyError as exc:
            raise KeyError(f"unknown affiliate program: {program_id}") from exc

    def approved_programs(self) -> tuple[AffiliateProgram, ...]:
        return tuple(
            sorted(
                (p for p in self._programs.values() if p.status is ProgramStatus.APPROVED),
                key=lambda p: p.program_id,
            )
        )

    def tracking_link(self, program_id: str) -> str:
        program = self.get(program_id)
        if program.status is not ProgramStatus.APPROVED:
            raise PermissionError("tracking link unavailable: program is not APPROVED")
        if program.evidence_state is not EvidenceState.VERIFIED:
            raise PermissionError("tracking link unavailable: approval is not VERIFIED")
        if not program.tracking_url or not program.terms_ref or not program.evidence_refs:
            raise PermissionError("tracking link unavailable: required approval evidence is incomplete")
        return program.tracking_url


def build_site_plan(
    opportunity: Opportunity,
    programs: Iterable[AffiliateProgram],
) -> SitePlan:
    if opportunity.evidence_state is EvidenceState.UNKNOWN:
        raise ValueError("site planning requires at least INFERRED opportunity evidence")
    approved = tuple(
        sorted(
            p.program_id
            for p in programs
            if p.status is ProgramStatus.APPROVED
            and p.evidence_state is EvidenceState.VERIFIED
            and p.tracking_url
            and p.terms_ref
            and p.evidence_refs
        )
    )
    if not approved:
        raise ValueError("site plan requires at least one VERIFIED approved affiliate program")

    evidence = opportunity.evidence_refs or ("source-required-before-publication",)
    pages = (
        SitePage("/", "home", "Explain the audience problem and route users to useful decision pages.", evidence),
        SitePage("/best/", "comparison", "Compare qualified options using explicit decision criteria.", evidence),
        SitePage("/reviews/", "review-index", "Index evidence-backed reviews without invented first-hand claims.", evidence),
        SitePage("/guides/", "supporting-guide", "Answer pre-purchase questions and build topical depth.", evidence),
        SitePage("/disclosure/", "disclosure", "Disclose affiliate relationships clearly and conspicuously.", evidence),
    )
    return SitePlan(
        opportunity_id=opportunity.opportunity_id,
        publication_state="DRAFT_SHADOW",
        affiliate_disclosure=(
            "Affiliate disclosure: this site may earn a commission when a reader purchases "
            "through qualifying links. Compensation does not change the evidence standard."
        ),
        pages=pages,
        approved_program_ids=approved,
    )


def review_content(
    text: str,
    *,
    evidence_refs: Iterable[str] = (),
    has_affiliate_links: bool = False,
    original_value_signals: Iterable[str] = (),
) -> ContentReview:
    text = text.strip()
    refs = normalize_evidence_refs(evidence_refs)
    value_signals = normalize_evidence_refs(original_value_signals)
    reasons: list[str] = []
    fixes: list[str] = []

    if not text:
        reasons.append("Empty content.")
        fixes.append("Provide substantive content.")
    if any(pattern.search(text) for pattern in _GUARANTEED_INCOME_PATTERNS):
        reasons.append("Guaranteed-income or no-loss claim detected.")
        fixes.append("Remove guaranteed-income/no-loss language and state uncertainty truthfully.")
    if any(pattern.search(text) for pattern in _UNSUPPORTED_EXPERIENCE_PATTERNS) and not refs:
        reasons.append("First-hand testing/use claim lacks evidence.")
        fixes.append("Attach evidence for the first-hand claim or rewrite it as sourced analysis.")
    if has_affiliate_links:
        lower = text.lower()
        if not ("affiliate" in lower and ("commission" in lower or "may earn" in lower)):
            reasons.append("Affiliate relationship is not clearly disclosed in the content.")
            fixes.append("Add a clear affiliate disclosure close to the recommendation/link.")
        if not value_signals:
            reasons.append("Affiliate content lacks declared original-value signals.")
            fixes.append(
                "Add measurable original value such as structured comparison criteria, "
                "source-backed analysis, original data, or verified hands-on evidence."
            )
    if not refs:
        reasons.append("No source/evidence references supplied.")
        fixes.append("Attach source/evidence references before publication review.")

    return ContentReview(
        allowed_for_draft=bool(text),
        allowed_for_publication=False,
        reasons=tuple(reasons) if reasons else ("Draft passes deterministic content checks.",),
        required_fixes=tuple(fixes),
    )


class RevenueLedger:
    """Idempotent in-memory event ledger. Events are facts supplied by upstream evidence sources."""

    def __init__(self) -> None:
        self._events: dict[str, RevenueEvent] = {}

    def ingest(self, event: RevenueEvent) -> bool:
        existing = self._events.get(event.event_id)
        if existing is None:
            self._events[event.event_id] = event
            return True
        if existing == event:
            return False
        raise ValueError("event_id collision: same id supplied with different facts")

    def metrics(self, opportunity_id: str) -> MetricSnapshot:
        events = [e for e in self._events.values() if e.opportunity_id == opportunity_id]
        impressions = sum(e.impressions for e in events)
        visits = sum(e.visits for e in events)
        clicks = sum(e.affiliate_clicks for e in events)
        conversions = sum(e.conversions for e in events)
        accrued = sum((e.commission_accrued for e in events), Decimal("0"))
        payout = sum((e.payout_received for e in events), Decimal("0"))

        def rate(numerator: int | Decimal, denominator: int) -> Decimal | None:
            if denominator == 0:
                return None
            return (Decimal(numerator) / Decimal(denominator)).quantize(_RATE_QUANTUM, rounding=ROUND_HALF_UP)

        states = {e.evidence_state for e in events}
        if events and states == {EvidenceState.VERIFIED}:
            evidence_state = EvidenceState.VERIFIED
        elif events and EvidenceState.UNKNOWN not in states:
            evidence_state = EvidenceState.INFERRED
        else:
            evidence_state = EvidenceState.UNKNOWN

        return MetricSnapshot(
            impressions=impressions,
            visits=visits,
            affiliate_clicks=clicks,
            conversions=conversions,
            commission_accrued=accrued,
            payout_received=payout,
            click_through_rate=rate(clicks, visits),
            conversion_rate=rate(conversions, clicks),
            earnings_per_click=rate(accrued, clicks),
            revenue_per_visit=rate(accrued, visits),
            evidence_state=evidence_state,
        )


def propose_single_change(metrics: MetricSnapshot) -> LearningProposal:
    """Choose one constraint only. This is a proposal, never an execution instruction."""
    if metrics.visits == 0:
        return LearningProposal(
            constraint="traffic",
            variable_to_change="distribution_channel_or_keyword_target",
            rationale="No visits are recorded; improve one acquisition variable before changing the offer.",
            evidence_state=metrics.evidence_state,
        )
    if metrics.affiliate_clicks == 0:
        return LearningProposal(
            constraint="click_intent",
            variable_to_change="primary_call_to_action",
            rationale="Visits exist but affiliate clicks do not; test one CTA variable.",
            evidence_state=metrics.evidence_state,
        )
    if metrics.conversions == 0:
        return LearningProposal(
            constraint="merchant_conversion",
            variable_to_change="recommended_offer",
            rationale="Clicks exist but conversions do not; test one offer while holding traffic/CTA constant.",
            evidence_state=metrics.evidence_state,
        )
    if metrics.payout_received == Decimal("0"):
        return LearningProposal(
            constraint="cash_realization",
            variable_to_change="payout_reconciliation",
            rationale="Conversions/commissions exist without received payout; reconcile before scaling.",
            evidence_state=metrics.evidence_state,
        )
    return LearningProposal(
        constraint="scale_after_proof",
        variable_to_change="winning_distribution_input",
        rationale="Verified cash is the next gate; scale only one proven acquisition input and re-measure.",
        evidence_state=metrics.evidence_state,
    )


def decision_receipt(action: str, evidence_refs: Iterable[str] = ()) -> DecisionReceipt:
    refs = normalize_evidence_refs(evidence_refs)
    policy = evaluate_action(action, refs)
    canonical = json.dumps(
        {
            "action": policy.action,
            "decision": policy.decision.value,
            "reason": policy.reason,
            "evidence_refs": list(policy.evidence_refs),
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return DecisionReceipt(
        action=policy.action,
        decision=policy.decision,
        reason=policy.reason,
        evidence_refs=policy.evidence_refs,
        receipt_sha256=digest,
    )
