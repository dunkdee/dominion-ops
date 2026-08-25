from __future__ import annotations

import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from apps.revenue_engine.engine import (
    AffiliateRegistry,
    RevenueLedger,
    _sha256_of,
    decision_receipt,
    run_compounding_lane,
    run_fast_cash_lane,
)
from apps.revenue_engine.models import (
    ActionDecision,
    AffiliateProgram,
    ApprovedProgramSnapshot,
    CampaignAsset,
    DraftInput,
    EvidenceState,
    KeywordEvidence,
    MetricSnapshot,
    Opportunity,
    ProgramStatus,
    RevenueEvent,
    require_sha256_digest,
)


AS_OF = datetime(2026, 8, 25, 12, 0, tzinfo=timezone.utc)


def verified_opportunity(**overrides) -> Opportunity:
    values = {
        "opportunity_id": "opp-lanes",
        "niche": "high-intent evidence-backed offers",
        "buyer_intent": 0.92,
        "demand": 0.85,
        "competition": 0.35,
        "economics": 0.81,
        "zero_capital_fit": 0.95,
        "original_value_fit": 0.88,
        "evidence_state": EvidenceState.VERIFIED,
        "evidence_refs": ("research:opportunity",),
    }
    values.update(overrides)
    return Opportunity(**values)


def campaign_asset(asset_id: str = "asset-1", **overrides) -> CampaignAsset:
    values = {
        "asset_id": asset_id,
        "title": f"Evidence Guide {asset_id}",
        "asset_type": "existing_content",
        "url_slug": f"/{asset_id}/",
        "evidence_state": EvidenceState.VERIFIED,
        "evidence_refs": (f"asset-evidence:{asset_id}",),
        "restrictions": (),
    }
    values.update(overrides)
    return CampaignAsset(**values)


def affiliate_program(
    program_id: str = "program-1", **overrides
) -> AffiliateProgram:
    values = {
        "program_id": program_id,
        "name": f"Program {program_id}",
        "status": ProgramStatus.APPROVED,
        "commission_rate": Decimal("12.5"),
        "cookie_days": 30,
        "payout_threshold": Decimal("25"),
        "tracking_url": f"https://merchant.example/{program_id}?ref=dominion",
        "terms_ref": f"terms:{program_id}",
        "evidence_state": EvidenceState.VERIFIED,
        "evidence_refs": (f"approval:{program_id}",),
        "restrictions": (),
    }
    values.update(overrides)
    return AffiliateProgram(**values)


def keyword(
    head_term: str = "buyer intent guide", **overrides
) -> KeywordEvidence:
    values = {
        "head_term": head_term,
        "variants": (head_term, f"best {head_term}"),
        "buyer_intent_score": 0.9,
        "evidence_state": EvidenceState.VERIFIED,
        "evidence_refs": (f"keyword-source:{head_term}",),
        "verified_at": (AS_OF - timedelta(hours=1)).isoformat(),
        "ttl_seconds": 7200,
    }
    values.update(overrides)
    return KeywordEvidence(**values)


def draft_input(
    asset_id: str = "asset-1",
    *,
    channel: str = "search",
    text: str = "A sourced comparison of qualified options for careful buyers.",
    cta: str = "Read the sourced comparison",
) -> DraftInput:
    return DraftInput(
        asset_id=asset_id,
        channel=channel,
        proposed_text=text,
        cta=cta,
        evidence_refs=("draft-source:comparison",),
    )


def affiliate_draft(
    asset_id: str = "asset-1",
    program_id: str = "program-1",
    *,
    channel: str = "search",
    text: str = (
        "Affiliate disclosure: we may earn a commission. "
        "This sourced comparison explains the decision criteria."
    ),
) -> DraftInput:
    return DraftInput(
        asset_id=asset_id,
        channel=channel,
        proposed_text=text,
        cta="Review the sourced comparison",
        evidence_refs=("draft-source:affiliate-comparison",),
        has_affiliate_links=True,
        affiliate_program_id=program_id,
        original_value_signals=("structured-comparison",),
    )


