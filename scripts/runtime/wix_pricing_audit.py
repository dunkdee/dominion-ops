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


def amount(value):
    if isinstance(value, dict):
        value = first(value, "amount", "value")
    try:
        return round(float(value), 2)
    except (TypeError, ValueError):
        return None


def price_from_product(product):
    price_range = product.get("actualPriceRange") or product.get("actual_price_range") or {}
    minimum = amount(first(price_range, "minValue", "min", "minimum"))
    maximum = amount(first(price_range, "maxValue", "max", "maximum"))
    if minimum is None and maximum is None:
        direct = amount(first(product, "price", "actualPrice", "actual_price"))
        minimum = maximum = direct
    return minimum, maximum


def query_variants():
    rows = []
    cursor = None
    while True:
        paging = {"limit": 1000}
        if cursor:
            paging["cursor"] = cursor
        response = httpx.post(
            VARIANTS_URL,
            headers={
                "Authorization": wix.WIX_API_KEY,
                "wix-site-id": wix.WIX_SITE_ID,
                "Content-Type": "application/json",
            },
            json={"fields": [], "query": {"cursorPaging": paging}},
            timeout=30.0,
        )
        response.raise_for_status()
        payload = response.json()
        page = payload.get("variants") or []
        rows.extend(item for item in page if isinstance(item, dict))
        metadata = payload.get("pagingMetadata") or {}
        cursors = metadata.get("cursors") or {}
        cursor = cursors.get("next")
        if not metadata.get("hasNext") or not cursor:
            break
    return rows


version = wix.detect_catalog_version()
products = wix.get_all_products(version)
variants = query_variants() if version == "v3" else []
variants_by_product = {}
for variant in variants:
    product_data = variant.get("productData") or {}
    product_id = first(product_data, "productId", "product_id")
    if product_id:
        variants_by_product.setdefault(str(product_id), []).append(variant)

rows = []
for product in products:
    if not isinstance(product, dict):
        continue
    product_id = first(product, "id", "_id")
    minimum, maximum = price_from_product(product)
    product_variants = variants_by_product.get(str(product_id), [])
    variant_prices = []
    for variant in product_variants:
        price = variant.get("price") or {}
        actual = price.get("actualPrice") or price.get("actual_price") or {}
        value = amount(actual)
        if value is not None:
            variant_prices.append(value)
    if variant_prices:
        minimum = min(variant_prices)
        maximum = max(variant_prices)
    rows.append({
        "id": product_id,
        "name": first(product, "name", "title"),
        "slug": first(product, "slug", "urlSlug"),
        "visible": first(product, "visible", "isVisible"),
        "currency": first(product, "currency", "currencyCode") or "USD",
        "current_min_price": minimum,
        "current_max_price": maximum,
        "variant_count": len(product_variants),
        "supplier_cost": None,
        "shipping_cost": None,
        "recommended_price": None,
        "pricing_status": "COST_INPUT_REQUIRED" if minimum is not None else "PRICE_MISSING",
    })

print(json.dumps({
    "generated_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
    "catalog_version": version,
    "product_count": len(rows),
    "variant_count": len(variants),
    "currency_default": "USD",
    "policy": {
        "target_gross_margin": 0.35,
        "price_changes_performed": False,
        "requires_supplier_cost": True,
        "requires_human_approval": True,
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
