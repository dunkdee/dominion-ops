import os
import sys
import tempfile
import importlib.util
import json
import sqlite3
import types
import unittest
from pathlib import Path
from unittest.mock import patch


AGENT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AGENT_DIR))

TEST_ROOT = tempfile.mkdtemp(prefix="wix-agent-tests-")
os.environ["WIX_AGENT_DB"] = str(Path(TEST_ROOT) / "state" / "wix_agent.db")
os.environ["WIX_API_KEY"] = "test-wix-key"
os.environ["WIX_SITE_ID"] = "test-site-id"
os.environ["ZENDROP_API_KEY"] = "test-zendrop-key"
os.environ["WIX_AGENT_OPERATOR_TOKEN"] = "test-operator-token"

if importlib.util.find_spec("httpx") is None:
    httpx_stub = types.ModuleType("httpx")
    httpx_stub.get = lambda *args, **kwargs: None
    httpx_stub.post = lambda *args, **kwargs: None
    httpx_stub.patch = lambda *args, **kwargs: None
    sys.modules["httpx"] = httpx_stub

if importlib.util.find_spec("empire") is None:
    empire_stub = types.ModuleType("empire")
    empire_stub.N8N_WEBHOOK_URL = ""
    empire_stub.notify_empire = lambda *args, **kwargs: None
    sys.modules["empire"] = empire_stub

if importlib.util.find_spec("zendrop_client") is None:
    zendrop_stub = types.ModuleType("zendrop_client")
    zendrop_stub.ZENDROP_API_KEY = "test-zendrop-key"
    zendrop_stub.submit_order = lambda payload: {"order": {"id": "test-order"}}
    zendrop_stub.get_order_status = lambda order_id: {"status": "pending"}
    sys.modules["zendrop_client"] = zendrop_stub

import fulfillment
import wix_client


def wix_order(order_id="wix-123", *, status="APPROVED", payment_status="PAID"):
    return {
        "id": order_id,
        "number": "1001",
        "status": status,
        "paymentStatus": payment_status,
        "buyerInfo": {"email": "buyer@example.test"},
        "shippingInfo": {
            "logistics": {
                "shippingDestination": {
                    "address": {
                        "firstName": "Test",
                        "lastName": "Buyer",
                        "addressLine": "1 Test Way",
                        "city": "Testville",
                        "postalCode": "12345",
                        "country": "US",
                    }
                }
            }
        },
        "lineItems": [
            {
                "quantity": 2,
                "catalogReference": {
                    "catalogItemId": "wix-product",
                    "options": {"variantId": "wix-variant"},
                },
                "physicalProperties": {"sku": "WIX-SKU"},
                "productName": {"original": "Test Product"},
            }
        ],
    }


