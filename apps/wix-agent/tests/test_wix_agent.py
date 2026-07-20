import os
import sys
import tempfile
import importlib.util
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


class WixClientTests(unittest.TestCase):
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


@unittest.skipUnless(importlib.util.find_spec("fastapi"), "FastAPI is not installed")
class ApiSafetyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from fastapi.testclient import TestClient
        from main import app

        cls.client_class = TestClient
        cls.app = app

    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.db_path = Path(self.tempdir.name) / "wix_agent.db"
        self.env_patch = patch.dict(os.environ, {"WIX_AGENT_DB": str(self.db_path)})
        self.env_patch.start()
        self.addCleanup(self.env_patch.stop)

    def test_readiness_checks_database_and_required_integrations(self):
        with self.client_class(self.app) as client:
            response = client.get("/ready")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ready"])
        self.assertTrue(self.db_path.is_file())

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


if __name__ == "__main__":
    unittest.main()
