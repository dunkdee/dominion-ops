"""The storefront must actually render before it can sell anything.

Before these tests existed the store had complete payment logic and no
storefront: `index.html` and `success.html` were never written, so `/` and
`/success` raised at render time. A customer could have paid and landed on a
500. These tests pin every route that a buyer walks through.

They also pin the Starlette signature. The app was written against the legacy
`TemplateResponse(name, context)` form, which current Starlette reads as
`(request, name)` -- it passes the context dict where the template name
belongs and every page fails. That is invisible until the package is upgraded,
so it is asserted here rather than left to a future deploy to discover.

No network, no Stripe key, no database: only page rendering is exercised.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
STORE = ROOT / "ascendant_store"
if str(STORE) not in sys.path:
    sys.path.insert(0, str(STORE))

pytest.importorskip("stripe")
pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402

import app as store  # noqa: E402


@pytest.fixture
def client():
    return TestClient(store.app)


# ── every route a buyer touches ─────────────────────────────────────────

@pytest.mark.parametrize("path", [
    "/",
    "/success",
    "/policies",
    "/product/divine-sovereignty",
    "/product/word-search-golden-years",
])
def test_buyer_facing_routes_render(client, path):
    assert client.get(path).status_code == 200, f"{path} did not render"


def test_unknown_product_redirects_rather_than_erroring(client):
    r = client.get("/product/no-such-product", follow_redirects=False)
    assert r.status_code in (302, 307)


# ── the catalogue is presented honestly ─────────────────────────────────

def test_every_product_appears_on_the_homepage(client):
    """Names are compared escaped -- Jinja autoescapes '&' and that is correct."""
    from html import escape

    body = client.get("/").text
    for product in store.PRODUCTS:
        assert escape(product["name"]) in body, f"{product['id']} missing from homepage"


def test_unpurchasable_products_cannot_be_bought_from_the_homepage(client):
    body = client.get("/").text
    unbuyable = [p for p in store.PRODUCTS if not p.get("purchasable")]
    assert unbuyable, "fixture assumption: at least one product is not purchasable"
    assert body.count("Coming soon") == len(unbuyable)


def test_purchasable_product_offers_a_buy_route(client):
    buyable = [p for p in store.PRODUCTS if p.get("purchasable")]
    assert buyable, "fixture assumption: at least one product is purchasable"
    body = client.get("/").text
    for product in buyable:
        assert f'/product/{product["id"]}' in body


def test_homepage_references_no_asset_that_does_not_exist(client):
    """Product images were referenced but never shipped; covers are CSS now."""
    body = client.get("/").text
    assert "/static/img" not in body


# ── trust surface ───────────────────────────────────────────────────────

def test_policies_cover_refund_privacy_and_terms(client):
    body = client.get("/policies").text.lower()
    for required in ("refund", "privacy", "terms", "delivery"):
        assert required in body, f"policies page does not cover {required}"


def test_homepage_links_to_policies(client):
    assert "/policies" in client.get("/").text


def test_affiliate_links_are_disclosed_and_rel_tagged(client):
    """Undisclosed affiliate links are an FTC problem, not a style problem."""
    body = client.get("/").text
    if not store.AFFILIATE_TOOLS:
        pytest.skip("no affiliate tools configured")
    assert "affiliate links" in body
    assert 'rel="sponsored noopener"' in body


def test_success_page_explains_delivery_and_support(client):
    """A buyer who paid must be told what arrives and what to do if it doesn't."""
    body = client.get("/success").text.lower()
    assert "delivery email" in body
    assert "spam" in body
    assert "support@" in body


# ── analytics is opt-in and fail-closed ─────────────────────────────────

def test_no_analytics_tag_when_unconfigured(client, monkeypatch):
    monkeypatch.setattr(store, "GA4_MEASUREMENT_ID", "")
    assert "gtag" not in client.get("/").text


def test_analytics_tag_emitted_when_configured(client, monkeypatch):
    monkeypatch.setattr(store, "GA4_MEASUREMENT_ID", "G-TESTID1234")
    body = client.get("/").text
    assert "G-TESTID1234" in body
    assert "googletagmanager.com/gtag/js" in body


def test_purchase_event_uses_the_catalogue_price_not_the_url(client, monkeypatch):
    """A tampered success URL must not be able to inflate reported revenue."""
    monkeypatch.setattr(store, "GA4_MEASUREMENT_ID", "G-TESTID1234")
    body = client.get("/success?product=divine-sovereignty").text
    assert "'purchase'" in body
    assert "19.0" in body, "value should come from the catalogue price in cents"


def test_unknown_product_on_success_fires_no_purchase_event(client, monkeypatch):
    monkeypatch.setattr(store, "GA4_MEASUREMENT_ID", "G-TESTID1234")
    body = client.get("/success?product=../../etc/passwd").text
    assert "'purchase'" not in body


# ── forward compatibility ───────────────────────────────────────────────

def test_template_calls_use_the_current_starlette_signature():
    """Legacy TemplateResponse(name, context) breaks silently on upgrade."""
    source = (STORE / "app.py").read_text(encoding="utf-8")
    assert "TemplateResponse(request," in source
    assert 'TemplateResponse("' not in source, (
        "legacy TemplateResponse(name, ...) form found; current Starlette "
        "reads the context dict as the template name"
    )
