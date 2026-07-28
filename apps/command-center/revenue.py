from __future__ import annotations

import json
import os
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Offer:
    slug: str
    name: str
    price_usd: int
    kind: str
    checkout_env: str
    delivery_env: str
    status: str = "blocked"

    def snapshot(self) -> dict[str, Any]:
        data = asdict(self)
        checkout = os.getenv(self.checkout_env, "").strip()
        delivery = os.getenv(self.delivery_env, "").strip()
        gates = {
            "checkout_configured": bool(checkout),
            "delivery_configured": bool(delivery),
            "refund_terms_published": True,
            "tracking_enabled": True,
        }
        data["gates"] = gates
        data["status"] = "revenue_ready" if all(gates.values()) else "blocked"
        data["checkout_url"] = checkout if gates["checkout_configured"] else None
        return data


OFFERS = (
    Offer("art-of-true-healing", "The Art of True Healing", 27, "digital_book", "CHECKOUT_ART_OF_TRUE_HEALING", "DELIVERY_ART_OF_TRUE_HEALING"),
    Offer("credit-dispute-toolkit", "Credit Dispute Toolkit", 47, "digital_toolkit", "CHECKOUT_CREDIT_DISPUTE_TOOLKIT", "DELIVERY_CREDIT_DISPUTE_TOOLKIT"),
    Offer("ai-automation-blueprint", "AI Automation Blueprint", 47, "digital_guide", "CHECKOUT_AI_AUTOMATION_BLUEPRINT", "DELIVERY_AI_AUTOMATION_BLUEPRINT"),
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def revenue_state() -> dict[str, Any]:
    offers = [offer.snapshot() for offer in OFFERS]
    ready = [offer for offer in offers if offer["status"] == "revenue_ready"]
    return {
        "vertical": "dominion-digital-products",
        "objective": "Convert owned educational products into tracked, verified sales.",
        "offers": offers,
        "ready_offer_count": len(ready),
        "vertical_status": "revenue_ready" if ready else "blocked",
        "closed_loop": ["traffic", "landing_page", "lead_or_checkout", "payment", "delivery", "support", "telemetry", "memory"],
        "time": utc_now(),
    }


def record_funnel_event(memory_path: Path, event: dict[str, Any]) -> dict[str, Any]:
    allowed = {"page_view", "cta_click", "lead", "checkout_started", "purchase", "delivery", "refund", "support"}
    event_type = str(event.get("event_type", "")).strip()
    offer_slug = str(event.get("offer_slug", "")).strip()
    if event_type not in allowed:
        raise ValueError("unsupported event_type")
    if offer_slug not in {offer.slug for offer in OFFERS}:
        raise ValueError("unknown offer_slug")

    payload = {
        "time": utc_now(),
        "event_type": event_type,
        "offer_slug": offer_slug,
        "source": str(event.get("source", "unknown"))[:120],
        "value_usd": float(event.get("value_usd", 0) or 0),
        "external_id": str(event.get("external_id", ""))[:200],
    }
    memory_path.mkdir(parents=True, exist_ok=True)
    path = memory_path / f"revenue-events-{datetime.now(timezone.utc).strftime('%Y-%m-%d')}.jsonl"
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
    return payload
