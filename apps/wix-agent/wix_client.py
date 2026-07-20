import os
from typing import Optional

import httpx


WIX_API_KEY = os.getenv("WIX_API_KEY", "")
WIX_SITE_ID = os.getenv("WIX_SITE_ID", "")

BASE_V3 = "https://www.wixapis.com/stores/v3"
BASE_V1_READ = "https://www.wixapis.com/stores-reader/v1"
BASE_V1_WRITE = "https://www.wixapis.com/stores/v1"
ECOM_BASE = "https://www.wixapis.com/ecom/v1"

TIMEOUT = 30.0


class UnsupportedWixOperation(RuntimeError):
    pass


class WixCatalogVersionError(RuntimeError):
    pass


def _headers() -> dict:
    return {
        "Authorization": WIX_API_KEY,
        "wix-site-id": WIX_SITE_ID,
        "Content-Type": "application/json",
    }


def detect_catalog_version() -> str:
    if not WIX_API_KEY or not WIX_SITE_ID:
        raise WixCatalogVersionError("Wix API key and site ID are required")
    response = httpx.get(
        f"{BASE_V3}/provision/version", headers=_headers(), timeout=TIMEOUT
    )
    response.raise_for_status()
    payload = response.json()
    version = str(
        payload.get("catalogVersion") or payload.get("version") or ""
    ).upper()
    if version == "V3_CATALOG" or version == "V3":
        return "v3"
    if version == "V1_CATALOG" or version == "V1":
        return "v1"
    raise WixCatalogVersionError(
        "Wix returned an unknown or unavailable catalog version"
    )


def _get_all_products_v3() -> list[dict]:
    products = []
    cursor = None
    while True:
        cursor_paging = {"limit": 100}
        if cursor:
            cursor_paging["cursor"] = cursor
        body = {
            "fields": ["PLAIN_DESCRIPTION", "MEDIA_ITEMS_INFO"],
            "query": {"cursorPaging": cursor_paging},
        }
        response = httpx.post(
            f"{BASE_V3}/products/query",
            headers=_headers(),
            json=body,
            timeout=TIMEOUT,
        )
        response.raise_for_status()
        data = response.json()
        page = data.get("products", [])
        products.extend(page)
        paging = data.get("pagingMetadata", {})
        cursor = paging.get("cursors", {}).get("next")
        if not paging.get("hasNext") or not cursor:
            break
    return products


def _get_all_products_v1() -> list[dict]:
    products = []
    offset = 0
    page_size = 100
    while True:
        body = {
            "includeVariants": True,
            "query": {"paging": {"limit": page_size, "offset": offset}},
        }
        response = httpx.post(
            f"{BASE_V1_READ}/products/query",
            headers=_headers(),
            json=body,
            timeout=TIMEOUT,
        )
        response.raise_for_status()
        data = response.json()
        page = data.get("products", [])
        products.extend(page)
        total = data.get("totalResults")
        if not page or len(page) < page_size:
            break
        if isinstance(total, int) and len(products) >= total:
            break
        offset += len(page)
    return products


def get_all_products(catalog_version: str = "v3") -> list[dict]:
    if catalog_version == "v3":
        return _get_all_products_v3()
    return _get_all_products_v1()


def _get_all_inventory_items_v3() -> list[dict]:
    items = []
    cursor = None
    while True:
        cursor_paging = {"limit": 1000}
        if cursor:
            cursor_paging["cursor"] = cursor
        body = {"query": {"cursorPaging": cursor_paging}}
        response = httpx.post(
            f"{BASE_V3}/inventory-items/query",
            headers=_headers(),
            json=body,
            timeout=TIMEOUT,
        )
        response.raise_for_status()
        data = response.json()
        page = data.get("inventoryItems", [])
        items.extend(page)
        paging = data.get("pagingMetadata", {})
        cursor = paging.get("cursors", {}).get("next")
        if not paging.get("hasNext") or not cursor:
            break
    return items


def _get_all_inventory_items_v1() -> list[dict]:
    items = []
    offset = 0
    page_size = 100
    while True:
        body = {"query": {"paging": {"limit": page_size, "offset": offset}}}
        response = httpx.post(
            "https://www.wixapis.com/stores-reader/v2/inventoryItems/query",
            headers=_headers(),
            json=body,
            timeout=TIMEOUT,
        )
        response.raise_for_status()
        data = response.json()
        page = data.get("inventoryItems", [])
        items.extend(page)
        total = data.get("totalResults")
        if not page or len(page) < page_size:
            break
        if isinstance(total, int) and len(items) >= total:
            break
        offset += len(page)
    return items


