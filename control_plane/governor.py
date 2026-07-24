"""Deterministic default-deny policy evaluator for Dominion actions."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .canonical import sha256_json

DECISIONS = {"ALLOW", "HOLD", "DENY"}
APPROVAL_DECISIONS = {"APPROVE", "APPROVE_WITH_CONDITIONS"}
VETO_DECISIONS = {"VETO"}


class PolicyConfigurationError(RuntimeError):
    """Raised when policy files are invalid or inconsistent."""


def _load_json(path: str | Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise PolicyConfigurationError(f"{path} must contain a JSON object")
    return value


@dataclass(frozen=True)
class GovernorPaths:
    authority: Path
    registry: Path
    council: Path
    activation_gates: Path


class Governor:
    def __init__(self, paths: GovernorPaths):
        self.authority = _load_json(paths.authority)
        self.registry = _load_json(paths.registry)
        self.council = _load_json(paths.council)
        self.activation_gates = _load_json(paths.activation_gates)
        self._validate_configuration()

    def _validate_configuration(self) -> None:
        if self.authority.get("default_behavior") != "deny":
            raise PolicyConfigurationError("authority policy must be default-deny")
        if self.authority.get("human_final_authority") != "human_overseer":
            raise PolicyConfigurationError("human_overseer must remain final authority")
        if self.activation_gates.get("mode") not in {"simulation_only", "shadow_only"}:
            raise PolicyConfigurationError("runtime activation mode must be simulation_only or shadow_only")
        if self.activation_gates.get("mode") == "shadow_only" and self.activation_gates.get("external_execution_enabled") is not False:
            raise PolicyConfigurationError("shadow_only mode must disable external execution")

    def _actor(self, actor_id: str) -> dict[str, Any] | None:
        for agent in self.registry.get("agents", []):
            if isinstance(agent, dict) and agent.get("id") == actor_id:
                return agent
        return None

    def _action(self, action_id: str) -> dict[str, Any] | None:
        for action in self.authority.get("actions", []):
            if isinstance(action, dict) and action.get("id") == action_id:
                return action
        return None

    def _decision(
        self,
        request: dict[str, Any],
        *,
        decision: str,
        risk: str | None,
        reasons: list[str],
        missing_requirements: list[str] | None = None,
    ) -> dict[str, Any]:
        if decision not in DECISIONS:
            raise ValueError(f"invalid decision: {decision}")
        external_execution_enabled = self.activation_gates.get("external_execution_enabled") is True
        result = {
            "decision": decision,
            "request_hash": sha256_json(request),
            "actor_id": request.get("actor_id"),
            "action_id": request.get("action_id"),
            "risk": risk,
            "reasons": reasons,
            "missing_requirements": sorted(set(missing_requirements or [])),
            "execution_authorized": decision == "ALLOW" and external_execution_enabled,
        }
        result["decision_hash"] = sha256_json(result)
        return result

    def evaluate(self, request: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(request, dict):
            raise TypeError("request must be an object")

        actor_id = request.get("actor_id")
        action_id = request.get("action_id")
        if not isinstance(actor_id, str) or not actor_id:
            return self._decision(request, decision="DENY", risk=None, reasons=["missing_or_invalid_actor_id"])
        if not isinstance(action_id, str) or not action_id:
            return self._decision(request, decision="DENY", risk=None, reasons=["missing_or_invalid_action_id"])

        actor = self._actor(actor_id)
        if actor is None:
            return self._decision(request, decision="DENY", risk=None, reasons=["unknown_actor"])
        if actor.get("state") in {"SUSPENDED", "RETIRED"}:
            return self._decision(request, decision="DENY", risk=None, reasons=["actor_not_active"])

        action = self._action(action_id)
        if action is None:
            return self._decision(request, decision="DENY", risk=None, reasons=["unknown_action_default_deny"])

        risk = action.get("risk")
        risk_policy = self.authority.get("risk_levels", {}).get(risk)
        if not isinstance(risk_policy, dict):
            return self._decision(request, decision="DENY", risk=risk, reasons=["invalid_risk_configuration"])
        if risk == "prohibited" or risk_policy.get("action") == "reject":
            return self._decision(request, decision="DENY", risk=risk, reasons=["action_prohibited"])

        actor_role = actor.get("role")
        if actor_role not in action.get("allowed_roles", []):
            return self._decision(request, decision="DENY", risk=risk, reasons=["role_not_authorized"])

        blocked_actions = set(self.activation_gates.get("blocked_actions", []))
        if action_id in blocked_actions:
            return self._decision(
                request,
                decision="HOLD",
                risk=risk,
                reasons=["runtime_activation_gate"],
                missing_requirements=self.activation_gates.get("promotion_requirements", []),
            )

        evidence = request.get("evidence", [])
        if not isinstance(evidence, list) or not all(isinstance(item, str) and item for item in evidence):
            return self._decision(request, decision="DENY", risk=risk, reasons=["invalid_evidence_format"])
        if actor.get("evidence_required") is True and not evidence:
            return self._decision(request, decision="HOLD", risk=risk, reasons=["missing_evidence"], missing_requirements=["evidence"])

        required_constraints = set(action.get("constraints", []))
        satisfied_value = request.get("satisfied_constraints", [])
        if not isinstance(satisfied_value, list) or not all(isinstance(item, str) and item for item in satisfied_value):
            return self._decision(request, decision="DENY", risk=risk, reasons=["invalid_constraint_format"])
        satisfied_constraints = set(satisfied_value)
        missing_constraints = sorted(required_constraints - satisfied_constraints)
        if missing_constraints:
            return self._decision(request, decision="HOLD", risk=risk, reasons=["constraints_unsatisfied"], missing_requirements=missing_constraints)

        if "data_classification" in required_constraints and request.get("data_classification") not in {"PUBLIC", "INTERNAL", "CONFIDENTIAL", "RESTRICTED"}:
            return self._decision(request, decision="HOLD", risk=risk, reasons=["unknown_data_classification"], missing_requirements=["data_classification"])

        legal_status = request.get("legal_status", "UNRESOLVED")
        if legal_status in {"UNRESOLVED", "CONFLICTED", "REQUIRES_COUNSEL"} and risk in {"moderate", "high", "critical"}:
            return self._decision(request, decision="HOLD", risk=risk, reasons=["legal_status_fail_closed"], missing_requirements=["resolved_legal_status"])

        approvals = request.get("council_approvals", [])
        if not isinstance(approvals, list):
            return self._decision(request, decision="DENY", risk=risk, reasons=["invalid_council_approvals"])

        known_councils = {item.get("id") for item in self.council.get("councils", []) if isinstance(item, dict)}
        approval_by_council: dict[str, str] = {}
        for approval in approvals:
            if not isinstance(approval, dict):
                return self._decision(request, decision="DENY", risk=risk, reasons=["invalid_council_approval_record"])
            council_id = approval.get("council_id")
            approval_decision = approval.get("decision")
            evidence_reference = approval.get("evidence")
            if council_id not in known_councils:
                return self._decision(request, decision="DENY", risk=risk, reasons=["unknown_council_approval"])
            if council_id in approval_by_council:
                return self._decision(request, decision="DENY", risk=risk, reasons=["duplicate_council_approval"])
            if approval_decision not in {"APPROVE", "APPROVE_WITH_CONDITIONS", "VETO", "HOLD", "ABSTAIN"} or not evidence_reference:
                return self._decision(request, decision="DENY", risk=risk, reasons=["invalid_council_approval_record"])
            approval_by_council[council_id] = approval_decision

        for veto_domain in self.authority.get("independent_veto_domains", []):
            if approval_by_council.get(veto_domain) in VETO_DECISIONS:
                return self._decision(request, decision="DENY", risk=risk, reasons=[f"{veto_domain}_veto"])

        approved_count = sum(1 for value in approval_by_council.values() if value in APPROVAL_DECISIONS)
        required_approvals = int(risk_policy.get("council_approvals_required", 0))
        if approved_count < required_approvals:
            return self._decision(request, decision="HOLD", risk=risk, reasons=["insufficient_council_approvals"], missing_requirements=[f"council_approvals:{required_approvals - approved_count}"])

        if risk_policy.get("human_approval_required") is True:
            human_approval = request.get("human_approval", {})
            if not (isinstance(human_approval, dict) and human_approval.get("approved") is True and human_approval.get("approver") == "human_overseer" and isinstance(human_approval.get("evidence"), str) and human_approval.get("evidence")):
                return self._decision(request, decision="HOLD", risk=risk, reasons=["human_approval_required"], missing_requirements=["recorded_human_overseer_approval"])

        return self._decision(request, decision="ALLOW", risk=risk, reasons=["all_policy_gates_satisfied"])
