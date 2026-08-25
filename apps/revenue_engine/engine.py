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
    normalize_evidence_refs,
)
from .policy import evaluate_action


_SCORE_QUANTUM = Decimal("0.01")
_RATE_QUANTUM = Decimal("0.0001")
_CLOCK_SKEW_SECONDS = 300

_STANDARD_MEASUREMENT_DIMENSIONS = (
    "impressions",
    "visits",
    "affiliate_clicks",
    "conversions",
    "commission_accrued",
    "payout_received",
)

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


def _normalized_strings(values: Iterable[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(value.strip() for value in values if value and value.strip()))


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
    score = (raw * Decimal("100")).quantize(
        _SCORE_QUANTUM, rounding=ROUND_HALF_UP
    )
    score = min(Decimal("100.00"), max(Decimal("0.00"), score))
    strongest = max(components, key=lambda key: (components[key], key))
    weakest = min(components, key=lambda key: (components[key], key))
    reason = (
        f"Strongest factor={strongest}; largest constraint={weakest}; "
        f"evidence={opportunity.evidence_state.value}."
    )
    return ScoredOpportunity(
        opportunity=opportunity, score=score, rank_reason=reason
    )


def rank_opportunities(
    opportunities: Iterable[Opportunity],
) -> tuple[ScoredOpportunity, ...]:
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
        existing = self._programs.get(program.program_id)
        if existing is None:
            self._programs[program.program_id] = program
            return
        if existing != program:
            raise ValueError(
                "program_id collision: same ID supplied with different facts"
            )

    def get(self, program_id: str) -> AffiliateProgram:
        try:
            return self._programs[program_id]
        except KeyError as exc:
            raise KeyError(f"unknown affiliate program: {program_id}") from exc

    def approved_programs(self) -> tuple[AffiliateProgram, ...]:
        return tuple(
            sorted(
                (
                    program
                    for program in self._programs.values()
                    if program.status is ProgramStatus.APPROVED
                ),
                key=lambda program: program.program_id,
            )
        )

    def tracking_link(self, program_id: str) -> str:
        program = self.get(program_id)
        if program.status is not ProgramStatus.APPROVED:
            raise PermissionError(
                "tracking link unavailable: program is not APPROVED"
            )
        if program.evidence_state is not EvidenceState.VERIFIED:
            raise PermissionError(
                "tracking link unavailable: approval is not VERIFIED"
            )
        if (
            not program.tracking_url
            or not program.terms_ref
            or not program.evidence_refs
        ):
            raise PermissionError(
                "tracking link unavailable: required approval evidence is incomplete"
            )
        return program.tracking_url


def build_site_plan(
    opportunity: Opportunity,
    programs: Iterable[AffiliateProgram],
) -> SitePlan:
    if opportunity.evidence_state is EvidenceState.UNKNOWN:
        raise ValueError(
            "site planning requires at least INFERRED opportunity evidence"
        )
    approved = tuple(
        sorted(
            program.program_id
            for program in programs
            if program.status is ProgramStatus.APPROVED
            and program.evidence_state is EvidenceState.VERIFIED
            and program.tracking_url
            and program.terms_ref
            and program.evidence_refs
        )
    )
    if not approved:
        raise ValueError(
            "site plan requires at least one VERIFIED approved affiliate program"
        )

    evidence = opportunity.evidence_refs or (
        "source-required-before-publication",
    )
    pages = (
        SitePage(
            "/",
            "home",
            "Explain the audience problem and route users to useful decision pages.",
            evidence,
        ),
        SitePage(
            "/best/",
            "comparison",
            "Compare qualified options using explicit decision criteria.",
            evidence,
        ),
        SitePage(
            "/reviews/",
            "review-index",
            "Index evidence-backed reviews without invented first-hand claims.",
            evidence,
        ),
        SitePage(
            "/guides/",
            "supporting-guide",
            "Answer pre-purchase questions and build topical depth.",
            evidence,
        ),
        SitePage(
            "/disclosure/",
            "disclosure",
            "Disclose affiliate relationships clearly and conspicuously.",
            evidence,
        ),
    )
    return SitePlan(
        opportunity_id=opportunity.opportunity_id,
        publication_state="DRAFT_SHADOW",
        affiliate_disclosure=(
            "Affiliate disclosure: this site may earn a commission when a reader "
            "purchases through qualifying links. Compensation does not change the "
            "evidence standard."
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
        fixes.append(
            "Remove guaranteed-income/no-loss language and state uncertainty truthfully."
        )
    if (
        any(pattern.search(text) for pattern in _UNSUPPORTED_EXPERIENCE_PATTERNS)
        and not refs
    ):
        reasons.append("First-hand testing/use claim lacks evidence.")
        fixes.append(
            "Attach evidence for the first-hand claim or rewrite it as sourced analysis."
        )
    if has_affiliate_links:
        lower = text.lower()
        if not (
            "affiliate" in lower
            and ("commission" in lower or "may earn" in lower)
        ):
            reasons.append(
                "Affiliate relationship is not clearly disclosed in the content."
            )
            fixes.append(
                "Add a clear affiliate disclosure close to the recommendation/link."
            )
        if not value_signals:
            reasons.append("Affiliate content lacks declared original-value signals.")
            fixes.append(
                "Add measurable original value such as structured comparison "
                "criteria, source-backed analysis, original data, or verified "
                "hands-on evidence."
            )
    if not refs:
        reasons.append("No source/evidence references supplied.")
        fixes.append("Attach source/evidence references before drafting.")

    return ContentReview(
        allowed_for_draft=bool(text) and not fixes,
        allowed_for_publication=False,
        reasons=(
            tuple(reasons)
            if reasons
            else ("Draft passes deterministic content checks.",)
        ),
        required_fixes=tuple(fixes),
    )


class RevenueLedger:
    """Idempotent in-memory ledger of upstream, evidence-bound revenue facts."""

    def __init__(self) -> None:
        self._events: dict[str, RevenueEvent] = {}

    def ingest(self, event: RevenueEvent) -> bool:
        existing = self._events.get(event.event_id)
        if existing is None:
            self._events[event.event_id] = event
            return True
        if existing == event:
            return False
        raise ValueError(
            "event_id collision: same ID supplied with different facts"
        )

    def metrics(self, opportunity_id: str) -> MetricSnapshot:
        opportunity_id = opportunity_id.strip()
        if not opportunity_id:
            raise ValueError("opportunity_id is required")
        events = [
            event
            for event in self._events.values()
            if event.opportunity_id == opportunity_id
        ]
        impressions = sum(event.impressions for event in events)
        visits = sum(event.visits for event in events)
        clicks = sum(event.affiliate_clicks for event in events)
        conversions = sum(event.conversions for event in events)
        accrued = sum(
            (event.commission_accrued for event in events), Decimal("0")
        )
        payout = sum(
            (event.payout_received for event in events), Decimal("0")
        )

        def rate(
            numerator: int | Decimal, denominator: int
        ) -> Decimal | None:
            if denominator == 0:
                return None
            return (Decimal(numerator) / Decimal(denominator)).quantize(
                _RATE_QUANTUM, rounding=ROUND_HALF_UP
            )

        states = {event.evidence_state for event in events}
        if events and states == {EvidenceState.VERIFIED}:
            evidence_state = EvidenceState.VERIFIED
        elif events and EvidenceState.UNKNOWN not in states:
            evidence_state = EvidenceState.INFERRED
        else:
            evidence_state = EvidenceState.UNKNOWN

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
            evidence_refs=normalize_evidence_refs(
                ref for event in events for ref in event.evidence_refs
            ),
        )

    def first_verified_revenue(
        self, opportunity_id: str
    ) -> RevenueEvent | None:
        """Return the earliest timestamped, verified positive-payout event."""

        opportunity_id = opportunity_id.strip()
        if not opportunity_id:
            raise ValueError("opportunity_id is required")
        qualifying = [
            event
            for event in self._events.values()
            if event.opportunity_id == opportunity_id
            and event.payout_received > Decimal("0")
            and event.evidence_state is EvidenceState.VERIFIED
            and bool(event.evidence_refs)
            and bool(event.event_timestamp)
        ]
        if not qualifying:
            return None

        def sort_key(event: RevenueEvent) -> tuple[datetime, str]:
            return (
                datetime.fromisoformat(event.event_timestamp),
                event.event_id,
            )

        return min(qualifying, key=sort_key)


def propose_single_change(metrics: MetricSnapshot) -> LearningProposal:
    """Choose one constraint only; never issue an execution instruction."""

    if metrics.visits == 0:
        return LearningProposal(
            constraint="traffic",
            variable_to_change="distribution_channel_or_keyword_target",
            rationale=(
                "No visits are recorded; improve one acquisition variable before "
                "changing the offer."
            ),
            evidence_state=metrics.evidence_state,
        )
    if metrics.affiliate_clicks == 0:
        return LearningProposal(
            constraint="click_intent",
            variable_to_change="primary_call_to_action",
            rationale=(
                "Visits exist but affiliate clicks do not; test one CTA variable."
            ),
            evidence_state=metrics.evidence_state,
        )
    if metrics.conversions == 0:
        return LearningProposal(
            constraint="merchant_conversion",
            variable_to_change="recommended_offer",
            rationale=(
                "Clicks exist but conversions do not; test one offer while holding "
                "traffic/CTA constant."
            ),
            evidence_state=metrics.evidence_state,
        )
    if metrics.payout_received == Decimal("0"):
        return LearningProposal(
            constraint="cash_realization",
            variable_to_change="payout_reconciliation",
            rationale=(
                "Conversions/commissions exist without received payout; reconcile "
                "before scaling."
            ),
            evidence_state=metrics.evidence_state,
        )
    return LearningProposal(
        constraint="scale_after_proof",
        variable_to_change="winning_distribution_input",
        rationale=(
            "Verified cash is the next gate; scale only one proven acquisition "
            "input and re-measure."
        ),
        evidence_state=metrics.evidence_state,
    )


def decision_receipt(
    action: str, evidence_refs: Iterable[str] = ()
) -> DecisionReceipt:
    refs = tuple(sorted(normalize_evidence_refs(evidence_refs)))
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


def _sha256_of(payload: object) -> str:
    """Hash strict canonical JSON; unsupported values and NaN fail closed."""

    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _asset_to_dict(asset: CampaignAsset) -> dict[str, object]:
    return {
        "asset_id": asset.asset_id,
        "asset_type": asset.asset_type,
        "evidence_refs": sorted(asset.evidence_refs),
        "evidence_state": asset.evidence_state.value,
        "restrictions": sorted(asset.restrictions),
        "title": asset.title,
        "url_slug": asset.url_slug,
    }


def _draft_to_dict(draft: ContentDraft) -> dict[str, object]:
    return {
        "affiliate_evidence_refs": sorted(draft.affiliate_evidence_refs),
        "affiliate_program_id": draft.affiliate_program_id,
        "affiliate_terms_ref": draft.affiliate_terms_ref,
        "asset_id": draft.asset_id,
        "buyer_intent_cta": draft.buyer_intent_cta,
        "channel": draft.channel,
        "draft_id": draft.draft_id,
        "evidence_refs": sorted(draft.evidence_refs),
        "has_affiliate_links": draft.has_affiliate_links,
        "measurement_dimensions": sorted(draft.measurement_dimensions),
        "opportunity_id": draft.opportunity_id,
        "original_value_signals": sorted(draft.original_value_signals),
        "publication_state": draft.publication_state,
        "short_form_text": draft.short_form_text,
        "tracking_id": draft.tracking_id,
    }


def _cluster_to_dict(cluster: KeywordCluster) -> dict[str, object]:
    return {
        "buyer_intent_score": str(cluster.buyer_intent_score),
        "cluster_id": cluster.cluster_id,
        "evidence_refs": sorted(cluster.evidence_refs),
        "evidence_state": cluster.evidence_state.value,
        "head_term": cluster.head_term,
        "ttl_seconds": cluster.ttl_seconds,
        "variants": sorted(cluster.variants),
        "verified_at": cluster.verified_at,
    }


def _receipt_to_dict(receipt: DecisionReceipt) -> dict[str, object]:
    return {
        "action": receipt.action,
        "decision": receipt.decision.value,
        "evidence_refs": sorted(receipt.evidence_refs),
        "reason": receipt.reason,
        "receipt_sha256": receipt.receipt_sha256,
    }


def _site_plan_to_dict(plan: SitePlan) -> dict[str, object]:
    pages = [
        {
            "page_type": page.page_type,
            "purpose": page.purpose,
            "required_evidence": sorted(page.required_evidence),
            "slug": page.slug,
        }
        for page in plan.pages
    ]
    return {
        "affiliate_disclosure": plan.affiliate_disclosure,
        "approved_program_ids": sorted(plan.approved_program_ids),
        "opportunity_id": plan.opportunity_id,
        "pages": sorted(pages, key=lambda page: str(page["slug"])),
        "publication_state": plan.publication_state,
    }


def _email_plan_to_dict(plan: EmailCapturePlan) -> dict[str, object]:
    return {
        "consent_mechanism": plan.consent_mechanism,
        "evidence_refs": sorted(plan.evidence_refs),
        "opportunity_id": plan.opportunity_id,
        "plan_id": plan.plan_id,
        "publication_state": plan.publication_state,
        "value_exchange": plan.value_exchange,
    }


def _learning_to_dict(proposal: LearningProposal) -> dict[str, object]:
    return {
        "constraint": proposal.constraint,
        "evidence_state": proposal.evidence_state.value,
        "rationale": proposal.rationale,
        "variable_to_change": proposal.variable_to_change,
    }


def _metrics_to_dict(snapshot: MetricSnapshot) -> dict[str, object]:
    def decimal_or_none(value: Decimal | None) -> str | None:
        return str(value) if value is not None else None

    return {
        "affiliate_clicks": snapshot.affiliate_clicks,
        "click_through_rate": decimal_or_none(snapshot.click_through_rate),
        "commission_accrued": str(snapshot.commission_accrued),
        "conversion_rate": decimal_or_none(snapshot.conversion_rate),
        "conversions": snapshot.conversions,
        "earnings_per_click": decimal_or_none(snapshot.earnings_per_click),
        "evidence_refs": sorted(snapshot.evidence_refs),
        "evidence_state": snapshot.evidence_state.value,
        "impressions": snapshot.impressions,
        "opportunity_id": snapshot.opportunity_id,
        "payout_received": str(snapshot.payout_received),
        "revenue_per_visit": decimal_or_none(snapshot.revenue_per_visit),
        "visits": snapshot.visits,
    }


def _approved_program_snapshot_to_dict(
    snapshot: ApprovedProgramSnapshot,
) -> dict[str, object]:
    return {
        "evidence_refs": sorted(snapshot.evidence_refs),
        "evidence_state": snapshot.evidence_state.value,
        "program_id": snapshot.program_id,
        "restrictions": sorted(snapshot.restrictions),
        "status": snapshot.status.value,
        "terms_ref": snapshot.terms_ref,
        "tracking_url": snapshot.tracking_url,
    }


def _tracking_id_of(
    asset_id: str,
    opportunity_id: str,
    channel: str,
    proposed_text: str,
    cta: str,
    affiliate_program_id: str | None,
) -> str:
    return _sha256_of(
        {
            "affiliate_program_id": affiliate_program_id,
            "asset_id": asset_id,
            "channel": channel,
            "cta": cta,
            "opportunity_id": opportunity_id,
            "proposed_text": proposed_text,
        }
    )[:16]


def _draft_id_of(
    asset: CampaignAsset,
    opportunity_id: str,
    channel: str,
    short_form_text: str,
    buyer_intent_cta: str,
    tracking_id: str,
    measurement_dimensions: tuple[str, ...],
    evidence_refs: tuple[str, ...],
    has_affiliate_links: bool,
    affiliate_program_id: str | None,
    affiliate_terms_ref: str | None,
    affiliate_evidence_refs: tuple[str, ...],
    original_value_signals: tuple[str, ...],
) -> str:
    return _sha256_of(
        {
            "affiliate_evidence_refs": sorted(affiliate_evidence_refs),
            "affiliate_program_id": affiliate_program_id,
            "affiliate_terms_ref": affiliate_terms_ref,
            "asset": _asset_to_dict(asset),
            "buyer_intent_cta": buyer_intent_cta,
            "channel": channel,
            "evidence_refs": sorted(evidence_refs),
            "has_affiliate_links": has_affiliate_links,
            "measurement_dimensions": sorted(measurement_dimensions),
            "opportunity_id": opportunity_id,
            "original_value_signals": sorted(original_value_signals),
            "short_form_text": short_form_text,
            "tracking_id": tracking_id,
        }
    )


def _plan_id_of(
    opportunity_id: str,
    consent_mechanism: str,
    value_exchange: str,
    evidence_refs: tuple[str, ...],
) -> str:
    return _sha256_of(
        {
            "consent_mechanism": consent_mechanism,
            "evidence_refs": sorted(evidence_refs),
            "opportunity_id": opportunity_id,
            "value_exchange": value_exchange,
        }
    )


def _package_sha256_of(
    opportunity_id: str,
    assets: tuple[CampaignAsset, ...],
    drafts: tuple[ContentDraft, ...],
    measurement_definitions: tuple[str, ...],
    decision_receipts: tuple[DecisionReceipt, ...],
    restrictions_held_for_review: tuple[tuple[str, str], ...],
    review_hold: bool,
    publication_state: str,
) -> str:
    return _sha256_of(
        {
            "assets": sorted(
                (_asset_to_dict(asset) for asset in assets),
                key=lambda asset: str(asset["asset_id"]),
            ),
            "decision_receipts": sorted(
                (_receipt_to_dict(receipt) for receipt in decision_receipts),
                key=lambda receipt: str(receipt["receipt_sha256"]),
            ),
            "drafts": sorted(
                (_draft_to_dict(draft) for draft in drafts),
                key=lambda draft: str(draft["draft_id"]),
            ),
            "measurement_definitions": sorted(measurement_definitions),
            "opportunity_id": opportunity_id,
            "publication_state": publication_state,
            "restrictions_held_for_review": sorted(
                [source_id, restriction]
                for source_id, restriction in restrictions_held_for_review
            ),
            "review_hold": review_hold,
        }
    )


def _result_sha256_of(
    opportunity_id: str,
    clusters: tuple[KeywordCluster, ...],
    site_plan: SitePlan,
    email_capture_plan: EmailCapturePlan,
    learning_proposal: LearningProposal | None,
    decision_receipts: tuple[DecisionReceipt, ...],
    restrictions_held_for_review: tuple[tuple[str, str], ...],
    metrics_snapshot: MetricSnapshot | None,
    review_hold: bool,
    publication_state: str,
    approved_program_snapshots: tuple[ApprovedProgramSnapshot, ...],
) -> str:
    return _sha256_of(
        {
            "approved_program_snapshots": sorted(
                (
                    _approved_program_snapshot_to_dict(snapshot)
                    for snapshot in approved_program_snapshots
                ),
                key=lambda snapshot: str(snapshot["program_id"]),
            ),
            "decision_receipts": sorted(
                (_receipt_to_dict(receipt) for receipt in decision_receipts),
                key=lambda receipt: str(receipt["receipt_sha256"]),
            ),
            "email_capture_plan": _email_plan_to_dict(email_capture_plan),
            "keyword_clusters": sorted(
                (_cluster_to_dict(cluster) for cluster in clusters),
                key=lambda cluster: str(cluster["cluster_id"]),
            ),
            "learning_proposal": (
                _learning_to_dict(learning_proposal)
                if learning_proposal is not None
                else None
            ),
            "metrics_snapshot": (
                _metrics_to_dict(metrics_snapshot)
                if metrics_snapshot is not None
                else None
            ),
            "opportunity_id": opportunity_id,
            "publication_state": publication_state,
            "restrictions_held_for_review": sorted(
                [source_id, restriction]
                for source_id, restriction in restrictions_held_for_review
            ),
            "review_hold": review_hold,
            "site_plan": _site_plan_to_dict(site_plan),
        }
    )


def cluster_keywords(
    opportunity: Opportunity,
    keyword_evidence: Iterable[KeywordEvidence],
    *,
    as_of: datetime | None = None,
) -> tuple[KeywordCluster, ...]:
    """Create clusters only from explicitly VERIFIED, fresh keyword evidence."""

    if opportunity.evidence_state is not EvidenceState.VERIFIED:
        raise ValueError("cluster_keywords requires a VERIFIED opportunity")
    if as_of is not None and as_of.utcoffset() is None:
        raise ValueError("as_of must be timezone-aware")
    reference_time = (
        as_of.astimezone(timezone.utc)
        if as_of is not None
        else datetime.now(timezone.utc)
    )

    seen_heads: set[str] = set()
    clusters: list[KeywordCluster] = []
    for evidence in keyword_evidence:
        if evidence.evidence_state is not EvidenceState.VERIFIED:
            raise ValueError(
                f"keyword evidence for {evidence.head_term!r} must be VERIFIED"
            )
        verified_at = datetime.fromisoformat(evidence.verified_at).astimezone(
            timezone.utc
        )
        if verified_at > reference_time + timedelta(
            seconds=_CLOCK_SKEW_SECONDS
        ):
            raise ValueError(
                f"keyword evidence for {evidence.head_term!r} is future-dated"
            )
        expires_at = verified_at + timedelta(seconds=evidence.ttl_seconds)
        if expires_at <= reference_time:
            raise ValueError(
                f"keyword evidence for {evidence.head_term!r} is stale"
            )
        normalized_head = evidence.head_term.casefold()
        if normalized_head in seen_heads:
            raise ValueError(
                f"duplicate normalized head_term: {normalized_head!r}"
            )
        seen_heads.add(normalized_head)
        cluster_id = _sha256_of(
            {
                "head_term": normalized_head,
                "opportunity_id": opportunity.opportunity_id,
            }
        )[:16]
        clusters.append(
            KeywordCluster(
                cluster_id=cluster_id,
                head_term=evidence.head_term,
                variants=evidence.variants,
                buyer_intent_score=evidence.buyer_intent_score,
                evidence_state=EvidenceState.VERIFIED,
                evidence_refs=evidence.evidence_refs,
                verified_at=verified_at.isoformat(),
                ttl_seconds=evidence.ttl_seconds,
            )
        )
    if not clusters:
        raise ValueError(
            "cluster_keywords requires at least one keyword evidence record"
        )
    return tuple(sorted(clusters, key=lambda cluster: cluster.cluster_id))


def plan_email_capture(
    opportunity: Opportunity,
    consent_mechanism: str,
    value_exchange: str,
    evidence_refs: Iterable[str] = (),
) -> EmailCapturePlan:
    """Build a consent plan only. No enrollment, contact, or network I/O."""

    if opportunity.evidence_state is EvidenceState.UNKNOWN:
        raise ValueError(
            "plan_email_capture requires at least INFERRED opportunity evidence"
        )
    consent_mechanism = consent_mechanism.strip()
    value_exchange = value_exchange.strip()
    if not consent_mechanism or not value_exchange:
        raise ValueError("consent_mechanism and value_exchange are required")
    refs = normalize_evidence_refs(evidence_refs)
    if not refs:
        raise ValueError("plan_email_capture requires evidence_refs")
    plan_id = _plan_id_of(
        opportunity.opportunity_id,
        consent_mechanism,
        value_exchange,
        refs,
    )
    return EmailCapturePlan(
        plan_id=plan_id,
        opportunity_id=opportunity.opportunity_id,
        consent_mechanism=consent_mechanism,
        value_exchange=value_exchange,
        evidence_refs=refs,
    )


def run_fast_cash_lane(
    opportunity: Opportunity,
    assets: Iterable[CampaignAsset],
    draft_inputs: Iterable[DraftInput],
    *,
    affiliate_registry: AffiliateRegistry | None = None,
    extra_evidence_refs: Iterable[str] = (),
    measurement_definitions: Iterable[str] = (),
) -> FastCashCampaignPackage:
    """Return a governed DRAFT_SHADOW package without external side effects."""

    if opportunity.evidence_state is not EvidenceState.VERIFIED:
        raise ValueError("FAST CASH lane requires a VERIFIED opportunity")

    assets_tuple = tuple(assets)
    if not assets_tuple:
        raise ValueError("FAST CASH lane requires at least one asset")
    asset_ids = [asset.asset_id for asset in assets_tuple]
    if len(asset_ids) != len(set(asset_ids)):
        raise ValueError("duplicate asset_id in assets")
    for asset in assets_tuple:
        if (
            asset.evidence_state is not EvidenceState.VERIFIED
            or not asset.evidence_refs
        ):
            raise ValueError("every FAST CASH asset must be VERIFIED with evidence")
    asset_map = {asset.asset_id: asset for asset in assets_tuple}

    inputs = tuple(draft_inputs)
    if not inputs:
        raise ValueError("FAST CASH lane requires at least one DraftInput")
    extra_refs = normalize_evidence_refs(extra_evidence_refs)
    dimensions = _normalized_strings(measurement_definitions)
    if not dimensions:
        dimensions = _STANDARD_MEASUREMENT_DIMENSIONS

    drafts: list[ContentDraft] = []
    restrictions: set[tuple[str, str]] = set()
    used_evidence: list[str] = []
    for asset in assets_tuple:
        restrictions.update(
            (asset.asset_id, restriction)
            for restriction in asset.restrictions
        )

    for draft_input in inputs:
        try:
            asset = asset_map[draft_input.asset_id]
        except KeyError as exc:
            raise ValueError(
                f"DraftInput references unknown asset_id {draft_input.asset_id!r}"
            ) from exc

        affiliate_program_id: str | None = None
        affiliate_terms_ref: str | None = None
        affiliate_evidence_refs: tuple[str, ...] = ()
        if draft_input.has_affiliate_links:
            if affiliate_registry is None:
                raise ValueError(
                    "affiliate_registry is required for affiliate DraftInput"
                )
            program_id = draft_input.affiliate_program_id
            if program_id is None:
                raise ValueError(
                    "affiliate DraftInput requires affiliate_program_id"
                )
            try:
                program = affiliate_registry.get(program_id)
            except KeyError as exc:
                raise ValueError(str(exc)) from exc
            if program.status is not ProgramStatus.APPROVED:
                raise ValueError("affiliate program must be APPROVED")
            if program.evidence_state is not EvidenceState.VERIFIED:
                raise ValueError("affiliate program must be VERIFIED")
            if (
                not program.tracking_url
                or not program.terms_ref
                or not program.evidence_refs
            ):
                raise ValueError(
                    "affiliate program approval evidence is incomplete"
                )
            affiliate_program_id = program.program_id
            affiliate_terms_ref = program.terms_ref
            affiliate_evidence_refs = program.evidence_refs
            restrictions.update(
                (program.program_id, restriction)
                for restriction in program.restrictions
            )

        merged_refs = normalize_evidence_refs(
            (
                *asset.evidence_refs,
                *draft_input.evidence_refs,
                *extra_refs,
                *affiliate_evidence_refs,
                *((affiliate_terms_ref,) if affiliate_terms_ref else ()),
            )
        )
        review = review_content(
            draft_input.proposed_text,
            evidence_refs=merged_refs,
            has_affiliate_links=draft_input.has_affiliate_links,
            original_value_signals=draft_input.original_value_signals,
        )
        if not review.allowed_for_draft:
            raise ValueError(
                f"content for asset {asset.asset_id!r} failed content gate: "
                + "; ".join(review.reasons)
            )

        tracking_id = _tracking_id_of(
            asset.asset_id,
            opportunity.opportunity_id,
            draft_input.channel,
            draft_input.proposed_text,
            draft_input.cta,
            affiliate_program_id,
        )
        draft_id = _draft_id_of(
            asset,
            opportunity.opportunity_id,
            draft_input.channel,
            draft_input.proposed_text,
            draft_input.cta,
            tracking_id,
            dimensions,
            merged_refs,
            draft_input.has_affiliate_links,
            affiliate_program_id,
            affiliate_terms_ref,
            affiliate_evidence_refs,
            draft_input.original_value_signals,
        )
        drafts.append(
            ContentDraft(
                draft_id=draft_id,
                asset_id=asset.asset_id,
                channel=draft_input.channel,
                opportunity_id=opportunity.opportunity_id,
                short_form_text=draft_input.proposed_text,
                buyer_intent_cta=draft_input.cta,
                tracking_id=tracking_id,
                measurement_dimensions=dimensions,
                evidence_refs=merged_refs,
                has_affiliate_links=draft_input.has_affiliate_links,
                affiliate_program_id=affiliate_program_id,
                affiliate_terms_ref=affiliate_terms_ref,
                affiliate_evidence_refs=affiliate_evidence_refs,
                original_value_signals=draft_input.original_value_signals,
            )
        )
        used_evidence.extend(merged_refs)

    drafts_tuple = tuple(drafts)
    restrictions_tuple = tuple(sorted(restrictions))
    all_draft_refs = normalize_evidence_refs(
        (*opportunity.evidence_refs, *extra_refs, *used_evidence)
    )
    receipts = (
        decision_receipt(
            "analyze_funnel",
            (*opportunity.evidence_refs, *extra_refs),
        ),
        decision_receipt("draft_offer", all_draft_refs),
        decision_receipt("prepare_experiment", all_draft_refs),
    )
    review_hold = bool(restrictions_tuple)
    package_sha256 = _package_sha256_of(
        opportunity.opportunity_id,
        assets_tuple,
        drafts_tuple,
        dimensions,
        receipts,
        restrictions_tuple,
        review_hold,
        "DRAFT_SHADOW",
    )
    return FastCashCampaignPackage(
        package_id=package_sha256[:16],
        opportunity_id=opportunity.opportunity_id,
        assets=assets_tuple,
        drafts=drafts_tuple,
        measurement_definitions=dimensions,
        publication_state="DRAFT_SHADOW",
        package_sha256=package_sha256,
        decision_receipts=receipts,
        restrictions_held_for_review=restrictions_tuple,
        review_hold=review_hold,
    )


def run_compounding_lane(
    opportunity: Opportunity,
    programs: Iterable[AffiliateProgram],
    keyword_evidence: Iterable[KeywordEvidence],
    *,
    consent_mechanism: str,
    value_exchange: str,
    email_evidence_refs: Iterable[str] = (),
    prior_metrics: MetricSnapshot | RevenueLedger | None = None,
    as_of: datetime | None = None,
) -> CompoundingLaneResult:
    """Return the evidence-bound COMPOUNDING lane result in DRAFT_SHADOW."""

    if opportunity.evidence_state is not EvidenceState.VERIFIED:
        raise ValueError("COMPOUNDING lane requires a VERIFIED opportunity")

    programs_tuple = tuple(programs)
    program_ids = [program.program_id for program in programs_tuple]
    if len(program_ids) != len(set(program_ids)):
        raise ValueError("duplicate program_id in programs")

    clusters = cluster_keywords(
        opportunity, keyword_evidence, as_of=as_of
    )
    site_plan = build_site_plan(opportunity, programs_tuple)
    email_plan = plan_email_capture(
        opportunity,
        consent_mechanism,
        value_exchange,
        email_evidence_refs,
    )

    resolved_metrics: MetricSnapshot | None = None
    proposal: LearningProposal | None = None
    if prior_metrics is not None:
        if isinstance(prior_metrics, RevenueLedger):
            resolved_metrics = prior_metrics.metrics(
                opportunity.opportunity_id
            )
        else:
            resolved_metrics = prior_metrics
        if resolved_metrics.opportunity_id != opportunity.opportunity_id:
            raise ValueError(
                "prior_metrics opportunity_id does not match lane opportunity"
            )
        if (
            resolved_metrics.evidence_state is EvidenceState.UNKNOWN
            or not resolved_metrics.evidence_refs
        ):
            raise ValueError(
                "prior_metrics requires non-UNKNOWN evidence and evidence_refs"
            )
        proposal = propose_single_change(resolved_metrics)

    approved_ids = set(site_plan.approved_program_ids)
    approved_snapshots = tuple(
        sorted(
            (
                ApprovedProgramSnapshot(
                    program_id=program.program_id,
                    status=program.status,
                    evidence_state=program.evidence_state,
                    evidence_refs=program.evidence_refs,
                    terms_ref=program.terms_ref or "",
                    tracking_url=program.tracking_url or "",
                    restrictions=program.restrictions,
                )
                for program in programs_tuple
                if program.program_id in approved_ids
            ),
            key=lambda snapshot: snapshot.program_id,
        )
    )

    restrictions = {
        (snapshot.program_id, restriction)
        for snapshot in approved_snapshots
        for restriction in snapshot.restrictions
    }
    restrictions_tuple = tuple(sorted(restrictions))
    review_hold = bool(restrictions_tuple)

    keyword_refs = normalize_evidence_refs(
        ref for cluster in clusters for ref in cluster.evidence_refs
    )
    program_refs = normalize_evidence_refs(
        (
            ref
            for snapshot in approved_snapshots
            for ref in (*snapshot.evidence_refs, snapshot.terms_ref)
        )
    )
    analyze_refs = normalize_evidence_refs(
        (*opportunity.evidence_refs, *keyword_refs)
    )
    draft_offer_refs = normalize_evidence_refs(
        (*keyword_refs, *program_refs, *email_plan.evidence_refs)
    )
    prepare_refs = normalize_evidence_refs(
        (
            *opportunity.evidence_refs,
            *keyword_refs,
            *program_refs,
            *email_plan.evidence_refs,
            *(
                resolved_metrics.evidence_refs
                if resolved_metrics is not None
                else ()
            ),
        )
    )

    receipt_list = [decision_receipt("analyze_funnel", analyze_refs)]
    if resolved_metrics is not None:
        receipt_list.append(
            decision_receipt(
                "measure_metrics", resolved_metrics.evidence_refs
            )
        )
    receipt_list.extend(
        (
            decision_receipt("draft_offer", draft_offer_refs),
            decision_receipt("prepare_experiment", prepare_refs),
        )
    )
    receipts = tuple(receipt_list)

    result_sha256 = _result_sha256_of(
        opportunity.opportunity_id,
        clusters,
        site_plan,
        email_plan,
        proposal,
        receipts,
        restrictions_tuple,
        resolved_metrics,
        review_hold,
        "DRAFT_SHADOW",
        approved_snapshots,
    )
    return CompoundingLaneResult(
        opportunity_id=opportunity.opportunity_id,
        keyword_clusters=clusters,
        site_plan=site_plan,
        email_capture_plan=email_plan,
        learning_proposal=proposal,
        publication_state="DRAFT_SHADOW",
        result_sha256=result_sha256,
        decision_receipts=receipts,
        restrictions_held_for_review=restrictions_tuple,
        approved_program_snapshots=approved_snapshots,
        metrics_snapshot=resolved_metrics,
        review_hold=review_hold,
    )
