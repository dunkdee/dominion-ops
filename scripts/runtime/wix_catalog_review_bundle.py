#!/usr/bin/env python3
"""Create a private, read-only Wix catalog review bundle.

The collector runs inside the existing Wix Agent container so credentials remain on
the VM. The full bundle contains product-side content required for human review:
current descriptions, SEO text, revisions, option labels, and variant SKUs. It
excludes customer/order data, inventory quantities, secret values, environment
values, raw API responses, and raw logs. No Wix mutation endpoint is called.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

WIX_CONTAINER = "wix-agent"
BUNDLE_PATH = Path(os.environ.get("BUNDLE_PATH", "/tmp/wix_catalog_review_bundle.json"))
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


def normalize_text(value):
    if not isinstance(value, str):
        return ""
    return re.sub(r"\s+", " ", value).strip()


def description_text(product):
    return normalize_text(first(product, "plainDescription", "description"))


def description_hash(text):
    return hashlib.sha256(text.lower().encode("utf-8")).hexdigest() if text else None


def seo_fields(product):
    seo_data = product.get("seoData") if isinstance(product.get("seoData"), dict) else {}
    return {
        "title": normalize_text(first(product, "seoTitle") or first(seo_data, "title")),
        "description": normalize_text(first(product, "seoDescription") or first(seo_data, "description")),
    }


def media_facts(product):
    media = product.get("media") if isinstance(product.get("media"), dict) else {}
    items_info = media.get("itemsInfo") if isinstance(media.get("itemsInfo"), dict) else {}
    items = items_info.get("items") if isinstance(items_info.get("items"), list) else []
    return {"count": len(items), "main_present": bool(media.get("main"))}


def option_rows(product):
    options = product.get("options")
    if isinstance(options, dict):
        options = list(options.values())
    if not isinstance(options, list):
        return []
    rows = []
    for option in options:
        if not isinstance(option, dict):
            continue
        choices = first(option, "choices", "values")
        if isinstance(choices, dict):
            choices = list(choices.values())
        if not isinstance(choices, list):
            choices = []
        labels = []
        for choice in choices:
            if isinstance(choice, dict):
                label = first(choice, "name", "label", "value", "description")
            else:
                label = choice
            text = normalize_text(str(label or ""))
            if text:
                labels.append(text)
        rows.append({
            "name": normalize_text(str(first(option, "name", "title", "key") or "")),
            "choices": labels,
        })
    return rows


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
        cursor = (paging.get("cursors") or {}).get("next")
        if not paging.get("hasNext") or not cursor:
            break
    return rows


def variant_product_id(variant):
    return first(variant.get("productData") or {}, "productId", "product_id")


def variant_choices(variant):
    value = first(variant, "choices", "optionChoices", "options")
    if isinstance(value, dict):
        return {str(k): normalize_text(str(v)) for k, v in value.items()}
    return {}


version = wix.detect_catalog_version()
products = wix.get_all_products(version)
variants = query_variants() if version == "v3" else []
variants_by_product = {}
for variant in variants:
    product_id = variant_product_id(variant)
    if product_id:
        variants_by_product.setdefault(str(product_id), []).append(variant)

records = []
groups = {}
for product in products:
    if not isinstance(product, dict):
        continue
    product_id = str(first(product, "id", "_id") or "")
    description = description_text(product)
    digest = description_hash(description)
    if digest:
        groups.setdefault(digest, []).append(product_id)
    brand = first(product, "brand", "brandName")
    if isinstance(brand, dict):
        brand = first(brand, "name", "label", "id")
    product_variants = []
    for variant in variants_by_product.get(product_id, []):
        sku = normalize_text(str(first(variant, "sku", "stockKeepingUnit") or ""))
        product_variants.append({
            "id": first(variant, "id", "_id"),
            "revision": first(variant, "revision", "_revision"),
            "sku": sku,
            "visible": first(variant, "visible", "isVisible"),
            "choices": variant_choices(variant),
        })
    media = media_facts(product)
    seo = seo_fields(product)
    records.append({
        "id": product_id,
        "revision": first(product, "revision", "_revision"),
        "name": normalize_text(str(first(product, "name", "title") or "")),
        "slug": normalize_text(str(first(product, "slug", "urlSlug") or "")),
        "visible": first(product, "visible", "isVisible"),
        "brand": normalize_text(str(brand or "")),
        "current_description": description,
        "description_hash": digest,
        "seo_title": seo["title"],
        "seo_description": seo["description"],
        "media_count": media["count"],
        "main_media_present": media["main_present"],
        "options": option_rows(product),
        "variants": product_variants,
    })

duplicate_groups = []
for digest, product_ids in groups.items():
    if len(product_ids) > 1:
        duplicate_groups.append({"description_hash": digest, "product_ids": sorted(product_ids), "count": len(product_ids)})
duplicate_groups.sort(key=lambda item: (-item["count"], item["description_hash"]))
affected = {product_id for group in duplicate_groups for product_id in group["product_ids"]}

print(json.dumps({
    "catalog_version": version,
    "generated_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
    "summary": {
        "products_total": len(records),
        "variants_total": len(variants),
        "duplicate_description_groups": len(duplicate_groups),
        "duplicate_description_products": len(affected),
        "missing_brand": sum(not item["brand"] for item in records),
        "missing_description": sum(not item["current_description"] for item in records),
        "missing_seo_title": sum(not item["seo_title"] for item in records),
        "missing_seo_description": sum(not item["seo_description"] for item in records),
        "missing_media": sum(item["media_count"] == 0 for item in records),
        "missing_main_media": sum(not item["main_media_present"] for item in records),
        "missing_variant_sku": sum(1 for item in records for variant in item["variants"] if not variant["sku"]),
    },
    "duplicate_description_groups": duplicate_groups,
    "products": records,
}, sort_keys=True))
'''


def command(args: list[str], *, input_text: str | None = None, timeout: int = 300) -> dict[str, Any]:
    try:
        result = subprocess.run(args, input=input_text, check=False, capture_output=True, text=True, timeout=timeout)
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        return {"returncode": None, "stdout": "", "stderr_type": type(exc).__name__}
    return {
        "returncode": result.returncode,
        "stdout": result.stdout or "",
        "stderr_type": None if not result.stderr else "present",
    }


def http_probe(name: str, port: int, path: str) -> dict[str, Any]:
    record = {"name": name, "port": port, "path": path, "reachable": False, "status": None}
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=5) as response:
            response.read(1024)
            record.update({"reachable": True, "status": response.status})
    except urllib.error.HTTPError as exc:
        record.update({"reachable": True, "status": exc.code})
    except Exception as exc:  # noqa: BLE001
        record["error_type"] = type(exc).__name__
    return record


def container_fingerprints() -> dict[str, str]:
    result = command(["docker", "ps", "--all", "--format", "{{.Names}}|{{.ID}}|{{.Image}}|{{.Status}}"], timeout=30)
    rows = {}
    if result["returncode"] == 0:
        for line in result["stdout"].splitlines():
            name, _, _, _ = (line.split("|", 3) + ["", "", "", ""])[:4]
            if name:
                rows[name] = line
    return rows


def main() -> int:
    before = container_fingerprints()
    health_before = [http_probe(*item) for item in PROTECTED_HTTP]
    errors: list[str] = []
    if any(item.get("status") != 200 for item in health_before):
        errors.append("protected_health_failed_before")

    collected = command(["docker", "exec", "-i", WIX_CONTAINER, "python", "-"], input_text=CHILD, timeout=300)
    bundle: dict[str, Any] = {}
    if collected["returncode"] != 0:
        errors.append("review_bundle_collector_failed")
    else:
        try:
            bundle = json.loads(collected["stdout"])
        except json.JSONDecodeError:
            errors.append("review_bundle_parse_failed")

    bundle_meta: dict[str, Any] = {}
    if not errors:
        BUNDLE_PATH.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(bundle, indent=2, sort_keys=True) + "\n"
        BUNDLE_PATH.write_text(payload, encoding="utf-8")
        os.chmod(BUNDLE_PATH, 0o600)
        bundle_meta = {
            "path": str(BUNDLE_PATH),
            "size_bytes": BUNDLE_PATH.stat().st_size,
            "sha256": hashlib.sha256(BUNDLE_PATH.read_bytes()).hexdigest(),
            "mode": oct(BUNDLE_PATH.stat().st_mode & 0o777),
        }

    health_after = [http_probe(*item) for item in PROTECTED_HTTP]
    after = container_fingerprints()
    unchanged = before == after
    if any(item.get("status") != 200 for item in health_after):
        errors.append("protected_health_failed_after")
    if not unchanged:
        errors.append("container_inventory_changed")

    summary = bundle.get("summary") if isinstance(bundle, dict) else {}
    success = not errors and bundle_meta.get("mode") == "0o600"
    report = {
        "alignment_stage": "wix-catalog-review-bundle",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "success" if success else "failed",
        "success": success,
        "catalog_summary": summary,
        "bundle": bundle_meta,
        "protected_health_before": health_before,
        "protected_health_after": health_after,
        "containers_unchanged": unchanged,
        "errors": errors,
        "next_gate": "Draft a review-only revision-safe change set; no Wix mutation without human approval",
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
            "product_content_written_to_private_artifact_only": True,
        },
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
