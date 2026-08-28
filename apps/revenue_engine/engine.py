from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Iterable

from .models import (
    AffiliateProgram,
    ApprovedProgramSnapshot,
    CampaignAsset,
    CompoundingLaneResult,
    ContentDraft,
    ContentReview,
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
    ScoredOpportunity,
    SitePage,
    SitePlan,
    _normalize_str_tuple,
    normalize_evidence_refs,
)
from .policy import evaluate_action


_SCORE_QUANTUM = Decimal("0.01")
_RATE_QUANTUM = Decimal("0.0001")
_CLOCK_SKEW_SECONDS = 300  # allowance for future-dated verified_at

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


# ---------------------------------------------------------------------------
# SHA-256 helpers
# ---------------------------------------------------------------------------

def _sha256_of(payload: object) -> str:
    """Deterministic SHA-256 of a JSON-serializable payload. allow_nan=False
    ensures unexpected float values raise TypeError rather than silently
    serializing as non-standard JSON."""
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _tracking_id_of(
    asset_id: str,
    opportunity_id: str,
    channel: str,
    proposed_text: str,
    cta: str,
    affiliate_program_id: str | None,
) -> str:
    """16-hex tracking ID unique per distinct draft (includes text+CTA+affiliate
    to prevent collision when multiple drafts share asset+opportunity+channel)."""
    return _sha256_of({
        "affiliate_program_id": affiliate_program_id,
        "asset_id": asset_id,
        "channel": channel,
        "cta": cta,
        "opportunity_id": opportunity_id,
        "proposed_text": proposed_text,
    })[:16]


def _d(value: float) -> Decimal:
    return Decimal(str(value))


# ---------------------------------------------------------------------------
# Opportunity scoring and ranking
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Affiliate registry
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Site plan builder
# ---------------------------------------------------------------------------

