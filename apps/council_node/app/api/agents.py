"""Agent registry, read-only over HTTP.

Registration is a deployment concern, not a runtime one: an endpoint that let
a caller register an agent would let a caller grant itself capabilities.
"""

from __future__ import annotations

from fastapi import APIRouter

from ..deps import services

router = APIRouter(prefix="/api/agents", tags=["agents"])


@router.get("")
def list_agents() -> dict:
    svc = services()
    return {"agents": [a.to_dict() for a in svc.agents.all()]}
