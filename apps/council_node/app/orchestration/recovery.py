"""Recovery proposals.

Recovery *proposes*, it never repairs. The work order is explicit that the
sweep must not mutate, and Gate 9 requires that a stopped service produce a
proposal without unauthorized self-repair. So this module returns structured
suggestions and nothing here touches a lane, a task, or a service.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from .state_machine import Lane, TaskState


@dataclass(frozen=True)
class RecoveryProposal:
    lane_id: str
    problem: str
    proposed_action: str
    requires_founder: bool
    created_at: str

    def to_dict(self) -> dict:
        return {
            "lane_id": self.lane_id, "problem": self.problem,
            "proposed_action": self.proposed_action,
            "requires_founder": self.requires_founder,
            "created_at": self.created_at,
            "applied": False,  # always: proposals are never auto-applied
        }


def propose_recovery(lane: Lane, *, stale: bool, stale_hours: int) -> RecoveryProposal | None:
    now = datetime.now(timezone.utc).isoformat()

    if lane.status is TaskState.HOLD:
        # A Founder HOLD is a decision, not a fault. Never propose around it.
        return None

    if lane.status is TaskState.BLOCKED:
        return RecoveryProposal(
            lane_id=lane.lane_id,
            problem=f"lane is BLOCKED: {lane.blocker or 'no blocker recorded'}",
            proposed_action=(
                "diagnose the recorded blocker and produce evidence that the "
                "condition is cleared before returning the lane to IN_PROGRESS"
            ),
            requires_founder=False,
            created_at=now,
        )

    if lane.status is TaskState.UNKNOWN:
        return RecoveryProposal(
            lane_id=lane.lane_id,
            problem="lane status is UNKNOWN; no evidence establishes its state",
            proposed_action=(
                "collect a fresh receipt for this lane; UNKNOWN must not be "
                "resolved by assumption"
            ),
            requires_founder=False,
            created_at=now,
        )

    if stale:
        return RecoveryProposal(
            lane_id=lane.lane_id,
            problem=f"no receipt recorded in the last {stale_hours}h",
            proposed_action=(
                "verify the lane's owning service is running and produce a "
                "health receipt"
            ),
            requires_founder=False,
            created_at=now,
        )
    return None
