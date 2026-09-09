"""Task intake and inspection."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..deps import services
from ..orchestration.state_machine import Task

router = APIRouter(prefix="/api/tasks", tags=["tasks"])

_TASKS: dict[str, Task] = {}


class TaskInput(BaseModel):
    lane_id: str = Field(min_length=1)
    agent_id: str = Field(min_length=1)
    capability_id: str = Field(min_length=1)
    objective: str = Field(min_length=1)
    action_id: str | None = None


@router.post("")
def create_task(payload: TaskInput) -> dict:
    """Submit a task. Governance runs immediately; nothing is queued past it.

    No handler is attached here, so a permitted task still stops at the
    executor's "no handler" branch and records UNKNOWN. Intake never becomes
    an execution path by accident.
    """
    svc = services()
    task = Task(
        lane_id=payload.lane_id, agent_id=payload.agent_id,
        capability_id=payload.capability_id, objective=payload.objective,
        action_id=payload.action_id,
    )
    outcome = svc.executor.execute(task)
    _TASKS[task.task_id] = task
    return outcome.to_dict()


@router.get("/{task_id}")
def get_task(task_id: str) -> dict:
    task = _TASKS.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="task not found")
    return task.to_dict()