def metric_snapshot(**overrides) -> MetricSnapshot:
    values = {
        "opportunity_id": "opp-lanes",
        "impressions": 1000,
        "visits": 100,
        "affiliate_clicks": 20,
        "conversions": 2,
        "commission_accrued": Decimal("24.60"),
        "payout_received": Decimal("0"),
        "click_through_rate": Decimal("0.2"),
        "conversion_rate": Decimal("0.1"),
        "earnings_per_click": Decimal("1.23"),
        "revenue_per_visit": Decimal("0.246"),
        "evidence_state": EvidenceState.VERIFIED,
        "evidence_refs": ("metrics:verified-export",),
    }
    values.update(overrides)
    return MetricSnapshot(**values)


def run_compounding(**overrides):
    values = {
        "opportunity": verified_opportunity(),
        "programs": (affiliate_program(),),
        "keyword_evidence": (keyword(),),
        "consent_mechanism": "Explicit unchecked opt-in checkbox",
        "value_exchange": "Evidence-backed buyer guide",
        "email_evidence_refs": ("consent-policy:v1",),
        "as_of": AS_OF,
    }
    values.update(overrides)
    return run_compounding_lane(**values)


class DigestAndModelInvariantTests(unittest.TestCase):
    def test_sha256_validator_is_exact_lowercase_hex(self):
        self.assertEqual(require_sha256_digest("x", "a" * 64), "a" * 64)
        for invalid in ("a" * 63, "a" * 65, "A" * 64, "g" * 64):
            with self.subTest(invalid=invalid[:8]):
                with self.assertRaises(ValueError):
                    require_sha256_digest("x", invalid)

    def test_canonical_json_rejects_nan_and_unknown_types(self):
        with self.assertRaises(ValueError):
            _sha256_of({"value": float("nan")})
        with self.assertRaises(TypeError):
            _sha256_of({"value": {"not", "json"}})

    def test_opportunity_strips_identity_before_hash_flows(self):
        item = verified_opportunity(
            opportunity_id="  opp-lanes  ", niche="  niche  "
        )
        self.assertEqual(item.opportunity_id, "opp-lanes")
        self.assertEqual(item.niche, "niche")

    def test_draft_input_rejects_non_bool_and_affiliate_field_when_false(self):
        with self.assertRaises(TypeError):
            DraftInput(
                asset_id="a",
                channel="search",
                proposed_text="text",
                cta="cta",
                evidence_refs=(),
                has_affiliate_links=1,
            )
        with self.assertRaises(ValueError):
            DraftInput(
                asset_id="a",
                channel="search",
                proposed_text="text",
                cta="cta",
                evidence_refs=(),
                affiliate_program_id="",
            )

    def test_approved_snapshot_fails_closed(self):
        valid = ApprovedProgramSnapshot(
            program_id="p",
            status=ProgramStatus.APPROVED,
            evidence_state=EvidenceState.VERIFIED,
            evidence_refs=("approval:p",),
            terms_ref="terms:p",
            tracking_url="https://merchant.example/p",
        )
        with self.assertRaises(ValueError):
            replace(valid, status=ProgramStatus.APPLIED)
        with self.assertRaises(ValueError):
            replace(valid, evidence_state=EvidenceState.INFERRED)
        with self.assertRaises(ValueError):
            replace(valid, terms_ref=" ")

    def test_metric_snapshot_normalizes_scope_and_evidence(self):
        snapshot = metric_snapshot(
            opportunity_id="  opp-lanes  ",
            evidence_refs=(" ref:a ", "ref:a", "ref:b"),
        )
        self.assertEqual(snapshot.opportunity_id, "opp-lanes")
        self.assertEqual(snapshot.evidence_refs, ("ref:a", "ref:b"))


