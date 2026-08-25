from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from enum import Enum
from math import isfinite
from typing import Iterable


class EvidenceState(str, Enum):
    VERIFIED = "VERIFIED"
    INFERRED = "INFERRED"
    UNKNOWN = "UNKNOWN"


class ProgramStatus(str, Enum):
    DISCOVERED = "DISCOVERED"
    APPLIED = "APPLIED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class ActionDecision(str, Enum):
    SIMULATION_ONLY = "SIMULATION_ONLY"
    BLOCKED = "BLOCKED"


_SHA256_RE = re.compile(r"[0-9a-f]{64}")
_HEX16_RE = re.compile(r"[0-9a-f]{16}")


def require_unit_interval(name: str, value: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name} must be a real number")
    value = float(value)
    if not isfinite(value) or value < 0.0 or value > 1.0:
        raise ValueError(f"{name} must be finite and between 0 and 1")
    return value


def require_nonnegative_decimal(name: str, value: Decimal | str | int) -> Decimal:
    try:
        result = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{name} must be a valid decimal") from exc
    if not result.is_finite() or result < 0:
        raise ValueError(f"{name} must be finite and nonnegative")
    return result


def normalize_evidence_refs(refs: Iterable[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(ref.strip() for ref in refs if ref and ref.strip()))


def _normalize_str_tuple(items: Iterable[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(item.strip() for item in items if item and item.strip()))


def _canonical_utc_timestamp(name: str, value: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a str")
    raw = value.strip()
    if not raw:
        return ""
    iso_value = raw[:-1] + "+00:00" if raw.endswith("Z") else raw
    try:
        parsed = datetime.fromisoformat(iso_value)
    except ValueError as exc:
        raise ValueError(f"{name} must be a valid ISO-8601 datetime; got {raw!r}") from exc
    if parsed.utcoffset() is None:
        raise ValueError(f"{name} must include timezone information; got {raw!r}")
    return parsed.astimezone(timezone.utc).isoformat()


def require_sha256_digest(name: str, value: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a str")
    if not _SHA256_RE.fullmatch(value):
        raise ValueError(
            f"{name} must be exactly 64 lowercase hexadecimal characters"
        )
    return value


def require_hex16_id(name: str, value: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a str")
    if not _HEX16_RE.fullmatch(value):
        raise ValueError(
            f"{name} must be exactly 16 lowercase hexadecimal characters"
        )
    return value


def _normalize_review_holds(
    holds: Iterable[tuple[str, str]],
) -> tuple[tuple[str, str], ...]:
    normalized: set[tuple[str, str]] = set()
    for hold in holds:
        if not isinstance(hold, (tuple, list)) or len(hold) != 2:
            raise ValueError(
                "each restrictions_held_for_review entry must be "
                "(source_id, restriction_text)"
            )
        source_id, restriction = hold
        if not isinstance(source_id, str) or not isinstance(restriction, str):
            raise TypeError("review-hold source and restriction must be strings")
        source_id = source_id.strip()
        restriction = restriction.strip()
        if not source_id or not restriction:
            raise ValueError("review-hold source and restriction must be nonempty")
        normalized.add((source_id, restriction))
    return tuple(sorted(normalized))


@dataclass(frozen=True)
class Opportunity:
    opportunity_id: str
    niche: str
    buyer_intent: float
    demand: float
    competition: float
    economics: float
    zero_capital_fit: float
    original_value_fit: float
    evidence_state: EvidenceState = EvidenceState.UNKNOWN
    evidence_refs: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        opportunity_id = self.opportunity_id.strip()
        niche = self.niche.strip()
        if not opportunity_id:
            raise ValueError("opportunity_id is required")
        if not niche:
            raise ValueError("niche is required")
        object.__setattr__(self, "opportunity_id", opportunity_id)
        object.__setattr__(self, "niche", niche)
        if not isinstance(self.evidence_state, EvidenceState):
            raise TypeError("evidence_state must be an EvidenceState")
        for name in (
            "buyer_intent",
            "demand",
            "competition",
            "economics",
            "zero_capital_fit",
            "original_value_fit",
        ):
            object.__setattr__(
                self, name, require_unit_interval(name, getattr(self, name))
            )
        refs = normalize_evidence_refs(self.evidence_refs)
        object.__setattr__(self, "evidence_refs", refs)
        if self.evidence_state is EvidenceState.VERIFIED and not refs:
            raise ValueError("VERIFIED opportunity requires at least one evidence_ref")


@dataclass(frozen=True)
class ScoredOpportunity:
    opportunity: Opportunity
    score: Decimal
    rank_reason: str


@dataclass(frozen=True)
class AffiliateProgram:
    program_id: str
    name: str
    status: ProgramStatus
    commission_rate: Decimal
    cookie_days: int
    payout_threshold: Decimal
    tracking_url: str | None = None
    terms_ref: str | None = None
    evidence_state: EvidenceState = EvidenceState.UNKNOWN
    evidence_refs: tuple[str, ...] = field(default_factory=tuple)
    restrictions: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        program_id = self.program_id.strip()
        name = self.name.strip()
        if not program_id or not name:
            raise ValueError("program_id and name are required")
        object.__setattr__(self, "program_id", program_id)
        object.__setattr__(self, "name", name)
        if not isinstance(self.status, ProgramStatus):
            raise TypeError("status must be a ProgramStatus")
        if not isinstance(self.evidence_state, EvidenceState):
            raise TypeError("evidence_state must be an EvidenceState")
        object.__setattr__(
            self,
            "commission_rate",
            require_nonnegative_decimal("commission_rate", self.commission_rate),
        )
        object.__setattr__(
            self,
            "payout_threshold",
            require_nonnegative_decimal("payout_threshold", self.payout_threshold),
        )
        if (
            isinstance(self.cookie_days, bool)
            or not isinstance(self.cookie_days, int)
            or self.cookie_days < 0
        ):
            raise ValueError("cookie_days must be a nonnegative integer")
        tracking_url = (
            self.tracking_url.strip() if self.tracking_url is not None else None
        )
        terms_ref = self.terms_ref.strip() if self.terms_ref is not None else None
        object.__setattr__(self, "tracking_url", tracking_url)
        object.__setattr__(self, "terms_ref", terms_ref)
        refs = normalize_evidence_refs(self.evidence_refs)
        object.__setattr__(self, "evidence_refs", refs)
        object.__setattr__(
            self, "restrictions", _normalize_str_tuple(self.restrictions)
        )
        if self.evidence_state is EvidenceState.VERIFIED and not refs:
            raise ValueError("VERIFIED affiliate program requires evidence_refs")
        if self.status is ProgramStatus.APPROVED:
            if not tracking_url or not tracking_url.startswith(("https://", "http://")):
                raise ValueError(
                    "APPROVED affiliate program requires an HTTP(S) tracking_url"
                )
            if not terms_ref:
                raise ValueError("APPROVED affiliate program requires terms_ref")


@dataclass(frozen=True)
class SitePage:
    slug: str
    page_type: str
    purpose: str
    required_evidence: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class SitePlan:
    opportunity_id: str
    publication_state: str
    affiliate_disclosure: str
    pages: tuple[SitePage, ...]
    approved_program_ids: tuple[str, ...]


@dataclass(frozen=True)
class ContentReview:
    allowed_for_draft: bool
    allowed_for_publication: bool
    reasons: tuple[str, ...]
    required_fixes: tuple[str, ...]


@dataclass(frozen=True)
class RevenueEvent:
    event_id: str
    opportunity_id: str
    impressions: int = 0
    visits: int = 0
    affiliate_clicks: int = 0
    conversions: int = 0
    commission_accrued: Decimal = Decimal("0")
    payout_received: Decimal = Decimal("0")
    evidence_state: EvidenceState = EvidenceState.UNKNOWN
    evidence_refs: tuple[str, ...] = field(default_factory=tuple)
    event_timestamp: str = ""

    def __post_init__(self) -> None:
        event_id = self.event_id.strip()
        opportunity_id = self.opportunity_id.strip()
        if not event_id or not opportunity_id:
            raise ValueError("event_id and opportunity_id are required")
        object.__setattr__(self, "event_id", event_id)
        object.__setattr__(self, "opportunity_id", opportunity_id)
        if not isinstance(self.evidence_state, EvidenceState):
            raise TypeError("evidence_state must be an EvidenceState")
        for name in ("impressions", "visits", "affiliate_clicks", "conversions"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} must be a nonnegative integer")
        if self.visits > self.impressions and self.impressions > 0:
            raise ValueError(
                "visits cannot exceed impressions when impressions are supplied"
            )
        if self.affiliate_clicks > self.visits and self.visits > 0:
            raise ValueError(
                "affiliate_clicks cannot exceed visits when visits are supplied"
            )
        if self.conversions > self.affiliate_clicks and self.affiliate_clicks > 0:
            raise ValueError(
                "conversions cannot exceed affiliate_clicks when clicks are supplied"
            )
        object.__setattr__(
            self,
            "commission_accrued",
            require_nonnegative_decimal(
                "commission_accrued", self.commission_accrued
            ),
        )
        object.__setattr__(
            self,
            "payout_received",
            require_nonnegative_decimal("payout_received", self.payout_received),
        )
        refs = normalize_evidence_refs(self.evidence_refs)
        object.__setattr__(self, "evidence_refs", refs)
        if self.evidence_state is EvidenceState.VERIFIED and not refs:
            raise ValueError("VERIFIED revenue event requires evidence_refs")
        object.__setattr__(
            self,
            "event_timestamp",
            _canonical_utc_timestamp("event_timestamp", self.event_timestamp),
        )


@dataclass(frozen=True)
class MetricSnapshot:
    opportunity_id: str
    impressions: int
    visits: int
    affiliate_clicks: int
    conversions: int
    commission_accrued: Decimal
    payout_received: Decimal
    click_through_rate: Decimal | None
    conversion_rate: Decimal | None
    earnings_per_click: Decimal | None
    revenue_per_visit: Decimal | None
    evidence_state: EvidenceState
    evidence_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        opportunity_id = self.opportunity_id.strip()
        if not opportunity_id:
            raise ValueError("opportunity_id is required")
        object.__setattr__(self, "opportunity_id", opportunity_id)
        if not isinstance(self.evidence_state, EvidenceState):
            raise TypeError("evidence_state must be an EvidenceState")
        for name in ("impressions", "visits", "affiliate_clicks", "conversions"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} must be a nonnegative integer")
        for name in ("commission_accrued", "payout_received"):
            object.__setattr__(
                self,
                name,
                require_nonnegative_decimal(name, getattr(self, name)),
            )
        for name in (
            "click_through_rate",
            "conversion_rate",
            "earnings_per_click",
            "revenue_per_visit",
        ):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(
                    self, name, require_nonnegative_decimal(name, value)
                )
        object.__setattr__(
            self, "evidence_refs", normalize_evidence_refs(self.evidence_refs)
        )


@dataclass(frozen=True)
class LearningProposal:
    constraint: str
    variable_to_change: str
    rationale: str
    evidence_state: EvidenceState


@dataclass(frozen=True)
class DecisionReceipt:
    action: str
    decision: ActionDecision
    reason: str
    evidence_refs: tuple[str, ...]
    receipt_sha256: str

    def __post_init__(self) -> None:
        action = self.action.strip()
        reason = self.reason.strip()
        if not action or not reason:
            raise ValueError("action and reason are required")
        if not isinstance(self.decision, ActionDecision):
            raise TypeError("decision must be an ActionDecision")
        object.__setattr__(self, "action", action)
        object.__setattr__(self, "reason", reason)
        object.__setattr__(
            self, "evidence_refs", normalize_evidence_refs(self.evidence_refs)
        )
        require_sha256_digest("receipt_sha256", self.receipt_sha256)


@dataclass(frozen=True)
class KeywordEvidence:
    head_term: str
    variants: tuple[str, ...]
    buyer_intent_score: float
    evidence_state: EvidenceState
    evidence_refs: tuple[str, ...]
    verified_at: str
    ttl_seconds: int

    def __post_init__(self) -> None:
        head_term = self.head_term.strip()
        if not head_term:
            raise ValueError("head_term is required")
        object.__setattr__(self, "head_term", head_term)
        object.__setattr__(
            self,
            "buyer_intent_score",
            require_unit_interval("buyer_intent_score", self.buyer_intent_score),
        )
        variants = _normalize_str_tuple(self.variants)
        if not variants:
            raise ValueError("KeywordEvidence requires at least one variant")
        object.__setattr__(self, "variants", variants)
        if not isinstance(self.evidence_state, EvidenceState):
            raise TypeError("evidence_state must be an EvidenceState")
        refs = normalize_evidence_refs(self.evidence_refs)
        object.__setattr__(self, "evidence_refs", refs)
        if self.evidence_state is EvidenceState.VERIFIED and not refs:
            raise ValueError("VERIFIED KeywordEvidence requires evidence_refs")
        verified_at = _canonical_utc_timestamp("verified_at", self.verified_at)
        if not verified_at:
            raise ValueError("verified_at is required")
        object.__setattr__(self, "verified_at", verified_at)
        if (
            isinstance(self.ttl_seconds, bool)
            or not isinstance(self.ttl_seconds, int)
            or self.ttl_seconds <= 0
        ):
            raise ValueError("ttl_seconds must be a positive integer")


@dataclass(frozen=True)
class DraftInput:
    asset_id: str
    channel: str
    proposed_text: str
    cta: str
    evidence_refs: tuple[str, ...]
    has_affiliate_links: bool = False
    affiliate_program_id: str | None = None
    original_value_signals: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not isinstance(self.has_affiliate_links, bool):
            raise TypeError("has_affiliate_links must be a bool")
        for name in ("asset_id", "channel", "proposed_text", "cta"):
            value = getattr(self, name).strip()
            if not value:
                raise ValueError(f"{name} is required")
            object.__setattr__(self, name, value)
        object.__setattr__(
            self, "evidence_refs", normalize_evidence_refs(self.evidence_refs)
        )
        object.__setattr__(
            self,
            "original_value_signals",
            _normalize_str_tuple(self.original_value_signals),
        )
        if self.has_affiliate_links:
            program_id = (self.affiliate_program_id or "").strip()
            if not program_id:
                raise ValueError(
                    "affiliate_program_id is required when has_affiliate_links=True"
                )
            object.__setattr__(self, "affiliate_program_id", program_id)
        elif self.affiliate_program_id is not None:
            raise ValueError(
                "affiliate_program_id must be None when has_affiliate_links=False"
            )


@dataclass(frozen=True)
class KeywordCluster:
    cluster_id: str
    head_term: str
    variants: tuple[str, ...]
    buyer_intent_score: float
    evidence_state: EvidenceState = EvidenceState.UNKNOWN
    evidence_refs: tuple[str, ...] = field(default_factory=tuple)
    verified_at: str = ""
    ttl_seconds: int = 0

    def __post_init__(self) -> None:
        cluster_id = self.cluster_id.strip()
        head_term = self.head_term.strip()
        if not cluster_id or not head_term:
            raise ValueError("cluster_id and head_term are required")
        object.__setattr__(self, "cluster_id", cluster_id)
        object.__setattr__(self, "head_term", head_term)
        variants = _normalize_str_tuple(self.variants)
        if not variants:
            raise ValueError("KeywordCluster requires at least one variant")
        object.__setattr__(self, "variants", variants)
        object.__setattr__(
            self,
            "buyer_intent_score",
            require_unit_interval("buyer_intent_score", self.buyer_intent_score),
        )
        if not isinstance(self.evidence_state, EvidenceState):
            raise TypeError("evidence_state must be an EvidenceState")
        refs = normalize_evidence_refs(self.evidence_refs)
        object.__setattr__(self, "evidence_refs", refs)
        if self.evidence_state is EvidenceState.VERIFIED and not refs:
            raise ValueError("VERIFIED keyword cluster requires evidence_refs")
        verified_at = _canonical_utc_timestamp(
            "KeywordCluster.verified_at", self.verified_at
        )
        object.__setattr__(self, "verified_at", verified_at)
        if (
            isinstance(self.ttl_seconds, bool)
            or not isinstance(self.ttl_seconds, int)
            or self.ttl_seconds < 0
        ):
            raise ValueError("ttl_seconds must be a nonnegative integer")
        if bool(verified_at) != bool(self.ttl_seconds):
            raise ValueError(
                "verified_at and positive ttl_seconds must be supplied together"
            )


@dataclass(frozen=True)
class CampaignAsset:
    asset_id: str
    title: str
    asset_type: str
    url_slug: str
    evidence_state: EvidenceState = EvidenceState.UNKNOWN
    evidence_refs: tuple[str, ...] = field(default_factory=tuple)
    restrictions: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        for name in ("asset_id", "title", "asset_type", "url_slug"):
            value = getattr(self, name).strip()
            if not value:
                raise ValueError(f"{name} is required")
            object.__setattr__(self, name, value)
        if not isinstance(self.evidence_state, EvidenceState):
            raise TypeError("evidence_state must be an EvidenceState")
        refs = normalize_evidence_refs(self.evidence_refs)
        object.__setattr__(self, "evidence_refs", refs)
        object.__setattr__(
            self, "restrictions", _normalize_str_tuple(self.restrictions)
        )
        if self.evidence_state is EvidenceState.VERIFIED and not refs:
            raise ValueError("VERIFIED asset requires evidence_refs")


@dataclass(frozen=True)
class ContentDraft:
    draft_id: str
    asset_id: str
    channel: str
    opportunity_id: str
    short_form_text: str
    buyer_intent_cta: str
    tracking_id: str
    measurement_dimensions: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    has_affiliate_links: bool = False
    affiliate_program_id: str | None = None
    affiliate_terms_ref: str | None = None
    affiliate_evidence_refs: tuple[str, ...] = field(default_factory=tuple)
    original_value_signals: tuple[str, ...] = field(default_factory=tuple)
    publication_state: str = "DRAFT_SHADOW"

    def __post_init__(self) -> None:
        if self.publication_state != "DRAFT_SHADOW":
            raise ValueError("ContentDraft must remain DRAFT_SHADOW")
        require_sha256_digest("draft_id", self.draft_id)
        require_hex16_id("tracking_id", self.tracking_id)
        if not isinstance(self.has_affiliate_links, bool):
            raise TypeError("has_affiliate_links must be a bool")
        for name in (
            "asset_id",
            "channel",
            "opportunity_id",
            "short_form_text",
            "buyer_intent_cta",
        ):
            value = getattr(self, name).strip()
            if not value:
                raise ValueError(f"{name} is required")
            object.__setattr__(self, name, value)
        dimensions = _normalize_str_tuple(self.measurement_dimensions)
        if not dimensions:
            raise ValueError("measurement_dimensions must be nonempty")
        object.__setattr__(self, "measurement_dimensions", dimensions)
        refs = normalize_evidence_refs(self.evidence_refs)
        if not refs:
            raise ValueError("ContentDraft requires evidence_refs")
        object.__setattr__(self, "evidence_refs", refs)
        signals = _normalize_str_tuple(self.original_value_signals)
        object.__setattr__(self, "original_value_signals", signals)
        if self.has_affiliate_links:
            program_id = (self.affiliate_program_id or "").strip()
            terms_ref = (self.affiliate_terms_ref or "").strip()
            affiliate_refs = normalize_evidence_refs(self.affiliate_evidence_refs)
            if not program_id or not terms_ref or not affiliate_refs:
                raise ValueError(
                    "affiliate drafts require program_id, terms_ref, and evidence_refs"
                )
            if not signals:
                raise ValueError(
                    "affiliate drafts require original_value_signals"
                )
            object.__setattr__(self, "affiliate_program_id", program_id)
            object.__setattr__(self, "affiliate_terms_ref", terms_ref)
            object.__setattr__(
                self, "affiliate_evidence_refs", affiliate_refs
            )
        else:
            if self.affiliate_program_id is not None:
                raise ValueError(
                    "affiliate_program_id must be None when links are absent"
                )
            if self.affiliate_terms_ref is not None:
                raise ValueError(
                    "affiliate_terms_ref must be None when links are absent"
                )
            if self.affiliate_evidence_refs:
                raise ValueError(
                    "affiliate_evidence_refs must be empty when links are absent"
                )


@dataclass(frozen=True)
class EmailCapturePlan:
    plan_id: str
    opportunity_id: str
    consent_mechanism: str
    value_exchange: str
    evidence_refs: tuple[str, ...]
    publication_state: str = "DRAFT_SHADOW"

    def __post_init__(self) -> None:
        if self.publication_state != "DRAFT_SHADOW":
            raise ValueError("EmailCapturePlan must remain DRAFT_SHADOW")
        require_sha256_digest("plan_id", self.plan_id)
        for name in ("opportunity_id", "consent_mechanism", "value_exchange"):
            value = getattr(self, name).strip()
            if not value:
                raise ValueError(f"{name} is required")
            object.__setattr__(self, name, value)
        refs = normalize_evidence_refs(self.evidence_refs)
        if not refs:
            raise ValueError("EmailCapturePlan requires evidence_refs")
        object.__setattr__(self, "evidence_refs", refs)


@dataclass(frozen=True)
class FastCashCampaignPackage:
    package_id: str
    opportunity_id: str
    assets: tuple[CampaignAsset, ...]
    drafts: tuple[ContentDraft, ...]
    measurement_definitions: tuple[str, ...]
    publication_state: str
    package_sha256: str
    decision_receipts: tuple[DecisionReceipt, ...]
    restrictions_held_for_review: tuple[tuple[str, str], ...] = field(
        default_factory=tuple
    )
    review_hold: bool = False

    def __post_init__(self) -> None:
        if self.publication_state != "DRAFT_SHADOW":
            raise ValueError("FastCashCampaignPackage must remain DRAFT_SHADOW")
        opportunity_id = self.opportunity_id.strip()
        if not opportunity_id:
            raise ValueError("opportunity_id is required")
        object.__setattr__(self, "opportunity_id", opportunity_id)
        require_sha256_digest("package_sha256", self.package_sha256)
        require_hex16_id("package_id", self.package_id)
        if self.package_id != self.package_sha256[:16]:
            raise ValueError("package_id must equal package_sha256[:16]")

        assets = tuple(self.assets)
        if not assets:
            raise ValueError("assets must be nonempty")
        asset_ids = [asset.asset_id for asset in assets]
        if len(asset_ids) != len(set(asset_ids)):
            raise ValueError("duplicate asset_id in assets")
        for asset in assets:
            if asset.evidence_state is not EvidenceState.VERIFIED:
                raise ValueError("every campaign asset must be VERIFIED")
            if not asset.evidence_refs:
                raise ValueError("every campaign asset requires evidence_refs")
        object.__setattr__(self, "assets", assets)

        drafts = tuple(self.drafts)
        if not drafts:
            raise ValueError("drafts must be nonempty")
        draft_ids = [draft.draft_id for draft in drafts]
        if len(draft_ids) != len(set(draft_ids)):
            raise ValueError("duplicate draft_id in drafts")
        asset_id_set = set(asset_ids)
        for draft in drafts:
            if draft.asset_id not in asset_id_set:
                raise ValueError("draft references unknown campaign asset")
            if draft.opportunity_id != opportunity_id:
                raise ValueError("draft opportunity_id does not match package")
        object.__setattr__(self, "drafts", drafts)

        dimensions = _normalize_str_tuple(self.measurement_definitions)
        if not dimensions:
            raise ValueError("measurement_definitions must be nonempty")
        object.__setattr__(self, "measurement_definitions", dimensions)

        receipts = tuple(self.decision_receipts)
        if not receipts:
            raise ValueError("decision_receipts must be nonempty")
        receipt_hashes = [receipt.receipt_sha256 for receipt in receipts]
        if len(receipt_hashes) != len(set(receipt_hashes)):
            raise ValueError("duplicate decision receipt hash")
        object.__setattr__(self, "decision_receipts", receipts)

        holds = _normalize_review_holds(self.restrictions_held_for_review)
        valid_sources = asset_id_set | {
            draft.affiliate_program_id
            for draft in drafts
            if draft.affiliate_program_id is not None
        }
        if any(source_id not in valid_sources for source_id, _ in holds):
            raise ValueError("review hold references an unknown asset or program")
        object.__setattr__(self, "restrictions_held_for_review", holds)
        object.__setattr__(self, "review_hold", bool(holds))


@dataclass(frozen=True)
class ApprovedProgramSnapshot:
    program_id: str
    status: ProgramStatus
    evidence_state: EvidenceState
    evidence_refs: tuple[str, ...]
    terms_ref: str
    tracking_url: str
    restrictions: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        program_id = self.program_id.strip()
        if not program_id:
            raise ValueError("program_id is required")
        if not isinstance(self.status, ProgramStatus):
            raise TypeError("status must be a ProgramStatus")
        if self.status is not ProgramStatus.APPROVED:
            raise ValueError("ApprovedProgramSnapshot status must be APPROVED")
        if not isinstance(self.evidence_state, EvidenceState):
            raise TypeError("evidence_state must be an EvidenceState")
        if self.evidence_state is not EvidenceState.VERIFIED:
            raise ValueError(
                "ApprovedProgramSnapshot evidence_state must be VERIFIED"
            )
        refs = normalize_evidence_refs(self.evidence_refs)
        if not refs:
            raise ValueError("ApprovedProgramSnapshot requires evidence_refs")
        terms_ref = self.terms_ref.strip()
        tracking_url = self.tracking_url.strip()
        if not terms_ref:
            raise ValueError("ApprovedProgramSnapshot requires terms_ref")
        if not tracking_url.startswith(("https://", "http://")):
            raise ValueError(
                "ApprovedProgramSnapshot requires an HTTP(S) tracking_url"
            )
        object.__setattr__(self, "program_id", program_id)
        object.__setattr__(self, "evidence_refs", refs)
        object.__setattr__(self, "terms_ref", terms_ref)
        object.__setattr__(self, "tracking_url", tracking_url)
        object.__setattr__(
            self, "restrictions", _normalize_str_tuple(self.restrictions)
        )


@dataclass(frozen=True)
class CompoundingLaneResult:
    opportunity_id: str
    keyword_clusters: tuple[KeywordCluster, ...]
    site_plan: SitePlan
    email_capture_plan: EmailCapturePlan
    learning_proposal: LearningProposal | None
    publication_state: str
    result_sha256: str
    decision_receipts: tuple[DecisionReceipt, ...]
    restrictions_held_for_review: tuple[tuple[str, str], ...]
    approved_program_snapshots: tuple[ApprovedProgramSnapshot, ...]
    metrics_snapshot: MetricSnapshot | None = None
    review_hold: bool = False

    def __post_init__(self) -> None:
        if self.publication_state != "DRAFT_SHADOW":
            raise ValueError("CompoundingLaneResult must remain DRAFT_SHADOW")
        opportunity_id = self.opportunity_id.strip()
        if not opportunity_id:
            raise ValueError("opportunity_id is required")
        object.__setattr__(self, "opportunity_id", opportunity_id)
        require_sha256_digest("result_sha256", self.result_sha256)

        clusters = tuple(self.keyword_clusters)
        if not clusters:
            raise ValueError("keyword_clusters must be nonempty")
        cluster_ids = [cluster.cluster_id for cluster in clusters]
        if len(cluster_ids) != len(set(cluster_ids)):
            raise ValueError("duplicate keyword cluster ID")
        for cluster in clusters:
            if cluster.evidence_state is not EvidenceState.VERIFIED:
                raise ValueError("every keyword cluster must be VERIFIED")
            if (
                not cluster.evidence_refs
                or not cluster.verified_at
                or cluster.ttl_seconds <= 0
            ):
                raise ValueError(
                    "every keyword cluster requires fresh timed evidence"
                )
        object.__setattr__(self, "keyword_clusters", clusters)

        if self.site_plan.publication_state != "DRAFT_SHADOW":
            raise ValueError("nested SitePlan must remain DRAFT_SHADOW")
        if self.site_plan.opportunity_id != opportunity_id:
            raise ValueError("SitePlan opportunity_id does not match result")
        if self.email_capture_plan.publication_state != "DRAFT_SHADOW":
            raise ValueError("nested EmailCapturePlan must remain DRAFT_SHADOW")
        if self.email_capture_plan.opportunity_id != opportunity_id:
            raise ValueError(
                "EmailCapturePlan opportunity_id does not match result"
            )

        receipts = tuple(self.decision_receipts)
        if not receipts:
            raise ValueError("decision_receipts must be nonempty")
        receipt_hashes = [receipt.receipt_sha256 for receipt in receipts]
        if len(receipt_hashes) != len(set(receipt_hashes)):
            raise ValueError("duplicate decision receipt hash")
        object.__setattr__(self, "decision_receipts", receipts)

        holds = _normalize_review_holds(self.restrictions_held_for_review)
        object.__setattr__(self, "restrictions_held_for_review", holds)
        object.__setattr__(self, "review_hold", bool(holds))

        snapshots = tuple(self.approved_program_snapshots)
        snapshot_ids = [snapshot.program_id for snapshot in snapshots]
        approved_ids = list(self.site_plan.approved_program_ids)
        if len(snapshot_ids) != len(set(snapshot_ids)):
            raise ValueError("duplicate approved program snapshot ID")
        if len(approved_ids) != len(set(approved_ids)):
            raise ValueError("duplicate approved program ID in SitePlan")
        if set(snapshot_ids) != set(approved_ids):
            raise ValueError(
                "approved_program_snapshots must exactly cover SitePlan programs"
            )
        object.__setattr__(self, "approved_program_snapshots", snapshots)
        if any(
            source_id not in set(approved_ids) for source_id, _ in holds
        ):
            raise ValueError("review hold references an unapproved program")

        measure_receipts = [
            receipt for receipt in receipts if receipt.action == "measure_metrics"
        ]
        if self.metrics_snapshot is None:
            if self.learning_proposal is not None:
                raise ValueError(
                    "learning_proposal requires a metrics_snapshot"
                )
            if measure_receipts:
                raise ValueError(
                    "measure_metrics receipt requires a metrics_snapshot"
                )
        else:
            if self.metrics_snapshot.opportunity_id != opportunity_id:
                raise ValueError(
                    "metrics_snapshot opportunity_id does not match result"
                )
            if (
                self.metrics_snapshot.evidence_state is EvidenceState.UNKNOWN
                or not self.metrics_snapshot.evidence_refs
            ):
                raise ValueError(
                    "metrics_snapshot requires non-UNKNOWN evidence and refs"
                )
            if self.learning_proposal is None:
                raise ValueError(
                    "metrics_snapshot requires a learning_proposal"
                )
            if len(measure_receipts) != 1:
                raise ValueError(
                    "metrics_snapshot requires exactly one measure_metrics receipt"
                )
            if set(measure_receipts[0].evidence_refs) != set(
                self.metrics_snapshot.evidence_refs
            ):
                raise ValueError(
                    "measure_metrics receipt must cite the metrics evidence_refs"
                )
            if (
                self.learning_proposal.evidence_state
                is not self.metrics_snapshot.evidence_state
            ):
                raise ValueError(
                    "learning_proposal evidence_state must match metrics_snapshot"
                )
