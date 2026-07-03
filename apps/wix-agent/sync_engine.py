import json
import os
from datetime import datetime, timezone
from typing import Optional

import wix_client as wix
import zendrop_client as zendrop

LOG_DIR = os.path.join(os.path.dirname(__file__), "logs")
os.makedirs(LOG_DIR, exist_ok=True)


def _ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def _write_log(filename: str, data: object) -> str:
    path = os.path.join(LOG_DIR, filename)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
    return path


def audit_inventory(catalog_version: str = "v3") -> dict:
    print("Fetching Wix products...")
    products = wix.get_all_products(catalog_version)
    product_map = {p["id"]: p for p in products}

    print(f"Fetched {len(products)} products. Fetching inventory items...")
    inv_items = wix.get_all_inventory_items(catalog_version)

    inv_by_product: dict[str, list] = {}
    for item in inv_items:
        pid = item.get("productId", "")
        inv_by_product.setdefault(pid, []).append(item)

    print(f"Fetched {len(inv_items)} inventory items. Querying Zendrop catalog...")
    try:
        zendrop_products = zendrop.get_all_products()
    except Exception as e:
        print(f"Zendrop catalog unavailable ({e}) — auditing Wix only")
        zendrop_products = []
    zendrop_by_name = {(p.get("name") or "").lower(): p for p in zendrop_products}

    broken = []
    healthy = []
    no_zendrop_match = []

    for product_id, product in product_map.items():
        product_name = product.get("name", "")
        product_name_lower = product_name.lower()
        items_for_product = inv_by_product.get(product_id, [])

        wix_statuses = [i.get("availabilityStatus", "UNKNOWN") for i in items_for_product]
        wix_quantities = [i.get("quantity", 0) or 0 for i in items_for_product if i.get("trackQuantity")]
        wix_status = ("IN_STOCK" if all(s == "IN_STOCK" for s in wix_statuses) and wix_statuses
                      else (wix_statuses[0] if wix_statuses else "NO_INVENTORY_ITEM"))
        wix_qty = sum(wix_quantities)

        zd_match = zendrop_by_name.get(product_name_lower)
        if not zd_match:
            for zd_name, zd_p in zendrop_by_name.items():
                if product_name_lower in zd_name or zd_name in product_name_lower:
                    zd_match = zd_p
                    break

        if not zd_match:
            no_zendrop_match.append({
                "product_id": product_id,
                "name": product_name,
                "wix_status": wix_status,
                "wix_quantity": wix_qty,
                "visible": product.get("visible", True),
                "inventory_items": items_for_product,
            })
            continue

        zd_id = zd_match.get("id") or zd_match.get("product_id", "")
        try:
            zd_stock = zendrop.get_product_stock(str(zd_id))
        except Exception as e:
            zd_stock = {"in_stock": None, "quantity": 0, "error": str(e)}

        needs_fix = (
            zd_stock.get("in_stock") is True and wix_status != "IN_STOCK"
        ) or (
            zd_stock.get("quantity", 0) > 0 and wix_qty == 0 and wix_status != "IN_STOCK"
        )

        record = {
            "product_id": product_id,
            "name": product_name,
            "wix_status": wix_status,
            "wix_quantity": wix_qty,
            "visible": product.get("visible", True),
            "zendrop_product_id": str(zd_id),
            "zendrop_in_stock": zd_stock.get("in_stock"),
            "zendrop_quantity": zd_stock.get("quantity", 0),
            "needs_fix": needs_fix,
            "inventory_items": items_for_product,
        }

        if needs_fix:
            broken.append(record)
        else:
            healthy.append(record)

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "catalog_version": catalog_version,
        "summary": {
            "total_products": len(products),
            "total_inventory_items": len(inv_items),
            "broken_count": len(broken),
            "healthy_count": len(healthy),
            "no_zendrop_match_count": len(no_zendrop_match),
        },
        "broken": broken,
        "no_zendrop_match": no_zendrop_match,
        "healthy": healthy,
    }

    log_path = _write_log(f"audit_{_ts()}.json", report)
    print(f"Audit complete. Report saved to {log_path}")
    return report


def fix_inventory(
    wix_items: list[dict],
    confirmed_product_ids: list[str],
    catalog_version: str = "v3",
    dry_run: bool = False,
) -> dict:
    changes = []
    skipped = []
    by_product_id = {item["product_id"]: item for item in wix_items}

    for pid in confirmed_product_ids:
        record = by_product_id.get(pid)
        if not record:
            skipped.append({"product_id": pid, "reason": "not in broken list"})
            continue

        inv_items = record.get("inventory_items", [])
        if not inv_items:
            skipped.append({"product_id": pid, "reason": "no inventory items on Wix"})
            continue

        zd_qty = record.get("zendrop_quantity", 0)
        use_track_qty = zd_qty > 0

        for inv_item in inv_items:
            item_id = inv_item.get("id")
            before = {
                "inventory_item_id": item_id,
                "product_id": pid,
                "product_name": record["name"],
                "wix_status": inv_item.get("availabilityStatus"),
                "wix_quantity": inv_item.get("quantity"),
                "wix_track_quantity": inv_item.get("trackQuantity"),
            }
            after = {"track_quantity": use_track_qty, "quantity": zd_qty if use_track_qty else None, "in_stock": True}

            if not dry_run:
                try:
                    if catalog_version == "v3":
                        wix.update_inventory_item_v3(item_id=item_id, in_stock=True,
                                                     quantity=zd_qty if use_track_qty else None,
                                                     track_quantity=use_track_qty)
                    else:
                        wix.update_inventory_item_v1(product_id=pid, in_stock=True,
                                                     quantity=zd_qty if use_track_qty else None)
                    status = "updated"
                except Exception as e:
                    status = f"error: {e}"
            else:
                status = "dry_run"

            changes.append({
                "product_id": pid,
                "product_name": record["name"],
                "inventory_item_id": item_id,
                "zendrop_source": {
                    "product_id": record.get("zendrop_product_id"),
                    "in_stock": record.get("zendrop_in_stock"),
                    "quantity": zd_qty,
                },
                "before": before,
                "after": after,
                "status": status,
            })

    result = {
        "applied_at": datetime.now(timezone.utc).isoformat(),
        "dry_run": dry_run,
        "catalog_version": catalog_version,
        "changes": changes,
        "skipped": skipped,
    }
    log_path = _write_log(f"inventory_changes_{_ts()}.json", result)
    print(f"Fix complete. Log saved to {log_path}")
    return result


def full_sync(catalog_version: str = "v3") -> dict:
    report = audit_inventory(catalog_version)
    broken = report["broken"]

    if not broken:
        return {**report, "sync_action": "no_changes_needed"}

    confirmed_ids = [item["product_id"] for item in broken if item.get("zendrop_in_stock") is True]
    fix_result = fix_inventory(
        wix_items=broken,
        confirmed_product_ids=confirmed_ids,
        catalog_version=catalog_version,
        dry_run=False,
    )

    hidden = []
    for item in report["no_zendrop_match"]:
        if item.get("visible") and item.get("wix_status") == "OUT_OF_STOCK":
            try:
                wix.set_product_visibility(item["product_id"], visible=False, catalog_version=catalog_version)
                hidden.append(item["product_id"])
            except Exception:
                pass

    return {
        **report,
        "sync_action": "auto_fixed",
        "fixed_count": len([c for c in fix_result["changes"] if c["status"] == "updated"]),
        "hidden_count": len(hidden),
        "fix_log": fix_result,
    }
