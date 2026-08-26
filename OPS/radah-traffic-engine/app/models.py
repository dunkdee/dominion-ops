from __future__ import annotations
from typing import Literal, Optional
from pydantic import BaseModel, Field, field_validator


SAFE_SLUG = r"^[a-z0-9][a-z0-9-]{1,79}$"


class OpportunityIn(BaseModel):
    name: str = Field(min_length=3, max_length=120)
    slug: str = Field(pattern=SAFE_SLUG)
    demand: float = Field(ge=0, le=10)
    buyer_intent: float = Field(ge=0, le=10)
    urgency: float = Field(ge=0, le=10)
    competition: float = Field(ge=0, le=10)
    scalability: float = Field(ge=0, le=10)
    defensibility: float = Field(ge=0, le=10)
    execution_ease: float = Field(ge=0, le=10)
    payout: float = Field(ge=0, le=1_000_000)
    conversion_rate: float = Field(ge=0, le=1)

    @field_validator("name")
    @classmethod
    def clean_name(cls, v: str) -> str:
        return " ".join(v.split())


class RadahEnvelope(BaseModel):
    correlation_id: str = Field(min_length=8, max_length=128)
    action: str = Field(min_length=3, max_length=80)
    target: str = Field(min_length=1, max_length=160)
    decision: Literal["ALLOW", "HOLD", "DENY"]
    reason: str = Field(min_length=3, max_length=500)
    authority_version: str = Field(min_length=1, max_length=80)
    expires_at: int = Field(gt=0)
    issued_at: int = Field(gt=0)


class GovernedOpportunityCreate(BaseModel):
    radah: RadahEnvelope
    opportunity: OpportunityIn


class VisitorIntent(BaseModel):
    opportunity_slug: str = Field(pattern=SAFE_SLUG)
    purchase_intent: float = Field(ge=0, le=1)
    service_need: float = Field(ge=0, le=1)
    information_intent: float = Field(ge=0, le=1)
    affiliate_value: float = Field(default=0, ge=0, le=1_000_000)
    lead_value: float = Field(default=0, ge=0, le=1_000_000)
    own_offer_value: float = Field(default=0, ge=0, le=1_000_000)
    email_available: bool = True


class TrackEvent(BaseModel):
    opportunity_slug: str = Field(pattern=SAFE_SLUG)
    event_type: Literal[
        "visit", "tool_start", "tool_complete", "email", "lead",
        "affiliate_click", "sale", "conversion"
    ]
    source: Optional[str] = Field(default=None, max_length=100)
    medium: Optional[str] = Field(default=None, max_length=100)
    campaign: Optional[str] = Field(default=None, max_length=160)
    page: Optional[str] = Field(default=None, max_length=500)
    revenue: float = Field(default=0, ge=0, le=10_000_000)
    occurred_at: Optional[int] = Field(default=None, gt=0)
    metadata: dict = Field(default_factory=dict)


class GovernedStatusChange(BaseModel):
    radah: RadahEnvelope
    status: Literal["ACTIVE", "PAUSED", "REJECTED"]
