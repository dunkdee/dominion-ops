import json
import os
import sqlite3
from datetime import datetime, timezone
from contextlib import contextmanager

import wix_client as wix
import zendrop_client as zendrop

DB_PATH = os.getenv("WIX_AGENT_DB", os.path.join(os.path.dirname(__file__), "wix_agent.db"))


@contextmanager
def _db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with _db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS fulfillments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                wix_order_id TEXT NOT NULL UNIQUE,
                zendrop_order_id TEXT,
                status TEXT NOT NULL DEFAULT 'pending_submit',
                tracking_number TEXT,
                carrier TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_status ON fulfillments(status)")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _map_wix_order_to_zendrop(order: dict) -> dict:
    shipping = order.get("shippingInfo", {}).get("logistics", {}).get("shippingDestination", {}).get("address", {})
    contact = order.get("buyerInfo", {})
    contact_name = contact.get("email", "").split("@")[0]
    line_items = []
    for li in order.get("lineItems", []):
        catalog_ref = li.get("catalogReference", {})
        line_items.append({
            "product_id": catalog_ref.get("catalogItemId", ""),
            "variant_id": catalog_ref.get("options", {}).get("variantId", ""),
            "quantity": li.get("quantity", 1),
            "sku": li.get("physicalProperties", {}).get("sku", ""),
            "name": li.get("productName", {}).get("original", ""),
        })
    return {
        "order": {
            "external_order_id": order.get("id", ""),
            "shipping_address": {
                "first_name": shipping.get("firstName", contact_name),
                "last_name": shipping.get("lastName", ""),
                "address1": shipping.get("addressLine", ""),
                "address2": shipping.get("addressLine2", ""),
                "city": shipping.get("city", ""),
                "province": shipping.get("subdivision", ""),
                "zip": shipping.get("postalCode", ""),
                "country": shipping.get("country", "US"),
                "phone": shipping.get("phone", contact.get("phone", "")),
            },
            "line_items": line_items,
            "note": f"Wix order {order.get('number', '')}",
        }
    }


def run_fulfillment_cycle(catalog_version: str = "v3") -> dict:
    init_db()
    orders = wix.get_orders(fulfillment_status="NOT_FULFILLED")
    submitted = []
    already_tracked = []
    errors = []
    with _db() as conn:
        existing_ids = {row["wix_order_id"] for row in conn.execute("SELECT wix_order_id FROM fulfillments").fetchall()}
    for order in orders:
        order_id = order.get("id", "")
        if order_id in existing_ids:
            already_tracked.append(order_id)
            continue
        try:
            payload = _map_wix_order_to_zendrop(order)
            result = zendrop.submit_order(payload)
            zd_order = result.get("order", result)
            zd_id = str(zd_order.get("id", zd_order.get("order_id", "")))
            with _db() as conn:
                conn.execute(
                    "INSERT OR IGNORE INTO fulfillments (wix_order_id, zendrop_order_id, status, created_at, updated_at) VALUES (?, ?, 'submitted', ?, ?)",
                    (order_id, zd_id, _now(), _now()),
                )
            submitted.append({"wix_order_id": order_id, "zendrop_order_id": zd_id})
        except Exception as e:
            errors.append({"wix_order_id": order_id, "error": str(e)})
    return {"run_at": _now(), "orders_found": len(orders), "submitted": submitted, "already_tracked": already_tracked, "errors": errors}


def check_pending_fulfillments(catalog_version: str = "v3") -> dict:
    init_db()
    with _db() as conn:
        rows = conn.execute("SELECT wix_order_id, zendrop_order_id FROM fulfillments WHERE status = 'submitted'").fetchall()
    updated = []
    still_pending = []
    errors = []
    for row in rows:
        wix_id = row["wix_order_id"]
        zd_id = row["zendrop_order_id"]
        try:
            status_data = zendrop.get_order_status(zd_id)
            tracking = status_data.get("tracking_number")
            carrier = status_data.get("carrier", "OTHER")
            if tracking:
                wix.fulfill_order(order_id=wix_id, tracking_number=tracking, shipping_provider=carrier or "OTHER")
                with _db() as conn:
                    conn.execute(
                        "UPDATE fulfillments SET status='fulfilled', tracking_number=?, carrier=?, updated_at=? WHERE wix_order_id=?",
                        (tracking, carrier, _now(), wix_id),
                    )
                updated.append({"wix_order_id": wix_id, "zendrop_order_id": zd_id, "tracking_number": tracking, "carrier": carrier})
            else:
                still_pending.append({"wix_order_id": wix_id, "zendrop_status": status_data.get("status")})
        except Exception as e:
            errors.append({"wix_order_id": wix_id, "error": str(e)})
    return {"checked_at": _now(), "updated": updated, "still_pending": still_pending, "errors": errors}


def get_fulfillment_summary() -> dict:
    init_db()
    with _db() as conn:
        rows = conn.execute("SELECT status, COUNT(*) as count FROM fulfillments GROUP BY status").fetchall()
    return {row["status"]: row["count"] for row in rows}
