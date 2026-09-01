import unittest
from copy import deepcopy
from pathlib import Path

from buddy_core.core.revenue_runtime import (
    MAX_PAYLOAD_BYTES,
    run_compounding_payload,
    run_fast_cash_payload,
)


def opportunity_payload() -> dict:
    return {
        "opportunity_id": "opp-1",
        "niche": "test niche",
        "buyer_intent": 0.9,
        "demand": 0.9,
        "competition": 0.4,
        "economics": 0.8,
        "zero_capital_fit": 0.9,
        "original_value_fit": 0.8,
        "evidence_state": "VERIFIED",
        "evidence_refs": ["evidence:opp"],
    }


def fast_cash_payload() -> dict:
    return {
        "opportunity": opportunity_payload(),
        "assets": [
            {
                "asset_id": "asset-1",
                "title": "Comparison guide",
                "asset_type": "article",
                "url_slug": "comparison-guide",
                "evidence_state": "VERIFIED",
                "evidence_refs": ["evidence:asset"],
                "restrictions": [],
            }
        ],
        "draft_inputs": [
            {
                "asset_id": "asset-1",
                "channel": "organic_search",
                "proposed_text": "Evidence-backed comparison draft.",
                "cta": "Review options",
                "evidence_refs": ["evidence:draft"],
                "has_affiliate_links": False,
                "original_value_signals": ["original comparison"],
            }
        ],
        "extra_evidence_refs": ["evidence:extra"],
        "measurement_definitions": ["qualified_click=buyer-intent outbound click"],
    }


def compounding_payload() -> dict:
    return {
        "opportunity": opportunity_payload(),
        "affiliate_programs": [
            {
                "program_id": "program-1",
                "name": "Example Program",
                "status": "APPROVED",
                "commission_rate": "0.10",
                "cookie_days": 30,
                "payout_threshold": "50.00",
                "tracking_url": "https://example.com/track",
                "terms_ref": "evidence:terms",
                "evidence_state": "VERIFIED",
                "evidence_refs": ["evidence:program"],
                "restrictions": [],
            }
        ],
        "keyword_evidence": [
            {
                "head_term": "best test product",
                "variants": ["test product comparison"],
                "buyer_intent_score": 0.9,
                "evidence_state": "VERIFIED",
                "evidence_refs": ["evidence:keyword"],
                "verified_at": "2026-08-25T13:30:00Z",
                "ttl_seconds": 7200,
            }
        ],
        "consent_mechanism": "Explicit opt-in checkbox",
        "value_exchange": "Buyer comparison guide",
        "email_evidence_refs": ["evidence:email"],
        "as_of": "2026-08-25T14:00:00Z",
    }


class RevenueRuntimeTests(unittest.TestCase):
    def test_fast_cash_returns_draft_shadow_envelope(self) -> None:
        result = run_fast_cash_payload(fast_cash_payload())
        self.assertEqual(result["lane"], "FAST_CASH")
        self.assertEqual(result["publication_state"], "DRAFT_SHADOW")
        self.assertFalse(result["external_actions_executed"])
        self.assertEqual(result["governance"], "RADAH MEMSHALAH")

    def test_compounding_returns_draft_shadow_envelope(self) -> None:
        result = run_compounding_payload(compounding_payload())
        self.assertEqual(result["lane"], "COMPOUNDING")
        self.assertEqual(result["publication_state"], "DRAFT_SHADOW")
        self.assertFalse(result["external_actions_executed"])
        self.assertEqual(result["governance"], "RADAH MEMSHALAH")

    def test_fast_cash_rejects_unknown_top_level_fields(self) -> None:
        payload = fast_cash_payload()
        payload["publish_now"] = True
        with self.assertRaisesRegex(ValueError, "unsupported fields"):
            run_fast_cash_payload(payload)

    def test_compounding_rejects_unknown_top_level_fields(self) -> None:
        payload = compounding_payload()
        payload["send_email"] = True
        with self.assertRaisesRegex(ValueError, "unsupported fields"):
            run_compounding_payload(payload)

    def test_unverified_opportunity_is_blocked(self) -> None:
        payload = fast_cash_payload()
        payload["opportunity"]["evidence_state"] = "UNVERIFIED"
        result = run_fast_cash_payload(payload)
        self.assertTrue(result["review_hold"])

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

        # The revenue adapter itself must remain deterministic and network-free.
        self.assertNotIn("requests.", revenue_runtime)
        self.assertNotIn("urllib.request", revenue_runtime)
        self.assertNotIn("subprocess.", revenue_runtime)

        # Buddy Bridge may use HTTP only for the separately governed loopback MCP
        # fabric, whose base URL is validated before every connector call.
        self.assertIn('BUDDY_MCP_BASE_URL', bridge)
        self.assertIn('http://127.0.0.1:8390', bridge)
        self.assertIn('parsed.hostname not in {"127.0.0.1", "localhost", "::1"}', bridge)
        self.assertIn('connector not registered as read-only', bridge)


if __name__ == "__main__":
    unittest.main()
