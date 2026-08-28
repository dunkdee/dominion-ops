"""Comprehensive tests for RADAH MEMSHALAH revenue lane orchestration.

Covers: positive paths, negative/validation, determinism, idempotency,
freshness, provenance, receipt evidence, timestamp handling, payout
ordering, and tamper/recomputation tests.
"""
from __future__ import annotations

import hashlib
import json
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from apps.revenue_engine.engine import (
    AffiliateRegistry,
    RevenueLedger,
    _sha256_of,
    build_site_plan,
    cluster_keywords,
    decision_receipt,
    plan_email_capture,
    propose_single_change,
    rank_opportunities,
    review_content,
    run_compounding_lane,
    run_fast_cash_lane,
    score_opportunity,
)
from apps.revenue_engine.models import (
    ActionDecision,
    AffiliateProgram,
    ApprovedProgramSnapshot,
    CampaignAsset,
    CompoundingLaneResult,
    ContentDraft,
    DecisionReceipt,
    DraftInput,
    EmailCapturePlan,
    EvidenceState,
    FastCashCampaignPackage,
    KeywordCluster,
    KeywordEvidence,
    LearningProposal,
    MetricSnapshot,
    Opportunity,
    ProgramStatus,
    RevenueEvent,
    SitePlan,
    require_sha256_digest,
)

# ---------------------------------------------------------------------------
# Shared fixtures — THEIRS (comprehensive set)
# ---------------------------------------------------------------------------

_NOW = datetime(2026, 8, 25, 12, 0, 0, tzinfo=timezone.utc)
_VERIFIED_AT = "2026-08-25T10:00:00+00:00"
_TTL = 86400  # 1 day


def _opportunity(**overrides):
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


