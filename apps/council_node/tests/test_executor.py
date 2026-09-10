"""The execution loop: governance first, receipt always.

The property worth guarding is that *every* outcome produces a persisted,
verifiable receipt -- including refusals. A blocked action with no receipt
would be an action with no record, which rule 14 forbids.
"""

from __future__ import annotations

from apps.council_node.app.orchestration.executor import Executor
from apps.council_node.app.orchestration.state_machine import (
    InvalidTransition, Task, TaskState,
)
from apps.council_node.app.receipts.verifier import verify_receipt
import pytest


def _executor(evaluator, agents, receipts) -> Executor:
    return Executor(evaluator, agents, receipts, code_revision="test-sha")


def _task(**kw) -> Task:
    base = dict(
        lane_id="traffic", agent_id="worker-01", capability_id="read.public",
        objective="collected public signal", action_id="read.public",
    )
    base.update(kw)
    return Task(**base)


def _ok_handler(task):
    return task.objective, [("probe", "handler", "ran")]


def test_permitted_task_executes_and_verifies(evaluator, agents, receipts):
    outcome = _executor(evaluator, agents, receipts).execute(_task(), _ok_handler)
    assert outcome.executed is True
    assert outcome.task.state is TaskState.DONE
    assert verify_receipt(receipts.read(outcome.receipt.receipt_id)).valid


def test_blocked_task_still_produces_a_receipt(evaluator, agents, receipts):
    """The receipt for a refusal is the evidence governance actually fired."""
    task = _task(capability_id="money.transfer", action_id="money.transfer")
    outcome = _executor(evaluator, agents, receipts).execute(task, _ok_handler)

    assert outcome.executed is False
    assert outcome.receipt.receipt_id in receipts.list_ids()
    assert outcome.receipt.status.value in {"BLOCKED", "UNKNOWN", "HOLD"}


def test_unregistered_agent_is_blocked_with_a_receipt(evaluator, agents, receipts):
    outcome = _executor(evaluator, agents, receipts).execute(
        _task(agent_id="ghost"), _ok_handler,
    )
    assert outcome.executed is False
    assert "not registered" in outcome.decision.reason
    assert receipts.read(outcome.receipt.receipt_id).status.value == "BLOCKED"


def test_advisory_agent_never_executes(evaluator, agents, receipts):
    """Policy may allow it; authority still refuses to act on it."""
    outcome = _executor(evaluator, agents, receipts).execute(
        _task(agent_id="advisor-01"), _ok_handler,
    )
    assert outcome.decision.verdict.permits_execution is True
    assert outcome.executed is False
    assert "advisory authority" in outcome.receipt.observed_result


def test_handler_exception_is_blocked_not_done(evaluator, agents, receipts):
    def explode(task):
        raise RuntimeError("provider timeout")

    outcome = _executor(evaluator, agents, receipts).execute(_task(), explode)
    assert outcome.executed is False
    assert outcome.task.state is TaskState.BLOCKED
    assert "provider timeout" in outcome.receipt.observed_result


def test_mismatched_observation_is_unknown_not_done(evaluator, agents, receipts):
    def wrong(task):
        return "something else happened", [("probe", "handler")]

    outcome = _executor(evaluator, agents, receipts).execute(_task(), wrong)
    assert outcome.task.state is TaskState.UNKNOWN
    assert outcome.receipt.status.value == "UNKNOWN"


def test_missing_handler_is_unknown(evaluator, agents, receipts):
    outcome = _executor(evaluator, agents, receipts).execute(_task(), None)
    assert outcome.task.state is TaskState.UNKNOWN


def test_receipt_carries_policy_and_code_revision(evaluator, agents, receipts):
    outcome = _executor(evaluator, agents, receipts).execute(_task(), _ok_handler)
    stored = receipts.read(outcome.receipt.receipt_id)
    assert stored.policy_revision
    assert stored.code_revision == "test-sha"


# ── state machine ───────────────────────────────────────────────────────

def test_done_is_terminal():
    task = _task()
    task.transition(TaskState.DONE, "finished")
    with pytest.raises(InvalidTransition):
        task.transition(TaskState.IN_PROGRESS, "reopening")


def test_blocked_cannot_jump_straight_to_done():
    """Recovery must re-enter through IN_PROGRESS and be re-evaluated."""
    task = _task()
    task.transition(TaskState.BLOCKED, "dependency down")
    with pytest.raises(InvalidTransition):
        task.transition(TaskState.DONE, "assume it healed")

    task.transition(TaskState.IN_PROGRESS, "retrying")
    task.transition(TaskState.DONE, "verified")
    assert task.state is TaskState.DONE


def test_transitions_are_recorded_with_reasons():
    task = _task()
    task.transition(TaskState.BLOCKED, "dependency down")
    assert task.history[-1]["reason"] == "dependency down"
    assert task.blocker == "dependency down"
