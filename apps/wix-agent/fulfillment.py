import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

import empire
import wix_client as wix
import zendrop_client as zendrop


DEFAULT_DB_PATH = Path(__file__).with_name("wix_agent.db")
VALID_FULFILLMENT_MODES = {"record_only", "live"}


def fulfillment_mode() -> str:
    return os.getenv("WIX_FULFILLMENT_MODE", "record_only").strip().lower()


def _variant_mapping() -> dict:
    raw = os.getenv("ZENDROP_VARIANT_MAP_JSON", "").strip()
    if not raw:
        return {}
    try:
        mapping = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Zendrop variant mapping is not valid JSON") from exc
    if not isinstance(mapping, dict):
        raise RuntimeError("Zendrop variant mapping must be a JSON object")
    return mapping


def variant_mapping_health() -> dict:
    try:
        mapping = _variant_mapping()
        invalid = 0
        for value in mapping.values():
            if not isinstance(value, dict) or not value.get(
                "product_id"
            ) or not value.get("variant_id"):
                invalid += 1
        if invalid:
            return {"status": "error", "entries": len(mapping), "invalid": invalid}
        return {
            "status": "ok" if mapping else "missing",
            "entries": len(mapping),
        }
    except Exception as exc:
        return {"status": "error", "error_type": exc.__class__.__name__}


def database_path() -> Path:
    return Path(os.getenv("WIX_AGENT_DB", str(DEFAULT_DB_PATH))).expanduser()