VARIANT_MAPPING = json.dumps(
    {
        "wix-product:wix-variant": {
            "product_id": "zendrop-product",
            "variant_id": "zendrop-variant",
            "wix_sku": "WIX-SKU",
        }
    }
)


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class FulfillmentDatabaseTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)

    def test_initializes_nested_sqlite_file(self):
        path = Path(self.tempdir.name) / "nested" / "wix_agent.db"
        with patch.dict(os.environ, {"WIX_AGENT_DB": str(path)}):
            fulfillment.init_db()
            self.assertTrue(path.is_file())
            self.assertEqual(fulfillment.database_health(), {"status": "ok"})
            self.assertEqual(fulfillment.get_fulfillment_summary(), {})

    def test_rejects_directory_as_database_path(self):
        with patch.dict(os.environ, {"WIX_AGENT_DB": self.tempdir.name}):
            health = fulfillment.database_health()
            self.assertEqual(health["status"], "error")
            self.assertIn("points to a directory", health["error"])

    def test_migrates_existing_database_for_submission_safety(self):
        path = Path(self.tempdir.name) / "legacy.db"
        with sqlite3.connect(path) as conn:
            conn.execute(
                "CREATE TABLE fulfillments ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "wix_order_id TEXT NOT NULL UNIQUE, zendrop_order_id TEXT, "
                "status TEXT NOT NULL DEFAULT 'pending_submit', "
                "tracking_number TEXT, carrier TEXT, "
                "created_at TEXT NOT NULL, updated_at TEXT NOT NULL)"
            )

        with patch.dict(os.environ, {"WIX_AGENT_DB": str(path)}):
            fulfillment.init_db()

        with sqlite3.connect(path) as conn:
            columns = {row[1] for row in conn.execute("PRAGMA table_info(fulfillments)")}
        self.assertIn("last_error", columns)
        self.assertIn("attempt_count", columns)

    def test_order_is_submitted_only_once(self):
        path = Path(self.tempdir.name) / "dedupe.db"
        order = wix_order()
        submissions = []

        def submit(payload):
            submissions.append(payload)
            return {"order": {"id": "zendrop-456"}}

        with (
            patch.dict(
                os.environ,
                {
                    "WIX_AGENT_DB": str(path),
                    "WIX_FULFILLMENT_MODE": "live",
                    "ZENDROP_VARIANT_MAP_JSON": VARIANT_MAPPING,
                },
            ),
            patch.object(fulfillment.wix, "get_orders", return_value=[order]),
            patch.object(fulfillment.zendrop, "submit_order", side_effect=submit),
            patch.object(fulfillment.empire, "notify_empire"),
        ):
            first = fulfillment.run_fulfillment_cycle()
            second = fulfillment.run_fulfillment_cycle()
            summary = fulfillment.get_fulfillment_summary()

        self.assertEqual(len(submissions), 1)
        self.assertEqual(first["submitted"][0]["zendrop_order_id"], "zendrop-456")
        self.assertEqual(second["already_tracked"], ["wix-123"])
        self.assertEqual(summary, {"submitted": 1})

    def test_failed_submission_stops_for_manual_reconciliation(self):
        path = Path(self.tempdir.name) / "failed.db"
        order = wix_order("wix-789")

        with (
            patch.dict(
                os.environ,
                {
                    "WIX_AGENT_DB": str(path),
                    "WIX_FULFILLMENT_MODE": "live",
                    "ZENDROP_VARIANT_MAP_JSON": VARIANT_MAPPING,
                },
            ),
            patch.object(fulfillment.wix, "get_orders", return_value=[order]),
            patch.object(
                fulfillment.zendrop,
                "submit_order",
                side_effect=RuntimeError("supplier unavailable"),
            ) as submit,
        ):
            first = fulfillment.run_fulfillment_cycle()
            second = fulfillment.run_fulfillment_cycle()
            summary = fulfillment.get_fulfillment_summary()

        self.assertEqual(submit.call_count, 1)
        self.assertEqual(first["errors"][0]["wix_order_id"], "wix-789")
        self.assertEqual(second["already_tracked"], ["wix-789"])
        self.assertEqual(summary, {"submit_failed": 1})

    def test_unpaid_order_is_never_submitted(self):
        path = Path(self.tempdir.name) / "unpaid.db"
        order = wix_order(payment_status="NOT_PAID")
        with (
            patch.dict(
                os.environ,
                {
                    "WIX_AGENT_DB": str(path),
                    "WIX_FULFILLMENT_MODE": "live",
                    "ZENDROP_VARIANT_MAP_JSON": VARIANT_MAPPING,
                },
            ),
            patch.object(fulfillment.wix, "get_orders", return_value=[order]),
            patch.object(fulfillment.zendrop, "submit_order") as submit,
        ):
            result = fulfillment.run_fulfillment_cycle()

        submit.assert_not_called()
        self.assertEqual(result["ineligible"], ["wix-123"])
        self.assertEqual(fulfillment.get_fulfillment_summary(), {})

    def test_exact_supplier_mapping_is_required_and_used(self):
        path = Path(self.tempdir.name) / "mapping.db"
        order = wix_order()
        submissions = []

        with (
            patch.dict(
                os.environ,
                {
                    "WIX_AGENT_DB": str(path),
                    "WIX_FULFILLMENT_MODE": "live",
                    "ZENDROP_VARIANT_MAP_JSON": VARIANT_MAPPING,
                },
            ),
            patch.object(fulfillment.wix, "get_orders", return_value=[order]),
            patch.object(
                fulfillment.zendrop,
                "submit_order",
                side_effect=lambda payload: submissions.append(payload)
                or {"order": {"id": "zendrop-order"}},
            ),
            patch.object(fulfillment.empire, "notify_empire"),
        ):
            fulfillment.run_fulfillment_cycle()

        item = submissions[0]["order"]["line_items"][0]
        self.assertEqual(item["product_id"], "zendrop-product")
        self.assertEqual(item["variant_id"], "zendrop-variant")
        self.assertEqual(item["quantity"], 2)

        with (
            patch.dict(
                os.environ,
                {
                    "WIX_AGENT_DB": str(Path(self.tempdir.name) / "missing.db"),
                    "WIX_FULFILLMENT_MODE": "live",
                    "ZENDROP_VARIANT_MAP_JSON": "{}",
                },
            ),
            patch.object(fulfillment.wix, "get_orders", return_value=[order]),
            patch.object(fulfillment.zendrop, "submit_order") as submit,
        ):
            result = fulfillment.run_fulfillment_cycle()
        submit.assert_not_called()
        self.assertIn("exact Zendrop mapping", result["errors"][0]["error"])

    def test_record_only_mode_holds_paid_orders(self):
        path = Path(self.tempdir.name) / "record-only.db"
        with (
            patch.dict(
                os.environ,
                {
                    "WIX_AGENT_DB": str(path),
                    "WIX_FULFILLMENT_MODE": "record_only",
                },
            ),
            patch.object(
                fulfillment.wix, "get_orders", return_value=[wix_order()]
            ),
            patch.object(fulfillment.zendrop, "submit_order") as submit,
        ):
            result = fulfillment.run_fulfillment_cycle()
        submit.assert_not_called()
        self.assertEqual(result["held_for_manual_fulfillment"], ["wix-123"])