def build_site_plan(
    opportunity: Opportunity,
    programs: Iterable[AffiliateProgram],
) -> SitePlan:
    if opportunity.evidence_state is EvidenceState.UNKNOWN:
        raise ValueError("site planning requires at least INFERRED opportunity evidence")

    programs_tuple = tuple(programs)

    # Reject duplicate program IDs before building
    program_ids = [p.program_id for p in programs_tuple]
    if len(program_ids) != len(set(program_ids)):
        dupes = sorted({pid for pid in program_ids if program_ids.count(pid) > 1})
        raise ValueError(f"duplicate program_ids in programs: {dupes}")

    approved = tuple(
        sorted(
            p.program_id
            for p in programs_tuple
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


# ---------------------------------------------------------------------------
# Content review
# ---------------------------------------------------------------------------

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
    # draft_blocking: violations that prevent even a DRAFT_SHADOW from being created.
    # publication_only: problems that must be resolved before publication, but do not
    #                   block the draft itself.
    draft_blocking: list[str] = []
    publication_only: list[str] = []

    if not text:
        reasons.append("Empty content.")
        draft_blocking.append("Provide substantive content.")
    if any(pattern.search(text) for pattern in _GUARANTEED_INCOME_PATTERNS):
        reasons.append("Guaranteed-income or no-loss claim detected.")
        draft_blocking.append("Remove guaranteed-income/no-loss language and state uncertainty truthfully.")
    if any(pattern.search(text) for pattern in _UNSUPPORTED_EXPERIENCE_PATTERNS) and not refs:
        reasons.append("First-hand testing/use claim lacks evidence.")
        draft_blocking.append("Attach evidence for the first-hand claim or rewrite it as sourced analysis.")
    if has_affiliate_links:
        lower = text.lower()
        if not ("affiliate" in lower and ("commission" in lower or "may earn" in lower)):
            reasons.append("Affiliate relationship is not clearly disclosed in the content.")
            publication_only.append("Add a clear affiliate disclosure close to the recommendation/link.")
        if not value_signals:
            reasons.append("Affiliate content lacks declared original-value signals.")
            publication_only.append(
                "Add measurable original value such as structured comparison criteria, "
                "source-backed analysis, original data, or verified hands-on evidence."
            )
    if not refs:
        reasons.append("No source/evidence references supplied.")
        publication_only.append("Attach source/evidence references before publication review.")

    return ContentReview(
        allowed_for_draft=bool(text) and not draft_blocking,
        allowed_for_publication=False,
        reasons=tuple(reasons) if reasons else ("Draft passes deterministic content checks.",),
        required_fixes=tuple(draft_blocking + publication_only),
    )


# ---------------------------------------------------------------------------
# Revenue ledger
# ---------------------------------------------------------------------------

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

        # Collect all evidence refs from events
        all_refs = normalize_evidence_refs(ref for e in events for ref in e.evidence_refs)

        return MetricSnapshot(
            opportunity_id=opportunity_id,
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
            evidence_refs=all_refs,
        )

    def first_verified_revenue(self, opportunity_id: str) -> RevenueEvent | None:
        """Return the earliest verified revenue event with a known timestamp.

        Excludes events without event_timestamp (timestamp ordering would be
        untrustworthy). Sorted by parsed UTC datetime, then event_id as tiebreaker.
        """
        qualifying = [
            e for e in self._events.values()
            if e.opportunity_id == opportunity_id
            and e.payout_received > Decimal("0")
            and e.evidence_state is EvidenceState.VERIFIED
            and bool(e.evidence_refs)
            and bool(e.event_timestamp)
        ]
        if not qualifying:
            return None
        return min(
            qualifying,
            key=lambda e: (datetime.fromisoformat(e.event_timestamp), e.event_id),
        )


# ---------------------------------------------------------------------------
# Learning proposal
# ---------------------------------------------------------------------------

def propose_single_change(metrics: MetricSnapshot) -> LearningProposal:
    """Choose one constraint only. This is a proposal, never an execution instruction."""
    refs = normalize_evidence_refs(metrics.evidence_refs)
    if metrics.visits == 0:
        return LearningProposal(
            constraint="traffic",
            variable_to_change="distribution_channel_or_keyword_target",
            rationale="No visits are recorded; improve one acquisition variable before changing the offer.",
            evidence_state=metrics.evidence_state,
            evidence_refs=refs,
        )
    if metrics.affiliate_clicks == 0:
        return LearningProposal(
            constraint="click_intent",
            variable_to_change="primary_call_to_action",
            rationale="Visits exist but affiliate clicks do not; test one CTA variable.",
            evidence_state=metrics.evidence_state,
            evidence_refs=refs,
        )
    if metrics.conversions == 0:
        return LearningProposal(
            constraint="merchant_conversion",
            variable_to_change="recommended_offer",
            rationale="Clicks exist but conversions do not; test one offer while holding traffic/CTA constant.",
            evidence_state=metrics.evidence_state,
            evidence_refs=refs,
        )
    if metrics.payout_received == Decimal("0"):
        return LearningProposal(
            constraint="cash_realization",
            variable_to_change="payout_reconciliation",
            rationale="Conversions/commissions exist without received payout; reconcile before scaling.",
            evidence_state=metrics.evidence_state,
            evidence_refs=refs,
        )
    return LearningProposal(
        constraint="scale_after_proof",
        variable_to_change="winning_distribution_input",
        rationale="Verified cash is the next gate; scale only one proven acquisition input and re-measure.",
        evidence_state=metrics.evidence_state,
        evidence_refs=refs,
    )


# ---------------------------------------------------------------------------
# Decision receipt (policy gateway)
# ---------------------------------------------------------------------------

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
        allow_nan=False,
    )
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return DecisionReceipt(
        action=policy.action,
        decision=policy.decision,
        reason=policy.reason,
        evidence_refs=policy.evidence_refs,
        receipt_sha256=digest,
    )


# ---------------------------------------------------------------------------
# Keyword clustering (COMPOUNDING lane input stage)
# ---------------------------------------------------------------------------

def cluster_keywords(
    evidence_items: Iterable[KeywordEvidence],
    as_of: datetime | None = None,
) -> tuple[KeywordCluster, ...]:
    """Convert KeywordEvidence records into KeywordCluster objects.

    Validates freshness at as_of (defaults to now UTC). Rejects stale evidence.
    Preserves verified_at and ttl_seconds from evidence into each cluster.
    _CLOCK_SKEW_SECONDS allows for evidence dated slightly in the future.
    """
    if as_of is None:
        as_of = datetime.now(timezone.utc)
    elif as_of.tzinfo is None:
        raise ValueError("as_of must be timezone-aware")

    clusters: list[KeywordCluster] = []
    for ev in evidence_items:
        if ev.evidence_state is not EvidenceState.VERIFIED:
            raise ValueError(
                f"keyword evidence for {ev.cluster_id!r} must be VERIFIED; "
                f"got {ev.evidence_state.value}"
            )
        verified_dt = datetime.fromisoformat(ev.verified_at)
        expires_at = verified_dt + timedelta(seconds=ev.ttl_seconds)
        # Reject future-dated evidence (beyond clock skew allowance)
        if verified_dt > as_of + timedelta(seconds=_CLOCK_SKEW_SECONDS):
            raise ValueError(
                f"KeywordEvidence for cluster {ev.cluster_id!r} is future-dated: "
                f"verified_at={ev.verified_at}, as_of={as_of.isoformat()}"
            )
        # Reject stale evidence
        if as_of > expires_at + timedelta(seconds=_CLOCK_SKEW_SECONDS):
            raise ValueError(
                f"KeywordEvidence for cluster {ev.cluster_id!r} is stale: "
                f"expired at {expires_at.isoformat()}, as_of={as_of.isoformat()}"
            )
        clusters.append(
            KeywordCluster(
                cluster_id=ev.cluster_id,
                head_term=ev.head_term,
                variants=ev.variants,
                buyer_intent_score=ev.buyer_intent_score,
                evidence_state=EvidenceState.VERIFIED,
                evidence_refs=ev.evidence_refs,
                verified_at=ev.verified_at,
                ttl_seconds=ev.ttl_seconds,
            )
        )
    return tuple(clusters)


# ---------------------------------------------------------------------------
# Email capture plan builder (COMPOUNDING lane)
# ---------------------------------------------------------------------------

def plan_email_capture(
    opportunity: Opportunity,
    consent_mechanism: str,
    value_exchange: str,
) -> EmailCapturePlan:
    """Build a consent-based email capture plan. Always DRAFT_SHADOW.
    plan_id is a deterministic SHA-256 of the canonical plan payload.
    """
    consent_mechanism = consent_mechanism.strip()
    value_exchange = value_exchange.strip()
    if not consent_mechanism:
        raise ValueError("consent_mechanism is required")
    if not value_exchange:
        raise ValueError("value_exchange is required")
    if not opportunity.evidence_refs:
        raise ValueError("plan_email_capture requires opportunity with evidence_refs")

    payload = {
        "consent_mechanism": consent_mechanism,
        "evidence_refs": sorted(opportunity.evidence_refs),
        "opportunity_id": opportunity.opportunity_id,
        "value_exchange": value_exchange,
    }
    plan_id = _sha256_of(payload)

    return EmailCapturePlan(
        plan_id=plan_id,
        opportunity_id=opportunity.opportunity_id,
        consent_mechanism=consent_mechanism,
        value_exchange=value_exchange,
        evidence_refs=opportunity.evidence_refs,
        publication_state="DRAFT_SHADOW",
    )


# ---------------------------------------------------------------------------
# FAST CASH lane orchestrator
# ---------------------------------------------------------------------------

def _build_approved_snapshot(program: AffiliateProgram) -> ApprovedProgramSnapshot:
    """Build an ApprovedProgramSnapshot from a fully qualified AffiliateProgram.
    Raises ValueError/PermissionError if program does not meet snapshot requirements.
    """
    if program.status is not ProgramStatus.APPROVED:
        raise ValueError(
            f"affiliate program {program.program_id!r} must be APPROVED; "
            f"got {program.status.value}"
        )
    if program.evidence_state is not EvidenceState.VERIFIED:
        raise ValueError(
            f"affiliate program {program.program_id!r} must be VERIFIED; "
            f"got {program.evidence_state.value}"
        )
    if not program.evidence_refs:
        raise ValueError(
            f"affiliate program {program.program_id!r} requires evidence_refs"
        )
    if not program.terms_ref or not program.terms_ref.strip():
        raise ValueError(
            f"affiliate program {program.program_id!r} requires nonempty terms_ref"
        )
    if not program.tracking_url or not program.tracking_url.strip():
        raise ValueError(
            f"affiliate program {program.program_id!r} requires nonempty tracking_url"
        )
    return ApprovedProgramSnapshot(
        program_id=program.program_id,
        status=program.status,
        evidence_state=program.evidence_state,
        evidence_refs=program.evidence_refs,
        terms_ref=program.terms_ref,
        tracking_url=program.tracking_url,
        restrictions=program.restrictions,
    )


def run_fast_cash_lane(
    opportunity: Opportunity,
    assets: Iterable[CampaignAsset],
    draft_inputs: Iterable[DraftInput],
    programs: Iterable[AffiliateProgram],
) -> FastCashCampaignPackage:
    """FAST CASH lane: score opportunity, review content, build governed draft package.

    Never publishes, never contacts merchants, never spends money.
    All output is DRAFT_SHADOW.
    """
    if opportunity.evidence_state is not EvidenceState.VERIFIED:
        raise ValueError(
            f"FAST CASH lane requires a VERIFIED opportunity; "
            f"got {opportunity.evidence_state.value}"
        )
    assets_tuple = tuple(assets)
    inputs_tuple = tuple(draft_inputs)
    programs_tuple = tuple(programs)

    # Index programs by ID for affiliate lookup
    program_map: dict[str, AffiliateProgram] = {p.program_id: p for p in programs_tuple}

    # Index assets by ID
    asset_map: dict[str, CampaignAsset] = {a.asset_id: a for a in assets_tuple}

    # Collect opportunity evidence for analyze_funnel receipt
    opp_evidence_refs = opportunity.evidence_refs

    # Collect all restriction strings from assets and programs (deduplicated)
    restriction_set: set[str] = set()
    for asset in assets_tuple:
        for r in asset.restrictions:
            restriction_set.add(r.strip())
    for prog in programs_tuple:
        for r in prog.restrictions:
            restriction_set.add(r.strip())
    restriction_set.discard("")
    restrictions_held = tuple(sorted(restriction_set))

    # Build analyze_funnel receipt (opportunity evidence)
    analyze_refs = normalize_evidence_refs(list(opp_evidence_refs))
    analyze_receipt = decision_receipt("analyze_funnel", analyze_refs)

    # Build all drafts
    built_drafts: list[ContentDraft] = []
    approved_snapshots: dict[str, ApprovedProgramSnapshot] = {}
    draft_offer_refs_accumulator: list[str] = []

    for inp in inputs_tuple:
        # Resolve asset
        if inp.asset_id not in asset_map:
            raise ValueError(f"DraftInput references unknown asset_id {inp.asset_id!r}")
        asset = asset_map[inp.asset_id]

        # Affiliate program validation
        affiliate_snapshot: ApprovedProgramSnapshot | None = None
        affiliate_evidence_refs: tuple[str, ...] = ()
        affiliate_terms_ref: str | None = None

        if inp.has_affiliate_links:
            if inp.affiliate_program_id not in program_map:
                raise ValueError(
                    f"DraftInput affiliate_program_id {inp.affiliate_program_id!r} "
                    f"not found in programs"
                )
            prog = program_map[inp.affiliate_program_id]
            affiliate_snapshot = _build_approved_snapshot(prog)
            approved_snapshots[prog.program_id] = affiliate_snapshot
            affiliate_evidence_refs = prog.evidence_refs
            affiliate_terms_ref = prog.terms_ref

        # Merge evidence refs: asset + affiliate program
        merged_refs = normalize_evidence_refs(
            list(asset.evidence_refs) + list(affiliate_evidence_refs)
        )

        # Content review gate — use allowed_for_draft
        review = review_content(
            inp.proposed_text,
            evidence_refs=merged_refs,
            has_affiliate_links=inp.has_affiliate_links,
            original_value_signals=inp.original_value_signals,
        )
        if not review.allowed_for_draft:
            raise ValueError(
                f"Content review blocked draft for asset {inp.asset_id!r}: "
                f"{'; '.join(review.reasons)}"
            )

        # Deterministic tracking ID (unique per distinct draft)
        tracking_id = _tracking_id_of(
            asset_id=inp.asset_id,
            opportunity_id=opportunity.opportunity_id,
            channel=inp.channel,
            proposed_text=inp.proposed_text,
            cta=inp.cta,
            affiliate_program_id=inp.affiliate_program_id,
        )

        # Build draft payload for SHA-256
        draft_payload = {
            "affiliate_program_id": inp.affiliate_program_id,
            "affiliate_terms_ref": affiliate_terms_ref,
            "asset_id": asset.asset_id,
            "buyer_intent_cta": inp.cta,
            "channel": inp.channel,
            "evidence_refs": sorted(merged_refs),
            "has_affiliate_links": inp.has_affiliate_links,
            "measurement_dimensions": sorted(inp.measurement_dimensions),
            "opportunity_id": opportunity.opportunity_id,
            "original_value_signals": sorted(inp.original_value_signals),
            "publication_state": "DRAFT_SHADOW",
            "short_form_text": inp.proposed_text,
            "tracking_id": tracking_id,
        }
        draft_id = _sha256_of(draft_payload)

        draft = ContentDraft(
            draft_id=draft_id,
            asset_id=asset.asset_id,
            opportunity_id=opportunity.opportunity_id,
            channel=inp.channel,
            short_form_text=inp.proposed_text,
            buyer_intent_cta=inp.cta,
            tracking_id=tracking_id,
            measurement_dimensions=inp.measurement_dimensions,
            evidence_refs=merged_refs,
            publication_state="DRAFT_SHADOW",
            has_affiliate_links=inp.has_affiliate_links,
            affiliate_program_id=inp.affiliate_program_id,
            affiliate_terms_ref=affiliate_terms_ref,
            affiliate_evidence_refs=affiliate_evidence_refs,
            original_value_signals=inp.original_value_signals,
        )
        built_drafts.append(draft)

        # Accumulate approved-program evidence + terms_refs for draft_offer receipt
        if inp.has_affiliate_links and affiliate_snapshot:
            draft_offer_refs_accumulator.extend(affiliate_snapshot.evidence_refs)
            draft_offer_refs_accumulator.append(affiliate_snapshot.terms_ref)

    # draft_offer receipt: approved-program evidence_refs + terms_refs
    draft_offer_refs = normalize_evidence_refs(draft_offer_refs_accumulator)
    draft_offer_receipt = decision_receipt("draft_offer", draft_offer_refs)

    # Package receipts
    receipts = (analyze_receipt, draft_offer_receipt)

    # Package SHA-256 covering all security-relevant fields
    snap_list = sorted(
        [
            {
                "evidence_refs": sorted(s.evidence_refs),
                "evidence_state": s.evidence_state.value,
                "program_id": s.program_id,
                "restrictions": sorted(s.restrictions),
                "status": s.status.value,
                "terms_ref": s.terms_ref,
                "tracking_url": s.tracking_url,
            }
            for s in approved_snapshots.values()
        ],
        key=lambda x: x["program_id"],
    )
    package_payload = {
        "approved_program_snapshots": snap_list,
        "assets": sorted(
            [
                {
                    "asset_id": a.asset_id,
                    "evidence_refs": sorted(a.evidence_refs),
                    "evidence_state": a.evidence_state.value,
                    "title": a.title,
                }
                for a in assets_tuple
            ],
            key=lambda x: x["asset_id"],
        ),
        "decision_receipts": [r.receipt_sha256 for r in receipts],
        "drafts": sorted(d.draft_id for d in built_drafts),
        "opportunity_id": opportunity.opportunity_id,
        "publication_state": "DRAFT_SHADOW",
        "restrictions_held_for_review": sorted(restrictions_held),
        "review_hold": bool(restrictions_held),
    }
    package_sha256 = _sha256_of(package_payload)
    package_id = package_sha256[:16]

    return FastCashCampaignPackage(
        package_id=package_id,
        opportunity_id=opportunity.opportunity_id,
        assets=assets_tuple,
        drafts=tuple(built_drafts),
        measurement_definitions=tuple(
            dict.fromkeys(dim for inp in inputs_tuple for dim in inp.measurement_dimensions)
        ),
        publication_state="DRAFT_SHADOW",
        package_sha256=package_sha256,
        decision_receipts=receipts,
        restrictions_held_for_review=restrictions_held,
        approved_program_snapshots=tuple(
            sorted(approved_snapshots.values(), key=lambda s: s.program_id)
        ),
    )


# ---------------------------------------------------------------------------
# COMPOUNDING lane orchestrator
# ---------------------------------------------------------------------------

def run_compounding_lane(
    opportunity: Opportunity,
    keyword_evidence: Iterable[KeywordEvidence],
    programs: Iterable[AffiliateProgram],
    consent_mechanism: str,
    value_exchange: str,
    prior_metrics: MetricSnapshot | None = None,
    as_of: datetime | None = None,
) -> CompoundingLaneResult:
    """COMPOUNDING lane: keyword clustering → site plan → email capture → learning proposal.

    Never publishes, never contacts affiliates, never spends money.
    All output is DRAFT_SHADOW.

    prior_metrics: if provided, must match opportunity_id, be non-UNKNOWN,
                   have nonempty evidence_refs. Generates learning proposal
                   and measure_metrics receipt. If None: no proposal, no
                   measure_metrics receipt.
    """
    # Cluster keywords
    clusters = cluster_keywords(keyword_evidence, as_of=as_of)
    if not clusters:
        raise ValueError("run_compounding_lane requires at least one KeywordEvidence item")

    # Validate prior_metrics scope and state
    resolved_metrics: MetricSnapshot | None = None
    if prior_metrics is not None:
        if prior_metrics.opportunity_id != opportunity.opportunity_id:
            raise ValueError(
                f"prior_metrics.opportunity_id {prior_metrics.opportunity_id!r} "
                f"does not match opportunity {opportunity.opportunity_id!r}"
            )
        if prior_metrics.evidence_state is not EvidenceState.VERIFIED:
            raise ValueError(
                "prior_metrics.evidence_state must be VERIFIED; "
                f"got {prior_metrics.evidence_state.value}"
            )
        if not prior_metrics.evidence_refs:
            raise ValueError("prior_metrics must have nonempty evidence_refs")
        resolved_metrics = prior_metrics

    # Build site plan (also rejects duplicate program IDs)
    programs_tuple = tuple(programs)
    site_plan = build_site_plan(opportunity, programs_tuple)

    # Build approved program snapshots with exact coverage of site_plan.approved_program_ids
    program_map = {p.program_id: p for p in programs_tuple}
    approved_snapshots: list[ApprovedProgramSnapshot] = []
    for pid in site_plan.approved_program_ids:
        prog = program_map[pid]
        approved_snapshots.append(_build_approved_snapshot(prog))
    approved_snapshots_tuple = tuple(
        sorted(approved_snapshots, key=lambda s: s.program_id)
    )

    # Collect restrictions from programs
    restriction_set: set[str] = set()
    for prog in programs_tuple:
        for r in prog.restrictions:
            restriction_set.add(r.strip())
    restriction_set.discard("")
    restrictions_held = tuple(sorted(restriction_set))

    # Build email capture plan
    email_plan = plan_email_capture(opportunity, consent_mechanism, value_exchange)

    # Collect evidence refs
    keyword_evidence_refs = normalize_evidence_refs(
        ref for c in clusters for ref in c.evidence_refs
    )
    approved_program_evidence_refs = normalize_evidence_refs(
        ref for s in approved_snapshots_tuple for ref in s.evidence_refs
    )
    approved_terms_refs = normalize_evidence_refs(
        s.terms_ref for s in approved_snapshots_tuple if s.terms_ref
    )

    # Learning proposal and measure_metrics receipt — only when metrics present
    learning_proposal: LearningProposal | None = None
    measure_metrics_receipt: DecisionReceipt | None = None

    if resolved_metrics is not None:
        learning_proposal = propose_single_change(resolved_metrics)
        measure_refs = normalize_evidence_refs(list(resolved_metrics.evidence_refs))
        measure_metrics_receipt = decision_receipt("measure_metrics", measure_refs)

    # analyze_funnel receipt: opportunity + keyword evidence
    analyze_refs = normalize_evidence_refs(
        list(opportunity.evidence_refs) + list(keyword_evidence_refs)
    )
    analyze_receipt = decision_receipt("analyze_funnel", analyze_refs)

    # draft_offer receipt: approved-program evidence + terms_refs + email + keyword
    draft_offer_refs = normalize_evidence_refs(
        list(approved_program_evidence_refs)
        + list(approved_terms_refs)
        + list(email_plan.evidence_refs)
        + list(keyword_evidence_refs)
    )
    draft_offer_receipt = decision_receipt("draft_offer", draft_offer_refs)

    # prepare_experiment receipt: all combined
    prepare_refs = normalize_evidence_refs(
        list(opportunity.evidence_refs)
        + list(keyword_evidence_refs)
        + list(approved_program_evidence_refs)
        + list(approved_terms_refs)
        + list(email_plan.evidence_refs)
        + (list(resolved_metrics.evidence_refs) if resolved_metrics else [])
    )
    prepare_receipt = decision_receipt("prepare_experiment", prepare_refs)

    # Assemble receipts tuple
    receipts_list: list[DecisionReceipt] = [analyze_receipt, draft_offer_receipt, prepare_receipt]
    if measure_metrics_receipt is not None:
        receipts_list.append(measure_metrics_receipt)
    receipts = tuple(receipts_list)

    # Result SHA-256 covering all security-relevant fields
    snap_list = sorted(
        [
            {
                "evidence_refs": sorted(s.evidence_refs),
                "evidence_state": s.evidence_state.value,
                "program_id": s.program_id,
                "restrictions": sorted(s.restrictions),
                "status": s.status.value,
                "terms_ref": s.terms_ref,
                "tracking_url": s.tracking_url,
            }
            for s in approved_snapshots_tuple
        ],
        key=lambda x: x["program_id"],
    )
    result_payload = {
        "approved_program_snapshots": snap_list,
        "decision_receipts": [r.receipt_sha256 for r in receipts],
        "email_capture_plan_id": email_plan.plan_id,
        "keyword_clusters": sorted(
            [
                {
                    "cluster_id": c.cluster_id,
                    "evidence_refs": sorted(c.evidence_refs),
                    "evidence_state": c.evidence_state.value,
                    "head_term": c.head_term,
                    "ttl_seconds": c.ttl_seconds,
                    "variants": sorted(c.variants),
                    "verified_at": c.verified_at,
                }
                for c in clusters
            ],
            key=lambda x: x["cluster_id"],
        ),
        "learning_proposal_constraint": learning_proposal.constraint if learning_proposal else None,
        "opportunity_id": opportunity.opportunity_id,
        "prior_metrics_digest": {
            "affiliate_clicks": resolved_metrics.affiliate_clicks,
            "commission_accrued": str(resolved_metrics.commission_accrued),
            "conversions": resolved_metrics.conversions,
            "earnings_per_click": str(resolved_metrics.earnings_per_click),
            "evidence_refs": sorted(resolved_metrics.evidence_refs),
            "evidence_state": resolved_metrics.evidence_state.value,
            "impressions": resolved_metrics.impressions,
            "opportunity_id": resolved_metrics.opportunity_id,
            "payout_received": str(resolved_metrics.payout_received),
            "revenue_per_visit": str(resolved_metrics.revenue_per_visit),
            "visits": resolved_metrics.visits,
        } if resolved_metrics is not None else None,
        "publication_state": "DRAFT_SHADOW",
        "restrictions_held_for_review": sorted(restrictions_held),
        "review_hold": bool(restrictions_held),
        "site_plan_opportunity_id": site_plan.opportunity_id,
    }
    result_sha256 = _sha256_of(result_payload)

    return CompoundingLaneResult(
        opportunity_id=opportunity.opportunity_id,
        keyword_clusters=clusters,
        site_plan=site_plan,
        email_capture_plan=email_plan,
        learning_proposal=learning_proposal,
        publication_state="DRAFT_SHADOW",
        result_sha256=result_sha256,
        decision_receipts=receipts,
        approved_program_snapshots=approved_snapshots_tuple,
        restrictions_held_for_review=restrictions_held,
    )
