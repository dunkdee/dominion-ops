"""The 3-6-9 governance sweep.

Runs every `sweep_interval_hours`. Its contract is narrow and enforced:

  it MAY   read lane state, check receipt freshness, detect drift, and write
           one sweep receipt describing what it found
  it MAY NOT publish, trade, send money, delete data, rotate secrets, or
           merge code

That prohibition is not a comment -- `SweepResult.mutations` is always empty
and the sweep holds no handles that could mutate. A single-flight lock stops
two sweeps overlapping, satisfying Gate 7's duplicate-prevention requirement.
"""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ..logging import get_logger
from ..receipts.schema import Receipt, ReceiptStatus
from ..receipts.writer import ReceiptWriter
from .recovery import RecoveryProposal, propose_recovery
from .state_machine import Lane, TaskState

log = get_logger("orchestration.scheduler")

SWEEP_AGENT_ID = "governance-sweep"
SWEEP_LANE_ID = "infrastructure"


class SweepLockHeld(RuntimeError):
    """Another sweep is in flight."""


@dataclass
class SweepResult:
    started_at: str
    lanes_examined: int = 0
    stale_lanes: tuple[str, ...] = field(default_factory=tuple)
    blocked_lanes: tuple[str, ...] = field(default_factory=tuple)
    unknown_lanes: tuple[str, ...] = field(default_factory=tuple)
    held_lanes: tuple[str, ...] = field(default_factory=tuple)
    proposals: tuple[RecoveryProposal, ...] = field(default_factory=tuple)
    receipt_id: str = ""

    # The sweep never mutates. This field exists so the property is assertable.
    mutations: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict:
        return {
            "started_at": self.started_at,
            "lanes_examined": self.lanes_examined,
            "stale_lanes": list(self.stale_lanes),
            "blocked_lanes": list(self.blocked_lanes),
            "unknown_lanes": list(self.unknown_lanes),
            "held_lanes": list(self.held_lanes),
            "proposals": [p.to_dict() for p in self.proposals],
            "receipt_id": self.receipt_id,
            "mutations": list(self.mutations),
        }


class _SingleFlightLock:
    """Directory-based lock. mkdir is atomic on every POSIX filesystem."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def __enter__(self) -> "_SingleFlightLock":
        try:
            self.path.mkdir(parents=True, exist_ok=False)
        except FileExistsError as exc:
            raise SweepLockHeld(f"a governance sweep is already running ({self.path})") from exc
        return self

    def __exit__(self, *exc_info) -> None:
        try:
            self.path.rmdir()
        except OSError:
            pass


class GovernanceSweep:
    def __init__(
        self,
        receipts: ReceiptWriter,
        *,
        stale_hours: int = 6,
        lock_dir: Path | str | None = None,
        policy_revision: str = "",
        code_revision: str = "",
    ) -> None:
        self.receipts = receipts
        self.stale_hours = stale_hours
        self.lock_path = Path(lock_dir) if lock_dir else self.receipts.root / ".sweep.lock"
        self.policy_revision = policy_revision
        self.code_revision = code_revision

    def _is_stale(self, lane: Lane, now: datetime) -> bool:
        if not lane.last_receipt_at:
            return True
        try:
            last = datetime.fromisoformat(lane.last_receipt_at)
        except ValueError:
            return True
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        return (now - last) > timedelta(hours=self.stale_hours)

    def run(self, lanes: list[Lane]) -> SweepResult:
        now = datetime.now(timezone.utc)
        result = SweepResult(started_at=now.isoformat())

        with _SingleFlightLock(self.lock_path):
            stale, blocked, unknown, held = [], [], [], []
            proposals: list[RecoveryProposal] = []

            for lane in lanes:
                result.lanes_examined += 1
                is_stale = self._is_stale(lane, now)
                if is_stale:
                    stale.append(lane.lane_id)
                if lane.status is TaskState.BLOCKED:
                    blocked.append(lane.lane_id)
                elif lane.status is TaskState.UNKNOWN:
                    unknown.append(lane.lane_id)
                elif lane.status is TaskState.HOLD:
                    held.append(lane.lane_id)

                proposal = propose_recovery(lane, stale=is_stale, stale_hours=self.stale_hours)
                if proposal is not None:
                    proposals.append(proposal)

            result.stale_lanes = tuple(stale)
            result.blocked_lanes = tuple(blocked)
            result.unknown_lanes = tuple(unknown)
            result.held_lanes = tuple(held)
            result.proposals = tuple(proposals)

            summary = (
                f"examined={result.lanes_examined} stale={len(stale)} "
                f"blocked={len(blocked)} unknown={len(unknown)} held={len(held)} "
                f"proposals={len(proposals)}"
            )
            receipt = Receipt(
                task_id=f"sweep-{now.strftime('%Y%m%dT%H%M%SZ')}",
                lane_id=SWEEP_LANE_ID,
                agent_id=SWEEP_AGENT_ID,
                action="governance_sweep",
                expected_result=summary,
            )
            receipt.add_evidence("sweep", "lane_scan", summary)
            for proposal in proposals:
                receipt.add_evidence("recovery_proposal", proposal.lane_id, proposal.problem)

            # A sweep that ran and observed is DONE; it claims nothing more.
            receipt.finalize(
                ReceiptStatus.DONE, summary,
                policy_revision=self.policy_revision,
                code_revision=self.code_revision,
            )
            self.receipts.write(receipt)
            result.receipt_id = receipt.receipt_id

        log.info("governance sweep complete: %s", summary)
        return result
