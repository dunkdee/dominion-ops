import os
import httpx
from typing import Optional

WIX_API_KEY = os.getenv("WIX_API_KEY", "")
WIX_SITE_ID = os.getenv("WIX_SITE_ID", "a790d430-a3a0-4b0e-9be6-4c874c229167")

BASE_V3 = "https://www.wixapis.com/stores/v3"
BASE_V1 = "https://www.wixapis.com/stores/v1"
ECOM_BASE = "https://www.wixapis.com/ecom/v1"

TIMEOUT = 30.0


def _headers() -> dict:
    return {
        "Authorization": WIX_API_KEY,
        "wix-site-id": WIX_SITE_ID,
        "Content-Type": "application/json",
    }


def detect_catalog_version() -> str:
    try:
        r = httpx.get(f"{BASE_V3}/provision/version", headers=_headers(), timeout=TIMEOUT)
        if r.status_code == 200:
            version = r.json().get("version", "")
            if "V3" in version.upper():
                return "v3"
    except Exception:
        pass
    return "v1"


def get_all_products(catalog_version: str = "v3") -> list[dict]:
    url = f"{BASE_V3}/products/query" if catalog_version == "v3" else f"{BASE_V1}/products/query"
    products = []
    cursor = None
    first_page = True
    while True:
        if first_page:
            body = {"query": {"fields": ["DESCRIPTION", "MEDIA_ITEMS_INFO"], "cursorPaging": {"limit": 100}}}
            first_page = False
        else:
            body = {"query": {"cursorPaging": {"limit": 100, "cursor": cursor}}}
        r = httpx.post(url, headers=_headers(), json=body, timeout=TIMEOUT)
        r.raise_for_status()
        data = r.json()
        products.extend(data.get("products", []))
        paging = data.get("pagingMetadata", {})
        if not paging.get("hasNext"):
            break
        cursor = paging.get("cursors", {}).get("next")
        if not cursor:
            break
    return products


def get_all_inventory_items(catalog_version: str = "v3") -> list[dict]:
    if catalog_version == "v3":
        url = f"{BASE_V3}/inventory-items/query"
        page_size = 1000
    else:
        url = "https://www.wixapis.com/stores-reader/v2/inventoryItems/query"
        page_size = 100
    items = []
    cursor = None
    first_page = True
    while True:
        if first_page:
            body = {"query": {"cursorPaging": {"limit": page_size}}}
            first_page = False
        else:
            body = {"query": {"cursorPaging": {"limit": page_size, "cursor": cursor}}}
        r = httpx.post(url, headers=_headers(), json=body, timeout=TIMEOUT)
        r.raise_for_status()
        data = r.json()
        items.extend(data.get("inventoryItems", []))
        paging = data.get("pagingMetadata", {})
        if not paging.get("hasNext"):
            break
        cursor = paging.get("cursors", {}).get("next")
        if not cursor:
            break
    return items


def update_inventory_item_v3(item_id: str, in_stock: bool, quantity: Optional[int] = None, track_quantity: bool = True) -> dict:
    url = f"{BASE_V3}/inventory-items/{item_id}"
    patch = {"inventoryItem": {"trackQuantity": track_quantity}}
    if track_quantity and quantity is not None:
        patch["inventoryItem"]["quantity"] = quantity
    else:
        patch["inventoryItem"]["inStock"] = in_stock
    r = httpx.patch(url, headers=_headers(), json=patch, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()


def update_inventory_item_v1(product_id: str, in_stock: bool, quantity: Optional[int] = None) -> dict:
    url = f"https://www.wixapis.com/stores/v2/inventoryItems/product/{product_id}"
    body = {"inventoryItem": {"trackQuantity": quantity is not None}}
    if quantity is not None:
        body["inventoryItem"]["variants"] = [{"quantity": quantity}]
    else:
        body["inventoryItem"]["variants"] = [{"inStock": in_stock}]
    r = httpx.patch(url, headers=_headers(), json=body, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()


def set_product_visibility(product_id: str, visible: bool, catalog_version: str = "v3") -> dict:
    base = BASE_V3 if catalog_version == "v3" else BASE_V1
    url = f"{base}/products/{product_id}"
    r = httpx.patch(url, headers=_headers(), json={"product": {"visible": visible}}, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()


def get_orders(fulfillment_status: str = "NOT_FULFILLED", limit: int = 100) -> list[dict]:
    url = f"{ECOM_BASE}/orders/search"
    body = {"search": {"filter": {"fulfillmentStatus": fulfillment_status}, "cursorPaging": {"limit": limit}}}
    r = httpx.post(url, headers=_headers(), json=body, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json().get("orders", [])


def fulfill_order(order_id: str, tracking_number: str, shipping_provider: str = "OTHER") -> dict:
    url = f"{ECOM_BASE}/fulfillments"
    body = {"fulfillment": {"orderId": order_id, "trackingInfo": {"trackingNumber": tracking_number, "shippingProvider": shipping_provider}}}
    r = httpx.post(url, headers=_headers(), json=body, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()