def _prepare_database_path() -> Path:
    path = database_path()
    if path.exists() and path.is_dir():
        raise RuntimeError(
            "WIX_AGENT_DB points to a directory; configure a writable SQLite file path"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


@contextmanager
def _db():
    path = _prepare_database_path()
    conn = sqlite3.connect(str(path), timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA busy_timeout = 5000")
        conn.execute("PRAGMA journal_mode = WAL")
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with _db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS fulfillments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                wix_order_id TEXT NOT NULL UNIQUE,
                zendrop_order_id TEXT,
                status TEXT NOT NULL DEFAULT 'pending_submit',
                tracking_number TEXT,
                carrier TEXT,
                last_error TEXT,
                attempt_count INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        columns = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(fulfillments)").fetchall()
        }
        if "last_error" not in columns:
            conn.execute("ALTER TABLE fulfillments ADD COLUMN last_error TEXT")
        if "attempt_count" not in columns:
            conn.execute(
                "ALTER TABLE fulfillments "
                "ADD COLUMN attempt_count INTEGER NOT NULL DEFAULT 0"
            )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_status ON fulfillments(status)")


def database_health() -> dict:
    try:
        init_db()
        with _db() as conn:
            result = conn.execute("PRAGMA quick_check").fetchone()[0]
        if result != "ok":
            return {"status": "error", "check": result}
        return {"status": "ok"}
    except Exception as exc:
        return {"status": "error", "error": str(exc)}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _reserve_order(order_id: str) -> bool:
    """Claim an order before calling Zendrop so retries cannot duplicate it."""
    now = _now()
    with _db() as conn:
        cursor = conn.execute(
            "INSERT OR IGNORE INTO fulfillments "
            "(wix_order_id, status, last_error, attempt_count, created_at, updated_at) "
            "VALUES (?, 'submitting', NULL, 1, ?, ?)",
            (order_id, now, now),
        )
    return cursor.rowcount == 1


def _record_submission(order_id: str, zendrop_order_id: str) -> None:
    with _db() as conn:
        conn.execute(
            "UPDATE fulfillments SET zendrop_order_id=?, status='submitted', "
            "last_error=NULL, updated_at=? WHERE wix_order_id=?",
            (zendrop_order_id, _now(), order_id),
        )


def _record_submission_failure(order_id: str, error: Exception) -> None:
    # Keep diagnostics bounded and do not automatically retry an uncertain
    # supplier submission; an operator must reconcile it with Zendrop first.
    message = str(error).strip() or error.__class__.__name__
    with _db() as conn:
        conn.execute(
            "UPDATE fulfillments SET status='submit_failed', last_error=?, "
            "updated_at=? WHERE wix_order_id=?",
            (message[:500], _now(), order_id),
        )


def _map_wix_order_to_zendrop(order: dict) -> dict:
    shipping = (
        order.get("shippingInfo", {})
        .get("logistics", {})
        .get("shippingDestination", {})
        .get("address", {})
    )
    contact = order.get("buyerInfo", {})
    contact_name = contact.get("email", "").split("@")[0]
    mapping = _variant_mapping()
    line_items = []
    for line_item in order.get("lineItems", []):
        catalog_ref = line_item.get("catalogReference", {})
        wix_product_id = str(catalog_ref.get("catalogItemId") or "")
        wix_variant_id = str(
            (catalog_ref.get("options") or {}).get("variantId") or ""
        )
        mapping_key = f"{wix_product_id}:{wix_variant_id}"
        supplier = mapping.get(mapping_key)
        if not wix_product_id or not wix_variant_id or not isinstance(supplier, dict):
            raise RuntimeError(
                "Order contains a Wix variant without an exact Zendrop mapping"
            )
        supplier_product_id = str(supplier.get("product_id") or "")
        supplier_variant_id = str(supplier.get("variant_id") or "")
        if not supplier_product_id or not supplier_variant_id:
            raise RuntimeError("Zendrop mapping is missing a product or variant ID")
        quantity = line_item.get("quantity", 1)
        if not isinstance(quantity, int) or isinstance(quantity, bool) or quantity < 1:
            raise RuntimeError("Order contains an invalid line-item quantity")
        wix_sku = str(
            (line_item.get("physicalProperties") or {}).get("sku") or ""
        )
        expected_sku = str(supplier.get("wix_sku") or "")
        if expected_sku and wix_sku != expected_sku:
            raise RuntimeError("Wix SKU does not match the approved Zendrop mapping")
        line_items.append(
            {
                "product_id": supplier_product_id,
                "variant_id": supplier_variant_id,
                "quantity": quantity,
                "sku": wix_sku,
                "name": line_item.get("productName", {}).get("original", ""),
            }
        )
    if not line_items:
        raise RuntimeError("Order has no physical line items to fulfill")
    required_address = {
        "first_name": shipping.get("firstName", contact_name),
        "address1": shipping.get("addressLine", ""),
        "city": shipping.get("city", ""),
        "zip": shipping.get("postalCode", ""),
        "country": shipping.get("country", ""),
    }
    if any(not str(value or "").strip() for value in required_address.values()):
        raise RuntimeError("Order shipping address is incomplete")
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
    mode = fulfillment_mode()
    if mode not in VALID_FULFILLMENT_MODES:
        raise RuntimeError("WIX_FULFILLMENT_MODE must be record_only or live")
    orders = wix.get_orders(fulfillment_status="NOT_FULFILLED")
    submitted = []
    already_tracked = []
    held = []
    ineligible = []
    errors = []
    for order in orders:
        order_id = order.get("id", "")
        if not order_id:
            errors.append({"wix_order_id": "", "error": "Wix order is missing an ID"})
            continue
        status = str(order.get("status") or "").upper()
        payment_status = str(order.get("paymentStatus") or "").upper()
        if status != "APPROVED" or payment_status != "PAID":
            ineligible.append(order_id)
            continue
        if mode == "record_only":
            held.append(order_id)
            continue
        try:
            payload = _map_wix_order_to_zendrop(order)
        except Exception as exc:
            errors.append({"wix_order_id": order_id, "error": str(exc)})
            continue
        if not _reserve_order(order_id):
            already_tracked.append(order_id)
            continue
        try:
            result = zendrop.submit_order(payload)
            zd_order = result.get("order", result)
            zd_id = str(zd_order.get("id", zd_order.get("order_id", "")))
            if not zd_id:
                raise RuntimeError(
                    "Zendrop response did not include an order ID; "
                    "manual reconciliation required"
                )
            _record_submission(order_id, zd_id)
            submitted.append({"wix_order_id": order_id, "zendrop_order_id": zd_id})
        except Exception as exc:
            _record_submission_failure(order_id, exc)
            errors.append({"wix_order_id": order_id, "error": str(exc)})

    result = {
        "run_at": _now(),
        "orders_found": len(orders),
        "submitted": submitted,
        "already_tracked": already_tracked,
        "held_for_manual_fulfillment": held,
        "ineligible": ineligible,
        "errors": errors,
    }

    if submitted:
        empire.notify_empire(
            "order_fulfilled",
            {
                "fulfilled_count": len(submitted),
                "orders_found": len(orders),
                "submitted_order_ids": [item["wix_order_id"] for item in submitted],
                "error_count": len(errors),
            },
        )

    return result


def check_pending_fulfillments(catalog_version: str = "v3") -> dict:
    init_db()
    with _db() as conn:
        rows = conn.execute(
            "SELECT wix_order_id, zendrop_order_id "
            "FROM fulfillments WHERE status = 'submitted'"
        ).fetchall()
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
                wix.fulfill_order(
                    order_id=wix_id,
                    tracking_number=tracking,
                    shipping_provider=carrier or "OTHER",
                )
                with _db() as conn:
                    conn.execute(
                        "UPDATE fulfillments SET status='fulfilled', "
                        "tracking_number=?, carrier=?, updated_at=? WHERE wix_order_id=?",
                        (tracking, carrier, _now(), wix_id),
                    )
                updated.append(
                    {
                        "wix_order_id": wix_id,
                        "zendrop_order_id": zd_id,
                        "tracking_number": tracking,
                        "carrier": carrier,
                    }
                )
            else:
                still_pending.append(
                    {
                        "wix_order_id": wix_id,
                        "zendrop_status": status_data.get("status"),
                    }
                )
        except Exception as exc:
            errors.append({"wix_order_id": wix_id, "error": str(exc)})

    if updated:
        empire.notify_empire(
            "tracking_updated",
            {
                "updated_count": len(updated),
                "still_pending": len(still_pending),
                "orders": [
                    {
                        "wix_order_id": item["wix_order_id"],
                        "tracking": item["tracking_number"],
                        "carrier": item["carrier"],
                    }
                    for item in updated
                ],
            },
        )

    return {
        "checked_at": _now(),
        "updated": updated,
        "still_pending": still_pending,
        "errors": errors,
    }


def get_fulfillment_summary() -> dict:
    init_db()
    with _db() as conn:
        rows = conn.execute(
            "SELECT status, COUNT(*) AS count FROM fulfillments GROUP BY status"
        ).fetchall()
    return {row["status"]: row["count"] for row in rows}