class FastCashLaneTests(unittest.TestCase):
    def test_happy_path_is_deterministic_draft_shadow(self):
        kwargs = {
            "opportunity": verified_opportunity(),
            "assets": (campaign_asset(),),
            "draft_inputs": (draft_input(),),
        }
        first = run_fast_cash_lane(**kwargs)
        second = run_fast_cash_lane(**kwargs)
        self.assertEqual(first, second)
        self.assertEqual(first.publication_state, "DRAFT_SHADOW")
        self.assertTrue(
            all(draft.publication_state == "DRAFT_SHADOW" for draft in first.drafts)
        )
        self.assertEqual(first.package_id, first.package_sha256[:16])
        self.assertFalse(first.review_hold)
        self.assertEqual(
            [receipt.action for receipt in first.decision_receipts],
            ["analyze_funnel", "draft_offer", "prepare_experiment"],
        )
        self.assertTrue(
            all(
                receipt.decision is ActionDecision.SIMULATION_ONLY
                for receipt in first.decision_receipts
            )
        )

    def test_affiliate_provenance_and_restrictions_are_held(self):
        registry = AffiliateRegistry()
        registry.register(
            affiliate_program(restrictions=("Founder review required",))
        )
        package = run_fast_cash_lane(
            verified_opportunity(),
            (
                campaign_asset(
                    restrictions=("Asset claim review required",)
                ),
            ),
            (affiliate_draft(),),
            affiliate_registry=registry,
        )
        draft = package.drafts[0]
        self.assertTrue(draft.has_affiliate_links)
        self.assertEqual(draft.affiliate_program_id, "program-1")
        self.assertIn("terms:program-1", draft.evidence_refs)
        self.assertIn("approval:program-1", draft.evidence_refs)
        self.assertEqual(
            draft.original_value_signals, ("structured-comparison",)
        )
        self.assertTrue(package.review_hold)
        self.assertEqual(
            set(package.restrictions_held_for_review),
            {
                ("asset-1", "Asset claim review required"),
                ("program-1", "Founder review required"),
            },
        )

    def test_program_restriction_is_deduplicated_across_drafts(self):
        registry = AffiliateRegistry()
        registry.register(
            affiliate_program(restrictions=("Human review",))
        )
        package = run_fast_cash_lane(
            verified_opportunity(),
            (campaign_asset(),),
            (
                affiliate_draft(text=(
                    "Affiliate disclosure: we may earn a commission. "
                    "Comparison version one."
                )),
                affiliate_draft(
                    channel="email",
                    text=(
                        "Affiliate disclosure: we may earn a commission. "
                        "Comparison version two."
                    ),
                ),
            ),
            affiliate_registry=registry,
        )
        self.assertEqual(
            package.restrictions_held_for_review,
            (("program-1", "Human review"),),
        )

    def test_same_channel_different_copy_has_distinct_tracking(self):
        package = run_fast_cash_lane(
            verified_opportunity(),
            (campaign_asset(),),
            (
                draft_input(text="Sourced comparison version one."),
                draft_input(text="Sourced comparison version two."),
            ),
        )
        self.assertNotEqual(
            package.drafts[0].tracking_id,
            package.drafts[1].tracking_id,
        )

    def test_equivalent_input_reordering_has_same_package_hash(self):
        assets = (campaign_asset("asset-1"), campaign_asset("asset-2"))
        drafts = (draft_input("asset-1"), draft_input("asset-2"))
        first = run_fast_cash_lane(
            verified_opportunity(), assets, drafts
        )
        second = run_fast_cash_lane(
            verified_opportunity(),
            tuple(reversed(assets)),
            tuple(reversed(drafts)),
        )
        self.assertEqual(first.package_sha256, second.package_sha256)

    def test_tamper_inputs_change_package_digest(self):
        base = run_fast_cash_lane(
            verified_opportunity(),
            (campaign_asset(),),
            (draft_input(),),
        )
        changed_asset = run_fast_cash_lane(
            verified_opportunity(),
            (campaign_asset(title="Changed title"),),
            (draft_input(),),
        )
        changed_signal_input = DraftInput(
            asset_id="asset-1",
            channel="search",
            proposed_text="A sourced comparison of qualified options for careful buyers.",
            cta="Read the sourced comparison",
            evidence_refs=("draft-source:comparison",),
            original_value_signals=("new-analysis",),
        )
        changed_signal = run_fast_cash_lane(
            verified_opportunity(),
            (campaign_asset(),),
            (changed_signal_input,),
        )
        self.assertNotEqual(base.package_sha256, changed_asset.package_sha256)
        self.assertNotEqual(
            base.package_sha256, changed_signal.package_sha256
        )

    def test_review_hold_cannot_be_suppressed(self):
        package = run_fast_cash_lane(
            verified_opportunity(),
            (campaign_asset(restrictions=("review",)),),
            (draft_input(),),
        )
        rebuilt = replace(package, review_hold=False)
        self.assertTrue(rebuilt.review_hold)

    def test_blocks_unverified_inputs_and_bad_content(self):
        with self.assertRaises(ValueError):
            run_fast_cash_lane(
                verified_opportunity(evidence_state=EvidenceState.INFERRED),
                (campaign_asset(),),
                (draft_input(),),
            )
        with self.assertRaises(ValueError):
            run_fast_cash_lane(
                verified_opportunity(),
                (campaign_asset(), campaign_asset()),
                (draft_input(),),
            )
        with self.assertRaises(ValueError):
            run_fast_cash_lane(
                verified_opportunity(),
                (campaign_asset(),),
                (draft_input(asset_id="missing"),),
            )
        with self.assertRaises(ValueError):
            run_fast_cash_lane(
                verified_opportunity(),
                (campaign_asset(),),
                (
                    draft_input(
                        text="This provides guaranteed income."
                    ),
                ),
            )

    def test_affiliate_gate_requires_registry_approval_and_evidence(self):
        with self.assertRaises(ValueError):
            run_fast_cash_lane(
                verified_opportunity(),
                (campaign_asset(),),
                (affiliate_draft(),),
            )

        registry = AffiliateRegistry()
        registry.register(
            affiliate_program(
                status=ProgramStatus.APPLIED,
                evidence_state=EvidenceState.VERIFIED,
            )
        )
        with self.assertRaises(ValueError):
            run_fast_cash_lane(
                verified_opportunity(),
                (campaign_asset(),),
                (affiliate_draft(),),
                affiliate_registry=registry,
            )

        unverified = AffiliateRegistry()
        unverified.register(
            affiliate_program(evidence_state=EvidenceState.INFERRED)
        )
        with self.assertRaises(ValueError):
            run_fast_cash_lane(
                verified_opportunity(),
                (campaign_asset(),),
                (affiliate_draft(),),
                affiliate_registry=unverified,
            )


