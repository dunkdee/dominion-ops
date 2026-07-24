from __future__ import annotations

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load(path: str) -> dict:
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


class Stage7RevenueVerticalTests(unittest.TestCase):
    def test_wave_one_is_wix_and_kdp_only(self):
        plan = load("governance/revenue_vertical_activation_plan.json")
        self.assertEqual(plan["current_wave"]["primary_verticals"], ["commerce_fulfillment", "kdp_publishing"])
        self.assertEqual(plan["wave_capacity"]["maximum_primary_verticals"], 2)
        self.assertEqual(plan["current_wave"]["activation_status"], "NOT_ACTIVATED")

    def test_large_outcome_is_not_forecast(self):
        plan = load("governance/revenue_vertical_activation_plan.json")
        self.assertTrue(plan["million_dollar_outcome_is_target_not_forecast"])

    def test_no_external_authority(self):
        plan = load("governance/revenue_vertical_activation_plan.json")
        for field in ("external_execution_authorized", "pricing_authorized", "publication_authorized", "money_movement_authorized"):
            self.assertFalse(plan[field])

    def test_registry_prioritizes_cash_engines(self):
        registry = load("governance/verticals.json")
        self.assertEqual([v["id"] for v in registry["verticals"][:3]], ["commerce_fulfillment", "kdp_publishing", "analytics_services"])
        self.assertEqual([v["priority"] for v in registry["verticals"][:3]], [1, 2, 3])

    def test_wix_remains_blocked_until_transaction_evidence(self):
        wix = load("revenue/verticals/wix_store.json")
        self.assertIn("existing_wix_isolation_diagnosis_not_closed", wix["current_blockers"])
        self.assertIn("checkout_succeeds_with_controlled_test_purchase", wix["launch_gates"])
        self.assertFalse(wix["revenue_verified"])
        self.assertFalse(wix["external_execution_authorized"])

    def test_kdp_requires_rights_and_human_publication(self):
        kdp = load("revenue/verticals/kdp_publishing.json")
        self.assertIn("publish_without_rights_review", kdp["prohibited_actions"])
        self.assertIn("autonomous_kdp_upload_or_publication", kdp["prohibited_actions"])
        self.assertIn("human_overseer_approves_upload_and_publication", kdp["launch_gates"])

    def test_analytics_monetizes_analysis_not_raw_data(self):
        analytics = load("revenue/verticals/analytics_services.json")
        self.assertIn("sell_raw_personal_data", analytics["prohibited_actions"])
        self.assertIn("represent_estimates_as_verified_revenue", analytics["prohibited_actions"])
        self.assertEqual(analytics["pricing_status"], "UNSET_REQUIRES_HUMAN_APPROVAL")

    def test_runtime_stays_shadow_only(self):
        gates = load("governance/runtime_activation_gates.json")
        self.assertEqual(gates["stage"], 7)
        self.assertEqual(gates["mode"], "shadow_only")
        self.assertFalse(gates["external_execution_enabled"])
        self.assertFalse(gates["revenue_vertical_activation_enabled"])
        self.assertIn("activate_revenue_wave_without_human_approval", gates["blocked_capabilities"])


if __name__ == "__main__":
    unittest.main()
