from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from control_plane.canonical import sha256_json
from control_plane.council import CouncilError, aggregate_council_decision
from control_plane.governor import Governor, GovernorPaths
from control_plane.ledger import AppendOnlyLedger, LedgerError
from control_plane.onboarding import validate_candidate
from control_plane.revenue_simulation import simulate_revenue_funnel


class FixtureMixin:
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.authority = {
            "human_final_authority": "human_overseer",
            "default_behavior": "deny",
            "independent_veto_domains": ["law_governance", "security_risk"],
            "risk_levels": {
                "low": {"council_approvals_required": 0, "human_approval_required": False},
                "moderate": {"council_approvals_required": 2, "human_approval_required": False},
                "high": {"council_approvals_required": 4, "human_approval_required": False},
                "critical": {"council_approvals_required": 5, "human_approval_required": True},
                "prohibited": {"council_approvals_required": 5, "human_approval_required": True, "action": "reject"},
            },
            "actions": [
                {"id": "read_public_information", "risk": "low", "allowed_roles": ["research"], "constraints": ["record_sources"]},
                {"id": "read_private_operational_data", "risk": "moderate", "allowed_roles": ["coordinator"], "constraints": ["least_privilege", "audit_log"]},
                {"id": "deploy_production", "risk": "critical", "allowed_roles": ["human_overseer"], "constraints": ["unanimous_council", "human_approval"]},
                {"id": "expand_own_permissions", "risk": "prohibited", "allowed_roles": [], "constraints": ["human_admin_only"]},
            ],
        }
        self.registry = {"agents": [
            {"id": "research", "role": "research", "state": "LIMITED_PRODUCTION", "evidence_required": True},
            {"id": "coordinator", "role": "coordinator", "state": "LIMITED_PRODUCTION", "evidence_required": True},
            {"id": "human_overseer", "role": "human_overseer", "state": "PRODUCTION", "evidence_required": True},
        ]}
        self.council = {
            "councils": [
                {"id": "truth_evidence", "veto": False},
                {"id": "law_governance", "veto": True},
                {"id": "security_risk", "veto": True},
                {"id": "engineering_reliability", "veto": False},
                {"id": "business_human_impact", "veto": False},
            ],
            "thresholds": {
                "low": {"required_approvals": 0, "human_required": False},
                "moderate": {"required_approvals": 2, "human_required": False},
                "high": {"required_approvals": 4, "human_required": False},
                "critical": {"required_approvals": 5, "human_required": True},
            },
        }
        self.gates = {
            "mode": "shadow_only",
            "external_execution_enabled": False,
            "registry_mutation_enabled": False,
            "blocked_actions": ["deploy_production"],
            "promotion_requirements": ["human_approval_recorded"],
        }
        for name, value in (("authority.json", self.authority), ("registry.json", self.registry), ("council.json", self.council), ("gates.json", self.gates)):
            (self.root / name).write_text(json.dumps(value), encoding="utf-8")
        self.governor = Governor(GovernorPaths(authority=self.root / "authority.json", registry=self.root / "registry.json", council=self.root / "council.json", activation_gates=self.root / "gates.json"))

    def tearDown(self) -> None:
        self.temp.cleanup()


class GovernorTests(FixtureMixin, unittest.TestCase):
    def test_low_risk_policy_allows_but_shadow_execution_stays_disabled(self) -> None:
        result = self.governor.evaluate({"actor_id": "research", "action_id": "read_public_information", "evidence": ["source:official"], "satisfied_constraints": ["record_sources"], "legal_status": "NOT_APPLICABLE", "council_approvals": []})
        self.assertEqual(result["decision"], "ALLOW")
        self.assertFalse(result["execution_authorized"])

    def test_unknown_action_is_denied_by_default(self) -> None:
        result = self.governor.evaluate({"actor_id": "research", "action_id": "invented_action", "evidence": ["source"], "satisfied_constraints": [], "legal_status": "NOT_APPLICABLE", "council_approvals": []})
        self.assertEqual(result["decision"], "DENY")
        self.assertIn("unknown_action_default_deny", result["reasons"])

    def test_moderate_action_holds_without_resolved_legal_status(self) -> None:
        result = self.governor.evaluate({"actor_id": "coordinator", "action_id": "read_private_operational_data", "evidence": ["ticket-1"], "satisfied_constraints": ["least_privilege", "audit_log"], "legal_status": "UNRESOLVED", "council_approvals": [{"council_id": "truth_evidence", "decision": "APPROVE", "evidence": "e1"}, {"council_id": "security_risk", "decision": "APPROVE", "evidence": "e2"}]})
        self.assertEqual(result["decision"], "HOLD")
        self.assertIn("legal_status_fail_closed", result["reasons"])

    def test_security_veto_denies(self) -> None:
        result = self.governor.evaluate({"actor_id": "coordinator", "action_id": "read_private_operational_data", "evidence": ["ticket-1"], "satisfied_constraints": ["least_privilege", "audit_log"], "legal_status": "RESOLVED", "council_approvals": [{"council_id": "truth_evidence", "decision": "APPROVE", "evidence": "e1"}, {"council_id": "security_risk", "decision": "VETO", "evidence": "e2"}]})
        self.assertEqual(result["decision"], "DENY")
        self.assertIn("security_risk_veto", result["reasons"])

    def test_production_deployment_is_held_by_activation_gate(self) -> None:
        result = self.governor.evaluate({"actor_id": "human_overseer", "action_id": "deploy_production", "evidence": ["run-1"], "satisfied_constraints": ["unanimous_council", "human_approval"], "legal_status": "RESOLVED", "council_approvals": [], "human_approval": {"approved": True, "approver": "human_overseer", "evidence": "approval-1"}})
        self.assertEqual(result["decision"], "HOLD")
        self.assertIn("runtime_activation_gate", result["reasons"])


