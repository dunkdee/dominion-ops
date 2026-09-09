"""Task executor — governance first, work second, receipt always.

The sequence is fixed and there is no path around it:

  1. resolve the agent            (unregistered/disabled agents cannot run)
  2. evaluate policy              (fail-closed; UNKNOWN blocks)
  3. check authority              (advisory agents never execute)
  4. run the handler
  5. finalize and persist a receipt

Step 5 happens on every outcome, including refusals and crashes. A blocked
task that produced no receipt would be an action with no record, and rule 14
requires every action to be attributable. The receipt for a refusal is as
important as the receipt for a success -- it is the evidence that governance
actually fired.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from ..agents.registry import AgentError, AgentRegistry
from ..governance.evaluator import Decision, PolicyEvaluator, Verdict
from ..logging import get_logger
from ..receipts.schema import Receipt, ReceiptStatus
from ..receipts.writer import ReceiptWriter
from .state_machine import Task, TaskState

log = get_logger("orchestration.executor")

# A handler receives the task and returns (observed_result, evidence list).
Handler = Callable[[Task], tuple[str, list[tuple[str, str, str]]]]


@dataclass(frozen=True)
class ExecutionOutcome:
    task: Task
    decision: Decision
    receipt: Receipt
    executed: bool

    def to_dict(self) -> dict:
        return {
            "task": self.task.to_dict(),
            "decision": self.decision.to_dict(),
            "receipt_id": self.receipt.receipt_id,
            "receipt_status": self.receipt.status.value,
            "executed": self.executed,
        }


class Executor:
    def __init__(
        self,
        evaluator: PolicyEvaluator,
        agents: AgentRegistry,
        receipts: ReceiptWriter,
        *,
        code_revision: str = "",
        secret_values: tuple[str, ...] = (),
    ) -> None:
        self.evaluator = evaluator
        self.agents = agents
        self.receipts = receipts
        self.code_revision = code_revision
        self._secrets = secret_values

    def execute(
        self,
        task: Task,
        handler: Handler | None = None,
        *,
        founder_approved: bool = False,
        council_approvals: int = 0,
    ) -> ExecutionOutcome:
        receipt = Receipt(
            task_id=task.task_id, lane_id=task.lane_id, agent_id=task.agent_id,
            action=task.capability_id,
            expected_result=task.objective,
        )

        def seal(status: ReceiptStatus, observed: str, decision: Decision) -> ExecutionOutcome:
            receipt.finalize(
                status, observed,
                policy_revision=decision.policy_revision,
                code_revision=self.code_revision,
                secret_values=self._secrets,
            )
            self.receipts.write(receipt)
            task.receipt_id = receipt.receipt_id
            return ExecutionOutcome(
                task=task, decision=decision, receipt=receipt,
                executed=status is ReceiptStatus.DONE,
            )

        # 1 ── agent resolution
        try:
            agent = self.agents.require(task.agent_id)
        except AgentError as exc:
            decision = Decision(verdict=Verdict.BLOCK, reason=str(exc))
            task.transition(TaskState.BLOCKED, str(exc))
            receipt.add_evidence("governance", "agent_registry", str(exc))
            return seal(ReceiptStatus.BLOCKED, str(exc), decision)

        # 2 ── policy
        decision = self.evaluator.evaluate(
            agent_id=agent.agent_id, lane_id=task.lane_id,
            capability_id=task.capability_id, action_id=task.action_id,
            allowed_capabilities=agent.allowed_capabilities,
            forbidden_capabilities=self.agents.effective_forbidden(agent),
            founder_approved=founder_approved, council_approvals=council_approvals,
        )
        receipt.add_evidence("governance", "policy_evaluator", decision.reason)

        if not decision.verdict.permits_execution:
            state = {
                Verdict.HOLD: TaskState.HOLD,
                Verdict.UNKNOWN: TaskState.UNKNOWN,
            }.get(decision.verdict, TaskState.BLOCKED)
            task.transition(state, decision.reason)
            status = {
                TaskState.HOLD: ReceiptStatus.HOLD,
                TaskState.UNKNOWN: ReceiptStatus.UNKNOWN,
            }.get(state, ReceiptStatus.BLOCKED)
            return seal(status, decision.reason, decision)

        # 3 ── authority. Advisory agents never act, even when policy allows.
        if not agent.may_execute:
            reason = (
                f"agent '{agent.agent_id}' holds advisory authority; output is a "
                "proposal and was not executed"
            )
            task.transition(TaskState.BLOCKED, reason)
            receipt.add_evidence("governance", "agent_authority", reason)
            return seal(ReceiptStatus.BLOCKED, reason, decision)

        if handler is None:
            reason = "no handler was supplied for an executing task"
            task.transition(TaskState.UNKNOWN, reason)
            return seal(ReceiptStatus.UNKNOWN, reason, decision)

        # 4 ── run
        try:
            observed, evidence = handler(task)
        except Exception as exc:  # noqa: BLE001 - a failed handler is BLOCKED, not DONE
            reason = f"handler raised {type(exc).__name__}: {exc}"
            log.exception("handler failed", extra={"task_id": task.task_id})
            task.transition(TaskState.BLOCKED, reason)
            receipt.add_evidence("execution", "handler_exception", reason)
            return seal(ReceiptStatus.BLOCKED, reason, decision)

        for item in evidence:
            receipt.add_evidence(*item)

        # 5 ── the honest status. DONE only when observation matched expectation.
        if observed != task.objective:
            reason = "observed result did not match the expected result"
            task.transition(TaskState.UNKNOWN, reason)
            receipt.add_evidence("verification", "expectation_mismatch", reason)
            return seal(ReceiptStatus.UNKNOWN, observed, decision)

        task.transition(TaskState.DONE, "completed and verified")
        return seal(ReceiptStatus.DONE, observed, decision)
