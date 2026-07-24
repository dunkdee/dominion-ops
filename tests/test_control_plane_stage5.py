from __future__ import annotations
import copy
import unittest
from control_plane.analytics_audit import build_growth_intelligence_audit
from control_plane.external_estimates import adapt_external_estimate

class Stage5Tests(unittest.TestCase):
    def fixture(self) -> dict:
        return {
            "snapshot_id":"signal_1","source_kind":"EXTERNAL_ESTIMATED","provider":"SIMILARWEB_EXPORT",
            "acquisition_method":"LOCAL_EXPORT","domain":"example.com","period_start":"2026-04-01",
            "period_end":"2026-06-30","as_of":"2026-07-24T00:00:00Z","evidence":["export:1"],
            "metrics":{"estimated_visits":1000,"bounce_rate":0.65,"pages_per_visit":1.5,
            "average_visit_duration_seconds":60,"channel_shares":{"direct":0.2,"organic":0.5,"social":0.3}}
        }

    def test_valid_estimate_is_market_signal_only(self) -> None:
        result = adapt_external_estimate(self.fixture())
        self.assertEqual(result["status"], "ESTIMATED_MARKET_SIGNAL")
        self.assertFalse(result["revenue_verified"])
        self.assertFalse(result["external_execution_authorized"])
        self.assertEqual(result["external_actions"], [])

    def test_sensitive_key_fails_closed(self) -> None:
        value = self.fixture()
        value["email"] = "person@example.com"
        result = adapt_external_estimate(value)
        self.assertEqual(result["status"], "HOLD")
        self.assertIn("sensitive_or_secret_material_forbidden", result["errors"])

    def test_channel_shares_must_sum_to_one(self) -> None:
        value = self.fixture()
        value["metrics"]["channel_shares"] = {"direct":0.2,"organic":0.2}
        result = adapt_external_estimate(value)
        self.assertEqual(result["status"], "HOLD")
        self.assertIn("channel_shares_must_sum_to_one", result["errors"])

    def test_invalid_domain_holds(self) -> None:
        value = self.fixture()
        value["domain"] = "localhost"
        self.assertEqual(adapt_external_estimate(value)["status"], "HOLD")

    def test_audit_has_no_revenue_or_execution_claim(self) -> None:
        signal = adapt_external_estimate(self.fixture())
        report = build_growth_intelligence_audit(signal)
        self.assertEqual(report["status"], "MARKET_SIGNAL_ONLY")
        self.assertFalse(report["claims_boundary"]["revenue_claim_allowed"])
        self.assertFalse(report["external_execution_authorized"])
        self.assertFalse(report["money_moved"])
        self.assertEqual(report["pricing_status"], "UNSET_REQUIRES_HUMAN_APPROVAL")

    def test_unusable_signal_holds_audit(self) -> None:
        value = self.fixture()
        value["evidence"] = []
        report = build_growth_intelligence_audit(adapt_external_estimate(value))
        self.assertEqual(report["status"], "HOLD")

    def test_verified_first_party_only_advances_to_human_review(self) -> None:
        signal = adapt_external_estimate(self.fixture())
        report = build_growth_intelligence_audit(signal, first_party_evidence={
            "source_kind":"FIRST_PARTY_VERIFIED","status":"VERIFIED","evidence":["approved-export"]
        })
        self.assertEqual(report["status"], "EVIDENCE_READY_FOR_HUMAN_REVIEW")
        self.assertFalse(report["external_execution_authorized"])

    def test_tampered_revenue_verified_flag_holds(self) -> None:
        signal = adapt_external_estimate(self.fixture())
        tampered = copy.deepcopy(signal)
        tampered["revenue_verified"] = True
        report = build_growth_intelligence_audit(tampered)
        self.assertEqual(report["status"], "HOLD")

if __name__ == "__main__":
    unittest.main()
