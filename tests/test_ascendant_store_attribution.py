"""
Group C focused tests — ascendant_store revenue attribution
Phase 5-6: UTM → Stripe Session metadata → orders INSERT
"""
import asyncio, importlib.util, json, os, re, sys, unittest
from pathlib import Path
from unittest.mock import MagicMock

APP_PATH = Path(__file__).parent.parent / "ascendant_store" / "app.py"
APP_SRC  = APP_PATH.read_text()


# ── Source-inspection tests ──────────────────────────────────────

class TestStripeEventsColumns(unittest.TestCase):
    """stripe_events INSERT must use live column names."""

    def _cols(self):
        m = re.search(r"INSERT INTO stripe_events \(([^)]+)\)", APP_SRC)
        self.assertIsNotNone(m, "No INSERT INTO stripe_events found")
        return [c.strip() for c in m.group(1).split(",")]

    def test_stripe_event_id_column(self):
        self.assertIn("stripe_event_id", self._cols())

    def test_payload_json_column(self):
        self.assertIn("payload_json", self._cols())

    def test_no_bare_event_id(self):
        self.assertNotIn("event_id", self._cols())

    def test_no_bare_payload(self):
        self.assertNotIn("payload", self._cols())


class TestOrdersColumns(unittest.TestCase):
    """orders INSERT must include all post-migration columns including UTM."""

    def _cols(self):
        m = re.search(r"INSERT INTO orders \(([^)]+)\)", APP_SRC)
        self.assertIsNotNone(m, "No INSERT INTO orders found")
        return [c.strip() for c in m.group(1).split(",")]

    def test_stripe_session_id(self):   self.assertIn("stripe_session_id", self._cols())
    def test_customer_email(self):      self.assertIn("customer_email",     self._cols())
    def test_product_id(self):          self.assertIn("product_id",         self._cols())
    def test_product_name(self):        self.assertIn("product_name",       self._cols())
    def test_amount_cents(self):        self.assertIn("amount_cents",       self._cols())
    def test_utm_source(self):          self.assertIn("utm_source",         self._cols())
    def test_utm_medium(self):          self.assertIn("utm_medium",         self._cols())
    def test_utm_campaign(self):        self.assertIn("utm_campaign",       self._cols())
    def test_utm_content(self):         self.assertIn("utm_content",        self._cols())


class TestPaymentLinkRemoved(unittest.TestCase):
    def test_checkout_mode_payment_link_gone(self):
        self.assertNotIn('"checkout_mode": "payment_link"', APP_SRC)


class TestDeadLetterRouting(unittest.TestCase):
    def test_print_only_handler_gone(self):
        self.assertNotIn("[WEBHOOK] Order store error", APP_SRC)

    def test_dead_letter_present_in_webhook(self):
        self.assertIn("_dead_letter", APP_SRC)


class TestEnsureTablesRemoved(unittest.TestCase):
    def test_ensure_tables_gone(self):
        self.assertNotIn("_ensure_tables", APP_SRC)


# ── Integration test: checkout UTM → Session metadata ────────────

def _load_app(stripe_mock, psycopg2_mock):
    """Load ascendant_store/app.py with mocked stripe + psycopg2."""
    filelock_mock = MagicMock()
    filelock_mock.FileLock = MagicMock(return_value=MagicMock(
        __enter__=lambda s, *a: s,
        __exit__=lambda s, *a: False,
    ))
    filelock_mock.Timeout = Exception

    # Remove any stale module cache
    for key in list(sys.modules):
        if "ascendant_store" in key or key.startswith("_asc_app"):
            del sys.modules[key]

    saved = {}
    for mod_name, mock in [("stripe", stripe_mock), ("psycopg2", psycopg2_mock), ("filelock", filelock_mock)]:
        saved[mod_name] = sys.modules.get(mod_name)
        sys.modules[mod_name] = mock

    try:
        spec = importlib.util.spec_from_file_location("_asc_app_test", APP_PATH)
        mod  = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        mod.STRIPE_KEY = "sk_test_fake"   # bypass load-time os.getenv guard
    finally:
        for mod_name, original in saved.items():
            if original is None:
                sys.modules.pop(mod_name, None)
            else:
                sys.modules[mod_name] = original

    return mod


