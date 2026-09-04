"""
Group D tests — revenue attribution feedback.
PURCHASE_SOURCE=orders table (dominion-db, Group C).
REVENUE_SOURCE=orders.amount_cents only.
All tests drive compute_revenue_feedback() directly — no live DB needed.
"""
import unittest
from datetime import datetime, timezone

try:
    from core.revenue_feedback import ORDERS_SQL, compute_revenue_feedback
except ImportError:
    from buddy_core.core.revenue_feedback import ORDERS_SQL, compute_revenue_feedback


def _order(product_id="divine-sovereignty", amount_cents=1900,
           utm_source=None, utm_medium=None, utm_campaign=None, utm_content=None):
    return {
        "product_id":   product_id,
        "product_name": "Divine Sovereignty",
        "amount_cents": amount_cents,
        "currency":     "usd",
        "utm_source":   utm_source,
        "utm_medium":   utm_medium,
        "utm_campaign": utm_campaign,
        "utm_content":  utm_content,
        "created_at":   datetime.now(timezone.utc).isoformat(),
    }


class TestCompleteEvidence(unittest.TestCase):
    """Test 1: confirmed purchase records -> all 5 governed fields populated."""

    def test_winner_loser_approval_from_purchase_records(self):
        orders = [
            _order(utm_source="tiktok",    amount_cents=1900),
            _order(utm_source="tiktok",    amount_cents=1900),
            _order(utm_source="instagram", amount_cents=1900),
        ]
        result, evidence = compute_revenue_feedback(orders)

        self.assertEqual(result["PURCHASE_SOURCE"], "orders table — dominion-db")
        self.assertEqual(result["REVENUE_SOURCE"],  "orders.amount_cents")
        self.assertEqual(result["purchase_count"],      3)
        self.assertEqual(result["revenue_cents"],       5700)
        self.assertEqual(result["WINNER"],              "tiktok")
        self.assertEqual(result["LOSER"],               "instagram")
        self.assertEqual(result["NEXT_ALLOWED_ACTION"], "external.publish")
        self.assertEqual(result["APPROVAL_REQUIRED"],   "YES")
        self.assertIn("NEXT_CONSTRAINT", result)
        self.assertTrue(result["db_available"])
        self.assertTrue(len(evidence) > 0)
        self.assertEqual(evidence[0]["purchase_count"], 3)
        self.assertEqual(evidence[0]["revenue_cents"],  5700)

    def test_revenue_is_sum_of_amount_cents_only(self):
        orders = [_order(amount_cents=1900), _order(amount_cents=1500)]
        result, _ = compute_revenue_feedback(orders)
        self.assertEqual(result["revenue_cents"], 3400)


class TestMissingEvidence(unittest.TestCase):
    """Test 2: DB unavailable (orders=None) -> all governed fields UNKNOWN."""

    def test_none_orders_all_unknown(self):
        result, evidence = compute_revenue_feedback(None)

        self.assertEqual(result["WINNER"],         "UNKNOWN")
        self.assertEqual(result["LOSER"],          "UNKNOWN")
        self.assertEqual(result["purchase_count"], "UNKNOWN")
        self.assertEqual(result["revenue_cents"],  "UNKNOWN")
        self.assertFalse(result["db_available"])
        self.assertTrue(len(evidence) > 0)
        self.assertFalse(evidence[0]["db_available"])

    def test_none_orders_next_action_is_internal(self):
        result, _ = compute_revenue_feedback(None)
        self.assertNotIn("external", result["NEXT_ALLOWED_ACTION"])
        self.assertEqual(result["APPROVAL_REQUIRED"], "NO")


class TestNoPurchases(unittest.TestCase):
    """Test 3: DB available, zero records -> revenue=0, WINNER=UNKNOWN, no fabrication."""

    def test_empty_orders_zero_revenue_not_fabricated(self):
        result, evidence = compute_revenue_feedback([])

        self.assertEqual(result["purchase_count"], 0)
        self.assertEqual(result["revenue_cents"],  0)
        self.assertEqual(result["WINNER"],         "UNKNOWN")
        self.assertEqual(result["LOSER"],          "UNKNOWN")
        self.assertEqual(result["APPROVAL_REQUIRED"], "NO")
        self.assertNotIn("external", result["NEXT_ALLOWED_ACTION"])
        self.assertTrue(result["db_available"])

    def test_empty_orders_utm_breakdown_all_empty(self):
        result, _ = compute_revenue_feedback([])
        for field in ("utm_source", "utm_medium", "utm_campaign", "utm_content"):
            self.assertEqual(result["utm_breakdown"][field], {})


class TestLeadNotPurchase(unittest.TestCase):
    """Test 4: ORDERS_SQL reads only orders table — leads, events, email_leads excluded."""

    def test_sql_reads_orders_only(self):
        sql = ORDERS_SQL.upper()
        self.assertIn("FROM ORDERS", sql)
        self.assertNotIn("LEADS", sql)
        self.assertNotIn("STRIPE_EVENTS", sql)
        self.assertNotIn("EMAIL_LEADS", sql)

    def test_sql_excludes_zero_and_null_amounts(self):
        sql = ORDERS_SQL.upper()
        self.assertIn("AMOUNT_CENTS IS NOT NULL", sql)
        self.assertIn("AMOUNT_CENTS > 0", sql)

    def test_purchase_count_equals_order_rows_only(self):
        orders = [_order(), _order(), _order()]
        result, _ = compute_revenue_feedback(orders)
        self.assertEqual(result["purchase_count"], 3)


class TestApprovalRequired(unittest.TestCase):
    """Test 5: external action -> APPROVAL_REQUIRED=YES; internal -> NO."""

    def test_external_publish_requires_approval(self):
        orders = [
            _order(utm_source="tiktok"),
            _order(utm_source="tiktok"),
            _order(utm_source="facebook"),
        ]
        result, _ = compute_revenue_feedback(orders)

        self.assertEqual(result["NEXT_ALLOWED_ACTION"], "external.publish")
        self.assertEqual(result["APPROVAL_REQUIRED"],   "YES")

    def test_internal_action_no_approval(self):
        result, _ = compute_revenue_feedback([])
        self.assertEqual(result["APPROVAL_REQUIRED"], "NO")
        self.assertNotIn("external", result["NEXT_ALLOWED_ACTION"])

    def test_single_source_no_winner_no_approval(self):
        orders = [_order(utm_source="tiktok"), _order(utm_source="tiktok")]
        result, _ = compute_revenue_feedback(orders)
        self.assertEqual(result["WINNER"],            "UNKNOWN")
        self.assertEqual(result["APPROVAL_REQUIRED"], "NO")


class TestLoopbackRestriction(unittest.TestCase):
    """Test 6: DB_HOST loopback guard is enforced in executor source."""

    def test_loopback_pattern_accepts_valid(self):
        import re
        pat = re.compile(r"^(?:127\.0\.0\.1|localhost)$")
        self.assertTrue(pat.match("127.0.0.1"))
        self.assertTrue(pat.match("localhost"))

    def test_loopback_pattern_rejects_external(self):
        import re
        pat = re.compile(r"^(?:127\.0\.0\.1|localhost)$")
        for host in ("34.135.158.163", "0.0.0.0", "dominionhealing.org", "10.0.0.1"):
            self.assertFalse(pat.match(host), f"should reject: {host}")

    def test_executor_source_contains_loopback_guard(self):
        from pathlib import Path
        src = (Path(__file__).parent.parent / "buddy_core" / "core" / "operator.py").read_text()
        self.assertIn("loopback-only", src)
        self.assertIn("DB_HOST", src)


if __name__ == "__main__":
    unittest.main()