class CompoundingLaneTests(unittest.TestCase):
    def test_happy_path_without_metrics_is_draft_shadow(self):
        result = run_compounding()
        self.assertEqual(result.publication_state, "DRAFT_SHADOW")
        self.assertIsNone(result.learning_proposal)
        self.assertIsNone(result.metrics_snapshot)
        self.assertNotIn(
            "measure_metrics",
            [receipt.action for receipt in result.decision_receipts],
        )
        self.assertEqual(
            {snapshot.program_id for snapshot in result.approved_program_snapshots},
            set(result.site_plan.approved_program_ids),
        )
        self.assertTrue(
            all(cluster.verified_at for cluster in result.keyword_clusters)
        )

    def test_metrics_are_scoped_committed_and_evidence_bound(self):
        metrics = metric_snapshot()
        result = run_compounding(prior_metrics=metrics)
        self.assertEqual(result.metrics_snapshot, metrics)
        self.assertIsNotNone(result.learning_proposal)
        measure = [
            receipt
            for receipt in result.decision_receipts
            if receipt.action == "measure_metrics"
        ]
        self.assertEqual(len(measure), 1)
        self.assertEqual(measure[0].evidence_refs, metrics.evidence_refs)

        changed = run_compounding(
            prior_metrics=metric_snapshot(visits=101)
        )
        self.assertNotEqual(result.result_sha256, changed.result_sha256)

    def test_action_receipts_cite_specific_evidence(self):
        result = run_compounding()
        receipts = {
            receipt.action: receipt for receipt in result.decision_receipts
        }
        draft_refs = set(receipts["draft_offer"].evidence_refs)
        self.assertIn("keyword-source:buyer intent guide", draft_refs)
        self.assertIn("approval:program-1", draft_refs)
        self.assertIn("terms:program-1", draft_refs)
        self.assertIn("consent-policy:v1", draft_refs)

    def test_keyword_freshness_and_status_fail_closed(self):
        stale = keyword(
            verified_at=(AS_OF - timedelta(hours=2)).isoformat(),
            ttl_seconds=3600,
        )
        with self.assertRaises(ValueError):
            run_compounding(keyword_evidence=(stale,))

        future = keyword(
            verified_at=(
                AS_OF + timedelta(seconds=301)
            ).isoformat()
        )
        with self.assertRaises(ValueError):
            run_compounding(keyword_evidence=(future,))

        inferred = keyword(evidence_state=EvidenceState.INFERRED)
        with self.assertRaises(ValueError):
            run_compounding(keyword_evidence=(inferred,))

        with self.assertRaises(ValueError):
            run_compounding(
                keyword_evidence=(keyword("Term"), keyword("term"))
            )

        with self.assertRaises(ValueError):
            run_compounding(
                as_of=datetime(2026, 8, 25, 12, 0)
            )

    def test_freshness_metadata_changes_result_digest(self):
        first = run_compounding(
            keyword_evidence=(
                keyword(
                    verified_at=(
                        AS_OF - timedelta(minutes=60)
                    ).isoformat(),
                    ttl_seconds=7200,
                ),
            )
        )
        second = run_compounding(
            keyword_evidence=(
                keyword(
                    verified_at=(
                        AS_OF - timedelta(minutes=59)
                    ).isoformat(),
                    ttl_seconds=7200,
                ),
            )
        )
        third = run_compounding(
            keyword_evidence=(
                keyword(
                    verified_at=(
                        AS_OF - timedelta(minutes=60)
                    ).isoformat(),
                    ttl_seconds=7201,
                ),
            )
        )
        self.assertNotEqual(first.result_sha256, second.result_sha256)
        self.assertNotEqual(first.result_sha256, third.result_sha256)

    def test_program_provenance_and_restrictions_are_committed(self):
        restricted = affiliate_program(restrictions=("Manual review",))
        result = run_compounding(programs=(restricted,))
        self.assertTrue(result.review_hold)
        self.assertEqual(
            result.restrictions_held_for_review,
            (("program-1", "Manual review"),),
        )

        changed_terms = run_compounding(
            programs=(affiliate_program(terms_ref="terms:changed"),)
        )
        self.assertNotEqual(result.result_sha256, changed_terms.result_sha256)

    def test_equivalent_reordering_has_same_result_hash(self):
        programs = (
            affiliate_program("program-1"),
            affiliate_program("program-2"),
        )
        keywords = (keyword("term one"), keyword("term two"))
        first = run_compounding(programs=programs, keyword_evidence=keywords)
        second = run_compounding(
            programs=tuple(reversed(programs)),
            keyword_evidence=tuple(reversed(keywords)),
        )
        self.assertEqual(first.result_sha256, second.result_sha256)

    def test_duplicate_program_and_snapshot_coverage_fail_closed(self):
        with self.assertRaises(ValueError):
            run_compounding(
                programs=(affiliate_program(), affiliate_program())
            )

        result = run_compounding()
        with self.assertRaises(ValueError):
            replace(result, approved_program_snapshots=())
        with self.assertRaises(ValueError):
            replace(
                result,
                approved_program_snapshots=(
                    result.approved_program_snapshots[0],
                    result.approved_program_snapshots[0],
                ),
            )

    def test_result_rejects_untimed_cluster_and_metrics_mismatch(self):
        result = run_compounding()
        untimed = replace(
            result.keyword_clusters[0],
            verified_at="",
            ttl_seconds=0,
        )
        with self.assertRaises(ValueError):
            replace(result, keyword_clusters=(untimed,))

        measured = run_compounding(prior_metrics=metric_snapshot())
        with self.assertRaises(ValueError):
            replace(measured, metrics_snapshot=None)
        with self.assertRaises(ValueError):
            replace(
                measured,
                metrics_snapshot=metric_snapshot(
                    opportunity_id="different"
                ),
            )
        wrong_measure_receipts = tuple(
            decision_receipt("measure_metrics", ("metrics:wrong",))
            if receipt.action == "measure_metrics"
            else receipt
            for receipt in measured.decision_receipts
        )
        with self.assertRaises(ValueError):
            replace(measured, decision_receipts=wrong_measure_receipts)
        assert measured.learning_proposal is not None
        with self.assertRaises(ValueError):
            replace(
                measured,
                learning_proposal=replace(
                    measured.learning_proposal,
                    evidence_state=EvidenceState.INFERRED,
                ),
            )

    def test_metrics_with_unknown_empty_or_wrong_scope_are_rejected(self):
        with self.assertRaises(ValueError):
            run_compounding(
                prior_metrics=metric_snapshot(
                    opportunity_id="different"
                )
            )
        with self.assertRaises(ValueError):
            run_compounding(
                prior_metrics=metric_snapshot(
                    evidence_state=EvidenceState.UNKNOWN
                )
            )
        with self.assertRaises(ValueError):
            run_compounding(
                prior_metrics=metric_snapshot(evidence_refs=())
            )


