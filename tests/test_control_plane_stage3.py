from __future__ import annotations

import unittest

from control_plane.cohort import validate_shadow_cohort
from control_plane.proposals import aggregate_bound_reviews, bind_council_review, prepare_proposal_envelope
from control_plane.shadow_revenue import run_shadow_revenue_experiment


class Stage3Fixture(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = {
            "agents": [
                {"id": "human_overseer", "role": "human_overseer", "state": "PRODUCTION", "permissions": ["approve_policy"], "evidence_required": True},
                {"id": "coordinator", "role": "coordinator", "state": "LIMITED_PRODUCTION", "permissions": ["read_operational_state", "route_review"], "evidence_required": True},
                {"id": "revenue_operations", "role": "revenue_operations", "state": "SIMULATION", "permissions": ["analyze_funnel", "prepare_experiment", "measure_metrics"], "evidence_required": True},
                {"id": "research", "role": "research", "state": "LIMITED_PRODUCTION", "permissions": ["read_public_information", "record_sources", "mark_uncertainty"], "evidence_required": True},
                {"id": "council_truth_evidence", "role": "truth_evidence", "state": "REGISTERED", "permissions": ["review_evidence", "issue_hold", "vote"], "evidence_required": True},
                {"id": "council_law_governance", "role": "law_governance", "state": "REGISTERED", "permissions": ["review_legal_governance", "issue_hold", "veto", "vote"], "evidence_required": True},
                {"id": "council_security_risk", "role": "security_risk", "state": "REGISTERED", "permissions": ["review_security", "issue_hold", "veto", "vote"], "evidence_required": True},
                {"id": "council_engineering_reliability", "role": "engineering_reliability", "state": "REGISTERED", "permissions": ["review_engineering", "issue_hold", "vote"], "evidence_required": True},
                {"id": "council_business_human_impact", "role": "business_human_impact", "state": "REGISTERED", "permissions": ["review_business_impact", "issue_hold", "vote"], "evidence_required": True},
            ]
        }
        self.authority = {
            "actions": [
                {"id": "read_private_operational_data", "risk": "moderate", "allowed_roles": ["coordinator"], "constraints": ["least_privilege", "audit_log"]}
            ]
        }
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
        self.gates = {"mode": "shadow_only", "external_execution_enabled": False, "registry_mutation_enabled": False}
        self.tools = {
            "default_behavior": "deny",
            "tools": [
                {"id": "repository_read", "external_effect": "read_only", "allowed_modes": ["SHADOW"]},
                {"id": "schema_validation", "external_effect": "none", "allowed_modes": ["SHADOW"]},
                {"id": "local_calculation", "external_effect": "none", "allowed_modes": ["SHADOW"]},
                {"id": "evidence_ledger_append", "external_effect": "none", "allowed_modes": ["SHADOW"]},
            ],
        }

    def cohort(self) -> dict:
        return {
            "cohort_id": "pilot_shadow",
            "mode": "SHADOW",
            "owner": "human_overseer",
            "objective": "Validate controlled shadow assignments.",
            "entry_evidence": ["merged-stage2"],
            "shared_prohibited_actions": [
                "merge_to_main",
                "deploy_production",
                "publish_external_content",
                "contact_customer_or_claimant",
                "spend_or_move_money",
                "sign_file_or_submit_legal_document",
                "reactivate_suspended_or_retired_agent",
            ],
            "exit_criteria": ["evidence records pass"],
            "assignments": [
                {
                    "agent_id": "revenue_operations",
                    "duties": ["analyze_funnel", "prepare_experiment"],
                    "tool_allowlist": ["repository_read", "schema_validation", "local_calculation", "evidence_ledger_append"],
                    "data_classification": ["INTERNAL"],
                    "escalates_to": "coordinator",
                    "lifecycle_change_requested": False,
                }
            ],
        }

    def proposal(self) -> dict:
        return {
            "proposal_id": "revenue_shadow_v1",
            "proposer_id": "coordinator",
            "objective": "Review verified operational data without external execution.",
            "requested_action": "read_private_operational_data",
            "risk": "moderate",
            "evidence": ["snapshot:1"],
            "assumptions": [],
            "unknowns": ["future conversion is unknown"],
            "rollback_plan": {"trigger": "evidence conflict", "procedure": "discard output"},
            "success_criteria": ["two independent approvals"],
            "external_effects": False,
        }

    def experiment(self, kind: str = "SYNTHETIC_TEST") -> dict:
        scenario = {
            "visitors": 1000,
            "visitor_to_lead_rate": 0.1,
            "lead_to_qualified_rate": 0.5,
            "qualified_to_proposal_rate": 0.5,
            "proposal_to_purchase_rate": 0.2,
            "average_order_value": 100,
            "variable_cost_per_purchase": 10,
            "fixed_cost": 50,
        }
        candidate = dict(scenario)
        candidate["proposal_to_purchase_rate"] = 0.3
        return {
            "experiment_id": "shadow_test",
            "owner_id": "revenue_operations",
            "proposal_hash": "a" * 64,
            "source_snapshot": {"kind": kind, "as_of": "2026-07-24T00:00:00Z", "evidence": ["snapshot:1"]},
            "baseline": scenario,
            "candidate": candidate,
            "guardrails": {"minimum_visitors": 500, "minimum_gross_margin": 0.4, "minimum_gross_profit_delta": 100, "maximum_fixed_cost": 100},
        }


class CohortTests(Stage3Fixture):
    def test_cohort_is_reviewable_without_promotion(self) -> None:
        result = validate_shadow_cohort(self.cohort(), self.registry, self.tools, self.gates)
        self.assertEqual(result["status"], "ELIGIBLE_FOR_SHADOW_ASSIGNMENT_REVIEW")
        self.assertFalse(result["registry_mutated"])
        self.assertFalse(result["agents_promoted"])
        self.assertFalse(result["runtime_started"])
        self.assertFalse(result["external_execution_authorized"])

    def test_unknown_tool_and_lifecycle_change_fail_closed(self) -> None:
        manifest = self.cohort()
        manifest["assignments"][0]["tool_allowlist"] = ["unknown_tool"]
        manifest["assignments"][0]["lifecycle_change_requested"] = True
        result = validate_shadow_cohort(manifest, self.registry, self.tools, self.gates)
        self.assertEqual(result["status"], "REJECTED")
        self.assertTrue(any("unknown_tool" in item for item in result["errors"]))
        self.assertTrue(any("lifecycle_change_forbidden" in item for item in result["errors"]))


class ProposalTests(Stage3Fixture):
    def test_proposal_and_reviews_are_hash_bound(self) -> None:
        envelope = prepare_proposal_envelope(self.proposal(), self.registry, self.authority, self.gates)
        self.assertEqual(envelope["status"], "READY_FOR_INDEPENDENT_COUNCIL_REVIEW")
        reviews = []
        for council_id, reviewer in (("truth_evidence", "council_truth_evidence"), ("security_risk", "council_security_risk")):
            bound = bind_council_review(
                envelope,
                {"council_id": council_id, "reviewer_agent_id": reviewer, "decision": "APPROVE", "evidence": [f"evidence:{council_id}"], "rationale": "Independent review passed.", "conditions": []},
                self.registry,
                self.council,
            )
            self.assertEqual(bound["status"], "BOUND")
            self.assertEqual(bound["proposal_hash"], envelope["proposal_hash"])
            reviews.append(bound)
        decision = aggregate_bound_reviews(envelope, reviews, council_policy=self.council)
        self.assertEqual(decision["decision"], "APPROVE")
        self.assertFalse(decision["external_execution_authorized"])

    def test_tampered_bound_review_is_rejected(self) -> None:
        envelope = prepare_proposal_envelope(self.proposal(), self.registry, self.authority, self.gates)
        bound = bind_council_review(
            envelope,
            {"council_id": "truth_evidence", "reviewer_agent_id": "council_truth_evidence", "decision": "APPROVE", "evidence": ["e1"], "rationale": "Passed.", "conditions": []},
            self.registry,
            self.council,
        )
        bound["decision"] = "VETO"
        with self.assertRaises(ValueError):
            aggregate_bound_reviews(envelope, [bound], council_policy=self.council)

    def test_external_effect_proposal_is_rejected(self) -> None:
        proposal = self.proposal()
        proposal["external_effects"] = True
        result = prepare_proposal_envelope(proposal, self.registry, self.authority, self.gates)
        self.assertEqual(result["status"], "REJECTED")
        self.assertIn("shadow_proposal_must_have_no_external_effects", result["errors"])


class ShadowRevenueTests(Stage3Fixture):
    def test_synthetic_fixture_can_never_support_promotion(self) -> None:
        result = run_shadow_revenue_experiment(self.experiment())
        self.assertEqual(result["decision"], "TEST_ONLY")
        self.assertFalse(result["promotion_authorized"])
        self.assertEqual(result["external_actions"], [])
        self.assertFalse(result["money_moved"])
        self.assertFalse(result["customers_contacted"])

    def test_verified_historical_inputs_can_only_reach_council_review(self) -> None:
        result = run_shadow_revenue_experiment(self.experiment("HISTORICAL_VERIFIED"))
        self.assertEqual(result["decision"], "ELIGIBLE_FOR_COUNCIL_REVIEW")
        self.assertFalse(result["promotion_authorized"])
        self.assertFalse(result["production_changes"])

    def test_missing_source_evidence_holds(self) -> None:
        experiment = self.experiment("HISTORICAL_VERIFIED")
        experiment["source_snapshot"]["evidence"] = []
        result = run_shadow_revenue_experiment(experiment)
        self.assertEqual(result["decision"], "HOLD")
        self.assertIn("source_evidence_must_be_nonempty_string_list", result["errors"])


if __name__ == "__main__":
    unittest.main()
