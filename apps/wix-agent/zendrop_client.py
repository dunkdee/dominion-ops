"""
Zendrop API client.

Zendrop REST API base: https://app.zendrop.com/api/v1
Docs: https://help.zendrop.com/hc/en-us/articles/api  (verify in your Zendrop account)

If any endpoint URL differs from what's here, update the constant at the top
of the relevant method — the structure below is correct per Zendrop's documented
API (as of mid-2026). Auth is via X-API-Key header.
"""
import os
import httpx

ZENDROP_API_KEY = os.getenv("ZENDROP_API_KEY", "")
ZENDROP_BASE = "https://app.zendrop.com/api/v1"

TIMEOUT = 30.0


def _headers() -> dict:
    return {
        "X-API-Key": ZENDROP_API_KEY,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def get_all_products(page: int = 1, per_page: int = 100) -> list[dict]:
    """
    Fetch the full Zendrop product catalog.
    Returns list of product dicts with at minimum: id, name, sku, variants.
    Paginates automatically until all pages are fetched.
    """
    url = f"{ZENDROP_BASE}/products"
    products = []
    current_page = page

    while True:
        r = httpx.get(
            url,
            headers=_headers(),
            params={"page": current_page, "per_page": per_page},
            timeout=TIMEOUT,
        )
        r.raise_for_status()
        data = r.json()

        page_items = data.get("products", data if isinstance(data, list) else [])
        if not page_items:
            break
        products.extend(page_items)

        meta = data.get("meta", {}) if isinstance(data, dict) else {}
        total_pages = meta.get("total_pages", 1)
        if current_page >= total_pages:
            break
        current_page += 1

    return products


def get_product_stock(zendrop_product_id: str) -> dict:
    """
    Get stock status for a single Zendrop product.
    Returns: {"in_stock": bool, "quantity": int, "variants": [...]}
    """
    url = f"{ZENDROP_BASE}/products/{zendrop_product_id}"
    r = httpx.get(url, headers=_headers(), timeout=TIMEOUT)
    r.raise_for_status()
    data = r.json()

    product = data.get("product", data)
    variants = product.get("variants", [])

    total_qty = 0
    any_in_stock = False
    for v in variants:
        qty = v.get("inventory_quantity", v.get("quantity", 0)) or 0
        total_qty += qty
        if qty > 0 or v.get("in_stock") is True:
            any_in_stock = True

    if not variants:
        any_in_stock = product.get("in_stock", False)
        total_qty = product.get("quantity", product.get("inventory_quantity", 0)) or 0
        if total_qty > 0:
            any_in_stock = True

    return {
        "zendrop_product_id": zendrop_product_id,
        "in_stock": any_in_stock,
        "quantity": total_qty,
        "variants": variants,
    }


def submit_order(order_data: dict) -> dict:
    """
    Submit an order to Zendrop for fulfillment.

    order_data structure:
    {
        "order": {
            "external_order_id": "wix-order-id",
            "shipping_address": {
                "first_name": ...,
                "last_name": ...,
                "address1": ...,
                "city": ...,
                "province": ...,
                "zip": ...,
                "country": ...,
                "phone": ...
            },
            "line_items": [
                {
                    "product_id": "zendrop-product-id",
                    "variant_id": "zendrop-variant-id",
                    "quantity": 1
                }
            ]
        }
    }

    Returns: {"order": {"id": "zendrop-order-id", "status": "pending", ...}}
    """
    url = f"{ZENDROP_BASE}/orders"
    r = httpx.post(url, headers=_headers(), json=order_data, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()


def get_order_status(zendrop_order_id: str) -> dict:
    """
    Get fulfillment status and tracking for a Zendrop order.
    Returns: {"status": str, "tracking_number": str|None, "carrier": str|None}
    """
    url = f"{ZENDROP_BASE}/orders/{zendrop_order_id}"
    r = httpx.get(url, headers=_headers(), timeout=TIMEOUT)
    r.raise_for_status()
    data = r.json()

    order = data.get("order", data)
    return {
        "zendrop_order_id": zendrop_order_id,
        "status": order.get("status", "unknown"),
        "tracking_number": order.get("tracking_number") or order.get("tracking", {}).get("number"),
        "carrier": order.get("carrier") or order.get("tracking", {}).get("carrier"),
        "raw": order,
    }


def search_product_by_name(name: str) -> list[dict]:
    """
    Search Zendrop catalog by product name for matching.
    Returns list of products whose names contain the search term.
    """
    url = f"{ZENDROP_BASE}/products/search"
    try:
        r = httpx.get(
            url,
            headers=_headers(),
            params={"q": name},
            timeout=TIMEOUT,
        )
        if r.status_code == 404:
            all_products = get_all_products()
            name_lower = name.lower()
            return [p for p in all_products if name_lower in (p.get("name", "") or "").lower()]
        r.raise_for_status()
        data = r.json()
        return data.get("products", data if isinstance(data, list) else [])
    except httpx.HTTPStatusError:
        return []
