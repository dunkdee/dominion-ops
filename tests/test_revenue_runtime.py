from __future__ import annotations

import json
import unittest
from copy import deepcopy
from pathlib import Path

from buddy_core.core.revenue_runtime import (
    MAX_PAYLOAD_BYTES,
    RUNTIME_SCHEMA,
    run_compounding_payload,
    run_fast_cash_payload,
)


def verified_opportunity() -> dict:
    return {
        "opportunity_id": "opp-runtime-1",
        "niche": "evidence-backed commerce education",
        "buyer_intent": 0.9,
        "demand": 0.8,
        "competition": 0.4,
        "economics": 0.8,
        "zero_capital_fit": 0.9,
        "original_value_fit": 0.9,
        "evidence_state": "VERIFIED",
        "evidence_refs": ["evidence://opportunity/1"],
    }


def verified_asset() -> dict:
    return {
        "asset_id": "asset-1",
        "title": "Evidence Commerce Guide",
        "asset_type": "digital_guide",
        "url_slug": "evidence-commerce-guide",
        "evidence_state": "VERIFIED",
        "evidence_refs": ["evidence://asset/1"],
        "restrictions": [],
    }


def approved_program() -> dict:
    return {
        "program_id": "program-1",
        "name": "Verified Partner",
        "status": "APPROVED",
        "commission_rate": "0.20",
        "cookie_days": 30,
        "payout_threshold": "50",
        "tracking_url": "https://example.com/track/1",
        "terms_ref": "evidence://program/terms/1",
        "evidence_state": "VERIFIED",
        "evidence_refs": ["evidence://program/approval/1"],
        "restrictions": [],
    }


def fast_cash_payload() -> dict:
    return {
        "opportunity": verified_opportunity(),
        "assets": [verified_asset()],
        "draft_inputs": [
            {
                "asset_id": "asset-1",
                "channel": "owned-site",
                "proposed_text": (
                    "Compare the documented features, limitations, and source "
                    "evidence before deciding whether this guide fits your needs."
                ),
                "cta": "Review the sourced comparison",
                "measurement_dimensions": ["clicks", "conversions"],
            }
        ],
    }


def compounding_payload() -> dict:
    return {
        "opportunity": verified_opportunity(),
        "affiliate_programs": [approved_program()],
        "keyword_evidence": [
            {
                "head_term": "evidence commerce guide",
                "variants": ["commerce guide with sources"],
                "buyer_intent_score": 0.85,
                "evidence_state": "VERIFIED",
                "evidence_refs": ["evidence://keyword/1"],
                "verified_at": "2026-08-25T12:00:00Z",
                "ttl_seconds": 3600,
            }
        ],
        "consent_mechanism": "Unchecked explicit opt-in checkbox",
        "value_exchange": "A sourced comparison worksheet",
        "as_of": "2026-08-25T12:10:00Z",
    }


