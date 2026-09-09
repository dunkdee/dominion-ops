"""Policy evaluator — the single gate every task passes through.

The evaluator answers one question: may this agent perform this capability in
this lane, right now? It is deliberately boring and deliberately pessimistic.

Order of checks matters, and it runs strictest-first so a denial reason is
always the most fundamental one:

  1. Founder HOLD on the lane        (rule 11 — human overrides automation)
  2. capability permitted for agent  (rule 6 — explicit allowlist)
  3. action risk classified          (undeclared risk is UNKNOWN, not low)
  4. risk level satisfiable          (prohibited actions reject outright)

Anything the evaluator cannot determine returns UNKNOWN, and UNKNOWN blocks
(rule 9/10). There is no path through this function that returns ALLOW by
default.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from .capabilities import CapabilityRegistry
from .constitution import Constitution, Status
from .founder_gate import FounderGate, FounderGateError


class Verdict(str, Enum):
    ALLOW = "ALLOW"
    BLOCK = "BLOCK"
    UNKNOWN = "UNKNOWN"
    HOLD = "HOLD"
    REQUIRES_COUNCIL = "REQUIRES_COUNCIL"
    REQUIRES_FOUNDER = "REQUIRES_FOUNDER"

    @property
    def permits_execution(self) -> bool:
        return self is Verdict.ALLOW


@dataclass(frozen=True)
class Decision:
    verdict: Verdict
    reason: str
    risk_level: str | None = None
    council_approvals_required: int = 0
    human_approval_required: bool = False
    policy_revision: str = ""
    checks: tuple[str, ...] = field(default_factory=tuple)

    @property
    def status(self) -> Status:
        if self.verdict is Verdict.ALLOW:
            return Status.IN_PROGRESS
        if self.verdict is Verdict.HOLD:
            return Status.HOLD
        if self.verdict is Verdict.UNKNOWN:
            return Status.UNKNOWN
        return Status.BLOCKED

    def to_dict(self) -> dict:
        return {
            "verdict": self.verdict.value,
            "reason": self.reason,
            "status": self.status.value,
            "risk_level": self.risk_level,
            "council_approvals_required": self.council_approvals_required,
            "human_approval_required": self.human_approval_required,
            "policy_revision": self.policy_revision,
            "checks": list(self.checks),
        }


class PolicyEvaluator:
    def __init__(
        self,
        constitution: Constitution,
        capabilities: CapabilityRegistry,
        founder_gate: FounderGate,
    ) -> None:
        self.constitution = constitution
        self.capabilities = capabilities
        self.founder_gate = founder_gate

    def evaluate(
        self,
        *,
        agent_id: str,
        lane_id: str,
        capability_id: str,
        action_id: str | None = None,
        allowed_capabilities: tuple[str, ...] = (),
        forbidden_capabilities: tuple[str, ...] = (),
        founder_approved: bool = False,
        council_approvals: int = 0,
    ) -> Decision:
        checks: list[str] = []
        revision = self.constitution.revision

        def decide(verdict: Verdict, reason: str, **kw) -> Decision:
            return Decision(
                verdict=verdict, reason=reason, policy_revision=revision,
                checks=tuple(checks), **kw,
            )

        # 1 ── Founder hold. Checked first: a held lane is closed to everyone.
        try:
            if self.founder_gate.is_held(lane_id):
                checks.append("founder_hold:HELD")
                return decide(Verdict.HOLD, f"lane '{lane_id}' is under a Founder HOLD")
        except FounderGateError as exc:
            # Unreadable hold state must not be read as "not held".
            checks.append("founder_hold:UNREADABLE")
            return decide(Verdict.UNKNOWN, f"Founder hold state could not be read: {exc}")
        checks.append("founder_hold:clear")

        # 2 ── Capability allowlist.
        permitted, reason = self.capabilities.permits(
            capability_id, allowed=allowed_capabilities, forbidden=forbidden_capabilities,
        )
        if not permitted:
            checks.append("capability:DENIED")
            return decide(Verdict.BLOCK, reason)
        checks.append("capability:granted")

        # 3 ── Risk classification. Undeclared risk is UNKNOWN, never low.
        lookup = action_id or capability_id
        risk_name = self.constitution.risk_for_action(lookup)
        if risk_name is None:
            checks.append("risk:UNCLASSIFIED")
            return decide(
                Verdict.UNKNOWN,
                f"action '{lookup}' has no declared risk level; unclassified actions are not authorized",
            )
        checks.append(f"risk:{risk_name}")

        try:
            risk = self.constitution.risk_level(risk_name)
        except Exception as exc:  # noqa: BLE001 - surfaced as UNKNOWN, never as allow
            checks.append("risk:UNRESOLVABLE")
            return decide(Verdict.UNKNOWN, f"risk level '{risk_name}' could not be resolved: {exc}")

        # 4 ── Prohibited actions are rejected outright.
        if risk.reject:
            checks.append("risk:PROHIBITED")
            return decide(
                Verdict.BLOCK,
                f"action '{lookup}' is classified prohibited",
                risk_level=risk_name,
                council_approvals_required=risk.council_approvals_required,
                human_approval_required=True,
            )

        # 5 ── Approval thresholds.
        if risk.human_approval_required and not founder_approved:
            checks.append("founder_approval:MISSING")
            return decide(
                Verdict.REQUIRES_FOUNDER,
                f"risk '{risk_name}' requires Founder approval before execution",
                risk_level=risk_name,
                council_approvals_required=risk.council_approvals_required,
                human_approval_required=True,
            )

        if council_approvals < risk.council_approvals_required:
            checks.append("council_approvals:INSUFFICIENT")
            return decide(
                Verdict.REQUIRES_COUNCIL,
                (
                    f"risk '{risk_name}' requires {risk.council_approvals_required} council "
                    f"approvals; {council_approvals} recorded"
                ),
                risk_level=risk_name,
                council_approvals_required=risk.council_approvals_required,
                human_approval_required=risk.human_approval_required,
            )

        checks.append("thresholds:satisfied")
        return decide(
            Verdict.ALLOW,
            f"authorized under risk '{risk_name}'",
            risk_level=risk_name,
            council_approvals_required=risk.council_approvals_required,
            human_approval_required=risk.human_approval_required,
        )
