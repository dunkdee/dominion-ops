from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from apps.revenue_runtime.core import deterministic_variant, evaluate_treatment
from apps.revenue_runtime.evaluator import reconcile_paid_orders
from apps.revenue_runtime.store import RevenueStore
from apps.revenue_runtime import wix_adapter


ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / "governance" / "revenue_execution_policy.json"
INSTALLER = ROOT / "scripts" / "revenue_runtime" / "install_revenue_runtime.sh"
KILL = ROOT / "scripts" / "revenue_runtime" / "disable_revenue_runtime.sh"
SERVICE = ROOT / "apps" / "revenue_runtime" / "service.py"


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload
    def json(self):
        return self.payload


class RevenueExecutionRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))

    def payload(self, exp_id="e1", product_id="p1"):
        return {
            "id": exp_id,
            "name": "test experiment",
            "product_id": product_id,
            "target_url": "https://www.voltedgegoods.com/product-page/test",
            "success_event": "purchase",
            "wix_field": "plainDescription",
            "treatment_pct": 50,
            "auto_promote": True,
            "control": {"headline":"A","body_text":"A","cta_text":"Shop","wix_value":"<p>A</p>"},
            "treatment": {"headline":"B","body_text":"B","cta_text":"Shop","wix_value":"<p>B</p>"},
        }

    def test_deterministic_split_is_stable_and_balanced(self):
        self.assertEqual(deterministic_variant("exp", "abc", 50), deterministic_variant("exp", "abc", 50))
        values = [deterministic_variant("exp", f"visitor-{i}", 50) for i in range(2000)]
        ratio = values.count("treatment") / len(values)
        self.assertGreater(ratio, 0.45)
        self.assertLess(ratio, 0.55)

    def test_statistical_winner_gate_can_promote_treatment(self):
        result = evaluate_treatment({
            "control": {"visitors": 500, "conversions": 40, "revenue_cents": 400000},
            "treatment": {"visitors": 500, "conversions": 70, "revenue_cents": 700000},
        }, self.policy)
        self.assertEqual(result.decision, "PROMOTE_TREATMENT")
        self.assertGreaterEqual(result.confidence, self.policy["statistics"]["min_confidence"])

    def test_revenue_guardrail_blocks_conversion_only_winner(self):
        result = evaluate_treatment({
            "control": {"visitors": 500, "conversions": 40, "revenue_cents": 800000},
            "treatment": {"visitors": 500, "conversions": 70, "revenue_cents": 300000},
        }, self.policy)
        self.assertEqual(result.decision, "KEEP_CONTROL")
        self.assertEqual(result.reason, "REVENUE_GUARDRAIL")

    def test_event_ingestion_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = RevenueStore(Path(tmp) / "r.db")
            store.create_experiment(self.payload())
            store.activate("e1")
            self.assertTrue(store.record_event(event_id="evt1", experiment_id="e1", visitor_id="v1", variant="control", event_type="impression"))
            self.assertFalse(store.record_event(event_id="evt1", experiment_id="e1", visitor_id="v1", variant="control", event_type="impression"))
            self.assertEqual(store.metrics("e1")["control"]["visitors"], 1)

    def test_only_one_active_experiment_per_product(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = RevenueStore(Path(tmp) / "r.db")
            store.create_experiment(self.payload("e1", "p1"))
            store.create_experiment(self.payload("e2", "p1"))
            store.activate("e1")
            with self.assertRaisesRegex(ValueError, "already has active experiment"):
                store.activate("e2")

    def test_paid_order_reconciliation_requires_unique_candidate(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = RevenueStore(Path(tmp) / "r.db")
            store.create_experiment(self.payload())
            store.activate("e1")
            order_time = datetime.now(timezone.utc)
            click_time = (order_time - timedelta(minutes=10)).isoformat()
            store.record_event(event_id="imp", experiment_id="e1", visitor_id="v1", variant="control", event_type="impression", occurred_at=click_time)
            store.record_event(event_id="clk", experiment_id="e1", visitor_id="v1", variant="control", event_type="click", occurred_at=click_time)
            orders = [{"id":"o1","created_date":order_time.isoformat(),"items":[{"product_id":"p1","revenue_cents":2999}]}]
            with patch("apps.revenue_runtime.evaluator.wix_adapter.search_recent_paid_orders", return_value=orders):
                receipts = reconcile_paid_orders(store, self.policy)
            self.assertEqual(receipts[0]["status"], "attributed")
            self.assertEqual(store.metrics("e1")["control"]["revenue_cents"], 2999)
            self.assertEqual(store.metrics("e1")["control"]["conversions"], 1)

    def test_ambiguous_paid_order_stays_unattributed(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = RevenueStore(Path(tmp) / "r.db")
            store.create_experiment(self.payload())
            store.activate("e1")
            order_time = datetime.now(timezone.utc)
            for idx, variant in ((1,"control"),(2,"treatment")):
                ts = (order_time - timedelta(minutes=idx)).isoformat()
                store.record_event(event_id=f"c{idx}", experiment_id="e1", visitor_id=f"v{idx}", variant=variant, event_type="click", occurred_at=ts)
            orders = [{"id":"o1","created_date":order_time.isoformat(),"items":[{"product_id":"p1","revenue_cents":2999}]}]
            with patch("apps.revenue_runtime.evaluator.wix_adapter.search_recent_paid_orders", return_value=orders):
                receipts = reconcile_paid_orders(store, self.policy)
            self.assertEqual(receipts[0]["status"], "unattributed")
            self.assertEqual(receipts[0]["reason"], "AMBIGUOUS_CANDIDATES")
            self.assertEqual(store.metrics("e1")["control"]["conversions"], 0)
            self.assertEqual(store.metrics("e1")["treatment"]["conversions"], 0)

    def test_wix_update_uses_current_revision_and_verifies_advance(self):
        before = {"id":"p1","revision":"10","plainDescription":"<p>old</p>"}
        after = {"id":"p1","revision":"11","plainDescription":"<p>new</p>"}
        with patch("apps.revenue_runtime.wix_adapter.get_product", side_effect=[before, after]), patch("apps.revenue_runtime.wix_adapter._request", return_value=FakeResponse({})) as req:
            result = wix_adapter.update_plain_description("p1", "<p>new</p>")
        self.assertEqual(result["before_revision"], "10")
        self.assertEqual(result["after_revision"], "11")
        payload = req.call_args.kwargs["json"]
        self.assertEqual(payload["product"]["revision"], "10")
        self.assertEqual(set(payload["product"]), {"id","revision","plainDescription"})

    def test_order_reader_strips_buyer_pii(self):
        payload = {"orders":[{
            "id":"o1","createdDate":"2026-08-25T00:00:00Z","paymentStatus":"PAID",
            "buyerInfo":{"email":"private@example.com"},
            "lineItems":[{"quantity":1,"catalogReference":{"appId":wix_adapter.STORES_APP_ID,"catalogItemId":"p1"},"totalPriceAfterTax":{"amount":"29.99"}}]
        }]}
        with patch("apps.revenue_runtime.wix_adapter._request", return_value=FakeResponse(payload)):
            orders = wix_adapter.search_recent_paid_orders()
        self.assertEqual(orders[0]["items"][0]["revenue_cents"], 2999)
        self.assertNotIn("buyerInfo", orders[0])
        self.assertNotIn("email", json.dumps(orders[0]))

    def test_governance_forbids_price_spend_and_destructive_automation(self):
        actions = self.policy["automatic_external_actions"]
        self.assertTrue(actions["cro_reversible"])
        self.assertFalse(actions["price_change"])
        self.assertFalse(actions["paid_spend"])
        self.assertFalse(actions["provider_change"])
        self.assertFalse(actions["destructive_change"])
        self.assertEqual(self.policy["wix"]["allowed_product_fields"], ["plainDescription"])
        self.assertEqual(self.policy["attribution"]["auto_promotion_requires_success_event"], "purchase")

    def test_public_offer_copy_is_escaped_not_raw_html(self):
        source = SERVICE.read_text(encoding="utf-8")
        self.assertIn("html.escape(copy['body_text'])", source)
        self.assertNotIn("copy['body_html']", source)

    def test_service_and_installer_expose_only_bounded_public_surface(self):
        source = SERVICE.read_text(encoding="utf-8")
        installer = INSTALLER.read_text(encoding="utf-8")
        kill = KILL.read_text(encoding="utf-8")
        self.assertIn('/r/{experiment_id}', source)
        self.assertIn('/revenue/events', source)
        self.assertIn('_require_auth(request)', source)
        self.assertIn('@dominion_revenue_public path /r /r/* /revenue/events', installer)
        self.assertNotIn('/control/*', installer)
        self.assertIn('sudo python3 - "$caddy_path"', installer)
        self.assertNotIn('sudo "$buddy_python" - "$caddy_path"', installer)
        self.assertIn('OnUnitActiveSec=10min', installer)
        self.assertIn('DOMINION_REVENUE_RUNTIME=DISABLED', kill)


if __name__ == "__main__":
    unittest.main()
