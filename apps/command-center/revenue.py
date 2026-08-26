from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from runtime_state import runtime_state as canonical_runtime_state


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def revenue_state() -> dict[str, Any]:
    """Return the authoritative live revenue-work-plane view.

    Production numbers come only from the host-generated runtime snapshot backed
    by the actual Revenue Runtime SQLite ledger. Missing runtime evidence is
    reported as unavailable; this module does not manufacture placeholder zeros.
    """
    snapshot = canonical_runtime_state()
    revenue = snapshot.get("revenue", {}) if isinstance(snapshot, dict) else {}
    connected = bool(revenue.get("connected"))
    totals = revenue.get("totals", {}) if isinstance(revenue.get("totals"), dict) else {}
    experiments = revenue.get("experiments", []) if isinstance(revenue.get("experiments"), list) else []
    active = [exp for exp in experiments if isinstance(exp, dict) and exp.get("status") == "active"]

    if not connected:
        return {
            "vertical": "voltedge-commerce",
            "objective": "Drive qualified traffic through measured VoltEdge experiments and compound verified winners.",
            "vertical_status": "runtime_unavailable",
            "runtime_connected": False,
            "ready_offer_count": 0,
            "offers": [],
            "experiments": [],
            "active_experiment_count": 0,
            "constraint": "RUNTIME_STATE_UNAVAILABLE",
            "metrics": {
                "visitors": None,
                "clicks": None,
                "purchases": None,
                "revenue_cents": None,
                "revenue_usd": None,
            },
            "closed_loop": [
                "qualified_traffic", "experiment_router", "offer", "click", "checkout",
                "paid_order", "attribution", "winner_gate", "reversible_promotion", "repeat",
            ],
            "time": snapshot.get("observed_at") or utc_now(),
        }

    revenue_cents = totals.get("revenue_cents")
    metrics = {
        "visitors": totals.get("visitors"),
        "clicks": totals.get("clicks"),
        "purchases": totals.get("purchases"),
        "revenue_cents": revenue_cents,
        "revenue_usd": (float(revenue_cents) / 100.0) if isinstance(revenue_cents, (int, float)) else None,
    }
    offers = []
    for exp in experiments:
        if not isinstance(exp, dict):
            continue
        offers.append({
            "slug": exp.get("id"),
            "name": exp.get("name"),
            "kind": "live_cro_experiment",
            "product_id": exp.get("product_id"),
            "target_url": exp.get("target_url"),
            "status": exp.get("status"),
            "winner": exp.get("winner"),
            "activated_at": exp.get("activated_at"),
            "variants": exp.get("variants", {}),
        })

    return {
        "vertical": "voltedge-commerce",
        "objective": "Drive qualified traffic through measured VoltEdge experiments and compound verified winners.",
        "vertical_status": "live" if active else "no_active_experiment",
        "runtime_connected": True,
        "ready_offer_count": len(active),
        "offers": offers,
        "experiments": experiments,
        "active_experiment_count": len(active),
        "constraint": revenue.get("constraint", "UNKNOWN"),
        "metrics": metrics,
        "closed_loop": [
            "qualified_traffic", "experiment_router", "offer", "click", "checkout",
            "paid_order", "attribution", "winner_gate", "reversible_promotion", "repeat",
        ],
        "time": snapshot.get("observed_at") or utc_now(),
    }


def record_funnel_event(memory_path: Path, event: dict[str, Any]) -> dict[str, Any]:
    """Record a Command Center auxiliary event.

    These records are explicitly non-authoritative. Revenue attribution remains
    owned by the Revenue Runtime ledger and paid-order reconciler.
    """
    allowed = {"page_view", "cta_click", "lead", "checkout_started", "purchase", "delivery", "refund", "support"}
    event_type = str(event.get("event_type", "")).strip()
    offer_slug = str(event.get("offer_slug", "")).strip()
    if event_type not in allowed:
        raise ValueError("unsupported event_type")
    if not offer_slug:
        raise ValueError("offer_slug is required")

    payload = {
        "time": utc_now(),
        "event_type": event_type,
        "offer_slug": offer_slug,
        "source": str(event.get("source", "unknown"))[:120],
        "value_usd": float(event.get("value_usd", 0) or 0),
        "external_id": str(event.get("external_id", ""))[:200],
        "authoritative": False,
        "authority_note": "Command Center auxiliary event; not used for production revenue attribution.",
    }
    memory_path.mkdir(parents=True, exist_ok=True)
    path = memory_path / f"command-center-events-{datetime.now(timezone.utc).strftime('%Y-%m-%d')}.jsonl"
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
    return payload
