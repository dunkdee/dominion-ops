from __future__ import annotations

import ast
import random
import unittest
from decimal import Decimal
from pathlib import Path

from apps.revenue_engine.engine import (
    AffiliateRegistry,
    RevenueLedger,
    build_site_plan,
    decision_receipt,
    propose_single_change,
    rank_opportunities,
    review_content,
    score_opportunity,
)
from apps.revenue_engine.models import (
    ActionDecision,
    AffiliateProgram,
    EvidenceState,
    Opportunity,
    ProgramStatus,
    RevenueEvent,
)


def opportunity(**overrides):
    values = dict(
        opportunity_id="opp-1",
        niche="buyer-intent niche",
        buyer_intent=0.9,
        demand=0.8,
        competition=0.3,
        economics=0.8,
        zero_capital_fit=1.0,
        original_value_fit=0.8,
        evidence_state=EvidenceState.VERIFIED,
        evidence_refs=("artifact:research-1",),
    )
    values.update(overrides)
    return Opportunity(**values)


def approved_program(**overrides):
    values = dict(
        program_id="program-1",
        name="Program One",
        status=ProgramStatus.APPROVED,
        commission_rate=Decimal("12.50"),
        cookie_days=30,
        payout_threshold=Decimal("50.00"),
        tracking_url="https://merchant.example/?ref=dominion",
        terms_ref="artifact:terms-1",
        evidence_state=EvidenceState.VERIFIED,
        evidence_refs=("artifact:approval-1",),
    )
    values.update(overrides)
    return AffiliateProgram(**values)


class OpportunityTests(unittest.TestCase):
    def test_score_is_bounded_and_deterministic(self):
        item = opportunity()
        first = score_opportunity(item)
        second = score_opportunity(item)
        self.assertEqual(first.score, second.score)
        self.assertGreaterEqual(first.score, Decimal("0"))
        self.assertLessEqual(first.score, Decimal("100"))

    def test_verified_requires_evidence(self):
        with self.assertRaises(ValueError):
            opportunity(evidence_refs=())

    def test_invalid_nan_is_rejected(self):
        with self.assertRaises(ValueError):
            opportunity(demand=float("nan"))

    def test_ranking_prefers_score_then_evidence_then_id(self):
        high = opportunity(opportunity_id="high", buyer_intent=1.0)
        low = opportunity(opportunity_id="low", buyer_intent=0.1)
        ranked = rank_opportunities([low, high])
        self.assertEqual(ranked[0].opportunity.opportunity_id, "high")

    def test_500_randomized_scores_hold_invariants(self):
        rng = random.Random(42)
        for index in range(500):
            item = opportunity(
                opportunity_id=f"rnd-{index}",
                buyer_intent=rng.random(),
                demand=rng.random(),
                competition=rng.random(),
                economics=rng.random(),
                zero_capital_fit=rng.random(),
                original_value_fit=rng.random(),
            )
            first = score_opportunity(item).score
            second = score_opportunity(item).score
            self.assertEqual(first, second)
            self.assertTrue(Decimal("0") <= first <= Decimal("100"))


class AffiliateTests(unittest.TestCase):
    def test_tracking_link_requires_verified_approval(self):
        registry = AffiliateRegistry()
        program = approved_program()
        registry.register(program)
        self.assertEqual(registry.tracking_link(program.program_id), program.tracking_url)

        unverified = AffiliateProgram(
            program_id="pending",
            name="Pending",
            status=ProgramStatus.APPLIED,
            commission_rate=Decimal("10"),
            cookie_days=7,
            payout_threshold=Decimal("25"),
        )
        registry.register(unverified)
        with self.assertRaises(PermissionError):
            registry.tracking_link("pending")

    def test_approved_program_requires_terms_and_tracking_url(self):
        with self.assertRaises(ValueError):
            approved_program(tracking_url=None)


class SiteAndContentTests(unittest.TestCase):
    def test_site_plan_is_shadow_only_and_disclosed(self):
        plan = build_site_plan(opportunity(), [approved_program()])
        self.assertEqual(plan.publication_state, "DRAFT_SHADOW")
        self.assertIn("Affiliate disclosure", plan.affiliate_disclosure)
        self.assertIn("program-1", plan.approved_program_ids)
        self.assertTrue(any(page.page_type == "disclosure" for page in plan.pages))

    def test_site_plan_rejects_unverified_affiliate_approval(self):
        program = AffiliateProgram(
            program_id="applied",
            name="Applied",
            status=ProgramStatus.APPLIED,
            commission_rate=Decimal("20"),
            cookie_days=30,
            payout_threshold=Decimal("10"),
        )
        with self.assertRaises(ValueError):
            build_site_plan(opportunity(), [program])

    def test_content_rejects_guaranteed_income_claim(self):
        review = review_content(
            "This system provides guaranteed income. Affiliate disclosure: we may earn a commission.",
            evidence_refs=("source:1",),
            has_affiliate_links=True,
            original_value_signals=("structured-comparison",),
        )
        self.assertFalse(review.allowed_for_publication)
        self.assertTrue(any("Guaranteed-income" in reason for reason in review.reasons))

    def test_content_rejects_unsupported_first_hand_claim(self):
        review = review_content("We personally tested this product and it won.", evidence_refs=())
        self.assertFalse(review.allowed_for_publication)
        self.assertTrue(any("First-hand" in reason for reason in review.reasons))

    def test_affiliate_content_requires_disclosure_and_original_value(self):
        review = review_content(
            "Our sourced comparison recommends Product A.",
            evidence_refs=("source:comparison",),
            has_affiliate_links=True,
        )
        self.assertTrue(any("Affiliate relationship" in reason for reason in review.reasons))
        self.assertTrue(any("original-value" in reason for reason in review.reasons))


