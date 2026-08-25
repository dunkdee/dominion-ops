from __future__ import annotations

from dataclasses import dataclass, field
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
    cleaned = tuple(dict.fromkeys(ref.strip() for ref in refs if ref and ref.strip()))
    return cleaned


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
        if not self.opportunity_id.strip():
            raise ValueError("opportunity_id is required")
        if not self.niche.strip():
            raise ValueError("niche is required")
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


@dataclass(frozen=True)
class MetricSnapshot:
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
