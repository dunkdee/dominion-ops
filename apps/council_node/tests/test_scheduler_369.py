"""The 3-6-9 governance sweep (Gate 7, Gate 9).

Two properties dominate: the sweep must never mutate, and two sweeps must
never run at once. Both are asserted directly rather than inferred.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from apps.council_node.app.orchestration.scheduler import (
    GovernanceSweep, SweepLockHeld, _SingleFlightLock,
)
from apps.council_node.app.orchestration.state_machine import Lane, TaskState
from apps.council_node.app.receipts.verifier import verify_receipt


def _lane(lane_id: str, status: TaskState, *, hours_ago: float | None = 0.0) -> Lane:
    last = None
    if hours_ago is not None:
        last = (datetime.now(timezone.utc) - timedelta(hours=hours_ago)).isoformat()
    return Lane(
        lane_id=lane_id, objective=f"objective for {lane_id}", status=status,
        last_receipt_at=last, blocker="stated blocker" if status is TaskState.BLOCKED else None,
    )


def test_sweep_writes_a_verifiable_receipt(receipts):
    sweep = GovernanceSweep(receipts, stale_hours=6)
    result = sweep.run([_lane("traffic", TaskState.IN_PROGRESS)])

    assert result.receipt_id
    stored = receipts.read(result.receipt_id)
    assert verify_receipt(stored).valid
    assert stored.agent_id == "governance-sweep"


def test_sweep_never_mutates(receipts):
    """The prohibition in the work order, asserted rather than assumed."""
    lanes = [
        _lane("publisher", TaskState.BLOCKED),
        _lane("traffic", TaskState.UNKNOWN),
        _lane("storefront", TaskState.HOLD),
    ]
    before = [lane.to_dict() for lane in lanes]
    result = GovernanceSweep(receipts, stale_hours=6).run(lanes)

    assert result.mutations == ()
    assert [lane.to_dict() for lane in lanes] == before, "sweep altered lane state"


def test_stale_lane_is_detected(receipts):
    result = GovernanceSweep(receipts, stale_hours=6).run([
        _lane("fresh", TaskState.IN_PROGRESS, hours_ago=1),
        _lane("stale", TaskState.IN_PROGRESS, hours_ago=48),
    ])
    assert result.stale_lanes == ("stale",)


def test_lane_with_no_receipt_ever_is_stale(receipts):
    result = GovernanceSweep(receipts, stale_hours=6).run([
        _lane("never", TaskState.IN_PROGRESS, hours_ago=None),
    ])
    assert "never" in result.stale_lanes


def test_blocked_and_unknown_lanes_produce_proposals(receipts):
    result = GovernanceSweep(receipts, stale_hours=6).run([
        _lane("publisher", TaskState.BLOCKED),
        _lane("traffic", TaskState.UNKNOWN),
    ])
    assert result.blocked_lanes == ("publisher",)
    assert result.unknown_lanes == ("traffic",)
    assert len(result.proposals) == 2
    assert all(p.to_dict()["applied"] is False for p in result.proposals)


def test_founder_hold_never_generates_a_recovery_proposal(receipts):
    """A HOLD is a decision, not a fault; recovery must not route around it."""
    result = GovernanceSweep(receipts, stale_hours=6).run([
        _lane("storefront", TaskState.HOLD, hours_ago=999),
    ])
    assert result.held_lanes == ("storefront",)
    assert result.proposals == ()


def test_duplicate_sweep_is_prevented(receipts, tmp_path):
    lock = tmp_path / "sweep.lock"
    sweep = GovernanceSweep(receipts, lock_dir=lock)
    with _SingleFlightLock(lock):
        with pytest.raises(SweepLockHeld):
            sweep.run([_lane("traffic", TaskState.IN_PROGRESS)])


def test_lock_is_released_so_the_next_sweep_runs(receipts, tmp_path):
    sweep = GovernanceSweep(receipts, lock_dir=tmp_path / "sweep.lock")
    first = sweep.run([_lane("traffic", TaskState.IN_PROGRESS)])
    second = sweep.run([_lane("traffic", TaskState.IN_PROGRESS)])
    assert first.receipt_id != second.receipt_id


def test_sweep_records_every_lane_it_examined(receipts):
    lanes = [_lane(f"lane-{i}", TaskState.IN_PROGRESS) for i in range(5)]
    result = GovernanceSweep(receipts, stale_hours=6).run(lanes)
    assert result.lanes_examined == 5
