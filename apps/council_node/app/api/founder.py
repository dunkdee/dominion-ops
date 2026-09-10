"""Founder controls — HOLD, RELEASE, APPROVE.

Every endpoint here is a mutation and every one requires the Founder token,
presented as `X-Founder-Token`. The gate is fail-closed: an unconfigured
token means these endpoints reject everything.
"""

from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from ..deps import services
from ..governance.founder_gate import FounderGateError

router = APIRouter(prefix="/api/founder", tags=["founder"])


class HoldInput(BaseModel):
    lane_id: str = Field(min_length=1)
    reason: str = Field(min_length=1)


class ReleaseInput(BaseModel):
    lane_id: str = Field(min_length=1)


def _require(token: str | None) -> None:
    try:
        services().founder_gate.require(token)
    except FounderGateError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.post("/hold")
def hold(payload: HoldInput, x_founder_token: str | None = Header(default=None)) -> dict:
    _require(x_founder_token)
    entry = services().founder_gate.hold(payload.lane_id, payload.reason)
    return {"held": True, "entry": entry}


@router.post("/release")
def release(payload: ReleaseInput, x_founder_token: str | None = Header(default=None)) -> dict:
    _require(x_founder_token)
    removed = services().founder_gate.release(payload.lane_id)
    return {"released": removed, "lane_id": payload.lane_id}


@router.get("/holds")
def holds(x_founder_token: str | None = Header(default=None)) -> dict:
    _require(x_founder_token)
    return {"holds": services().founder_gate.held_lanes()}
