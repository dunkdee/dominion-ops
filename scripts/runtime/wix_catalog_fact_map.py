#!/usr/bin/env python3
"""Map factual Wix product metadata without mutating the store.

The child collector executes inside the existing Wix Agent container so it can use
its already-configured Wix credentials without exposing them. The report includes
product/catalog metadata only. It excludes environment values, customer/order data,
raw API responses, inventory quantities, secret values, and raw logs.
"""

from __future__ import annotations

import json
import subprocess
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any

WIX_CONTAINER = "wix-agent"
PROTECTED_HTTP = (
    ("baby-api", 8080, "/"),
    ("wix-agent", 8082, "/ready"),
    ("dominion-web", 8090, "/"),
    ("n8n", 5678, "/healthz"),
    ("alpha-engine", 8787, "/health"),
    ("conductor", 5060, "/health"),
)

CHILD = r'''
import json
import wix_client as wix


def first(mapping, *keys):
    for key in keys:
        value = mapping.get(key)
        if value is not None:
            return value
    return None


def length(value):
    if isinstance(value, (list, tuple, dict, str)):
        return len(value)
    return 0


def description_text(product):
    for key in ("plainDescription", "description"):
        value = product.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def media_count(product):
    for key in ("mediaItemsInfo", "media", "mediaItems"):
        value = product.get(key)
        if isinstance(value, list):
            return len(value)
        if isinstance(value, dict):
            for nested in ("items", "mediaItems"):
                nested_value = value.get(nested)
                if isinstance(nested_value, list):
                    return len(nested_value)
    return 0


def variant_rows(product):
    direct = product.get("variants")
    if isinstance(direct, list):
        return direct
    info = product.get("variantsInfo")
    if isinstance(info, dict):
        rows = info.get("variants")
        if isinstance(rows, list):
            return rows
    return []


def option_rows(product):
    value = product.get("options")
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        return list(value.values())
    return []


def sku_count(product, variants):
    count = 0
    candidates = [product] + list(variants)
    for item in candidates:
        if not isinstance(item, dict):
            continue
        sku = first(item, "sku", "stockKeepingUnit")
        if isinstance(sku, str) and sku.strip():
            count += 1
        elif sku not in (None, ""):
            count += 1
    return count


def price_present(product, variants):
    keys = {
        "price", "priceData", "actualPrice", "actualPriceRange",
        "compareAtPrice", "compareAtPriceRange", "basePriceRange"
    }
    if any(product.get(key) not in (None, {}, [], "") for key in keys):
        return True
    for variant in variants:
        if isinstance(variant, dict) and any(
            variant.get(key) not in (None, {}, [], "") for key in keys
        ):
            return True
    return False


version = wix.detect_catalog_version()
products = wix.get_all_products(version)
records = []
all_keys = set()
for product in products:
    if not isinstance(product, dict):
        continue
    all_keys.update(product.keys())
    variants = variant_rows(product)
    options = option_rows(product)
    brand = first(product, "brand", "brandName")
    if isinstance(brand, dict):
        brand = first(brand, "name", "label")
    record = {
        "id": first(product, "id", "_id"),
        "revision": first(product, "revision", "_revision"),
        "name": first(product, "name", "title"),
        "slug": first(product, "slug", "urlSlug"),
        "visible": first(product, "visible", "isVisible"),
        "product_type": first(product, "productType", "product_type", "type"),
        "brand": brand,
        "description_characters": len(description_text(product)),
        "media_count": media_count(product),
        "option_count": len(options),
        "variant_count": len(variants),
        "sku_entries": sku_count(product, variants),
        "price_present": price_present(product, variants),
    }
    records.append(record)

summary = {
    "total": len(records),
    "missing_revision": sum(not item.get("revision") for item in records),
    "missing_name": sum(not str(item.get("name") or "").strip() for item in records),
    "missing_slug": sum(not str(item.get("slug") or "").strip() for item in records),
    "missing_brand": sum(not str(item.get("brand") or "").strip() for item in records),
    "missing_description": sum(item["description_characters"] == 0 for item in records),
    "description_under_150": sum(item["description_characters"] < 150 for item in records),
    "missing_media": sum(item["media_count"] == 0 for item in records),
    "missing_sku": sum(item["sku_entries"] == 0 for item in records),
    "missing_price_field": sum(not item["price_present"] for item in records),
    "with_options": sum(item["option_count"] > 0 for item in records),
    "with_variants": sum(item["variant_count"] > 0 for item in records),
    "visibility_true": sum(item.get("visible") is True for item in records),
    "visibility_false": sum(item.get("visible") is False for item in records),
    "visibility_unknown": sum(item.get("visible") not in {True, False} for item in records),
}

print(json.dumps({
    "catalog_version": version,
    "summary": summary,
    "available_product_fields": sorted(all_keys),
    "products": records,
}, sort_keys=True))
'''


