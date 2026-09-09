"""Lane state. Derived from the canonical store, never from a second file."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..deps import services
from ..orchestration.state_machine import Lane, TaskState

router = APIRouter(prefix="/api/lanes", tags=["lanes"])

# Initial verticals from the work order §13.
_LANES: dict[str, Lane] = {
    lane_id: Lane(lane_id=lane_id, objective=objective, status=TaskState.UNKNOWN)
    for lane_id, objective in (
        ("publisher", "distribute approved content to bound accounts"),
        ("traffic", "produce qualified visits"),
        ("youtube", "publish faceless video content"),
        ("storefront", "convert visits into orders"),
        ("seo", "earn organic search visibility"),
        ("affiliate", "earn commission on referred conversions"),
        ("digital_products", "sell owned digital assets"),
        ("email", "operate governed lifecycle messaging"),
        ("market_research", "produce research-only market analysis"),
        ("analytics", "measure and evaluate experiments"),
        ("infrastructure", "keep the estate reliable and observable"),
    )
}


@router.get("")
def list_lanes() -> dict:
    svc = services()
    held = svc.founder_gate.held_lanes()
    rows = []
    for lane in _LANES.values():
        data = lane.to_dict()
        data["founder_hold"] = lane.lane_id in held
        rows.append(data)
    return {"lanes": rows}


@router.get("/{lane_id}")
def get_lane(lane_id: str) -> dict:
    lane = _LANES.get(lane_id)
    if lane is None:
        raise HTTPException(status_code=404, detail="lane not found")
    data = lane.to_dict()
    data["founder_hold"] = services().founder_gate.is_held(lane_id)
    return data
