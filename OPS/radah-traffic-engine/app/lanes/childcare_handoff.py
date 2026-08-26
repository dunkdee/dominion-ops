from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

from ..models import RadahEnvelope
from .employer_childcare import TOOTRIS_REFERRAL_SOURCE


class GovernedChildcareHandoff(BaseModel):
    radah: RadahEnvelope
    provider: Literal["tootris"] = "tootris"
    ttl_minutes: int = Field(default=1440, ge=5, le=1440)


class GovernedChildcareConversion(BaseModel):
    radah: RadahEnvelope
    provider_receipt_id: str = Field(min_length=3, max_length=200)
    confirmed_reward_usd: float = Field(ge=0, le=100_000)


def provider_is_current(as_of: date | None = None) -> bool:
    as_of = as_of or date.today()
    refresh_after = TOOTRIS_REFERRAL_SOURCE.get("refresh_after")
    if not refresh_after:
        return False
    return as_of <= date.fromisoformat(refresh_after)


def provider_public_descriptor(as_of: date | None = None) -> dict:
    current = provider_is_current(as_of)
    return {
        "id": "tootris",
        "name": "TOOTRiS Employer Referral",
        "handoff_mode": "USER_REDIRECT_TO_OFFICIAL_FORM",
        "destination_url": TOOTRIS_REFERRAL_SOURCE["url"],
        "published_reward_usd": TOOTRIS_REFERRAL_SOURCE["published_reward_usd"],
        "reward_trigger": TOOTRIS_REFERRAL_SOURCE["trigger"],
        "verified_at": TOOTRIS_REFERRAL_SOURCE["verified_at"],
        "refresh_after": TOOTRIS_REFERRAL_SOURCE["refresh_after"],
        "terms_current": current,
        "transmits_saved_lead_data": False,
        "note": (
            "The handoff opens the provider's official employer-referral form. "
            "The service does not append stored lead PII to the destination URL or "
            "submit the provider form in the background."
        ),
    }