class TestCheckoutUTMMetadata(unittest.TestCase):
    """create_checkout must embed all four UTM fields in Stripe Session.create metadata."""

    def _run(self, coro):
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()

    def test_four_utm_fields_in_session_metadata(self):
        captured = {}

        def fake_create(**kwargs):
            captured.update(kwargs)
            m = MagicMock()
            m.url = "https://checkout.stripe.com/fake"
            return m

        stripe_mock = MagicMock()
        stripe_mock.checkout.Session.create = fake_create
        stripe_mock.error.SignatureVerificationError = Exception

        mod = _load_app(stripe_mock, MagicMock())

        from httpx import AsyncClient, ASGITransport

        async def _body():
            async with AsyncClient(
                transport=ASGITransport(app=mod.app),
                base_url="http://test",
            ) as client:
                return await client.post("/api/checkout", json={
                    "product_id":   "divine-sovereignty",
                    "utm_source":   "tiktok",
                    "utm_medium":   "social",
                    "utm_campaign": "sovereignty-launch",
                    "utm_content":  "v2",
                })

        resp = self._run(_body())
        self.assertEqual(resp.status_code, 200, resp.text)

        meta = captured.get("metadata", {})
        self.assertEqual(meta.get("utm_source"),   "tiktok",              "utm_source missing from Session metadata")
        self.assertEqual(meta.get("utm_medium"),   "social",              "utm_medium missing from Session metadata")
        self.assertEqual(meta.get("utm_campaign"), "sovereignty-launch",  "utm_campaign missing from Session metadata")
        self.assertEqual(meta.get("utm_content"),  "v2",                  "utm_content missing from Session metadata")

    def test_product_id_in_session_metadata(self):
        captured = {}

        def fake_create(**kwargs):
            captured.update(kwargs)
            m = MagicMock()
            m.url = "https://checkout.stripe.com/fake"
            return m

        stripe_mock = MagicMock()
        stripe_mock.checkout.Session.create = fake_create
        stripe_mock.error.SignatureVerificationError = Exception

        mod = _load_app(stripe_mock, MagicMock())

        from httpx import AsyncClient, ASGITransport

        async def _body():
            async with AsyncClient(
                transport=ASGITransport(app=mod.app),
                base_url="http://test",
            ) as client:
                return await client.post("/api/checkout", json={
                    "product_id": "divine-sovereignty",
                })

        self._run(_body())
        self.assertEqual(captured.get("metadata", {}).get("product_id"), "divine-sovereignty")

    def test_missing_utm_fields_omitted_from_metadata(self):
        """Empty UTM values must not appear in metadata (no blank keys)."""
        captured = {}

        def fake_create(**kwargs):
            captured.update(kwargs)
            m = MagicMock()
            m.url = "https://checkout.stripe.com/fake"
            return m

        stripe_mock = MagicMock()
        stripe_mock.checkout.Session.create = fake_create
        stripe_mock.error.SignatureVerificationError = Exception

        mod = _load_app(stripe_mock, MagicMock())

        from httpx import AsyncClient, ASGITransport

        async def _body():
            async with AsyncClient(
                transport=ASGITransport(app=mod.app),
                base_url="http://test",
            ) as client:
                return await client.post("/api/checkout", json={
                    "product_id": "divine-sovereignty",
                    "utm_source": "",
                })

        self._run(_body())
        meta = captured.get("metadata", {})
        self.assertNotIn("utm_source", meta)
        self.assertNotIn("utm_medium", meta)


if __name__ == "__main__":
    unittest.main()