class RevenueRuntimeTests(unittest.TestCase):
    def test_fast_cash_payload_is_draft_shadow_and_json_native(self) -> None:
        result = run_fast_cash_payload(fast_cash_payload())

        self.assertEqual(result["schema"], RUNTIME_SCHEMA)
        self.assertEqual(result["governance"], "RADAH MEMSHALAH")
        self.assertEqual(result["lane"], "FAST_CASH")
        self.assertEqual(result["publication_state"], "DRAFT_SHADOW")
        self.assertFalse(result["external_actions_executed"])
        self.assertEqual(result["result"]["publication_state"], "DRAFT_SHADOW")
        json.dumps(result, allow_nan=False, sort_keys=True)

    def test_fast_cash_is_deterministic(self) -> None:
        first = run_fast_cash_payload(fast_cash_payload())
        second = run_fast_cash_payload(fast_cash_payload())
        self.assertEqual(
            first["result"]["package_sha256"],
            second["result"]["package_sha256"],
        )

    def test_unverified_fast_cash_opportunity_is_blocked(self) -> None:
        payload = fast_cash_payload()
        payload["opportunity"]["evidence_state"] = "INFERRED"
        with self.assertRaisesRegex(ValueError, "VERIFIED opportunity"):
            run_fast_cash_payload(payload)

    def test_unknown_top_level_field_is_blocked(self) -> None:
        payload = fast_cash_payload()
        payload["publish_now"] = True
        with self.assertRaisesRegex(ValueError, "unsupported fields"):
            run_fast_cash_payload(payload)

    def test_legacy_draft_evidence_refs_are_rejected(self) -> None:
        payload = fast_cash_payload()
        payload["draft_inputs"][0]["evidence_refs"] = ["evidence://draft/legacy"]
        with self.assertRaisesRegex(ValueError, "evidence_refs is no longer supported"):
            run_fast_cash_payload(payload)

    def test_draft_missing_measurement_dimensions_is_rejected(self) -> None:
        payload = fast_cash_payload()
        del payload["draft_inputs"][0]["measurement_dimensions"]
        with self.assertRaisesRegex(ValueError, "missing required fields"):
            run_fast_cash_payload(payload)

    def test_affiliate_draft_missing_terms_ref_is_rejected(self) -> None:
        payload = fast_cash_payload()
        draft = payload["draft_inputs"][0]
        draft["has_affiliate_links"] = True
        draft["affiliate_program_id"] = "program-1"
        draft["proposed_text"] = (
            "Affiliate disclosure: we may earn a commission. Compare the "
            "documented evidence and limitations before deciding."
        )
        # affiliate_terms_ref absent → DraftInput.__post_init__ rejects
        with self.assertRaisesRegex(ValueError, "affiliate_terms_ref is required"):
            run_fast_cash_payload(payload)

    def test_affiliate_draft_requires_registry_evidence(self) -> None:
        payload = fast_cash_payload()
        draft = payload["draft_inputs"][0]
        draft["has_affiliate_links"] = True
        draft["affiliate_program_id"] = "program-1"
        draft["affiliate_terms_ref"] = "evidence://program/terms/1"
        draft["original_value_signals"] = ["structured comparison criteria"]
        draft["proposed_text"] = (
            "Affiliate disclosure: we may earn a commission. Compare the "
            "documented evidence and limitations before deciding."
        )
        with self.assertRaisesRegex(ValueError, "not found in programs"):
            run_fast_cash_payload(payload)

    def test_compounding_payload_is_draft_shadow(self) -> None:
        result = run_compounding_payload(compounding_payload())

        self.assertEqual(result["lane"], "COMPOUNDING")
        self.assertEqual(result["publication_state"], "DRAFT_SHADOW")
        self.assertFalse(result["external_actions_executed"])
        self.assertEqual(result["result"]["publication_state"], "DRAFT_SHADOW")
        self.assertEqual(
            result["result"]["approved_program_snapshots"][0]["program_id"],
            "program-1",
        )

    def test_compounding_is_deterministic_for_fixed_as_of(self) -> None:
        first = run_compounding_payload(compounding_payload())
        second = run_compounding_payload(compounding_payload())
        self.assertEqual(
            first["result"]["result_sha256"],
            second["result"]["result_sha256"],
        )

    def test_compounding_requires_timezone_aware_as_of(self) -> None:
        payload = compounding_payload()
        payload["as_of"] = "2026-08-25T12:10:00"
        with self.assertRaisesRegex(ValueError, "timezone"):
            run_compounding_payload(payload)

    def test_stale_keyword_evidence_is_blocked(self) -> None:
        payload = compounding_payload()
        payload["as_of"] = "2026-08-25T14:00:00Z"
        with self.assertRaisesRegex(ValueError, "stale"):
            run_compounding_payload(payload)

    def test_payload_limit_is_enforced(self) -> None:
        payload = fast_cash_payload()
        payload["draft_inputs"][0]["proposed_text"] = "x" * MAX_PAYLOAD_BYTES
        with self.assertRaisesRegex(ValueError, "runtime limit"):
            run_fast_cash_payload(payload)

    def test_input_is_not_mutated(self) -> None:
        payload = compounding_payload()
        before = deepcopy(payload)
        run_compounding_payload(payload)
        self.assertEqual(payload, before)

    def test_bridge_exposes_authenticated_revenue_routes_and_isolates_networking(self) -> None:
        root = Path(__file__).resolve().parents[1]
        bridge = (root / "buddy_core" / "buddy_bridge_api.py").read_text(encoding="utf-8")
        revenue_runtime = (root / "buddy_core" / "core" / "revenue_runtime.py").read_text(encoding="utf-8")

        self.assertIn('/webhook/buddy/revenue/fast-cash', bridge)
        self.assertIn('/webhook/buddy/revenue/compounding', bridge)
        self.assertIn("if not _authorized(request):", bridge)
        self.assertIn("MAX_PAYLOAD_BYTES", bridge)

        # Revenue execution stays deterministic and network-free.
        self.assertNotIn("requests.", revenue_runtime)
        self.assertNotIn("urllib.request", revenue_runtime)
        self.assertNotIn("subprocess.", revenue_runtime)

        # Bridge networking is separately constrained to the governed loopback
        # MCP fabric and only read-only registered connectors may be invoked.
        self.assertIn("BUDDY_MCP_BASE_URL", bridge)
        self.assertIn("http://127.0.0.1:8390", bridge)
        self.assertIn('parsed.hostname not in {"127.0.0.1", "localhost", "::1"}', bridge)
        self.assertIn("connector not registered as read-only", bridge)


if __name__ == "__main__":
    unittest.main()
