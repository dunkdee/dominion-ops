"""Focused tests for buddy_core/core/attribution.py.

Covers build_tracked_url (14 cases) and _cta_with_utm (5 cases).
"""
from __future__ import annotations

import unittest
from urllib.parse import parse_qs, urlparse

try:
    from core.attribution import _cta_with_utm, build_tracked_url
except ImportError:
    from buddy_core.core.attribution import _cta_with_utm, build_tracked_url


def _params(url: str) -> dict:
    """Return query params as {key: [values]} for assertion convenience."""
    return parse_qs(urlparse(url).query, keep_blank_values=True)


class TestBuildTrackedUrl(unittest.TestCase):

    # ── 1. https:// root domain ──────────────────────────────────────────────
    def test_https_root_domain(self):
        result = build_tracked_url(
            "https://dominionhealing.org",
            utm_source="social", utm_medium="organic", utm_campaign="c1",
        )
        parsed = urlparse(result)
        self.assertEqual(parsed.scheme, "https")
        self.assertEqual(parsed.hostname, "dominionhealing.org")
        p = _params(result)
        self.assertEqual(p["utm_source"], ["social"])
        self.assertEqual(p["utm_medium"], ["organic"])
        self.assertEqual(p["utm_campaign"], ["c1"])
        self.assertNotIn("utm_content", p)

    # ── 2. Schemeless root domain ────────────────────────────────────────────
    def test_schemeless_root_domain(self):
        result = build_tracked_url(
            "dominionhealing.org",
            utm_source="social", utm_medium="organic", utm_campaign="c1",
        )
        parsed = urlparse(result)
        self.assertEqual(parsed.scheme, "https")
        self.assertEqual(parsed.hostname, "dominionhealing.org")
        p = _params(result)
        self.assertEqual(p["utm_source"], ["social"])

    # ── 3. https:// /store path ──────────────────────────────────────────────
    def test_https_store_path(self):
        result = build_tracked_url(
            "https://dominionhealing.org/store",
            utm_source="social", utm_medium="organic", utm_campaign="c1",
        )
        parsed = urlparse(result)
        self.assertEqual(parsed.path, "/store")
        p = _params(result)
        self.assertEqual(p["utm_campaign"], ["c1"])

    # ── 4. Schemeless /store path ────────────────────────────────────────────
    def test_schemeless_store_path(self):
        result = build_tracked_url(
            "dominionhealing.org/store",
            utm_source="social", utm_medium="organic", utm_campaign="c1",
        )
        parsed = urlparse(result)
        self.assertEqual(parsed.scheme, "https")
        self.assertEqual(parsed.path, "/store")
        p = _params(result)
        self.assertEqual(p["utm_campaign"], ["c1"])

    # ── 5. Existing query params preserved ───────────────────────────────────
    def test_existing_query_params_preserved(self):
        result = build_tracked_url(
            "https://dominionhealing.org?ref=bio&offer=spring",
            utm_source="social", utm_medium="organic", utm_campaign="c1",
        )
        p = _params(result)
        self.assertEqual(p["ref"], ["bio"])
        self.assertEqual(p["offer"], ["spring"])
        self.assertEqual(p["utm_source"], ["social"])

    # ── 6. Fragment preserved ────────────────────────────────────────────────
    def test_fragment_preserved(self):
        result = build_tracked_url(
            "https://dominionhealing.org/page#section",
            utm_source="social", utm_medium="organic", utm_campaign="c1",
        )
        parsed = urlparse(result)
        self.assertEqual(parsed.fragment, "section")
        p = _params(result)
        self.assertIn("utm_source", p)

    # ── 7. Existing UTM params overwritten by caller ─────────────────────────
    def test_existing_utm_overwritten(self):
        result = build_tracked_url(
            "https://dominionhealing.org?utm_source=old&foo=bar",
            utm_source="social", utm_medium="organic", utm_campaign="c1",
        )
        p = _params(result)
        self.assertEqual(p["utm_source"], ["social"])   # caller wins
        self.assertEqual(p["foo"], ["bar"])              # unrelated param preserved
        self.assertEqual(len(p["utm_source"]), 1)       # not duplicated

    # ── 8. www subdomain ─────────────────────────────────────────────────────
    def test_www_subdomain(self):
        result = build_tracked_url(
            "https://www.dominionhealing.org",
            utm_source="social", utm_medium="organic", utm_campaign="c1",
        )
        parsed = urlparse(result)
        self.assertEqual(parsed.hostname, "www.dominionhealing.org")
        self.assertIn("utm_source=social", result)

    # ── 9. shop subdomain ────────────────────────────────────────────────────
    def test_shop_subdomain(self):
        result = build_tracked_url(
            "https://shop.dominionhealing.org",
            utm_source="social", utm_medium="organic", utm_campaign="c1",
        )
        parsed = urlparse(result)
        self.assertEqual(parsed.hostname, "shop.dominionhealing.org")
        self.assertIn("utm_source=social", result)

    # ── 10. External URL unchanged ───────────────────────────────────────────
    def test_external_url_unchanged(self):
        url = "https://amazon.com/dp/B0GY6LM72W"
        self.assertEqual(
            build_tracked_url(url, "social", "organic", "c1"), url
        )

    # ── 11. Non-URL CTA string unchanged ────────────────────────────────────
    def test_non_url_cta_unchanged(self):
        cta = "Save this. Share with someone who needs it."
        self.assertEqual(
            build_tracked_url(cta, "social", "organic", "c1"), cta
        )

    # ── 12. Empty input unchanged ────────────────────────────────────────────
    def test_empty_input(self):
        self.assertEqual(build_tracked_url("", "social", "organic", "c1"), "")

    # ── 13. Duplicate query values preserved ─────────────────────────────────
    def test_duplicate_query_values_preserved(self):
        result = build_tracked_url(
            "https://dominionhealing.org?tag=a&tag=b",
            utm_source="social", utm_medium="organic", utm_campaign="c1",
        )
        p = _params(result)
        self.assertEqual(sorted(p["tag"]), ["a", "b"])
        self.assertEqual(p["utm_source"], ["social"])

    # ── 14. Deterministic campaign value ─────────────────────────────────────
    def test_deterministic_campaign(self):
        url = "https://dominionhealing.org"
        r1 = build_tracked_url(url, "social", "organic", "daily_short_20260903_1")
        r2 = build_tracked_url(url, "social", "organic", "daily_short_20260903_1")
        self.assertEqual(r1, r2)
        self.assertIn("utm_campaign=daily_short_20260903_1", r1)