def command(args: list[str], *, input_text: str | None = None, timeout: int = 180) -> dict[str, Any]:
    try:
        result = subprocess.run(
            args,
            input=input_text,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        return {
            "available": False,
            "returncode": None,
            "stdout": "",
            "stderr_type": type(exc).__name__,
        }
    return {
        "available": True,
        "returncode": result.returncode,
        "stdout": (result.stdout or "").strip(),
        "stderr_type": None if not result.stderr else "present",
    }


def http_probe(name: str, port: int, path: str) -> dict[str, Any]:
    record: dict[str, Any] = {
        "name": name,
        "port": port,
        "path": path,
        "reachable": False,
        "status": None,
    }
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=5) as response:
            response.read(1024)
            record.update({"reachable": True, "status": response.status})
    except urllib.error.HTTPError as exc:
        record.update({"reachable": True, "status": exc.code})
    except Exception as exc:  # noqa: BLE001
        record["error_type"] = type(exc).__name__
    return record


def container_fingerprints() -> dict[str, dict[str, Any]]:
    names = command(["docker", "ps", "--all", "--format", "{{.Names}}"], timeout=30)
    rows: dict[str, dict[str, Any]] = {}
    if names["returncode"] != 0:
        return rows
    for name in filter(None, names["stdout"].splitlines()):
        inspected = command(
            ["docker", "inspect", "--format", "{{.Id}}|{{.Image}}|{{.State.Status}}|{{.RestartCount}}", name],
            timeout=30,
        )
        if inspected["returncode"] == 0:
            parts = inspected["stdout"].split("|", 3)
            rows[name] = {
                "container_id": parts[0] if len(parts) > 0 else None,
                "image_id": parts[1] if len(parts) > 1 else None,
                "state": parts[2] if len(parts) > 2 else None,
                "restart_count": parts[3] if len(parts) > 3 else None,
            }
    return rows


def main() -> int:
    before = container_fingerprints()
    health_before = [http_probe(*item) for item in PROTECTED_HTTP]
    errors: list[str] = []

    if any(item.get("status") != 200 for item in health_before):
        errors.append("protected_health_failed_before")

    collector = command(
        ["docker", "exec", "-i", WIX_CONTAINER, "python", "-"],
        input_text=CHILD,
        timeout=240,
    )
    catalog: dict[str, Any] = {}
    if collector["returncode"] != 0:
        errors.append("catalog_collector_failed")
    else:
        try:
            catalog = json.loads(collector["stdout"])
        except json.JSONDecodeError:
            errors.append("catalog_report_parse_failed")

    health_after = [http_probe(*item) for item in PROTECTED_HTTP]
    after = container_fingerprints()
    containers_unchanged = before == after
    if any(item.get("status") != 200 for item in health_after):
        errors.append("protected_health_failed_after")
    if not containers_unchanged:
        errors.append("container_inventory_changed")

    success = not errors
    report = {
        "alignment_stage": "wix-catalog-fact-map",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "success" if success else "failed",
        "success": success,
        "catalog": catalog,
        "protected_health_before": health_before,
        "protected_health_after": health_after,
        "containers_unchanged": containers_unchanged,
        "errors": errors,
        "next_gate": (
            "Draft product descriptions only from verified product/supplier facts; "
            "do not mutate Wix until revision-safe writes and human approval exist"
        ),
        "safety": {
            "wix_mutations_performed": False,
            "products_changed": False,
            "inventory_changed": False,
            "orders_changed": False,
            "customer_data_collected": False,
            "order_data_collected": False,
            "inventory_quantities_collected": False,
            "environment_values_collected": False,
            "secret_values_collected": False,
            "raw_api_responses_collected": False,
            "raw_logs_collected": False,
            "containers_changed": False,
            "networks_changed": False,
            "volumes_changed": False,
            "databases_changed": False,
            "dns_changed": False,
        },
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
