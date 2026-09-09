"""Liveness, readiness and status.

/health is liveness only -- it must stay cheap enough to poll.
/ready reports whether governance actually loaded; a Council Node that cannot
read its constitution is not ready, and says so rather than serving traffic.
"""

from __future__ import annotations

from fastapi import APIRouter

from ..deps import services

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "dominion-council-node"}


@router.get("/ready")
def ready() -> dict:
    try:
        svc = services()
        revision = svc.constitution.revision
    except Exception as exc:  # noqa: BLE001 - unreadable governance is NOT ready
        return {"ready": False, "reason": f"governance unavailable: {type(exc).__name__}"}
    return {
        "ready": True,
        "policy_revision": revision,
        "code_revision": svc.code_revision,
        "founder_gate_configured": svc.founder_gate.configured,
    }


@router.get("/api/status")
def status() -> dict:
    svc = services()
    return {
        "governance": "RADAH MEMSHALAH",
        "policy_revision": svc.constitution.revision,
        "code_revision": svc.code_revision,
        "councils": list(svc.constitution.council_ids),
        "veto_domains": sorted(svc.constitution.veto_councils),
        "agents_registered": len(svc.agents.all()),
        "receipts_stored": len(svc.receipts.list_ids()),
        "memory_items": svc.memory.count(),
        "held_lanes": sorted(svc.founder_gate.held_lanes()),
        "settings": svc.settings.redacted(),
    }
