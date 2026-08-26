from __future__ import annotations

import os
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any


BASE = "https://www.wixapis.com/stores/v3"
ORDERS_URL = "https://www.wixapis.com/ecom/v1/orders/search"
TIMEOUT = 30.0
STORES_APP_ID = "215238eb-22a5-4c36-9e7b-e7c08025e04e"


class WixActuatorError(RuntimeError):
    pass


def _headers() -> dict[str, str]:
    api_key = os.getenv("WIX_API_KEY", "")
    site_id = os.getenv("WIX_SITE_ID", "")
    if not api_key or not site_id:
        raise WixActuatorError("Wix credentials are not configured")
    return {
        "Authorization": api_key,
        "wix-site-id": site_id,
        "Content-Type": "application/json",
    }


def _request(method: str, url: str, **kwargs: Any):
    if not url.startswith("https://www.wixapis.com/"):
        raise WixActuatorError("non-Wix destination rejected")
    try:
        import httpx
    except ImportError as exc:  # keeps policy/ledger imports stdlib-only
        raise WixActuatorError("httpx runtime dependency unavailable") from exc
    response = httpx.request(method, url, headers=_headers(), timeout=TIMEOUT, **kwargs)
    response.raise_for_status()
    return response


def get_product(product_id: str) -> dict[str, Any]:
    """Read current V3 product and revision without relying on filter semantics."""
    cursor = None
    while True:
        cursor_paging: dict[str, Any] = {"limit": 100}
        if cursor:
            cursor_paging["cursor"] = cursor
        body = {
            "fields": ["PLAIN_DESCRIPTION", "URL"],
            "query": {"cursorPaging": cursor_paging},
        }
        data = _request("POST", f"{BASE}/products/query", json=body).json()
        for product in data.get("products", []):
            if product.get("id") == product_id:
                return product
        paging = data.get("pagingMetadata", {})
        cursor = paging.get("cursors", {}).get("next")
        if not paging.get("hasNext") or not cursor:
            break
    raise WixActuatorError(f"product not found: {product_id}")


def update_plain_description(product_id: str, value: str) -> dict[str, Any]:
    current = get_product(product_id)
    revision = str(current.get("revision") or "")
    if not revision:
        raise WixActuatorError("current product revision unavailable")
    before = str(current.get("plainDescription") or "")
    payload = {
        "product": {
            "id": product_id,
            "revision": revision,
            "plainDescription": value,
        },
        "fields": ["PLAIN_DESCRIPTION"],
    }
    _request("PATCH", f"{BASE}/products/{product_id}", json=payload)
    verified = get_product(product_id)
    after = str(verified.get("plainDescription") or "")
    if after != value:
        raise WixActuatorError("post-update verification mismatch")
    after_revision = str(verified.get("revision") or "")
    if not after_revision or after_revision == revision:
        raise WixActuatorError("Wix revision did not advance")
    return {
        "product_id": product_id,
        "field": "plainDescription",
        "before_value": before,
        "after_value": after,
        "before_revision": revision,
        "after_revision": after_revision,
    }


def rollback_plain_description(product_id: str, before_value: str) -> dict[str, Any]:
    """Rollback always re-reads current revision; stale revisions are never reused."""
    return update_plain_description(product_id, before_value)


def _money_to_cents(value: Any) -> int:
    if value is None:
        return 0
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return 0
    return int((amount * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def search_recent_paid_orders(limit: int = 100) -> list[dict[str, Any]]:
    """Return only non-PII fields required for deterministic revenue reconciliation."""
    if limit < 1 or limit > 100:
        raise WixActuatorError("order limit must be 1..100")
    body = {
        "search": {
            "sort": [{"fieldName": "createdDate", "order": "DESC"}],
            "cursorPaging": {"limit": limit},
        }
    }
    data = _request("POST", ORDERS_URL, json=body).json()
    orders: list[dict[str, Any]] = []
    for order in data.get("orders", []):
        if order.get("paymentStatus") != "PAID":
            continue
        items = []
        for item in order.get("lineItems", []):
            ref = item.get("catalogReference") or {}
            if ref.get("appId") != STORES_APP_ID:
                continue
            price = item.get("totalPriceAfterTax") or item.get("lineItemPrice") or {}
            items.append({
                "product_id": ref.get("catalogItemId"),
                "revenue_cents": _money_to_cents(price.get("amount")),
                "quantity": int(item.get("quantity") or 0),
            })
        orders.append({
            "id": order.get("id"),
            "created_date": order.get("createdDate"),
            "payment_status": order.get("paymentStatus"),
            "items": items,
        })
    return orders
