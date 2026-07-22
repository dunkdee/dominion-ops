#!/usr/bin/env python3
"""Map factual Wix V3 product, media, and variant metadata without mutations.

The collector runs inside the existing Wix Agent container so configured Wix
credentials never leave the VM. The report contains product-side metadata only:
counts, identifiers, revisions, field-presence flags, and description hashes. It
excludes environment values, raw API responses, inventory quantities, order data,
customer data, secret values, and raw logs.
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
import hashlib
import json
import re

import httpx
import wix_client as wix

VARIANTS_URL = "https://www.wixapis.com/stores/v3/products/query-variants"


def first(mapping, *keys):
    if not isinstance(mapping, dict):
        return None
    for key in keys:
        value = mapping.get(key)
        if value is not None:
            return value
    return None


def description_text(product):
    for key in ("plainDescription", "description"):
        value = product.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def normalized_description_hash(text):
    normalized = re.sub(r"\s+", " ", text).strip().lower()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest() if normalized else None


def media_facts(product):
    media = product.get("media")
    if not isinstance(media, dict):
        return {"items": 0, "main_present": False, "shape": "missing"}
    items_info = media.get("itemsInfo")
    if not isinstance(items_info, dict):
        items_info = media.get("items_info") if isinstance(media.get("items_info"), dict) else {}
    items = items_info.get("items") if isinstance(items_info, dict) else None
    if not isinstance(items, list):
        items = []
    return {
        "items": len(items),
        "main_present": bool(media.get("main")),
        "shape": "media.itemsInfo.items" if isinstance(items_info, dict) else "media",
    }


def option_count(product):
    options = product.get("options")
    if isinstance(options, list):
        return len(options)
    if isinstance(options, dict):
        return len(options)
    return 0


def query_variants():
    rows = []
    cursor = None
    while True:
        cursor_paging = {"limit": 1000}
        if cursor:
            cursor_paging["cursor"] = cursor
        body = {"fields": [], "query": {"cursorPaging": cursor_paging}}
        response = httpx.post(
            VARIANTS_URL,
            headers={
                "Authorization": wix.WIX_API_KEY,
                "wix-site-id": wix.WIX_SITE_ID,
                "Content-Type": "application/json",
            },
            json=body,
            timeout=30.0,
        )
        response.raise_for_status()
        payload = response.json()
        page = payload.get("variants") or []
        if isinstance(page, list):
            rows.extend(item for item in page if isinstance(item, dict))
        paging = payload.get("pagingMetadata") or {}
        cursors = paging.get("cursors") or {}
        cursor = cursors.get("next")
        if not paging.get("hasNext") or not cursor:
            break
    return rows


def variant_product_id(variant):
    product_data = variant.get("productData") or {}
    return first(product_data, "productId", "product_id")


def variant_price_present(variant):
    price = variant.get("price") or {}
    actual = price.get("actualPrice") or price.get("actual_price") or {}
    return actual.get("amount") not in (None, "")


version = wix.detect_catalog_version()
products = wix.get_all_products(version)
variant_error = None
variants = []
try:
    variants = query_variants() if version == "v3" else []
except Exception as exc:
    variant_error = exc.__class__.__name__

variants_by_product = {}
for variant in variants:
    product_id = variant_product_id(variant)
    if product_id:
        variants_by_product.setdefault(str(product_id), []).append(variant)

records = []
all_keys = set()
description_hash_counts = {}
for product in products:
    if not isinstance(product, dict):
        continue
    all_keys.update(product.keys())
    product_id = first(product, "id", "_id")
    product_variants = variants_by_product.get(str(product_id), [])
    description = description_text(product)
    description_hash = normalized_description_hash(description)
    if description_hash:
        description_hash_counts[description_hash] = description_hash_counts.get(description_hash, 0) + 1
    media = media_facts(product)
    brand = first(product, "brand", "brandName")
    if isinstance(brand, dict):
        brand = first(brand, "name", "label", "id")
    variant_summary = product.get("variantSummary") or {}
    summary_count = first(variant_summary, "variantCount", "count", "total")
    sku_entries = sum(
        1 for item in product_variants
        if str(first(item, "sku", "stockKeepingUnit") or "").strip()
    )
    record = {
        "id": product_id,
        "revision": first(product, "revision", "_revision"),
        "name": first(product, "name", "title"),
        "slug": first(product, "slug", "urlSlug"),
        "visible": first(product, "visible", "isVisible"),
        "product_type": first(product, "productType", "product_type", "type"),
        "brand": brand,
        "description_characters": len(description),
        "description_hash": description_hash,
        "media_count": media["items"],
        "main_media_present": media["main_present"],
        "option_count": option_count(product),
        "variant_summary_count": summary_count,
        "queried_variant_count": len(product_variants),
        "sku_entries": sku_entries,
        "variant_price_entries": sum(1 for item in product_variants if variant_price_present(item)),
        "visible_variant_count": sum(item.get("visible") is True for item in product_variants),
        "price_present": product.get("actualPriceRange") not in (None, {}, []),
    }
    records.append(record)

duplicate_groups = sorted(
    (count for count in description_hash_counts.values() if count > 1), reverse=True
)
summary = {
    "total": len(records),
    "missing_revision": sum(not item.get("revision") for item in records),
    "missing_name": sum(not str(item.get("name") or "").strip() for item in records),
    "missing_slug": sum(not str(item.get("slug") or "").strip() for item in records),
    "missing_brand": sum(not str(item.get("brand") or "").strip() for item in records),
    "missing_description": sum(item["description_characters"] == 0 for item in records),
    "description_under_150": sum(item["description_characters"] < 150 for item in records),
    "duplicate_description_groups": len(duplicate_groups),
    "largest_duplicate_description_group": max(duplicate_groups, default=1),
    "missing_media": sum(item["media_count"] == 0 for item in records),
    "missing_main_media": sum(not item["main_media_present"] for item in records),
    "missing_sku": sum(item["sku_entries"] == 0 for item in records),
    "missing_price_field": sum(not item["price_present"] for item in records),
    "with_options": sum(item["option_count"] > 0 for item in records),
    "with_queried_variants": sum(item["queried_variant_count"] > 0 for item in records),
    "queried_variants_total": len(variants),
    "variant_query_error_type": variant_error,
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


def command(args: list[str], *, input_text: str | None = None, timeout: int = 300) -> dict[str, Any]:
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
        timeout=360,
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
        "alignment_stage": "wix-catalog-deep-fact-map",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "success" if success else "failed",
        "success": success,
        "catalog": catalog,
        "protected_health_before": health_before,
        "protected_health_after": health_after,
        "containers_unchanged": containers_unchanged,
        "errors": errors,
        "next_gate": (
            "Reconcile descriptions, media, SKUs, variants, and supplier facts; "
            "do not mutate Wix until a revision-safe reviewed change set exists"
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