class LedgerTests(unittest.TestCase):
    def test_append_and_verify_hash_chain(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            ledger = AppendOnlyLedger(Path(temp) / "ledger.jsonl")
            ledger.append(event_type="policy_decision", actor="governor", payload={"decision": "HOLD"}, timestamp="2026-01-01T00:00:00+00:00")
            ledger.append(event_type="council_decision", actor="coordinator", payload={"decision": "APPROVE"}, timestamp="2026-01-01T00:01:00+00:00")
            verification = ledger.verify()
            self.assertEqual(verification["record_count"], 2)
            self.assertEqual(len(verification["head_hash"]), 64)

    def test_tampering_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "ledger.jsonl"
            ledger = AppendOnlyLedger(path)
            ledger.append(event_type="test", actor="sentinel", payload={"value": 1}, timestamp="2026-01-01T00:00:00+00:00")
            path.write_text(path.read_text(encoding="utf-8").replace('"value":1', '"value":2'), encoding="utf-8")
            with self.assertRaises(LedgerError):
                ledger.verify()


class CouncilTests(FixtureMixin, unittest.TestCase):
    def _reviews(self, proposal: dict, security_decision: str = "APPROVE") -> list[dict]:
        proposal_hash = sha256_json(proposal)
        decisions = {"truth_evidence": "APPROVE", "law_governance": "APPROVE", "security_risk": security_decision, "engineering_reliability": "APPROVE", "business_human_impact": "APPROVE"}
        return [{"council_id": council_id, "reviewer": f"council_{council_id}", "proposal_hash": proposal_hash, "decision": decision, "evidence": [f"evidence:{council_id}"], "rationale": "independent review completed"} for council_id, decision in decisions.items()]

    def test_critical_requires_unanimous_and_human(self) -> None:
        proposal = {"action": "critical-change"}
        result = aggregate_council_decision(proposal, self._reviews(proposal), risk="critical", council_policy=self.council, human_approval={"approved": True, "approver": "human_overseer", "evidence": "approval-1"})
        self.assertEqual(result["decision"], "APPROVE")

    def test_independent_veto_wins(self) -> None:
        proposal = {"action": "critical-change"}
        result = aggregate_council_decision(proposal, self._reviews(proposal, security_decision="VETO"), risk="critical", council_policy=self.council, human_approval={"approved": True, "approver": "human_overseer", "evidence": "approval-1"})
        self.assertEqual(result["decision"], "VETO")
        self.assertEqual(result["vetoes"], ["security_risk"])

    def test_duplicate_review_rejected(self) -> None:
        proposal = {"action": "change"}
        reviews = self._reviews(proposal)
        reviews.append(dict(reviews[0]))
        with self.assertRaises(CouncilError):
            aggregate_council_decision(proposal, reviews, risk="high", council_policy=self.council)


class OnboardingTests(FixtureMixin, unittest.TestCase):
    def candidate(self) -> dict:
        return {"id": "offer-analysis-agent", "role": "revenue_analysis", "purpose": "Analyze offers without external execution.", "owner": "human_overseer", "requested_actions": ["read_public_information"], "prohibited_actions": ["spend_or_move_money"], "input_contract": {"type": "scenario"}, "output_contract": {"type": "report"}, "success_metrics": ["evidence coverage"], "failure_modes": ["missing evidence"], "data_classification": "INTERNAL", "tool_allowlist": ["read_repository"], "escalates_to": "coordinator"}

    def test_candidate_is_only_eligible_for_spec_review(self) -> None:
        result = validate_candidate(self.candidate(), self.registry, self.authority)
        self.assertEqual(result["status"], "ELIGIBLE_FOR_SPEC_REVIEW")
        self.assertFalse(result["registry_mutated"])
        self.assertFalse(result["production_authority_granted"])

    def test_wildcard_and_production_requests_rejected(self) -> None:
        candidate = self.candidate()
        candidate["requested_actions"] = ["*", "deploy_production"]
        candidate["tool_allowlist"] = ["*"]
        result = validate_candidate(candidate, self.registry, self.authority)
        self.assertEqual(result["status"], "REJECTED")
        self.assertIn("wildcard_action_forbidden", result["errors"])
        self.assertIn("wildcard_tool_forbidden", result["errors"])
        self.assertIn("activation_action_forbidden:deploy_production", result["errors"])


class RevenueSimulationTests(unittest.TestCase):
    def test_simulation_has_no_external_side_effects(self) -> None:
        result = simulate_revenue_funnel({"name": "baseline", "visitors": 1000, "visitor_to_lead_rate": 0.1, "lead_to_qualified_rate": 0.5, "qualified_to_proposal_rate": 0.5, "proposal_to_purchase_rate": 0.2, "average_order_value": 100, "variable_cost_per_purchase": 10, "fixed_cost": 50})
        self.assertEqual(result["mode"], "SIMULATION_ONLY")
        self.assertEqual(result["economics"]["revenue"], "500.00")
        self.assertEqual(result["economics"]["gross_profit"], "400.00")
        self.assertEqual(result["external_actions"], [])
        self.assertFalse(result["money_moved"])
        self.assertFalse(result["customers_contacted"])

    def test_invalid_rate_rejected(self) -> None:
        with self.assertRaises(ValueError):
            simulate_revenue_funnel({"visitors": 1, "visitor_to_lead_rate": 1.1, "lead_to_qualified_rate": 0, "qualified_to_proposal_rate": 0, "proposal_to_purchase_rate": 0, "average_order_value": 0, "variable_cost_per_purchase": 0, "fixed_cost": 0})


if __name__ == "__main__":
    unittest.main()