def get_all_inventory_items(catalog_version: str = "v3") -> list[dict]:
    if catalog_version == "v3":
        return _get_all_inventory_items_v3()
    return _get_all_inventory_items_v1()


def update_inventory_item_v3(
    item_id: str,
    in_stock: bool,
    quantity: Optional[int] = None,
    track_quantity: bool = True,
) -> dict:
    raise UnsupportedWixOperation(
        "Catalog V3 inventory writes are disabled until the current item "
        "revision and an exact supplier-variant mapping are verified"
    )


def update_inventory_item_v1(
    product_id: str, in_stock: bool, quantity: Optional[int] = None
) -> dict:
    url = (
        "https://www.wixapis.com/stores/v2/inventoryItems/product/"
        f"{product_id}"
    )
    body = {"inventoryItem": {"trackQuantity": quantity is not None}}
    if quantity is not None:
        body["inventoryItem"]["variants"] = [{"quantity": quantity}]
    else:
        body["inventoryItem"]["variants"] = [{"inStock": in_stock}]
    response = httpx.patch(url, headers=_headers(), json=body, timeout=TIMEOUT)
    response.raise_for_status()
    return response.json()


def set_product_visibility(
    product_id: str, visible: bool, catalog_version: str = "v3"
) -> dict:
    if catalog_version == "v3":
        raise UnsupportedWixOperation(
            "Catalog V3 product writes require the current product revision; "
            "use a reviewed revision-safe workflow"
        )
    base = BASE_V1_WRITE
    url = f"{base}/products/{product_id}"
    response = httpx.patch(
        url,
        headers=_headers(),
        json={"product": {"visible": visible}},
        timeout=TIMEOUT,
    )
    response.raise_for_status()
    return response.json()


def get_orders(
    fulfillment_status: str = "NOT_FULFILLED", limit: int = 100
) -> list[dict]:
    url = f"{ECOM_BASE}/orders/search"
    body = {
        "search": {
            "filter": {"fulfillmentStatus": fulfillment_status},
            "cursorPaging": {"limit": limit},
        }
    }
    response = httpx.post(
        url, headers=_headers(), json=body, timeout=TIMEOUT
    )
    response.raise_for_status()
    return response.json().get("orders", [])


def fulfill_order(
    order_id: str, tracking_number: str, shipping_provider: str = "OTHER"
) -> dict:
    url = f"{ECOM_BASE}/fulfillments"
    body = {
        "fulfillment": {
            "orderId": order_id,
            "trackingInfo": {
                "trackingNumber": tracking_number,
                "shippingProvider": shipping_provider,
            },
        }
    }
    response = httpx.post(
        url, headers=_headers(), json=body, timeout=TIMEOUT
    )
    response.raise_for_status()
    return response.json()


def get_store_settings() -> dict:
    raise UnsupportedWixOperation(
        "Checkout policy settings are not available through the documented "
        "Wix Stores REST API; verify them in the Wix dashboard"
    )


def update_store_settings(policy_patch: dict) -> dict:
    raise UnsupportedWixOperation(
        "Checkout policy settings are not available through the documented "
        "Wix Stores REST API; update them in the Wix dashboard"
    )


def get_pages() -> list[dict]:
    raise UnsupportedWixOperation(
        "Wix editor page creation is not available through the documented "
        "site-level REST API; verify published pages in the Wix editor"
    )


def create_page(title: str, slug: str) -> dict:
    raise UnsupportedWixOperation(
        "Wix editor page creation is not available through the documented "
        "site-level REST API; create this page in the Wix editor"
    )


def update_product_content(
    product_id: str,
    description: str,
    seo_title: str,
    seo_description: str,
    catalog_version: str = "v3",
) -> dict:
    if catalog_version == "v3":
        raise UnsupportedWixOperation(
            "Catalog V3 product writes require the current product revision; "
            "use a reviewed revision-safe workflow"
        )
    url = f"{BASE_V1_WRITE}/products/{product_id}"
    payload = {
        "product": {
            "description": description,
            "seoTitle": seo_title,
            "seoDescription": seo_description,
        }
    }
    response = httpx.patch(
        url, headers=_headers(), json=payload, timeout=TIMEOUT
    )
    response.raise_for_status()
    return response.json()
