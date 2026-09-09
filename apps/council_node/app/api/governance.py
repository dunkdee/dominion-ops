"""Governance evaluation, exposed so a decision can be previewed."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from ..deps import services

router = APIRouter(prefix="/api/governance", tags=["governance"])


class EvaluateInput(BaseModel):
    agent_id: str = Field(min_length=1)
    lane_id: str = Field(min_length=1)
    capability_id: str = Field(min_length=1)
    action_id: str | None = None


@router.post("/evaluate")
def evaluate(payload: EvaluateInput) -> dict:
    """Dry-run the policy evaluator. Read-only; executes nothing."""
    svc = services()
    agent = svc.agents.get(payload.agent_id)
    allowed = agent.allowed_capabilities if agent else ()
    forbidden = svc.agents.effective_forbidden(agent) if agent else ()
    decision = svc.evaluator.evaluate(
        agent_id=payload.agent_id, lane_id=payload.lane_id,
        capability_id=payload.capability_id, action_id=payload.action_id,
        allowed_capabilities=allowed, forbidden_capabilities=forbidden,
    )
    return decision.to_dict()


@router.get("/constitution")
def constitution() -> dict:
    svc = services()
    return {
        "governing_name": "RADAH MEMSHALAH",
        "policy_revision": svc.constitution.revision,
        "councils": list(svc.constitution.council_ids),
        "veto_domains": sorted(svc.constitution.veto_councils),
        "preserve_dissent": svc.constitution.preserve_dissent,
        "allowed_statuses": ["DONE", "IN_PROGRESS", "BLOCKED", "UNKNOWN", "HOLD"],
    }