class TestCtaWithUtm(unittest.TestCase):

    CAMPAIGN = "daily_short_20260903_1"

    def test_cta_with_schemeless_domain(self):
        cta = "Link in bio → dominionhealing.org"
        result = _cta_with_utm(cta, self.CAMPAIGN)
        self.assertIn("utm_source=social", result)
        self.assertIn("utm_medium=organic", result)
        self.assertIn(f"utm_campaign={self.CAMPAIGN}", result)
        self.assertIn("Link in bio →", result)

    def test_cta_with_store_path(self):
        cta = "Learn more at dominionhealing.org/store"
        result = _cta_with_utm(cta, self.CAMPAIGN)
        self.assertIn("/store", result)
        self.assertIn("utm_source=social", result)

    def test_cta_without_url_unchanged(self):
        cta = "Save this. Share with someone who needs it."
        self.assertEqual(_cta_with_utm(cta, self.CAMPAIGN), cta)

    def test_cta_with_external_url_unchanged(self):
        cta = "View on Amazon https://amazon.com/dp/B0GY6LM72W"
        result = _cta_with_utm(cta, self.CAMPAIGN)
        self.assertIn("https://amazon.com/dp/B0GY6LM72W", result)
        self.assertNotIn("utm_source", result)

    def test_cta_with_https_domain_url(self):
        cta = "Visit https://dominionhealing.org for more"
        result = _cta_with_utm(cta, self.CAMPAIGN)
        self.assertIn("utm_source=social", result)
        self.assertIn("for more", result)


if __name__ == "__main__":
    unittest.main()
