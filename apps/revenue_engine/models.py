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
    cleaned = tuple(sorted(dict.fromkeys(ref.strip() for ref in refs if ref and ref.strip())))
    return cleaned


# ---------------------------------------------------------------------------
# Digest and compact-ID validators
#
# SHA-256 fields (64 lowercase hex chars):
#   DecisionReceipt.receipt_sha256
#   ContentDraft.draft_id
#   EmailCapturePlan.plan_id
#   FastCashCampaignPackage.package_sha256
#   CompoundingLaneResult.result_sha256
#
# Compact hex-16 fields (16 lowercase hex chars):
#   ContentDraft.tracking_id
#   FastCashCampaignPackage.package_id  (must equal package_sha256[:16])
# ---------------------------------------------------------------------------

_SHA256_RE = re.compile(r"[0-9a-f]{64}")
_HEX16_RE  = re.compile(r"[0-9a-f]{16}")


def require_sha256_digest(name: str, value: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a str")
    if not _SHA256_RE.fullmatch(value):
        raise ValueError(
            f"{name} must be a lowercase SHA-256 hex digest "
            f"(exactly 64 chars, [0-9a-f] only); got {value!r}"
        )
    return value


def require_hex16_id(name: str, value: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a str")
    if not _HEX16_RE.fullmatch(value):
        raise ValueError(
            f"{name} must be exactly 16 lowercase hex chars [0-9a-f]; got {value!r}"
        )
    return value


def _normalize_str_tuple(items: Iterable[str]) -> tuple[str, ...]:
    """Strip strings, drop empty, deduplicate preserving first-seen order."""
    return tuple(dict.fromkeys(s.strip() for s in items if s and s.strip()))


# ---------------------------------------------------------------------------
# Core domain models
# ---------------------------------------------------------------------------


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
        opp_id = self.opportunity_id.strip()
        if not opp_id:
            raise ValueError("opportunity_id is required")
        object.__setattr__(self, "opportunity_id", opp_id)
        niche = self.niche.strip()
        if not niche:
            raise ValueError("niche is required")
        object.__setattr__(self, "niche", niche)
        for name in (
            "buyer_intent",
            "demand",
            "competition",
            "economics",
            "zero_capital_fit",
            "original_value_fit",
        ):
            object.__setattr__(self, name, require_unit_interval(name, getattr(self, name)))
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
        if not self.program_id.strip() or not self.name.strip():
            raise ValueError("program_id and name are required")
        object.__setattr__(
            self, "commission_rate", require_nonnegative_decimal("commission_rate", self.commission_rate)
        )
        object.__setattr__(
            self, "payout_threshold", require_nonnegative_decimal("payout_threshold", self.payout_threshold)
        )
        if isinstance(self.cookie_days, bool) or not isinstance(self.cookie_days, int) or self.cookie_days < 0:
            raise ValueError("cookie_days must be a nonnegative integer")
        refs = normalize_evidence_refs(self.evidence_refs)
        object.__setattr__(self, "evidence_refs", refs)
        if self.evidence_state is EvidenceState.VERIFIED and not refs:
            raise ValueError("VERIFIED affiliate program requires evidence_refs")
        if self.status is ProgramStatus.APPROVED:
            if not self.tracking_url or not self.tracking_url.startswith(("https://", "http://")):
                raise ValueError("APPROVED affiliate program requires a tracking_url")
            if not self.terms_ref:
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
    event_timestamp: str = ""  # UTC ISO-8601; empty = unknown

    def __post_init__(self) -> None:
        if not self.event_id.strip() or not self.opportunity_id.strip():
            raise ValueError("event_id and opportunity_id are required")
        for name in ("impressions", "visits", "affiliate_clicks", "conversions"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} must be a nonnegative integer")
        if self.visits > self.impressions and self.impressions > 0:
            raise ValueError("visits cannot exceed impressions when impressions are supplied")
        if self.affiliate_clicks > self.visits and self.visits > 0:
            raise ValueError("affiliate_clicks cannot exceed visits when visits are supplied")
        if self.conversions > self.affiliate_clicks and self.affiliate_clicks > 0:
            raise ValueError("conversions cannot exceed affiliate_clicks when clicks are supplied")
        object.__setattr__(
            self,
            "commission_accrued",
            require_nonnegative_decimal("commission_accrued", self.commission_accrued),
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
        # UTC canonicalize event_timestamp
        ts = self.event_timestamp.strip()
        if ts:
            try:
                parsed = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            except ValueError as exc:
                raise ValueError(f"event_timestamp is not a valid ISO-8601 string: {ts!r}") from exc
            if parsed.tzinfo is None:
                raise ValueError(
                    "event_timestamp must include timezone info (use UTC, e.g. '+00:00' or 'Z')"
                )
            ts = parsed.astimezone(timezone.utc).isoformat()
        object.__setattr__(self, "event_timestamp", ts)


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
    evidence_refs: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        opp_id = self.opportunity_id.strip()
        if not opp_id:
            raise ValueError("MetricSnapshot.opportunity_id is required")
        object.__setattr__(self, "opportunity_id", opp_id)
        if not isinstance(self.evidence_state, EvidenceState):
            raise TypeError(
                f"MetricSnapshot.evidence_state must be an EvidenceState enum; "
                f"got {type(self.evidence_state).__name__}"
            )
        refs = normalize_evidence_refs(self.evidence_refs)
        object.__setattr__(self, "evidence_refs", refs)


@dataclass(frozen=True)
class LearningProposal:
    constraint: str
    variable_to_change: str
    rationale: str
    evidence_state: EvidenceState
    evidence_refs: tuple[str, ...]


@dataclass(frozen=True)
class DecisionReceipt:
    action: str
    decision: ActionDecision
    reason: str
    evidence_refs: tuple[str, ...]
    receipt_sha256: str

    def __post_init__(self) -> None:
        action = self.action.strip()
        if not action:
            raise ValueError("action is required")
        object.__setattr__(self, "action", action)
        reason = self.reason.strip()
        if not reason:
            raise ValueError("reason is required")
        object.__setattr__(self, "reason", reason)
        refs = normalize_evidence_refs(self.evidence_refs)
        object.__setattr__(self, "evidence_refs", refs)
        require_sha256_digest("receipt_sha256", self.receipt_sha256)


# ---------------------------------------------------------------------------
# Lane orchestration models
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class KeywordEvidence:
    """Caller-supplied keyword research evidence for the COMPOUNDING lane.

    All fields are required. evidence_state must be explicitly provided;
    there is no default — callers must assert VERIFIED themselves.
    cluster_keywords() fails closed: only VERIFIED evidence is accepted.
    """

    cluster_id: str
    head_term: str
    variants: tuple[str, ...]
    buyer_intent_score: float
    evidence_refs: tuple[str, ...]
    evidence_state: EvidenceState
    verified_at: str        # UTC ISO-8601; required nonempty
    ttl_seconds: int        # seconds the evidence is valid; must be > 0

    def __post_init__(self) -> None:
        for fname in ("cluster_id", "head_term"):
            val = getattr(self, fname).strip()
            if not val:
                raise ValueError(f"KeywordEvidence.{fname} is required")
            object.__setattr__(self, fname, val)
        object.__setattr__(
            self,
            "buyer_intent_score",
            require_unit_interval("buyer_intent_score", self.buyer_intent_score),
        )
        cleaned = _normalize_str_tuple(self.variants)
        if not cleaned:
            raise ValueError("KeywordEvidence requires at least one usable variant keyword")
        object.__setattr__(self, "variants", cleaned)
        refs = normalize_evidence_refs(self.evidence_refs)
        if not refs:
            raise ValueError("KeywordEvidence requires nonempty evidence_refs")
        object.__setattr__(self, "evidence_refs", refs)
        if not isinstance(self.evidence_state, EvidenceState):
            raise TypeError(
                f"KeywordEvidence.evidence_state must be an EvidenceState enum; "
                f"got {type(self.evidence_state).__name__}"
            )
        ts = self.verified_at.strip()
        if not ts:
            raise ValueError("KeywordEvidence.verified_at is required")
        try:
            parsed = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError(
                f"KeywordEvidence.verified_at is not a valid ISO-8601 string: {ts!r}"
            ) from exc
        if parsed.tzinfo is None:
            raise ValueError(
                "KeywordEvidence.verified_at must include timezone info (use UTC)"
            )
        ts = parsed.astimezone(timezone.utc).isoformat()
        object.__setattr__(self, "verified_at", ts)
        if isinstance(self.ttl_seconds, bool) or not isinstance(self.ttl_seconds, int) or self.ttl_seconds <= 0:
            raise ValueError("KeywordEvidence.ttl_seconds must be a positive integer")


@dataclass(frozen=True)
class KeywordCluster:
    """A buyer-intent keyword cluster derived from opportunity research.

    variants:       normalized nonempty tuple; at least one keyword required.
    evidence_state: VERIFIED requires nonempty evidence_refs.
    verified_at:    UTC ISO-8601; empty = not set (CompoundingLaneResult requires nonempty).
    ttl_seconds:    0 = no TTL info (CompoundingLaneResult requires > 0).
    """

    cluster_id: str
    head_term: str
    variants: tuple[str, ...]
    buyer_intent_score: float
    evidence_state: EvidenceState = EvidenceState.UNKNOWN
    evidence_refs: tuple[str, ...] = field(default_factory=tuple)
    verified_at: str = ""   # UTC ISO-8601 canonicalized; empty = not set
    ttl_seconds: int = 0    # 0 = no TTL info

    def __post_init__(self) -> None:
        cluster_id = self.cluster_id.strip()
        if not cluster_id:
            raise ValueError("cluster_id is required")
        object.__setattr__(self, "cluster_id", cluster_id)
        head_term = self.head_term.strip()
        if not head_term:
            raise ValueError("head_term is required")
        object.__setattr__(self, "head_term", head_term)
        object.__setattr__(
            self,
            "buyer_intent_score",
            require_unit_interval("buyer_intent_score", self.buyer_intent_score),
        )
        cleaned = _normalize_str_tuple(self.variants)
        if not cleaned:
            raise ValueError("KeywordCluster requires at least one usable variant keyword")
        object.__setattr__(self, "variants", cleaned)
        refs = normalize_evidence_refs(self.evidence_refs)
        object.__setattr__(self, "evidence_refs", refs)
        if self.evidence_state is EvidenceState.VERIFIED and not refs:
            raise ValueError("VERIFIED keyword cluster requires evidence_refs")


@dataclass(frozen=True)
class CampaignAsset:
    """A verified existing digital asset or offer eligible for the FAST CASH lane."""

    asset_id: str
    title: str
    asset_type: str
    url_slug: str
    evidence_state: EvidenceState = EvidenceState.UNKNOWN
    evidence_refs: tuple[str, ...] = field(default_factory=tuple)
    restrictions: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        for fname in ("asset_id", "title", "asset_type", "url_slug"):
            val = getattr(self, fname).strip()
            if not val:
                raise ValueError(f"{fname} is required")
            object.__setattr__(self, fname, val)
        refs = normalize_evidence_refs(self.evidence_refs)
        object.__setattr__(self, "evidence_refs", refs)
        restrictions = _normalize_str_tuple(self.restrictions)
        object.__setattr__(self, "restrictions", restrictions)
        if self.evidence_state is EvidenceState.VERIFIED and not refs:
            raise ValueError("VERIFIED asset requires evidence_refs")


@dataclass(frozen=True)
class ApprovedProgramSnapshot:
    """Immutable snapshot of an affiliate program's approval state.

    Enforces: APPROVED-only, VERIFIED-only, nonempty evidence_refs,
    nonempty stripped terms_ref and tracking_url, strict enum types.
    """

    program_id: str
    status: ProgramStatus
    evidence_state: EvidenceState
    evidence_refs: tuple[str, ...]
    terms_ref: str
    tracking_url: str
    restrictions: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not isinstance(self.status, ProgramStatus):
            raise TypeError(
                f"ApprovedProgramSnapshot.status must be a ProgramStatus enum; "
                f"got {type(self.status).__name__}"
            )
        if self.status is not ProgramStatus.APPROVED:
            raise ValueError(
                f"ApprovedProgramSnapshot requires APPROVED status; got {self.status.value}"
            )
        if not isinstance(self.evidence_state, EvidenceState):
            raise TypeError(
                f"ApprovedProgramSnapshot.evidence_state must be an EvidenceState enum; "
                f"got {type(self.evidence_state).__name__}"
            )
        if self.evidence_state is not EvidenceState.VERIFIED:
            raise ValueError(
                f"ApprovedProgramSnapshot requires VERIFIED evidence_state; "
                f"got {self.evidence_state.value}"
            )
        program_id = self.program_id.strip()
        if not program_id:
            raise ValueError("ApprovedProgramSnapshot.program_id is required")
        object.__setattr__(self, "program_id", program_id)
        refs = normalize_evidence_refs(self.evidence_refs)
        if not refs:
            raise ValueError("ApprovedProgramSnapshot requires nonempty evidence_refs")
        object.__setattr__(self, "evidence_refs", refs)
        terms_ref = self.terms_ref.strip()
        if not terms_ref:
            raise ValueError("ApprovedProgramSnapshot requires nonempty terms_ref")
        object.__setattr__(self, "terms_ref", terms_ref)
        tracking_url = self.tracking_url.strip()
        if not tracking_url:
            raise ValueError("ApprovedProgramSnapshot requires nonempty tracking_url")
        object.__setattr__(self, "tracking_url", tracking_url)
        restrictions = _normalize_str_tuple(self.restrictions)
        object.__setattr__(self, "restrictions", restrictions)


@dataclass(frozen=True)
class DraftInput:
    """Caller-supplied specification for a single ContentDraft in the FAST CASH lane.

    has_affiliate_links: must be bool (not int/str).
    affiliate_program_id: required when has_affiliate_links=True; must be None when False.
    affiliate_terms_ref: required when has_affiliate_links=True; must be None when False.
    """

    asset_id: str
    channel: str
    proposed_text: str
    cta: str
    measurement_dimensions: tuple[str, ...]
    has_affiliate_links: bool = False
    affiliate_program_id: str | None = None
    affiliate_terms_ref: str | None = None
    original_value_signals: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        for fname in ("asset_id", "channel", "proposed_text", "cta"):
            val = getattr(self, fname).strip()
            if not val:
                raise ValueError(f"DraftInput.{fname} is required")
            object.__setattr__(self, fname, val)
        if not isinstance(self.has_affiliate_links, bool):
            raise TypeError(
                f"DraftInput.has_affiliate_links must be bool; "
                f"got {type(self.has_affiliate_links).__name__}"
            )
        if not self.has_affiliate_links:
            if self.affiliate_program_id is not None:
                raise ValueError(
                    "affiliate_program_id must be None when has_affiliate_links=False"
                )
            if self.affiliate_terms_ref is not None:
                raise ValueError(
                    "affiliate_terms_ref must be None when has_affiliate_links=False"
                )
        else:
            if self.affiliate_program_id is None:
                raise ValueError(
                    "affiliate_program_id is required when has_affiliate_links=True"
                )
            if self.affiliate_terms_ref is None:
                raise ValueError(
                    "affiliate_terms_ref is required when has_affiliate_links=True"
                )
        dims = _normalize_str_tuple(self.measurement_dimensions)
        if not dims:
            raise ValueError("DraftInput.measurement_dimensions must be nonempty")
        object.__setattr__(self, "measurement_dimensions", dims)
        signals = _normalize_str_tuple(self.original_value_signals)
        object.__setattr__(self, "original_value_signals", signals)


@dataclass(frozen=True)
class ContentDraft:
    """Short-form buyer-intent content draft. Always DRAFT_SHADOW; never published.

    draft_id:       64-hex SHA-256 of the deterministic draft payload.
    tracking_id:    16-hex token derived from asset+opportunity+channel+text+cta+affiliate.
    evidence_refs:  nonempty; inherited from verified asset plus affiliate refs.
    has_affiliate_links: must be bool.
    affiliate_program_id / affiliate_terms_ref: must be None when has_affiliate_links=False.
    affiliate_evidence_refs: must be empty when has_affiliate_links=False.
    """

    draft_id: str
    asset_id: str
    opportunity_id: str
    channel: str
    short_form_text: str
    buyer_intent_cta: str
    tracking_id: str
    measurement_dimensions: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    publication_state: str = "DRAFT_SHADOW"
    has_affiliate_links: bool = False
    affiliate_program_id: str | None = None
    affiliate_terms_ref: str | None = None
    affiliate_evidence_refs: tuple[str, ...] = field(default_factory=tuple)
    original_value_signals: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.publication_state != "DRAFT_SHADOW":
            raise ValueError("ContentDraft publication_state must be DRAFT_SHADOW")
        require_sha256_digest("draft_id", self.draft_id)
        require_hex16_id("tracking_id", self.tracking_id)
        for fname in ("asset_id", "opportunity_id", "channel", "short_form_text", "buyer_intent_cta"):
            val = getattr(self, fname).strip()
            if not val:
                raise ValueError(f"{fname} is required")
            object.__setattr__(self, fname, val)
        dims = _normalize_str_tuple(self.measurement_dimensions)
        if not dims:
            raise ValueError("measurement_dimensions must be nonempty")
        object.__setattr__(self, "measurement_dimensions", dims)
        refs = normalize_evidence_refs(self.evidence_refs)
        if not refs:
            raise ValueError("ContentDraft requires nonempty evidence_refs")
        object.__setattr__(self, "evidence_refs", refs)
        if not isinstance(self.has_affiliate_links, bool):
            raise TypeError(
                f"ContentDraft.has_affiliate_links must be bool; "
                f"got {type(self.has_affiliate_links).__name__}"
            )
        aff_refs = normalize_evidence_refs(self.affiliate_evidence_refs)
        object.__setattr__(self, "affiliate_evidence_refs", aff_refs)
        if not self.has_affiliate_links:
            if self.affiliate_program_id is not None:
                raise ValueError(
                    "affiliate_program_id must be None when has_affiliate_links=False"
                )
            if self.affiliate_terms_ref is not None:
                raise ValueError(
                    "affiliate_terms_ref must be None when has_affiliate_links=False"
                )
            if aff_refs:
                raise ValueError(
                    "affiliate_evidence_refs must be empty when has_affiliate_links=False"
                )
        signals = _normalize_str_tuple(self.original_value_signals)
        object.__setattr__(self, "original_value_signals", signals)


@dataclass(frozen=True)
class EmailCapturePlan:
    """Consent-based email capture plan. Planning only — no enrollment, no I/O.
    Always DRAFT_SHADOW.
    """

    plan_id: str
    opportunity_id: str
    consent_mechanism: str
    value_exchange: str
    evidence_refs: tuple[str, ...]
    publication_state: str = "DRAFT_SHADOW"

    def __post_init__(self) -> None:
        if self.publication_state != "DRAFT_SHADOW":
            raise ValueError("EmailCapturePlan publication_state must be DRAFT_SHADOW")
        require_sha256_digest("plan_id", self.plan_id)
        for fname in ("opportunity_id", "consent_mechanism", "value_exchange"):
            val = getattr(self, fname).strip()
            if not val:
                raise ValueError(f"{fname} is required")
            object.__setattr__(self, fname, val)
        refs = normalize_evidence_refs(self.evidence_refs)
        object.__setattr__(self, "evidence_refs", refs)
        if not refs:
            raise ValueError("EmailCapturePlan requires nonempty evidence_refs")


@dataclass(frozen=True)
class FastCashCampaignPackage:
    """Output of the FAST CASH lane orchestrator. Always DRAFT_SHADOW.

    package_id must equal package_sha256[:16].
    restrictions_held_for_review: deduplicated restriction strings from assets and programs.
    review_hold: derived from bool(restrictions_held_for_review); never caller-controlled.
    approved_program_snapshots: snapshots of affiliate programs referenced in drafts.
    """

    package_id: str
    opportunity_id: str
    assets: tuple[CampaignAsset, ...]
    drafts: tuple[ContentDraft, ...]
    measurement_definitions: tuple[str, ...]
    publication_state: str
    package_sha256: str
    decision_receipts: tuple[DecisionReceipt, ...]
    restrictions_held_for_review: tuple[str, ...]
    review_hold: bool = False
    metrics_snapshot: MetricSnapshot | None = None
    approved_program_snapshots: tuple[ApprovedProgramSnapshot, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.publication_state != "DRAFT_SHADOW":
            raise ValueError("FastCashCampaignPackage must be DRAFT_SHADOW")
        opp_id = self.opportunity_id.strip()
        if not opp_id:
            raise ValueError("opportunity_id is required")
        object.__setattr__(self, "opportunity_id", opp_id)

        # Hash cross-field
        require_sha256_digest("package_sha256", self.package_sha256)
        require_hex16_id("package_id", self.package_id)
        if self.package_id != self.package_sha256[:16]:
            raise ValueError(
                "package_id must equal the first 16 hex chars of package_sha256; "
                f"got package_id={self.package_id!r}, "
                f"package_sha256[:16]={self.package_sha256[:16]!r}"
            )

        # review_hold derived — override caller value
        restrictions = _normalize_str_tuple(self.restrictions_held_for_review)
        object.__setattr__(self, "restrictions_held_for_review", restrictions)
        object.__setattr__(self, "review_hold", bool(restrictions))

        # Assets
        assets = tuple(self.assets)
        object.__setattr__(self, "assets", assets)
        if not assets:
            raise ValueError("assets must be nonempty")
        for asset in assets:
            if asset.evidence_state is not EvidenceState.VERIFIED:
                raise ValueError(
                    f"asset {asset.asset_id!r} must be VERIFIED; "
                    f"got {asset.evidence_state.value}"
                )
            if not asset.evidence_refs:
                raise ValueError(f"asset {asset.asset_id!r} must have evidence_refs")
        asset_ids = [a.asset_id for a in assets]
        if len(asset_ids) != len(set(asset_ids)):
            dupes = sorted({aid for aid in asset_ids if asset_ids.count(aid) > 1})
            raise ValueError(f"duplicate asset_ids in assets: {dupes}")
        asset_id_set = set(asset_ids)

        # Drafts
        drafts = tuple(self.drafts)
        object.__setattr__(self, "drafts", drafts)
        if not drafts:
            raise ValueError("drafts must be nonempty")
        draft_ids: list[str] = []
        for draft in drafts:
            if draft.publication_state != "DRAFT_SHADOW":
                raise ValueError(
                    f"nested ContentDraft {draft.draft_id!r} must be DRAFT_SHADOW"
                )
            if draft.asset_id not in asset_id_set:
                raise ValueError(
                    f"draft {draft.draft_id!r} references unknown asset_id "
                    f"{draft.asset_id!r}"
                )
            if draft.opportunity_id != opp_id:
                raise ValueError(
                    f"draft {draft.draft_id!r} opportunity_id "
                    f"{draft.opportunity_id!r} does not match "
                    f"package opportunity_id {opp_id!r}"
                )
            draft_ids.append(draft.draft_id)
        if len(draft_ids) != len(set(draft_ids)):
            dupes = sorted({did for did in draft_ids if draft_ids.count(did) > 1})
            raise ValueError(f"duplicate draft_ids in drafts: {dupes}")

        # Measurement definitions
        dims = _normalize_str_tuple(self.measurement_definitions)
        if not dims:
            raise ValueError("measurement_definitions must be nonempty")
        object.__setattr__(self, "measurement_definitions", dims)

        # Decision receipts
        receipts = tuple(self.decision_receipts)
        object.__setattr__(self, "decision_receipts", receipts)
        if not receipts:
            raise ValueError("decision_receipts must be nonempty")
        receipt_hashes = [r.receipt_sha256 for r in receipts]
        if len(receipt_hashes) != len(set(receipt_hashes)):
            raise ValueError("duplicate decision-receipt hashes in decision_receipts")

        # Approved program snapshots — normalize, no duplicate program_ids
        snapshots = tuple(self.approved_program_snapshots)
        object.__setattr__(self, "approved_program_snapshots", snapshots)
        snap_ids = [s.program_id for s in snapshots]
        if len(snap_ids) != len(set(snap_ids)):
            dupes = sorted({pid for pid in snap_ids if snap_ids.count(pid) > 1})
            raise ValueError(f"duplicate program_ids in approved_program_snapshots: {dupes}")


@dataclass(frozen=True)
class CompoundingLaneResult:
    """Output of the COMPOUNDING lane orchestrator. Always DRAFT_SHADOW.

    keyword_clusters: nonempty; every cluster must be VERIFIED with nonempty evidence_refs,
                      nonempty verified_at, and ttl_seconds > 0; no duplicate cluster_ids.
    approved_program_snapshots: must exactly cover site_plan.approved_program_ids
                                (no missing, no extra, no duplicate IDs).
    restrictions_held_for_review: deduplicated restriction strings from programs.
    review_hold: derived from bool(restrictions_held_for_review); never caller-controlled.
    """

    opportunity_id: str
    keyword_clusters: tuple[KeywordCluster, ...]
    site_plan: SitePlan
    email_capture_plan: EmailCapturePlan
    learning_proposal: LearningProposal | None
    publication_state: str
    result_sha256: str
    decision_receipts: tuple[DecisionReceipt, ...]
    approved_program_snapshots: tuple[ApprovedProgramSnapshot, ...]
    restrictions_held_for_review: tuple[str, ...] = field(default_factory=tuple)
    review_hold: bool = False

    def __post_init__(self) -> None:
        if self.publication_state != "DRAFT_SHADOW":
            raise ValueError("CompoundingLaneResult must be DRAFT_SHADOW")
        opp_id = self.opportunity_id.strip()
        if not opp_id:
            raise ValueError("opportunity_id is required")
        object.__setattr__(self, "opportunity_id", opp_id)
        require_sha256_digest("result_sha256", self.result_sha256)

        # review_hold derived — override caller value
        restrictions = _normalize_str_tuple(self.restrictions_held_for_review)
        object.__setattr__(self, "restrictions_held_for_review", restrictions)
        object.__setattr__(self, "review_hold", bool(restrictions))

        # Keyword clusters — VERIFIED with freshness fields, no dupes
        clusters = tuple(self.keyword_clusters)
        object.__setattr__(self, "keyword_clusters", clusters)
        if not clusters:
            raise ValueError("CompoundingLaneResult requires at least one keyword cluster")
        for cluster in clusters:
            if cluster.evidence_state is not EvidenceState.VERIFIED:
                raise ValueError(
                    f"keyword cluster {cluster.cluster_id!r} must be VERIFIED; "
                    f"got {cluster.evidence_state.value}"
                )
            if not cluster.evidence_refs:
                raise ValueError(
                    f"keyword cluster {cluster.cluster_id!r} must have evidence_refs"
                )
            if not cluster.verified_at:
                raise ValueError(
                    f"keyword cluster {cluster.cluster_id!r} must have nonempty verified_at"
                )
            if cluster.ttl_seconds <= 0:
                raise ValueError(
                    f"keyword cluster {cluster.cluster_id!r} must have ttl_seconds > 0; "
                    f"got {cluster.ttl_seconds}"
                )
        cluster_ids = [c.cluster_id for c in clusters]
        if len(cluster_ids) != len(set(cluster_ids)):
            dupes = sorted({cid for cid in cluster_ids if cluster_ids.count(cid) > 1})
            raise ValueError(f"duplicate cluster_ids: {dupes}")

        # SitePlan
        if self.site_plan.publication_state != "DRAFT_SHADOW":
            raise ValueError("nested SitePlan must be DRAFT_SHADOW")
        if self.site_plan.opportunity_id != opp_id:
            raise ValueError(
                f"site_plan.opportunity_id {self.site_plan.opportunity_id!r} "
                f"does not match result opportunity_id {opp_id!r}"
            )

        # EmailCapturePlan
        if self.email_capture_plan.publication_state != "DRAFT_SHADOW":
            raise ValueError("nested EmailCapturePlan must be DRAFT_SHADOW")
        if self.email_capture_plan.opportunity_id != opp_id:
            raise ValueError(
                f"email_capture_plan.opportunity_id "
                f"{self.email_capture_plan.opportunity_id!r} "
                f"does not match result opportunity_id {opp_id!r}"
            )

        # Approved program snapshots — exact coverage of site_plan.approved_program_ids
        snapshots = tuple(self.approved_program_snapshots)
        object.__setattr__(self, "approved_program_snapshots", snapshots)
        snap_ids = [s.program_id for s in snapshots]
        if len(snap_ids) != len(set(snap_ids)):
            dupes = sorted({pid for pid in snap_ids if snap_ids.count(pid) > 1})
            raise ValueError(
                f"duplicate program_ids in approved_program_snapshots: {dupes}"
            )
        snapshot_id_set = set(snap_ids)
        approved_id_set = set(self.site_plan.approved_program_ids)
        missing = approved_id_set - snapshot_id_set
        extra = snapshot_id_set - approved_id_set
        if missing:
            raise ValueError(
                f"approved_program_snapshots missing IDs from site_plan: {sorted(missing)}"
            )
        if extra:
            raise ValueError(
                f"approved_program_snapshots has extra IDs not in site_plan: {sorted(extra)}"
            )

        # Decision receipts
        receipts = tuple(self.decision_receipts)
        object.__setattr__(self, "decision_receipts", receipts)
        if not receipts:
            raise ValueError("decision_receipts must be nonempty")
        receipt_hashes = [r.receipt_sha256 for r in receipts]
        if len(receipt_hashes) != len(set(receipt_hashes)):
            raise ValueError("duplicate decision-receipt hashes in decision_receipts")

        # LearningProposal integrity — fail closed
        measure_receipts = [r for r in receipts if r.action == "measure_metrics"]
        if len(measure_receipts) > 1:
            raise ValueError("multiple measure_metrics receipts are not allowed")
        has_measure_receipt = bool(measure_receipts)
        if has_measure_receipt and self.learning_proposal is None:
            raise ValueError(
                "CompoundingLaneResult has a measure_metrics receipt but no learning_proposal; "
                "metrics commitment requires a learning proposal"
            )
        if self.learning_proposal is not None:
            if self.learning_proposal.evidence_state is not EvidenceState.VERIFIED:
                raise ValueError(
                    f"learning_proposal.evidence_state must be VERIFIED; "
                    f"got {self.learning_proposal.evidence_state.value}"
                )
            lp_refs = self.learning_proposal.evidence_refs
            if not lp_refs:
                raise ValueError("learning_proposal.evidence_refs must be nonempty")
            if has_measure_receipt:
                # uniqueness guaranteed above; safe to access single element
                if measure_receipts[0].evidence_refs != lp_refs:
                    raise ValueError(
                        "measure_metrics receipt evidence_refs do not match "
                        "learning_proposal.evidence_refs; tampered receipt detected"
                    )
