#!/usr/bin/env python3
"""Collect a redacted, read-only Wix catalog pricing audit from the live agent container."""

from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

CONTAINER = "wix-agent"
OUTPUT = Path("/tmp/wix-pricing-audit.json")

CHILD = r'''
import json
from datetime import datetime, timezone

import httpx
import wix_client as wix

PRODUCTS_URL = "https://www.wixapis.com/stores/v3/products/query"
PRODUCT_FIELDS = ["MERCHANT_DATA", "CURRENCY", "MIN_PRICE_VARIANT"]


def first(mapping, *keys):
    if not isinstance(mapping, dict):
        return None
    for key in keys:
        value = mapping.get(key)
        if value is not None:
            return value
    return None


def amount(value):
    if isinstance(value, dict):
        value = first(value, "amount", "value")
    try:
        return round(float(value), 2)
    except (TypeError, ValueError):
        return None


def query_products():
    products = []
    cursor = None
    while True:
        paging = {"limit": 100}
        if cursor:
            paging["cursor"] = cursor
        response = httpx.post(
            PRODUCTS_URL,
            headers={
                "Authorization": wix.WIX_API_KEY,
                "wix-site-id": wix.WIX_SITE_ID,
                "Content-Type": "application/json",
            },
            json={
                "fields": PRODUCT_FIELDS,
                "query": {"cursorPaging": paging},
            },
            timeout=30.0,
        )
        response.raise_for_status()
        payload = response.json()
        page = payload.get("products") or []
        products.extend(item for item in page if isinstance(item, dict))
        metadata = payload.get("pagingMetadata") or {}
        cursor = (metadata.get("cursors") or {}).get("next")
        if not metadata.get("hasNext") or not cursor:
            break
    return products


def price_range(product):
    value = product.get("actualPriceRange") or product.get("actual_price_range") or {}
    return (
        amount(first(value, "minValue", "min", "minimum")),
        amount(first(value, "maxValue", "max", "maximum")),
    )


def min_variant(product):
    return (product.get("variantSummary") or {}).get("minPriceVariant") or {}


def item_cost(product, variant):
    revenue = variant.get("revenueDetails") or {}
    return amount(revenue.get("cost")) or amount(
        first(product.get("costRange") or {}, "minValue", "min", "minimum")
    )


version = wix.detect_catalog_version()
if version != "v3":
    raise SystemExit(f"unsupported catalog version for cost-evidenced pricing audit: {version}")

rows = []
for product in query_products():
    variant = min_variant(product)
    minimum, maximum = price_range(product)
    cost = item_cost(product, variant)
    current_margin = first(variant.get("revenueDetails") or {}, "profitMargin")
    try:
        current_margin = round(float(current_margin), 4)
    except (TypeError, ValueError):
        current_margin = None
    count = (product.get("variantSummary") or {}).get("variantCount") or 0
    try:
        count = int(count)
    except (TypeError, ValueError):
        count = 0
    if minimum is None:
        status = "PRICE_MISSING"
    elif cost is None:
        status = "COST_INPUT_REQUIRED"
    else:
        status = "SHIPPING_AND_PAYMENT_COSTS_REQUIRED"
    rows.append({
        "id": first(product, "id", "_id"),
        "name": first(product, "name", "title"),
        "slug": first(product, "slug", "urlSlug"),
        "visible": first(product, "visible", "isVisible"),
        "currency": first(product, "currency", "currencyCode") or "USD",
        "current_min_price": minimum,
        "current_max_price": maximum,
        "variant_count": count,
        "item_cost": cost,
        "supplier_cost": cost,
        "current_gross_margin": current_margin,
        "shipping_cost": None,
        "payment_processing_cost": None,
        "recommended_price": None,
        "pricing_status": status,
    })

print(json.dumps({
    "generated_at": datetime.now(timezone.utc).isoformat(),
    "catalog_version": version,
    "product_count": len(rows),
    "variant_count": sum(row["variant_count"] for row in rows),
    "currency_default": "USD",
    "policy": {
        "price_changes_performed": False,
        "requires_human_approval": True,
        "requires_shipping_cost": True,
        "requires_payment_processing_cost": True,
        "no_price_recommendation_without_all_cost_inputs": True,
    },
    "products": sorted(rows, key=lambda item: str(item.get("name") or "").lower()),
}, indent=2, sort_keys=True))
'''


def run(args: list[str], *, stdin: str | None = None, timeout: int = 360) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        input=stdin,
        text=True,
        capture_output=True,
        check=False,
        timeout=timeout,
    )


def main() -> int:
    before = run(["docker", "inspect", "--format", "{{.Id}}|{{.State.Status}}|{{.RestartCount}}", CONTAINER], timeout=30)
    if before.returncode != 0:
        raise SystemExit("wix-agent container unavailable")

    collected = run(["docker", "exec", "-i", CONTAINER, "python", "-"], stdin=CHILD)
    if collected.returncode != 0:
        raise SystemExit(f"pricing audit failed: {collected.stderr.strip()[:300]}")

    payload: dict[str, Any] = json.loads(collected.stdout)
    payload["audit_wrapper_generated_at"] = datetime.now(timezone.utc).isoformat()

    after = run(["docker", "inspect", "--format", "{{.Id}}|{{.State.Status}}|{{.RestartCount}}", CONTAINER], timeout=30)
    payload["container_unchanged"] = before.stdout.strip() == after.stdout.strip()
    payload["secrets_collected"] = False
    payload["customer_data_collected"] = False
    payload["orders_collected"] = False
    payload["mutations_performed"] = False

    OUTPUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(str(OUTPUT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