def _program(**overrides):
    values = dict(
        program_id="prog-1",
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


def _asset(**overrides):
    values = dict(
        asset_id="asset-1",
        title="Best Picks Guide",
        asset_type="guide",
        url_slug="best-picks",
        evidence_state=EvidenceState.VERIFIED,
        evidence_refs=("artifact:asset-1",),
    )
    values.update(overrides)
    return CampaignAsset(**values)


def _draft_input(**overrides):
    values = dict(
        asset_id="asset-1",
        channel="email",
        proposed_text="Compare these options based on your needs. Affiliate disclosure: we may earn a commission.",
        cta="See the comparison",
        measurement_dimensions=("clicks", "conversions"),
        has_affiliate_links=True,
        affiliate_program_id="prog-1",
        affiliate_terms_ref="artifact:terms-1",
        original_value_signals=("structured-comparison",),
    )
    values.update(overrides)
    return DraftInput(**values)


def _keyword_evidence(**overrides):
    values = dict(
        cluster_id="kw-1",
        head_term="best budget pick",
        variants=("best budget", "budget option", "affordable pick"),
        buyer_intent_score=0.85,
        evidence_refs=("artifact:kw-research-1",),
        evidence_state=EvidenceState.VERIFIED,
        verified_at=_VERIFIED_AT,
        ttl_seconds=_TTL,
    )
    values.update(overrides)
    return KeywordEvidence(**values)


def _revenue_event(**overrides):
    values = dict(
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
        event_timestamp="2026-08-20T12:00:00+00:00",
    )
    values.update(overrides)
    return RevenueEvent(**values)


# ---------------------------------------------------------------------------
# Shared fixtures — OURS (invariant/integration test set)
# These use opportunity_id="opp-lanes" and program_id="program-1" to stay
# distinct from the THEIRS fixture set above.
# ---------------------------------------------------------------------------

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
        "cluster_id": head_term.replace(" ", "-"),
        "head_term": head_term,
        "variants": (head_term, f"best {head_term}"),
        "buyer_intent_score": 0.9,
        "evidence_refs": (f"keyword-source:{head_term}",),
        "evidence_state": EvidenceState.VERIFIED,
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
        measurement_dimensions=("clicks", "conversions"),
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
    # affiliate_terms_ref is required by HARDENED DraftInput when has_affiliate_links=True.
    # Value matches affiliate_program(program_id=program_id).terms_ref — the actual
    # program terms reference, not caller-invented. Engine uses prog.terms_ref from the
    # matched program object; this field is a model-level acknowledgement guard.
    # Old evidence_refs=("draft-source:affiliate-comparison",) was intentionally removed
    # in HARDENED: per-draft caller evidence is replaced by asset.evidence_refs +
    # prog.evidence_refs composed by the lane engine.
    return DraftInput(
        asset_id=asset_id,
        channel=channel,
        proposed_text=text,
        cta="Review the sourced comparison",
        measurement_dimensions=("clicks", "conversions"),
        has_affiliate_links=True,
        affiliate_program_id=program_id,
        affiliate_terms_ref=f"terms:{program_id}",
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
    """Helper that calls run_compounding_lane using OURS fixture set."""
    values = {
        "opportunity": verified_opportunity(),
        "keyword_evidence": (keyword(),),
        "programs": (affiliate_program(),),
        "consent_mechanism": "Explicit unchecked opt-in checkbox",
        "value_exchange": "Evidence-backed buyer guide",
        "prior_metrics": None,
        "as_of": AS_OF,
    }
    values.update(overrides)
    return run_compounding_lane(
        values["opportunity"],
        values["keyword_evidence"],
        values["programs"],
        values["consent_mechanism"],
        values["value_exchange"],
        values["prior_metrics"],
        values["as_of"],
    )


# ---------------------------------------------------------------------------
# DigestAndModelInvariantTests — OURS-only class
# ---------------------------------------------------------------------------

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
                measurement_dimensions=("clicks",),
                has_affiliate_links=1,
            )
        with self.assertRaises(ValueError):
            DraftInput(
                asset_id="a",
                channel="search",
                proposed_text="text",
                cta="cta",
                measurement_dimensions=("clicks",),
                affiliate_program_id="p",
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


# ---------------------------------------------------------------------------
# RevenueEvent timestamp tests
# ---------------------------------------------------------------------------

class RevenueEventTimestampTests(unittest.TestCase):
    def test_utc_timestamp_canonicalized(self):
        evt = RevenueEvent(event_id="e1", opportunity_id="opp-1",
                           event_timestamp="2026-08-20T12:00:00+00:00")
        self.assertIn("+00:00", evt.event_timestamp)

    def test_z_suffix_accepted_and_canonicalized(self):
        evt = RevenueEvent(event_id="e1", opportunity_id="opp-1",
                           event_timestamp="2026-08-20T12:00:00Z")
        self.assertIn("+00:00", evt.event_timestamp)

    def test_offset_timestamp_canonicalized_to_utc(self):
        # +05:30 offset -> UTC equivalent stored
        evt = RevenueEvent(event_id="e1", opportunity_id="opp-1",
                           event_timestamp="2026-08-20T17:30:00+05:30")
        self.assertIn("+00:00", evt.event_timestamp)
        # 17:30 +05:30 == 12:00 UTC
        self.assertIn("12:00:00", evt.event_timestamp)

    def test_naive_timestamp_rejected(self):
        with self.assertRaises(ValueError):
            RevenueEvent(event_id="e1", opportunity_id="opp-1",
                         event_timestamp="2026-08-20T12:00:00")

    def test_invalid_timestamp_rejected(self):
        with self.assertRaises(ValueError):
            RevenueEvent(event_id="e1", opportunity_id="opp-1",
                         event_timestamp="not-a-date")

    def test_empty_timestamp_accepted(self):
        evt = RevenueEvent(event_id="e1", opportunity_id="opp-1",
                           event_timestamp="")
        self.assertEqual(evt.event_timestamp, "")

    def test_default_timestamp_is_empty(self):
        evt = RevenueEvent(event_id="e1", opportunity_id="opp-1")
        self.assertEqual(evt.event_timestamp, "")

    def test_timestamp_is_normalized_and_naive_time_rejected(self):
        """OURS: offset timestamp normalizes to UTC; naive raises."""
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


# ---------------------------------------------------------------------------
# first_verified_revenue tests
# ---------------------------------------------------------------------------

class FirstVerifiedRevenueTests(unittest.TestCase):
    def setUp(self):
        self.ledger = RevenueLedger()

    def test_returns_none_when_no_events(self):
        self.assertIsNone(self.ledger.first_verified_revenue("opp-1"))

    def test_returns_none_when_all_lack_timestamps(self):
        self.ledger.ingest(_revenue_event(event_timestamp=""))
        self.assertIsNone(self.ledger.first_verified_revenue("opp-1"))

    def test_returns_none_wrong_opportunity(self):
        self.ledger.ingest(_revenue_event(event_id="e1", opportunity_id="opp-2",
                                          event_timestamp="2026-08-20T12:00:00+00:00"))
        self.assertIsNone(self.ledger.first_verified_revenue("opp-1"))

    def test_returns_none_zero_payout(self):
        self.ledger.ingest(_revenue_event(payout_received=Decimal("0"),
                                          commission_accrued=Decimal("0")))
        self.assertIsNone(self.ledger.first_verified_revenue("opp-1"))

    def test_returns_none_inferred_state(self):
        self.ledger.ingest(_revenue_event(
            evidence_state=EvidenceState.INFERRED,
            evidence_refs=("ref:1",),
        ))
        self.assertIsNone(self.ledger.first_verified_revenue("opp-1"))

    def test_excludes_untimestamped_picks_earliest_with_timestamp(self):
        # evt-no-ts has no timestamp (excluded); evt-early is the first
        self.ledger.ingest(_revenue_event(event_id="evt-no-ts", event_timestamp=""))
        self.ledger.ingest(_revenue_event(event_id="evt-early",
                                          event_timestamp="2026-08-19T00:00:00+00:00"))
        self.ledger.ingest(_revenue_event(event_id="evt-late",
                                          event_timestamp="2026-08-21T00:00:00+00:00"))
        result = self.ledger.first_verified_revenue("opp-1")
        self.assertIsNotNone(result)
        self.assertEqual(result.event_id, "evt-early")

    def test_datetime_sort_not_string_sort(self):
        # String-sorted: "2026-08-09" < "2026-08-20" -- but both are real datetimes
        # Insert in reverse order to ensure sorting is by datetime, not insertion
        self.ledger.ingest(_revenue_event(event_id="e2",
                                          event_timestamp="2026-08-20T00:00:00+00:00"))
        self.ledger.ingest(_revenue_event(event_id="e1",
                                          event_timestamp="2026-08-09T00:00:00+00:00"))
        result = self.ledger.first_verified_revenue("opp-1")
        self.assertEqual(result.event_id, "e1")  # Aug 9 is earlier

    def test_event_id_tiebreaker(self):
        ts = "2026-08-20T12:00:00+00:00"
        self.ledger.ingest(_revenue_event(event_id="evt-b", event_timestamp=ts))
        self.ledger.ingest(_revenue_event(event_id="evt-a", event_timestamp=ts))
        result = self.ledger.first_verified_revenue("opp-1")
        self.assertEqual(result.event_id, "evt-a")  # "evt-a" < "evt-b"

    def test_first_verified_revenue_uses_time_then_event_id(self):
        """OURS: time-then-event_id ordering with multiple edge cases."""
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
        """OURS: untimed and INFERRED events never qualify as first verified."""
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


# ---------------------------------------------------------------------------
# MetricSnapshot validation tests
# ---------------------------------------------------------------------------

class MetricSnapshotValidationTests(unittest.TestCase):
    def _snapshot(self, **overrides):
        vals = dict(
            opportunity_id="opp-1",
            impressions=100,
            visits=10,
            affiliate_clicks=2,
            conversions=0,
            commission_accrued=Decimal("0"),
            payout_received=Decimal("0"),
            click_through_rate=None,
            conversion_rate=None,
            earnings_per_click=None,
            revenue_per_visit=None,
            evidence_state=EvidenceState.INFERRED,
            evidence_refs=("ref:1",),
        )
        vals.update(overrides)
        return MetricSnapshot(**vals)

    def test_blank_opportunity_id_rejected(self):
        with self.assertRaises(ValueError):
            self._snapshot(opportunity_id="   ")

    def test_wrong_evidence_state_type_rejected(self):
        with self.assertRaises(TypeError):
            self._snapshot(evidence_state="VERIFIED")

    def test_evidence_refs_normalized(self):
        s = self._snapshot(evidence_refs=("  ref:a  ", "ref:a", "ref:b"))
        self.assertEqual(s.evidence_refs, ("ref:a", "ref:b"))

    def test_ledger_metrics_populates_opportunity_id(self):
        ledger = RevenueLedger()
        ledger.ingest(_revenue_event())
        snap = ledger.metrics("opp-1")
        self.assertEqual(snap.opportunity_id, "opp-1")

    def test_ledger_metrics_populates_evidence_refs(self):
        ledger = RevenueLedger()
        ledger.ingest(_revenue_event(evidence_refs=("receipt:evt-1",)))
        snap = ledger.metrics("opp-1")
        self.assertIn("receipt:evt-1", snap.evidence_refs)


# ---------------------------------------------------------------------------
# DraftInput validation tests
# ---------------------------------------------------------------------------

class DraftInputValidationTests(unittest.TestCase):
    def test_has_affiliate_links_must_be_bool(self):
        with self.assertRaises(TypeError):
            _draft_input(has_affiliate_links=1)

    def test_affiliate_program_id_must_be_none_when_false(self):
        with self.assertRaises(ValueError):
            _draft_input(
                has_affiliate_links=False,
                affiliate_program_id="prog-1",
                affiliate_terms_ref=None,
            )

    def test_affiliate_terms_ref_must_be_none_when_false(self):
        with self.assertRaises(ValueError):
            _draft_input(
                has_affiliate_links=False,
                affiliate_program_id=None,
                affiliate_terms_ref="artifact:terms-1",
            )

    def test_affiliate_program_id_required_when_true(self):
        with self.assertRaises(ValueError):
            _draft_input(has_affiliate_links=True, affiliate_program_id=None)

    def test_affiliate_terms_ref_required_when_true(self):
        with self.assertRaises(ValueError):
            _draft_input(has_affiliate_links=True, affiliate_terms_ref=None)

    def test_empty_measurement_dimensions_rejected(self):
        with self.assertRaises(ValueError):
            _draft_input(measurement_dimensions=())

    def test_valid_non_affiliate_draft_input(self):
        inp = _draft_input(
            has_affiliate_links=False,
            affiliate_program_id=None,
            affiliate_terms_ref=None,
            original_value_signals=(),
        )
        self.assertFalse(inp.has_affiliate_links)
        self.assertIsNone(inp.affiliate_program_id)


# ---------------------------------------------------------------------------
# ContentDraft validation tests (is-not-None checks)
# ---------------------------------------------------------------------------

class ContentDraftValidationTests(unittest.TestCase):
    def _draft_id(self):
        return "a" * 64

    def _tracking_id(self):
        return "b" * 16

    def test_affiliate_program_id_not_none_when_false_raises(self):
        with self.assertRaises(ValueError):
            ContentDraft(
                draft_id=self._draft_id(),
                asset_id="a1",
                opportunity_id="opp-1",
                channel="email",
                short_form_text="text",
                buyer_intent_cta="click",
                tracking_id=self._tracking_id(),
                measurement_dimensions=("clicks",),
                evidence_refs=("ref:1",),
                has_affiliate_links=False,
                affiliate_program_id="prog-1",  # must be None
                affiliate_terms_ref=None,
            )

    def test_affiliate_terms_ref_not_none_when_false_raises(self):
        with self.assertRaises(ValueError):
            ContentDraft(
                draft_id=self._draft_id(),
                asset_id="a1",
                opportunity_id="opp-1",
                channel="email",
                short_form_text="text",
                buyer_intent_cta="click",
                tracking_id=self._tracking_id(),
                measurement_dimensions=("clicks",),
                evidence_refs=("ref:1",),
                has_affiliate_links=False,
                affiliate_program_id=None,
                affiliate_terms_ref="terms",  # must be None
            )

    def test_affiliate_evidence_refs_must_be_empty_when_false(self):
        with self.assertRaises(ValueError):
            ContentDraft(
                draft_id=self._draft_id(),
                asset_id="a1",
                opportunity_id="opp-1",
                channel="email",
                short_form_text="text",
                buyer_intent_cta="click",
                tracking_id=self._tracking_id(),
                measurement_dimensions=("clicks",),
                evidence_refs=("ref:1",),
                has_affiliate_links=False,
                affiliate_evidence_refs=("ref:x",),  # must be empty
            )

    def test_empty_evidence_refs_rejected(self):
        with self.assertRaises(ValueError):
            ContentDraft(
                draft_id=self._draft_id(),
                asset_id="a1",
                opportunity_id="opp-1",
                channel="email",
                short_form_text="text",
                buyer_intent_cta="click",
                tracking_id=self._tracking_id(),
                measurement_dimensions=("clicks",),
                evidence_refs=(),  # must be nonempty
            )

    def test_original_value_signals_stored(self):
        draft = ContentDraft(
            draft_id=self._draft_id(),
            asset_id="a1",
            opportunity_id="opp-1",
            channel="email",
            short_form_text="text",
            buyer_intent_cta="click",
            tracking_id=self._tracking_id(),
            measurement_dimensions=("clicks",),
            evidence_refs=("ref:1",),
            original_value_signals=("comparison", "data"),
        )
        self.assertIn("comparison", draft.original_value_signals)


# ---------------------------------------------------------------------------
# ApprovedProgramSnapshot tests
# ---------------------------------------------------------------------------

class ApprovedProgramSnapshotTests(unittest.TestCase):
    def _snap(self, **overrides):
        vals = dict(
            program_id="prog-1",
            status=ProgramStatus.APPROVED,
            evidence_state=EvidenceState.VERIFIED,
            evidence_refs=("artifact:approval-1",),
            terms_ref="artifact:terms-1",
            tracking_url="https://merchant.example/?ref=x",
        )
        vals.update(overrides)
        return ApprovedProgramSnapshot(**vals)

    def test_valid_snapshot(self):
        s = self._snap()
        self.assertEqual(s.program_id, "prog-1")
        self.assertIs(s.status, ProgramStatus.APPROVED)

    def test_non_approved_status_rejected(self):
        with self.assertRaises(ValueError):
            self._snap(status=ProgramStatus.APPLIED)

    def test_non_verified_evidence_rejected(self):
        with self.assertRaises(ValueError):
            self._snap(evidence_state=EvidenceState.INFERRED)

    def test_empty_evidence_refs_rejected(self):
        with self.assertRaises(ValueError):
            self._snap(evidence_refs=())

    def test_empty_terms_ref_rejected(self):
        with self.assertRaises(ValueError):
            self._snap(terms_ref="")

    def test_empty_tracking_url_rejected(self):
        with self.assertRaises(ValueError):
            self._snap(tracking_url="")

    def test_wrong_status_type_rejected(self):
        with self.assertRaises(TypeError):
            self._snap(status="APPROVED")

    def test_wrong_evidence_state_type_rejected(self):
        with self.assertRaises(TypeError):
            self._snap(evidence_state="VERIFIED")


# ---------------------------------------------------------------------------
# KeywordEvidence and cluster_keywords tests
# ---------------------------------------------------------------------------

class KeywordEvidenceTests(unittest.TestCase):
    def test_valid_evidence(self):
        ev = _keyword_evidence()
        self.assertEqual(ev.cluster_id, "kw-1")
        self.assertIn("+00:00", ev.verified_at)

    def test_naive_verified_at_rejected(self):
        with self.assertRaises(ValueError):
            _keyword_evidence(verified_at="2026-08-25T10:00:00")

    def test_zero_ttl_rejected(self):
        with self.assertRaises(ValueError):
            _keyword_evidence(ttl_seconds=0)

    def test_negative_ttl_rejected(self):
        with self.assertRaises(ValueError):
            _keyword_evidence(ttl_seconds=-1)

    def test_empty_evidence_refs_rejected(self):
        with self.assertRaises(ValueError):
            _keyword_evidence(evidence_refs=())

    def test_z_suffix_canonicalized(self):
        ev = _keyword_evidence(verified_at="2026-08-25T10:00:00Z")
        self.assertIn("+00:00", ev.verified_at)


class ClusterKeywordsTests(unittest.TestCase):
    def test_happy_path_produces_verified_cluster(self):
        clusters = cluster_keywords([_keyword_evidence()], as_of=_NOW)
        self.assertEqual(len(clusters), 1)
        self.assertIs(clusters[0].evidence_state, EvidenceState.VERIFIED)

    def test_freshness_fields_preserved(self):
        ev = _keyword_evidence()
        clusters = cluster_keywords([ev], as_of=_NOW)
        self.assertEqual(clusters[0].verified_at, ev.verified_at)
        self.assertEqual(clusters[0].ttl_seconds, ev.ttl_seconds)

    def test_stale_evidence_rejected(self):
        # TTL of 3600s from 2026-08-25T10:00:00 expires at 11:00:00
        # as_of is 2026-08-25T12:00:00 -- stale
        with self.assertRaises(ValueError):
            cluster_keywords(
                [_keyword_evidence(ttl_seconds=3600)],
                as_of=_NOW,
            )

    def test_clock_skew_allowance(self):
        # verified_at slightly in the future (within 300s) should be accepted
        future_ts = (_NOW + timedelta(seconds=100)).isoformat()
        ev = _keyword_evidence(verified_at=future_ts, ttl_seconds=_TTL)
        clusters = cluster_keywords([ev], as_of=_NOW)
        self.assertEqual(len(clusters), 1)

    def test_naive_as_of_rejected(self):
        with self.assertRaises(ValueError):
            cluster_keywords([_keyword_evidence()], as_of=datetime(2026, 8, 25, 12, 0))

    def test_multiple_clusters(self):
        ev2 = _keyword_evidence(cluster_id="kw-2", head_term="other term")
        clusters = cluster_keywords([_keyword_evidence(), ev2], as_of=_NOW)
        self.assertEqual(len(clusters), 2)


# ---------------------------------------------------------------------------
# FAST CASH lane tests
# ---------------------------------------------------------------------------

class FastCashLaneTests(unittest.TestCase):
    def _run(self, **overrides):
        opp = overrides.pop("opportunity", _opportunity())
        assets = overrides.pop("assets", [_asset()])
        inputs = overrides.pop("draft_inputs", [_draft_input()])
        programs = overrides.pop("programs", [_program()])
        return run_fast_cash_lane(opp, assets, inputs, programs)

    def test_happy_path_returns_draft_shadow_package(self):
        pkg = self._run()
        self.assertEqual(pkg.publication_state, "DRAFT_SHADOW")
        self.assertFalse(pkg.review_hold)
        self.assertGreater(len(pkg.drafts), 0)
        self.assertGreater(len(pkg.decision_receipts), 0)

    def test_package_id_equals_sha256_prefix(self):
        pkg = self._run()
        self.assertEqual(pkg.package_id, pkg.package_sha256[:16])

    def test_determinism_same_inputs_same_sha(self):
        pkg1 = self._run()
        pkg2 = self._run()
        self.assertEqual(pkg1.package_sha256, pkg2.package_sha256)

    def test_analyze_funnel_receipt_present(self):
        pkg = self._run()
        actions = [r.action for r in pkg.decision_receipts]
        self.assertIn("analyze_funnel", actions)

    def test_draft_offer_receipt_present(self):
        pkg = self._run()
        actions = [r.action for r in pkg.decision_receipts]
        self.assertIn("draft_offer", actions)

    def test_draft_offer_receipt_includes_terms_ref(self):
        pkg = self._run()
        receipt = next(r for r in pkg.decision_receipts if r.action == "draft_offer")
        self.assertIn("artifact:terms-1", receipt.evidence_refs)

    def test_draft_offer_receipt_includes_program_evidence(self):
        pkg = self._run()
        receipt = next(r for r in pkg.decision_receipts if r.action == "draft_offer")
        self.assertIn("artifact:approval-1", receipt.evidence_refs)

    def test_approved_program_snapshot_included(self):
        pkg = self._run()
        self.assertEqual(len(pkg.approved_program_snapshots), 1)
        self.assertEqual(pkg.approved_program_snapshots[0].program_id, "prog-1")

    def test_restriction_triggers_review_hold(self):
        asset = _asset(restrictions=("no-email-marketing",))
        pkg = self._run(assets=[asset])
        self.assertTrue(pkg.review_hold)
        self.assertIn("no-email-marketing", pkg.restrictions_held_for_review)

    def test_restriction_deduplication(self):
        asset1 = _asset(asset_id="a1", url_slug="slug-1", restrictions=("rule-x",))
        asset2 = _asset(asset_id="a2", url_slug="slug-2", restrictions=("rule-x",))
        inp1 = _draft_input(asset_id="a1")
        inp2 = _draft_input(asset_id="a2", cta="different cta")
        pkg = run_fast_cash_lane(_opportunity(), [asset1, asset2], [inp1, inp2], [_program()])
        self.assertEqual(pkg.restrictions_held_for_review.count("rule-x"), 1)

    def test_review_hold_derived_not_caller_controlled(self):
        # FastCashCampaignPackage.__post_init__ always derives review_hold from restrictions
        asset = _asset(restrictions=("some-restriction",))
        pkg = self._run(assets=[asset])
        # review_hold must be True regardless of what we might attempt to pass
        self.assertTrue(pkg.review_hold)

    def test_tracking_id_per_distinct_draft(self):
        inp1 = _draft_input(cta="Click here")
        inp2 = _draft_input(cta="Buy now")
        pkg = run_fast_cash_lane(_opportunity(), [_asset()], [inp1, inp2], [_program()])
        ids = [d.tracking_id for d in pkg.drafts]
        self.assertEqual(len(ids), len(set(ids)))  # all unique

    def test_draft_evidence_includes_asset_and_program_refs(self):
        pkg = self._run()
        draft = pkg.drafts[0]
        self.assertIn("artifact:asset-1", draft.evidence_refs)
        self.assertIn("artifact:approval-1", draft.evidence_refs)

    def test_duplicate_assets_rejected(self):
        with self.assertRaises(ValueError):
            run_fast_cash_lane(
                _opportunity(),
                [_asset(), _asset()],  # duplicate asset_ids
                [_draft_input()],
                [_program()],
            )

    def test_unknown_asset_id_in_draft_input_rejected(self):
        with self.assertRaises(ValueError):
            run_fast_cash_lane(
                _opportunity(),
                [_asset()],
                [_draft_input(asset_id="nonexistent")],
                [_program()],
            )

    def test_unverified_affiliate_program_rejected(self):
        prog = _program(evidence_state=EvidenceState.INFERRED, evidence_refs=("ref:1",))
        with self.assertRaises(ValueError):
            self._run(programs=[prog])

    def test_non_approved_affiliate_program_rejected(self):
        prog = AffiliateProgram(
            program_id="prog-1",
            name="Applied Prog",
            status=ProgramStatus.APPLIED,
            commission_rate=Decimal("10"),
            cookie_days=7,
            payout_threshold=Decimal("25"),
        )
        with self.assertRaises(ValueError):
            self._run(programs=[prog])

    def test_tamper_different_text_different_sha(self):
        pkg1 = self._run(draft_inputs=[_draft_input(proposed_text="Text A. Affiliate disclosure: we may earn a commission.")])
        pkg2 = self._run(draft_inputs=[_draft_input(proposed_text="Text B. Affiliate disclosure: we may earn a commission.")])
        self.assertNotEqual(pkg1.package_sha256, pkg2.package_sha256)

    def test_non_affiliate_draft_no_program_required(self):
        inp = _draft_input(
            has_affiliate_links=False,
            affiliate_program_id=None,
            affiliate_terms_ref=None,
            original_value_signals=(),
        )
        asset = _asset(asset_id="asset-1")
        pkg = run_fast_cash_lane(_opportunity(), [asset], [inp], [])
        self.assertEqual(len(pkg.approved_program_snapshots), 0)

    def test_duplicate_program_ids_in_programs_rejected(self):
        prog = _program()
        with self.assertRaises(ValueError):
            build_site_plan(_opportunity(), [prog, prog])

    # ------------------------------------------------------------------
    # OURS-only invariant tests (use verified_opportunity / campaign_asset
    # fixtures and AffiliateRegistry-based API)
    # ------------------------------------------------------------------

    def test_happy_path_is_deterministic_draft_shadow(self):
        kwargs = {
            "opportunity": verified_opportunity(),
            "assets": (campaign_asset(),),
            "draft_inputs": (draft_input(),),
            "programs": (),
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
        # HARDENED: prepare_experiment is a compounding-lane-only action.
        # run_fast_cash_lane emits analyze_funnel + draft_offer only;
        # OURS had a duplicate prepare_experiment with identical refs to draft_offer.
        self.assertEqual(
            [receipt.action for receipt in first.decision_receipts],
            ["analyze_funnel", "draft_offer"],
        )
        self.assertTrue(
            all(
                receipt.decision is ActionDecision.SIMULATION_ONLY
                for receipt in first.decision_receipts
            )
        )

    def test_affiliate_provenance_and_restrictions_are_held(self):
        # HARDENED: programs passed directly; engine derives affiliate_terms_ref/evidence
        # from prog.terms_ref and prog.evidence_refs respectively.
        prog = affiliate_program(restrictions=("Founder review required",))
        package = run_fast_cash_lane(
            verified_opportunity(),
            (
                campaign_asset(
                    restrictions=("Asset claim review required",)
                ),
            ),
            (affiliate_draft(),),
            (prog,),
        )
        draft = package.drafts[0]
        self.assertTrue(draft.has_affiliate_links)
        self.assertEqual(draft.affiliate_program_id, "program-1")
        # HARDENED: affiliate_evidence_refs carries prog.evidence_refs on the draft.
        self.assertIn("approval:program-1", draft.affiliate_evidence_refs)
        # HARDENED: terms_ref goes into draft_offer receipt, not draft.evidence_refs.
        draft_offer = next(r for r in package.decision_receipts if r.action == "draft_offer")
        self.assertIn("terms:program-1", draft_offer.evidence_refs)
        self.assertEqual(
            draft.original_value_signals, ("structured-comparison",)
        )
        self.assertTrue(package.review_hold)
        # HARDENED: restrictions_held_for_review is tuple[str,...] — plain strings, no source_id pairs.
        self.assertEqual(
            set(package.restrictions_held_for_review),
            {"Asset claim review required", "Founder review required"},
        )

    def test_program_restriction_is_deduplicated_across_drafts(self):
        prog = affiliate_program(restrictions=("Human review",))
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
            (prog,),
        )
        # HARDENED: restrictions_held_for_review is tuple[str,...] — plain strings.
        self.assertEqual(package.restrictions_held_for_review, ("Human review",))

    def test_same_channel_different_copy_has_distinct_tracking(self):
        package = run_fast_cash_lane(
            verified_opportunity(),
            (campaign_asset(),),
            (
                draft_input(text="Sourced comparison version one."),
                draft_input(text="Sourced comparison version two."),
            ),
            (),
        )
        self.assertNotEqual(
            package.drafts[0].tracking_id,
            package.drafts[1].tracking_id,
        )

    def test_equivalent_input_reordering_has_same_package_hash(self):
        assets = (campaign_asset("asset-1"), campaign_asset("asset-2"))
        drafts = (draft_input("asset-1"), draft_input("asset-2"))
        first = run_fast_cash_lane(
            verified_opportunity(), assets, drafts, ()
        )
        second = run_fast_cash_lane(
            verified_opportunity(),
            tuple(reversed(assets)),
            tuple(reversed(drafts)),
            (),
        )
        self.assertEqual(first.package_sha256, second.package_sha256)

    def test_tamper_inputs_change_package_digest(self):
        base = run_fast_cash_lane(
            verified_opportunity(),
            (campaign_asset(),),
            (draft_input(),),
            (),
        )
        changed_asset = run_fast_cash_lane(
            verified_opportunity(),
            (campaign_asset(title="Changed title"),),
            (draft_input(),),
            (),
        )
        changed_signal_input = DraftInput(
            asset_id="asset-1",
            channel="search",
            proposed_text="A sourced comparison of qualified options for careful buyers.",
            cta="Read the sourced comparison",
            measurement_dimensions=("clicks", "conversions"),
            original_value_signals=("new-analysis",),
        )
        changed_signal = run_fast_cash_lane(
            verified_opportunity(),
            (campaign_asset(),),
            (changed_signal_input,),
            (),
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
            (),
        )
        rebuilt = replace(package, review_hold=False)
        self.assertTrue(rebuilt.review_hold)

    def test_blocks_unverified_inputs_and_bad_content(self):
        # HARDENED: opportunity evidence_state gate moved to model construction;
        # lane trusts what it receives. Remaining gates are: duplicate assets,
        # unknown asset_id, and content review (guaranteed income claim).
        with self.assertRaises(ValueError):
            run_fast_cash_lane(
                verified_opportunity(),
                (campaign_asset(), campaign_asset()),
                (draft_input(),),
                (),
            )
        with self.assertRaises(ValueError):
            run_fast_cash_lane(
                verified_opportunity(),
                (campaign_asset(),),
                (draft_input(asset_id="missing"),),
                (),
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
                (),
            )

    def test_affiliate_gate_requires_registry_approval_and_evidence(self):
        # Empty programs: engine can't find "program-1" → ValueError
        with self.assertRaises(ValueError):
            run_fast_cash_lane(
                verified_opportunity(),
                (campaign_asset(),),
                (affiliate_draft(),),
                (),
            )

        # APPLIED status: _build_approved_snapshot rejects non-APPROVED → ValueError
        with self.assertRaises(ValueError):
            run_fast_cash_lane(
                verified_opportunity(),
                (campaign_asset(),),
                (affiliate_draft(),),
                (affiliate_program(status=ProgramStatus.APPLIED, evidence_state=EvidenceState.VERIFIED),),
            )

        # INFERRED evidence: _build_approved_snapshot rejects non-VERIFIED → ValueError
        with self.assertRaises(ValueError):
            run_fast_cash_lane(
                verified_opportunity(),
                (campaign_asset(),),
                (affiliate_draft(),),
                (affiliate_program(evidence_state=EvidenceState.INFERRED),),
            )


# ---------------------------------------------------------------------------
# COMPOUNDING lane tests
# ---------------------------------------------------------------------------

class CompoundingLaneTests(unittest.TestCase):
    def _run(self, **overrides):
        opp = overrides.pop("opportunity", _opportunity())
        kw = overrides.pop("keyword_evidence", [_keyword_evidence()])
        programs = overrides.pop("programs", [_program()])
        consent = overrides.pop("consent_mechanism", "Double opt-in email form")
        value = overrides.pop("value_exchange", "Free buyer guide PDF")
        prior = overrides.pop("prior_metrics", None)
        return run_compounding_lane(opp, kw, programs, consent, value, prior, as_of=_NOW)

    def test_happy_path_draft_shadow(self):
        result = self._run()
        self.assertEqual(result.publication_state, "DRAFT_SHADOW")
        self.assertIsNone(result.learning_proposal)  # no metrics

    def test_result_sha256_is_64_hex(self):
        result = self._run()
        self.assertRegex(result.result_sha256, r"^[0-9a-f]{64}$")

    def test_determinism(self):
        r1 = self._run()
        r2 = self._run()
        self.assertEqual(r1.result_sha256, r2.result_sha256)

    def test_no_metrics_no_learning_proposal(self):
        result = self._run()
        self.assertIsNone(result.learning_proposal)

    def test_no_metrics_no_measure_metrics_receipt(self):
        result = self._run()
        actions = [r.action for r in result.decision_receipts]
        self.assertNotIn("measure_metrics", actions)

    def test_with_metrics_learning_proposal_present(self):
        # Compounding lane requires VERIFIED metrics; INFERRED is rejected at the gate.
        snap = MetricSnapshot(
            opportunity_id="opp-1",
            impressions=100, visits=10, affiliate_clicks=2, conversions=0,
            commission_accrued=Decimal("0"), payout_received=Decimal("0"),
            click_through_rate=None, conversion_rate=None,
            earnings_per_click=None, revenue_per_visit=None,
            evidence_state=EvidenceState.VERIFIED,
            evidence_refs=("ref:metric-1",),
        )
        result = self._run(prior_metrics=snap)
        self.assertIsNotNone(result.learning_proposal)

    def test_with_metrics_measure_metrics_receipt_present(self):
        snap = MetricSnapshot(
            opportunity_id="opp-1",
            impressions=100, visits=10, affiliate_clicks=2, conversions=0,
            commission_accrued=Decimal("0"), payout_received=Decimal("0"),
            click_through_rate=None, conversion_rate=None,
            earnings_per_click=None, revenue_per_visit=None,
            evidence_state=EvidenceState.VERIFIED,
            evidence_refs=("ref:metric-1",),
        )
        result = self._run(prior_metrics=snap)
        actions = [r.action for r in result.decision_receipts]
        self.assertIn("measure_metrics", actions)

    def test_measure_metrics_receipt_uses_metric_evidence_only(self):
        snap = MetricSnapshot(
            opportunity_id="opp-1",
            impressions=100, visits=10, affiliate_clicks=2, conversions=0,
            commission_accrued=Decimal("0"), payout_received=Decimal("0"),
            click_through_rate=None, conversion_rate=None,
            earnings_per_click=None, revenue_per_visit=None,
            evidence_state=EvidenceState.VERIFIED,
            evidence_refs=("ref:metric-only",),
        )
        result = self._run(prior_metrics=snap)
        receipt = next(r for r in result.decision_receipts if r.action == "measure_metrics")
        self.assertIn("ref:metric-only", receipt.evidence_refs)
        # opportunity evidence not in measure_metrics receipt
        self.assertNotIn("artifact:research-1", receipt.evidence_refs)

    def test_metrics_wrong_opportunity_rejected(self):
        snap = MetricSnapshot(
            opportunity_id="opp-WRONG",
            impressions=0, visits=0, affiliate_clicks=0, conversions=0,
            commission_accrued=Decimal("0"), payout_received=Decimal("0"),
            click_through_rate=None, conversion_rate=None,
            earnings_per_click=None, revenue_per_visit=None,
            evidence_state=EvidenceState.INFERRED,
            evidence_refs=("ref:1",),
        )
        with self.assertRaises(ValueError):
            self._run(prior_metrics=snap)

    def test_metrics_unknown_state_rejected(self):
        snap = MetricSnapshot(
            opportunity_id="opp-1",
            impressions=0, visits=0, affiliate_clicks=0, conversions=0,
            commission_accrued=Decimal("0"), payout_received=Decimal("0"),
            click_through_rate=None, conversion_rate=None,
            earnings_per_click=None, revenue_per_visit=None,
            evidence_state=EvidenceState.UNKNOWN,
            evidence_refs=(),
        )
        with self.assertRaises(ValueError):
            self._run(prior_metrics=snap)

    def test_metrics_empty_evidence_refs_rejected(self):
        snap = MetricSnapshot(
            opportunity_id="opp-1",
            impressions=100, visits=10, affiliate_clicks=0, conversions=0,
            commission_accrued=Decimal("0"), payout_received=Decimal("0"),
            click_through_rate=None, conversion_rate=None,
            earnings_per_click=None, revenue_per_visit=None,
            evidence_state=EvidenceState.INFERRED,
            evidence_refs=(),
        )
        with self.assertRaises(ValueError):
            self._run(prior_metrics=snap)

    def test_analyze_funnel_receipt_includes_keyword_and_opportunity_evidence(self):
        result = self._run()
        receipt = next(r for r in result.decision_receipts if r.action == "analyze_funnel")
        self.assertIn("artifact:research-1", receipt.evidence_refs)
        self.assertIn("artifact:kw-research-1", receipt.evidence_refs)

    def test_draft_offer_receipt_includes_terms_ref(self):
        result = self._run()
        receipt = next(r for r in result.decision_receipts if r.action == "draft_offer")
        self.assertIn("artifact:terms-1", receipt.evidence_refs)

    def test_prepare_experiment_receipt_combines_all_evidence(self):
        result = self._run()
        receipt = next(r for r in result.decision_receipts if r.action == "prepare_experiment")
        self.assertIn("artifact:research-1", receipt.evidence_refs)
        self.assertIn("artifact:kw-research-1", receipt.evidence_refs)
        self.assertIn("artifact:approval-1", receipt.evidence_refs)
        self.assertIn("artifact:terms-1", receipt.evidence_refs)

    def test_keyword_freshness_fields_in_clusters(self):
        result = self._run()
        cluster = result.keyword_clusters[0]
        self.assertNotEqual(cluster.verified_at, "")
        self.assertGreater(cluster.ttl_seconds, 0)

    def test_approved_program_snapshots_exactly_cover_site_plan(self):
        result = self._run()
        snap_ids = {s.program_id for s in result.approved_program_snapshots}
        plan_ids = set(result.site_plan.approved_program_ids)
        self.assertEqual(snap_ids, plan_ids)

    def test_duplicate_program_ids_rejected(self):
        prog = _program()
        with self.assertRaises(ValueError):
            self._run(programs=[prog, prog])

    def test_restriction_from_program_triggers_review_hold(self):
        prog = _program(restrictions=("no-email-list",))
        result = self._run(programs=[prog])
        self.assertTrue(result.review_hold)
        self.assertIn("no-email-list", result.restrictions_held_for_review)

    def test_restriction_deduplication(self):
        prog1 = _program(program_id="prog-1", restrictions=("rule-y",))
        prog2 = _program(
            program_id="prog-2",
            evidence_refs=("artifact:approval-2",),
            terms_ref="artifact:terms-2",
            tracking_url="https://merchant2.example/?ref=x",
            restrictions=("rule-y",),
        )
        result = run_compounding_lane(
            _opportunity(), [_keyword_evidence()], [prog1, prog2],
            "Double opt-in", "Free guide", as_of=_NOW,
        )
        self.assertEqual(result.restrictions_held_for_review.count("rule-y"), 1)

    def test_tamper_different_cluster_different_sha(self):
        r1 = self._run(keyword_evidence=[_keyword_evidence(head_term="term-A")])
        r2 = self._run(keyword_evidence=[_keyword_evidence(head_term="term-B")])
        self.assertNotEqual(r1.result_sha256, r2.result_sha256)

    def test_compounding_lane_result_rejects_missing_snapshot(self):
        # Build a result then verify the model rejects snapshot/plan mismatch
        with self.assertRaises((ValueError, TypeError)):
            plan = SitePlan(
                opportunity_id="opp-1",
                publication_state="DRAFT_SHADOW",
                affiliate_disclosure="disclosure",
                pages=(),
                approved_program_ids=("prog-1",),
            )
            email = EmailCapturePlan(
                plan_id="a" * 64,
                opportunity_id="opp-1",
                consent_mechanism="opt-in",
                value_exchange="guide",
                evidence_refs=("ref:1",),
            )
            receipt = decision_receipt("analyze_funnel", ("ref:1",))
            CompoundingLaneResult(
                opportunity_id="opp-1",
                keyword_clusters=(KeywordCluster(
                    cluster_id="kw-1",
                    head_term="term",
                    variants=("v1",),
                    buyer_intent_score=0.8,
                    evidence_state=EvidenceState.VERIFIED,
                    evidence_refs=("ref:1",),
                    verified_at="2026-08-25T10:00:00+00:00",
                    ttl_seconds=86400,
                ),),
                site_plan=plan,
                email_capture_plan=email,
                learning_proposal=None,
                publication_state="DRAFT_SHADOW",
                result_sha256="b" * 64,
                decision_receipts=(receipt,),
                approved_program_snapshots=(),  # missing prog-1
            )

    # ------------------------------------------------------------------
    # OURS-only invariant tests (use run_compounding() helper with
    # verified_opportunity / keyword / affiliate_program fixtures)
    # ------------------------------------------------------------------

    def test_happy_path_without_metrics_is_draft_shadow(self):
        result = run_compounding()
        self.assertEqual(result.publication_state, "DRAFT_SHADOW")
        self.assertIsNone(result.learning_proposal)
        # HARDENED: metrics_snapshot removed from CompoundingLaneResult;
        # absence of metrics is confirmed by no measure_metrics receipt.
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
        # HARDENED: metrics_snapshot removed from CompoundingLaneResult;
        # metrics commitment is evidenced by learning_proposal and measure_metrics receipt.
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
        # HARDENED: restrictions_held_for_review is tuple[str,...] — plain strings, no source_id pairs.
        self.assertEqual(
            result.restrictions_held_for_review,
            ("Manual review",),
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
        # HARDENED: metrics_snapshot removed from CompoundingLaneResult.
        # Integrity is now enforced by:
        #   1. has_measure_receipt → learning_proposal not None gate
        #   2. Receipt tamper detection (below)
        #   3. learning_proposal.evidence_state VERIFIED guard
        # Clearing learning_proposal when a measure_metrics receipt exists is rejected.
        with self.assertRaises(ValueError):
            replace(measured, learning_proposal=None)
        # Scope mismatch (opportunity_id="different") is caught at lane time;
        # see test_metrics_with_unknown_empty_or_wrong_scope_are_rejected.
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


# ---------------------------------------------------------------------------
# Static hardening -- no forbidden imports in lane module files
# ---------------------------------------------------------------------------

class StaticLaneHardeningTests(unittest.TestCase):
    def test_engine_no_forbidden_imports(self):
        import ast
        from pathlib import Path
        forbidden = {"requests", "httpx", "socket", "subprocess", "paramiko",
                     "ftplib", "boto3", "selenium", "playwright"}
        forbidden_calls = {"eval", "exec", "compile"}
        for path in Path("apps/revenue_engine").glob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        self.assertNotIn(alias.name.split(".")[0], forbidden, path)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    self.assertNotIn(node.module.split(".")[0], forbidden, path)
                elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                    self.assertNotIn(node.func.id, forbidden_calls, path)


if __name__ == "__main__":
    unittest.main()