class WixClientTests(unittest.TestCase):
    def test_catalog_detection_uses_catalog_version_and_fails_closed(self):
        with patch.object(
            wix_client.httpx,
            "get",
            return_value=FakeResponse({"catalogVersion": "V3_CATALOG"}),
        ):
            self.assertEqual(wix_client.detect_catalog_version(), "v3")

        with patch.object(
            wix_client.httpx,
            "get",
            return_value=FakeResponse({}, status_code=401),
        ):
            with self.assertRaises(RuntimeError):
                wix_client.detect_catalog_version()

    def test_v3_products_use_top_level_fields_and_cursor_paging(self):
        calls = []

        def fake_post(url, **kwargs):
            calls.append((url, kwargs["json"]))
            if len(calls) == 1:
                return FakeResponse(
                    {
                        "products": [{"id": "first"}],
                        "pagingMetadata": {
                            "hasNext": True,
                            "cursors": {"next": "next-cursor"},
                        },
                    }
                )
            return FakeResponse(
                {
                    "products": [{"id": "second"}],
                    "pagingMetadata": {"hasNext": False},
                }
            )

        with patch.object(wix_client.httpx, "post", side_effect=fake_post):
            products = wix_client.get_all_products("v3")

        self.assertEqual([item["id"] for item in products], ["first", "second"])
        self.assertEqual(
            calls[0][0], "https://www.wixapis.com/stores/v3/products/query"
        )
        self.assertEqual(
            calls[0][1]["fields"], ["PLAIN_DESCRIPTION", "MEDIA_ITEMS_INFO"]
        )
        self.assertNotIn("fields", calls[0][1]["query"])
        self.assertEqual(
            calls[1][1]["query"]["cursorPaging"]["cursor"], "next-cursor"
        )

    def test_v1_products_use_documented_reader_endpoint_and_offset_paging(self):
        first_page = [{"id": str(index)} for index in range(100)]
        second_page = [{"id": "100"}]
        calls = []

        def fake_post(url, **kwargs):
            calls.append((url, kwargs["json"]))
            if len(calls) == 1:
                return FakeResponse({"products": first_page, "totalResults": 101})
            return FakeResponse({"products": second_page, "totalResults": 101})

        with patch.object(wix_client.httpx, "post", side_effect=fake_post):
            products = wix_client.get_all_products("v1")

        self.assertEqual(len(products), 101)
        self.assertEqual(
            calls[0][0],
            "https://www.wixapis.com/stores-reader/v1/products/query",
        )
        self.assertEqual(calls[0][1]["query"]["paging"]["offset"], 0)
        self.assertEqual(calls[1][1]["query"]["paging"]["offset"], 100)

    def test_v1_inventory_uses_documented_reader_endpoint(self):
        calls = []

        def fake_post(url, **kwargs):
            calls.append((url, kwargs["json"]))
            return FakeResponse({"inventoryItems": [], "totalResults": 0})

        with patch.object(wix_client.httpx, "post", side_effect=fake_post):
            self.assertEqual(wix_client.get_all_inventory_items("v1"), [])

        self.assertEqual(
            calls[0][0],
            "https://www.wixapis.com/stores-reader/v2/inventoryItems/query",
        )

    def test_undocumented_page_mutation_is_disabled(self):
        with self.assertRaises(wix_client.UnsupportedWixOperation):
            wix_client.create_page("Returns", "returns")

    def test_revision_unsafe_v3_mutations_are_disabled(self):
        with self.assertRaises(wix_client.UnsupportedWixOperation):
            wix_client.update_inventory_item_v3("item", True)
        with self.assertRaises(wix_client.UnsupportedWixOperation):
            wix_client.set_product_visibility("product", True, "v3")
        with self.assertRaises(wix_client.UnsupportedWixOperation):
            wix_client.update_product_content(
                "product", "description", "title", "description", "v3"
            )


