"""Task and lane state.

Only the five constitutional statuses exist. Transitions are explicit, and an
illegal transition raises rather than being coerced -- silently moving a
BLOCKED task to DONE is exactly the kind of drift the receipt system exists
to catch, so the state machine refuses it at the source.

DONE is terminal and unreachable from BLOCKED without passing back through
IN_PROGRESS, which forces a fresh evaluation and a fresh receipt.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


class InvalidTransition(RuntimeError):
    """A task was moved between states that governance does not connect."""


class TaskState(str, Enum):
    IN_PROGRESS = "IN_PROGRESS"
    DONE = "DONE"
    BLOCKED = "BLOCKED"
    UNKNOWN = "UNKNOWN"
    HOLD = "HOLD"


# A task may only move along these edges.
_ALLOWED: dict[TaskState, frozenset[TaskState]] = {
    TaskState.IN_PROGRESS: frozenset({
        TaskState.DONE, TaskState.BLOCKED, TaskState.UNKNOWN, TaskState.HOLD,
    }),
    # Recovery always re-enters through IN_PROGRESS so it is re-evaluated.
    TaskState.BLOCKED: frozenset({TaskState.IN_PROGRESS, TaskState.UNKNOWN}),
    TaskState.UNKNOWN: frozenset({TaskState.IN_PROGRESS, TaskState.BLOCKED}),
    TaskState.HOLD: frozenset({TaskState.IN_PROGRESS, TaskState.BLOCKED}),
    TaskState.DONE: frozenset(),  # terminal
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Task:
    lane_id: str
    agent_id: str
    capability_id: str
    objective: str
    task_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    action_id: str | None = None
    state: TaskState = TaskState.IN_PROGRESS
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)
    blocker: str | None = None
    receipt_id: str | None = None
    history: list[dict] = field(default_factory=list)

    def transition(self, new_state: TaskState, reason: str) -> "Task":
        if new_state is self.state:
            return self
        allowed = _ALLOWED.get(self.state, frozenset())
        if new_state not in allowed:
            raise InvalidTransition(
                f"task {self.task_id}: {self.state.value} -> {new_state.value} is not a "
                f"permitted transition"
            )
        self.history.append({
            "from": self.state.value, "to": new_state.value,
            "reason": reason, "at": _now(),
        })
        self.state = new_state
        self.blocker = reason if new_state in {
            TaskState.BLOCKED, TaskState.UNKNOWN, TaskState.HOLD,
        } else None
        self.updated_at = _now()
        return self

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id, "lane_id": self.lane_id, "agent_id": self.agent_id,
            "capability_id": self.capability_id, "action_id": self.action_id,
            "objective": self.objective, "state": self.state.value,
            "created_at": self.created_at, "updated_at": self.updated_at,
            "blocker": self.blocker, "receipt_id": self.receipt_id,
            "history": list(self.history),
        }


@dataclass
class Lane:
    lane_id: str
    objective: str
    status: TaskState = TaskState.UNKNOWN
    current_signal: str = ""
    next_action: str = ""
    blocker: str | None = None
    receipt_required: str = ""
    owner_agent: str = ""
    last_receipt_at: str | None = None

    def to_dict(self) -> dict:
        return {
            "lane_id": self.lane_id, "objective": self.objective,
            "status": self.status.value, "current_signal": self.current_signal,
            "next_action": self.next_action, "blocker": self.blocker,
            "receipt_required": self.receipt_required, "owner_agent": self.owner_agent,
            "last_receipt_at": self.last_receipt_at,
        }