class RevenueLedgerTests(unittest.TestCase):
    def test_idempotent_ingest_and_decimal_metrics(self):
        ledger = RevenueLedger()
        event = RevenueEvent(
            event_id="evt-1",
            opportunity_id="opp-1",
            impressions=1000,
            visits=100,
            affiliate_clicks=20,
            conversions=2,
            commission_accrued=Decimal("24.60"),
            payout_received=Decimal("24.60"),
            evidence_state=EvidenceState.VERIFIED,
            evidence_refs=("receipt:evt-1",),
        )
        self.assertTrue(ledger.ingest(event))
        self.assertFalse(ledger.ingest(event))
        snapshot = ledger.metrics("opp-1")
        self.assertEqual(snapshot.click_through_rate, Decimal("0.2000"))
        self.assertEqual(snapshot.conversion_rate, Decimal("0.1000"))
        self.assertEqual(snapshot.earnings_per_click, Decimal("1.2300"))
        self.assertEqual(snapshot.revenue_per_visit, Decimal("0.2460"))
        self.assertEqual(snapshot.evidence_state, EvidenceState.VERIFIED)

    def test_event_collision_with_different_facts_fails_closed(self):
        ledger = RevenueLedger()
        first = RevenueEvent(event_id="evt", opportunity_id="opp", visits=1)
        second = RevenueEvent(event_id="evt", opportunity_id="opp", visits=2)
        ledger.ingest(first)
        with self.assertRaises(ValueError):
            ledger.ingest(second)

    def test_learning_loop_proposes_exactly_one_variable(self):
        ledger = RevenueLedger()
        ledger.ingest(
            RevenueEvent(
                event_id="evt",
                opportunity_id="opp",
                impressions=100,
                visits=10,
                evidence_state=EvidenceState.INFERRED,
            )
        )
        proposal = propose_single_change(ledger.metrics("opp"))
        self.assertEqual(proposal.constraint, "click_intent")
        self.assertEqual(proposal.variable_to_change, "primary_call_to_action")
        self.assertNotIn(",", proposal.variable_to_change)


class PolicyTests(unittest.TestCase):
    def test_consequential_actions_are_blocked(self):
        for action in (
            "publish_external_content",
            "contact_customer",
            "spend_or_move_money",
            "claim_guaranteed_income",
            "enroll_affiliate_program",
            "deploy_production",
        ):
            receipt = decision_receipt(action, ("policy:test",))
            self.assertEqual(receipt.decision, ActionDecision.BLOCKED)
            self.assertEqual(len(receipt.receipt_sha256), 64)

    def test_unknown_action_fails_closed(self):
        self.assertEqual(decision_receipt("invent_new_power").decision, ActionDecision.BLOCKED)

    def test_analysis_action_is_simulation_only(self):
        receipt = decision_receipt("analyze_funnel")
        self.assertEqual(receipt.decision, ActionDecision.SIMULATION_ONLY)

    def test_internal_capability_names_do_not_expand_registry_authority(self):
        for action in ("rank_opportunities", "build_site_plan", "review_content", "propose_learning_change"):
            self.assertEqual(decision_receipt(action).decision, ActionDecision.BLOCKED)


class StaticHardeningTests(unittest.TestCase):
    def test_package_has_no_network_process_or_dynamic_execution_imports(self):
        package = Path("apps/revenue_engine")
        forbidden_import_roots = {
            "requests",
            "httpx",
            "socket",
            "subprocess",
            "paramiko",
            "ftplib",
            "boto3",
            "selenium",
            "playwright",
        }
        forbidden_calls = {"eval", "exec", "compile"}
        for path in package.glob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        self.assertNotIn(alias.name.split(".")[0], forbidden_import_roots, path)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    self.assertNotIn(node.module.split(".")[0], forbidden_import_roots, path)
                elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                    self.assertNotIn(node.func.id, forbidden_calls, path)


if __name__ == "__main__":
    unittest.main()