@unittest.skipUnless(importlib.util.find_spec("fastapi"), "FastAPI is not installed")
class ApiSafetyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from fastapi.testclient import TestClient
        import main

        cls.client_class = TestClient
        cls.main = main
        cls.app = main.app

    def setUp(self):
        self.main.CATALOG_VERSION = None
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.db_path = Path(self.tempdir.name) / "wix_agent.db"
        self.env_patch = patch.dict(os.environ, {"WIX_AGENT_DB": str(self.db_path)})
        self.env_patch.start()
        self.addCleanup(self.env_patch.stop)

    def test_readiness_checks_database_and_required_integrations(self):
        with (
            patch.object(
                self.main.wix, "detect_catalog_version", return_value="v3"
            ),
            self.client_class(self.app) as client,
        ):
            response = client.get("/ready")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ready"])
        self.assertEqual(response.json()["catalog"], {"status": "ok", "version": "v3"})
        self.assertTrue(self.db_path.is_file())

    def test_readiness_fails_when_wix_access_is_invalid(self):
        with (
            patch.object(
                self.main.wix,
                "detect_catalog_version",
                side_effect=RuntimeError("unauthorized"),
            ),
            self.client_class(self.app) as client,
        ):
            response = client.get("/ready")
        self.assertEqual(response.status_code, 503)
        self.assertIn("wix_catalog_access", response.json()["blockers"])
        self.assertNotIn("unauthorized", response.text)

    def test_sensitive_routes_require_operator_token(self):
        with self.client_class(self.app) as client:
            response = client.get("/orders")
        self.assertEqual(response.status_code, 401)

    def test_bulk_store_mutation_is_disabled(self):
        with self.client_class(self.app) as client:
            response = client.post(
                "/store/setup",
                headers={"X-Operator-Token": "test-operator-token"},
            )
        self.assertEqual(response.status_code, 409)

    def test_product_and_inventory_writes_are_dry_run_only(self):
        headers = {"X-Operator-Token": "test-operator-token"}
        with (
            patch.object(
                self.main.wix, "detect_catalog_version", return_value="v3"
            ),
            self.client_class(self.app) as client,
        ):
            inventory = client.post(
                "/sync/fix",
                headers=headers,
                json={"product_ids": ["product"], "dry_run": False},
            )
            products = client.post(
                "/store/setup/products?dry_run=false", headers=headers
            )
        self.assertEqual(inventory.status_code, 409)
        self.assertEqual(products.status_code, 409)


if __name__ == "__main__":
    unittest.main()