class VerifiedRevenueTests(unittest.TestCase):
    def test_timestamp_is_normalized_and_naive_time_rejected(self):
        event = RevenueEvent(
            event_id="offset",
            opportunity_id="opp-lanes",
            payout_received=Decimal("1"),
            evidence_state=EvidenceState.VERIFIED,
            evidence_refs=("payout:offset",),
            event_timestamp="2026-08-25T12:00:00+05:30",
        )
        self.assertEqual(
            event.event_timestamp, "2026-08-25T06:30:00+00:00"
        )
        with self.assertRaises(ValueError):
            replace(event, event_timestamp="2026-08-25T12:00:00")

    def test_first_verified_revenue_uses_time_then_event_id(self):
        ledger = RevenueLedger()
        for event in (
            RevenueEvent(
                event_id="untimed",
                opportunity_id="opp-lanes",
                payout_received=Decimal("50"),
                evidence_state=EvidenceState.VERIFIED,
                evidence_refs=("payout:untimed",),
            ),
            RevenueEvent(
                event_id="z-later-id",
                opportunity_id="opp-lanes",
                payout_received=Decimal("1"),
                evidence_state=EvidenceState.VERIFIED,
                evidence_refs=("payout:z",),
                event_timestamp="2026-08-25T10:00:00Z",
            ),
            RevenueEvent(
                event_id="a-earlier-id",
                opportunity_id="opp-lanes",
                payout_received=Decimal("1"),
                evidence_state=EvidenceState.VERIFIED,
                evidence_refs=("payout:a",),
                event_timestamp="2026-08-25T10:00:00+00:00",
            ),
            RevenueEvent(
                event_id="other-opportunity",
                opportunity_id="other",
                payout_received=Decimal("100"),
                evidence_state=EvidenceState.VERIFIED,
                evidence_refs=("payout:other",),
                event_timestamp="2026-08-25T09:00:00Z",
            ),
        ):
            ledger.ingest(event)
        first = ledger.first_verified_revenue("opp-lanes")
        self.assertIsNotNone(first)
        assert first is not None
        self.assertEqual(first.event_id, "a-earlier-id")

    def test_untimestamped_or_unverified_payout_is_not_first_verified(self):
        ledger = RevenueLedger()
        ledger.ingest(
            RevenueEvent(
                event_id="untimed",
                opportunity_id="opp-lanes",
                payout_received=Decimal("20"),
                evidence_state=EvidenceState.VERIFIED,
                evidence_refs=("payout:untimed",),
            )
        )
        ledger.ingest(
            RevenueEvent(
                event_id="inferred",
                opportunity_id="opp-lanes",
                payout_received=Decimal("30"),
                evidence_state=EvidenceState.INFERRED,
                evidence_refs=("payout:inferred",),
                event_timestamp="2026-08-25T10:00:00Z",
            )
        )
        self.assertIsNone(
            ledger.first_verified_revenue("opp-lanes")
        )


if __name__ == "__main__":
    unittest.main()
