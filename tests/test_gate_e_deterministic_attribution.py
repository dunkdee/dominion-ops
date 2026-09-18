from __future__ import annotations

import hashlib
import json
import sqlite3
import tempfile
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from apps.revenue_runtime.attribution_bridge import AttributionBridgeStore
from apps.revenue_runtime.core import deterministic_variant
from apps.revenue_runtime.evaluator import load_policy, reconcile_paid_orders
from apps.revenue_runtime.store import RevenueStore
from apps.revenue_runtime import wix_adapter


ROOT = Path(__file__).resolve().parents[1]
SERVICE = ROOT / "apps" / "revenue_runtime" / "service.py"
WIX_BRIDGE = ROOT / "integrations" / "wix" / "voltedge" / "revenue-attribution-bridge.js"


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def json(self):
        return self.payload


class GateEDeterministicAttributionTests(unittest.TestCase):
    def setUp(self):
        self.policy = load_policy()

    def payload(self):
        return {
            "id": "e1",
            "name": "deterministic attribution",
            "product_id": "p1",
            "target_url": "https://www.voltedgegoods.com/product-page/test",
            "success_event": "purchase",
            "wix_field": "plainDescription",
            "treatment_pct": 50,
            "auto_promote": False,
            "control": {"headline": "A", "body_text": "A", "cta_text": "Shop", "wix_value": "A"},
            "treatment": {"headline": "B", "body_text": "B", "cta_text": "Shop", "wix_value": "B"},
        }

    def test_bridge_token_is_one_time_hashed_experiment_bound_and_four_hour_bounded(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "r.db"
            bridge = AttributionBridgeStore(db_path)
            before = datetime.now(timezone.utc)
            token = bridge.issue_token(experiment_id="e1", visitor_id="v1", variant="control")
            with sqlite3.connect(db_path) as db:
                row = db.execute(
                    "SELECT token_hash,issued_at,expires_at,used_at FROM attribution_bridge_tokens"
                ).fetchone()
            self.assertEqual(row[0], hashlib.sha256(token.encode()).hexdigest())
            self.assertNotEqual(row[0], token)
            self.assertIsNone(row[3])
            issued = datetime.fromisoformat(row[1])
            expires = datetime.fromisoformat(row[2])
            self.assertGreaterEqual(issued, before)
            self.assertEqual(expires - issued, timedelta(minutes=240))

            flow_id = str(uuid.uuid4())
            with self.assertRaisesRegex(ValueError, "experiment mismatch"):
                bridge.bind_token(
                    token=token,
                    expected_experiment_id="wrong",
                    purchase_flow_id=flow_id,
                )
            result = bridge.bind_token(
                token=token,
                expected_experiment_id="e1",
                purchase_flow_id=flow_id,
            )
            self.assertEqual(result["bound"], ["purchase_flow"])
            with self.assertRaisesRegex(ValueError, "already used"):
                bridge.bind_token(
                    token=token,
                    expected_experiment_id="e1",
                    purchase_flow_id=flow_id,
                )

    def test_native_purchase_flow_attribution_wins_with_multiple_clicks(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "r.db"
            store = RevenueStore(db_path)
            store.create_experiment(self.payload())
            store.activate("e1")
            bridge = AttributionBridgeStore(db_path)
            order_time = datetime.now(timezone.utc)

            for idx, visitor in enumerate(("v1", "v2"), start=1):
                variant = deterministic_variant("e1", visitor, 50)
                store.record_event(
                    event_id=f"c{idx}",
                    experiment_id="e1",
                    visitor_id=visitor,
                    variant=variant,
                    event_type="click",
                    occurred_at=(order_time - timedelta(minutes=idx)).isoformat(),
                )

            v1_variant = deterministic_variant("e1", "v1", 50)
            flow_id = str(uuid.uuid4())
            token = bridge.issue_token(experiment_id="e1", visitor_id="v1", variant=v1_variant)
            bridge.bind_token(
                token=token,
                expected_experiment_id="e1",
                purchase_flow_id=flow_id,
            )
            orders = [{
                "id": "o1",
                "created_date": order_time.isoformat(),
                "payment_status": "PAID",
                "purchase_flow_id": flow_id,
                "checkout_id": "",
                "items": [{"product_id": "p1", "revenue_cents": 2999}],
            }]
            with patch("apps.revenue_runtime.evaluator.wix_adapter.search_recent_paid_orders", return_value=orders):
                receipts = reconcile_paid_orders(store, self.policy)

            self.assertEqual(receipts[0]["status"], "attributed")
            self.assertEqual(receipts[0]["reason"], "WIX_PURCHASE_FLOW_LINK")
            self.assertEqual(receipts[0]["variant"], v1_variant)
            self.assertEqual(receipts[0]["receipt"], "SOURCE_TO_ORDER_ATTRIBUTION_RECEIPT=PASS")

    def test_native_order_link_wins_with_multiple_clicks_without_new_checkout(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "r.db"
            store = RevenueStore(db_path)
            store.create_experiment(self.payload())
            store.activate("e1")
            bridge = AttributionBridgeStore(db_path)
            order_time = datetime.now(timezone.utc)

            for idx, visitor in enumerate(("v1", "v2"), start=1):
                variant = deterministic_variant("e1", visitor, 50)
                store.record_event(
                    event_id=f"c{idx}",
                    experiment_id="e1",
                    visitor_id=visitor,
                    variant=variant,
                    event_type="click",
                    occurred_at=(order_time - timedelta(minutes=idx)).isoformat(),
                )

            order_id = str(uuid.uuid4())
            v1_variant = deterministic_variant("e1", "v1", 50)
            token = bridge.issue_token(experiment_id="e1", visitor_id="v1", variant=v1_variant)
            result = bridge.bind_token(
                token=token,
                expected_experiment_id="e1",
                order_id=order_id,
            )
            self.assertEqual(result["bound"], ["order"])

            orders = [{
                "id": order_id,
                "created_date": order_time.isoformat(),
                "payment_status": "PAID",
                "purchase_flow_id": "",
                "checkout_id": "",
                "items": [{"product_id": "p1", "revenue_cents": 0}],
            }]
            with patch("apps.revenue_runtime.evaluator.wix_adapter.search_recent_paid_orders", return_value=orders):
                receipts = reconcile_paid_orders(store, self.policy)

            self.assertEqual(receipts[0]["status"], "attributed")
            self.assertEqual(receipts[0]["reason"], "WIX_ORDER_LINK")
            self.assertEqual(receipts[0]["variant"], v1_variant)
            self.assertEqual(receipts[0]["revenue_cents"], 0)
            self.assertEqual(receipts[0]["receipt"], "SOURCE_TO_ORDER_ATTRIBUTION_RECEIPT=PASS")

    def test_unattributed_order_can_upgrade_after_late_native_binding(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "r.db"
            store = RevenueStore(db_path)
            store.create_experiment(self.payload())
            store.activate("e1")
            bridge = AttributionBridgeStore(db_path)
            order_time = datetime.now(timezone.utc)
            for idx, visitor in enumerate(("v1", "v2"), start=1):
                variant = deterministic_variant("e1", visitor, 50)
                store.record_event(
                    event_id=f"c{idx}", experiment_id="e1", visitor_id=visitor,
                    variant=variant, event_type="click",
                    occurred_at=(order_time - timedelta(minutes=idx)).isoformat(),
                )
            flow_id = str(uuid.uuid4())
            orders = [{
                "id": "o1", "created_date": order_time.isoformat(), "payment_status": "PAID",
                "purchase_flow_id": flow_id, "checkout_id": "",
                "items": [{"product_id": "p1", "revenue_cents": 2999}],
            }]
            with patch("apps.revenue_runtime.evaluator.wix_adapter.search_recent_paid_orders", return_value=orders):
                first = reconcile_paid_orders(store, self.policy)
            self.assertEqual(first[0]["reason"], "AMBIGUOUS_CANDIDATES")

            variant = deterministic_variant("e1", "v1", 50)
            token = bridge.issue_token(experiment_id="e1", visitor_id="v1", variant=variant)
            bridge.bind_token(token=token, expected_experiment_id="e1", purchase_flow_id=flow_id)
            with patch("apps.revenue_runtime.evaluator.wix_adapter.search_recent_paid_orders", return_value=orders):
                second = reconcile_paid_orders(store, self.policy)
            self.assertEqual(second[0]["status"], "attributed")
            self.assertEqual(second[0]["reason"], "WIX_PURCHASE_FLOW_LINK")

    def test_wix_reader_preserves_native_ids_and_strips_buyer_pii(self):
        flow_id = str(uuid.uuid4())
        checkout_id = str(uuid.uuid4())
        payload = {"orders": [{
            "id": "o1",
            "createdDate": "2026-09-17T12:00:00Z",
            "paymentStatus": "PAID",
            "purchaseFlowId": flow_id,
            "checkoutId": checkout_id,
            "buyerInfo": {"email": "private@example.com"},
            "lineItems": [{
                "quantity": 1,
                "catalogReference": {"appId": wix_adapter.STORES_APP_ID, "catalogItemId": "p1"},
                "totalPriceAfterTax": {"amount": "29.99"},
            }],
        }]}
        with patch("apps.revenue_runtime.wix_adapter._request", return_value=FakeResponse(payload)):
            order = wix_adapter.search_recent_paid_orders()[0]
        self.assertEqual(order["purchase_flow_id"], flow_id)
        self.assertEqual(order["checkout_id"], checkout_id)
        encoded = json.dumps(order)
        self.assertNotIn("buyerInfo", encoded)
        self.assertNotIn("private@example.com", encoded)

    def test_service_keeps_bridge_on_existing_public_r_surface(self):
        source = SERVICE.read_text(encoding="utf-8")
        self.assertIn('"dr_token": bridge_token', source)
        self.assertIn('@app.post("/r/{experiment_id}/bridge")', source)
        self.assertIn("expected_experiment_id=experiment_id", source)
        self.assertIn("order_id=payload.order_id", source)
        self.assertIn("_variant_guard(payload.control)", source)
        self.assertIn("_variant_guard(payload.treatment)", source)

    def test_wix_bridge_retries_on_native_cart_change_without_mutating_commerce(self):
        source = WIX_BRIDGE.read_text(encoding="utf-8")
        self.assertIn('import { ecom } from "@wix/site-ecom"', source)
        self.assertIn("ecom.onCartChange", source)
        self.assertIn("currentCartV2.getCurrentCart", source)
        self.assertIn("purchaseFlowId", source)
        self.assertNotIn("updateCurrentCart", source)
        self.assertNotIn("addLineItemsToCurrentCart", source)
        self.assertNotIn("placeOrder", source)


if __name__ == "__main__":
    unittest.main()
