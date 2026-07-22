#!/usr/bin/env python3
"""Create a private, product-specific Wix description proposal without mutations.

The collector runs inside the existing Wix Agent container. It reads live Wix V3
product and variant metadata, identifies products sharing normalized descriptions,
and creates revision-locked replacement copy from exact title facts and live variant
counts. No Wix write endpoint is called. Full proposal content is written only to a
private artifact.
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
PROPOSAL_PATH = Path(
    os.environ.get("PROPOSAL_PATH", "/tmp/wix_catalog_description_proposal_v2.json")
)
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
import html
import json
import re

import httpx
import wix_client as wix

VARIANTS_URL = "https://www.wixapis.com/stores/v3/products/query-variants"

SPEC_PATTERNS = (
    r"\b\d+(?:\.\d+)?\s?(?:mAh|MB/s|GB|TB|W|A|V|ft|feet|inch(?:es)?|in|mm|P|K|Hz)\b",
    r"\b(?:Bluetooth|BT)\s*\d+(?:\.\d+)?\b",
    r"\bWi-?Fi\s*\d+(?:\.\d+)?\b",
    r"\bUSB\s*\d+(?:\.\d+)?\b",
    r"\bIP\d{2}\b",
    r"\bPD\s*\d+\s?W\b",
    r"\b(?:USB-C|USB A|USB-A|Type-C|Lightning|8\s?Pin|Micro USB|Thunderbolt\s*3)\b",
    r"\b(?:TWS|UHS-I|C10|U1|Full HD|HD720P|1080P|4K|FM Radio|TF Card)\b",
    r"\b(?:Night Vision|Motion Detection|Activity Alert|LED Flashlight|Dual USB|4 in 1|5 USB Port|2-In-1|Over-Ear|Ear Hook|Ring Stand|Card Holder|Waterproof|Solar|Rechargeable|Tempered Glass|Hydrogel|Nylon Braided|Braided|Magnetic|Adjustable)\b",
)

BANNED_GENERATED_PHRASES = (
    "guaranteed",
    "best in class",
    "premium quality",
    "perfect for everyone",
    "indestructible",
    "shockproof",
    "drop protection",
    "scratch resistant",
    "lasts for hours",
)


def first(mapping, *keys):
    if not isinstance(mapping, dict):
        return None
    for key in keys:
        value = mapping.get(key)
        if value is not None:
            return value
    return None


def normalize(value):
    if not isinstance(value, str):
        return ""
    return re.sub(r"\s+", " ", value).strip()


def digest(value):
    text = normalize(value).lower()
    return hashlib.sha256(text.encode("utf-8")).hexdigest() if text else None


def description_text(product):
    return normalize(first(product, "plainDescription", "description"))


def query_variants():
    rows = []
    cursor = None
    while True:
        cursor_paging = {"limit": 1000}
        if cursor:
            cursor_paging["cursor"] = cursor
        response = httpx.post(
            VARIANTS_URL,
            headers={
                "Authorization": wix.WIX_API_KEY,
                "wix-site-id": wix.WIX_SITE_ID,
                "Content-Type": "application/json",
            },
            json={"fields": [], "query": {"cursorPaging": cursor_paging}},
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


def category_for(name):
    value = name.lower()
    if any(token in value for token in ("screen protector", "tempered glass", "hydrogel")):
        return "screen_protector"
    if any(token in value for token in ("case", "cover", "bumper", "folio")):
        return "case"
    if any(token in value for token in ("power bank", "battery backup")):
        return "power_bank"
    if any(token in value for token in ("charger", "charging cable", "usb cable", "lightning cable", "type-c", "usb-c", "cable")):
        return "charging"
    if any(token in value for token in ("speaker", "earbud", "headset", "headphone", "karaoke")):
        return "audio"
    if any(token in value for token in ("camera", "endoscope")):
        return "camera"
    if any(token in value for token in ("memory card", "sd card", "r4i")):
        return "storage"
    if any(token in value for token in ("mount", "holder", "stand", "docking station")):
        return "mount"
    if any(token in value for token in ("dvd drive", "cd dvd", "external drive")):
        return "optical_drive"
    return "general"


def exact_title_facts(name):
    facts = []
    lowered = set()
    for pattern in SPEC_PATTERNS:
        for match in re.finditer(pattern, name, re.IGNORECASE):
            value = normalize(match.group(0))
            key = value.lower()
            if value and key not in lowered:
                facts.append(value)
                lowered.add(key)
    return facts


def intro_sentence(name, category):
    safe_name = html.escape(name, quote=False)
    templates = {
        "charging": f"The power, connector, and cable combination named in <strong>{safe_name}</strong> defines this charging accessory.",
        "case": f"<strong>{safe_name}</strong> pairs the device fit named in the title with the stated case style or finish.",
        "screen_protector": f"<strong>{safe_name}</strong> is listed for the device and protector format identified in the product title.",
        "power_bank": f"<strong>{safe_name}</strong> is a portable power product with the capacity and charging features stated in the title.",
        "audio": f"<strong>{safe_name}</strong> is an audio product built around the connection and playback features stated in the title.",
        "camera": f"<strong>{safe_name}</strong> is a camera product with the resolution, connection, or inspection features stated in the title.",
        "storage": f"<strong>{safe_name}</strong> is a storage or gaming accessory with the capacity, speed, or compatibility stated in the title.",
        "mount": f"<strong>{safe_name}</strong> is a holder or stand for the device types and placement described in the title.",
        "optical_drive": f"<strong>{safe_name}</strong> is an external optical-drive product with the connection and computer compatibility stated in the title.",
        "general": f"<strong>{safe_name}</strong> is offered in the exact configuration identified by the product title.",
    }
    return templates[category]


def proposed_description(name, category, facts, variant_count):
    detail = ", ".join(html.escape(item, quote=False) for item in facts[:8])
    if not detail:
        detail = "the model, format, and compatibility named in the title"
    configuration = "configuration" if variant_count == 1 else "configurations"
    return (
        f"<p>{intro_sentence(name, category)}</p>"
        "<ul>"
        f"<li><strong>Listing details:</strong> {detail}.</li>"
        f"<li><strong>Selection:</strong> This product currently has {variant_count} listed SKU {configuration}; choose the option that matches the intended device, size, color, or connector.</li>"
        "</ul>"
        "<p>Use the product images and option selector to verify fit, finish, included components, and compatibility before checkout. Contact the store when any listing detail is unclear.</p>"
    )


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
    revision = str(first(product, "revision", "_revision") or "")
    name = normalize(str(first(product, "name", "title") or ""))
    current = description_text(product)
    current_hash = digest(current)
    if current_hash:
        groups.setdefault(current_hash, []).append(product_id)
    product_variants = variants_by_product.get(product_id, [])
    sku_count = sum(
        1
        for item in product_variants
        if normalize(str(first(item, "sku", "stockKeepingUnit") or ""))
    )
    records.append(
        {
            "id": product_id,
            "revision": revision,
            "name": name,
            "current_description_hash": current_hash,
            "current_description_characters": len(current),
            "visible": first(product, "visible", "isVisible"),
            "variant_count": len(product_variants),
            "sku_count": sku_count,
        }
    )

by_id = {item["id"]: item for item in records}
duplicate_groups = [
    {"current_description_hash": key, "product_ids": sorted(ids), "count": len(ids)}
    for key, ids in groups.items()
    if len(ids) > 1
]
duplicate_groups.sort(key=lambda item: (-item["count"], item["current_description_hash"]))

proposal = []
for group in duplicate_groups:
    for product_id in group["product_ids"]:
        item = by_id[product_id]
        category = category_for(item["name"])
        facts = exact_title_facts(item["name"])
        proposed = proposed_description(
            item["name"], category, facts, item["variant_count"]
        )
        proposal.append(
            {
                "id": product_id,
                "expected_revision": item["revision"],
                "name": item["name"],
                "visible": item["visible"],
                "current_description_hash": item["current_description_hash"],
                "current_description_characters": item["current_description_characters"],
                "category": category,
                "exact_title_facts": facts,
                "variant_count": item["variant_count"],
                "sku_count": item["sku_count"],
                "proposed_description": proposed,
                "proposed_description_hash": digest(proposed),
                "proposed_description_characters": len(proposed),
                "reason": "duplicate_description_quality_v2",
                "brand_change_proposed": False,
                "seo_change_proposed": False,
            }
        )

proposed_hashes = [item["proposed_description_hash"] for item in proposal]
category_counts = {}
for item in proposal:
    category_counts[item["category"]] = category_counts.get(item["category"], 0) + 1

validation = {
    "quality_version": 2,
    "proposal_count": len(proposal),
    "all_product_ids_present": all(item["id"] for item in proposal),
    "all_revisions_present": all(item["expected_revision"] for item in proposal),
    "all_names_present": all(item["name"] for item in proposal),
    "all_current_hashes_present": all(item["current_description_hash"] for item in proposal),
    "all_proposed_hashes_unique": len(proposed_hashes) == len(set(proposed_hashes)),
    "all_proposals_changed": all(item["proposed_description_hash"] != item["current_description_hash"] for item in proposal),
    "all_proposals_bounded": all(350 <= item["proposed_description_characters"] <= 900 for item in proposal),
    "all_titles_embedded": all(html.escape(item["name"], quote=False) in item["proposed_description"] for item in proposal),
    "all_variant_counts_positive": all(item["variant_count"] > 0 for item in proposal),
    "all_variant_skus_present": all(item["sku_count"] == item["variant_count"] for item in proposal),
    "unsupported_generated_phrases_absent": all(
        not any(phrase in item["proposed_description"].lower() for phrase in BANNED_GENERATED_PHRASES)
        for item in proposal
    ),
}

print(
    json.dumps(
        {
            "catalog_version": version,
            "generated_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
            "summary": {
                "quality_version": 2,
                "products_total": len(records),
                "duplicate_description_groups": len(duplicate_groups),
                "duplicate_description_products": len(proposal),
                "proposal_count": len(proposal),
                "variants_total": len(variants),
                "categories": category_counts,
                "brand_changes_proposed": 0,
                "seo_changes_proposed": 0,
            },
            "validation": validation,
            "duplicate_groups": duplicate_groups,
            "proposals": proposal,
        },
        sort_keys=True,
    )
)
'''


def command(
    args: list[str], *, input_text: str | None = None, timeout: int = 300
) -> dict[str, Any]:
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
        return {"returncode": None, "stdout": "", "stderr_type": type(exc).__name__}
    return {
        "returncode": result.returncode,
        "stdout": result.stdout or "",
        "stderr_type": None if not result.stderr else "present",
    }


def http_probe(name: str, port: int, path: str) -> dict[str, Any]:
    record = {
        "name": name,
        "port": port,
        "path": path,
        "reachable": False,
        "status": None,
    }
    try:
        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}{path}", timeout=5
        ) as response:
            response.read(1024)
            record.update({"reachable": True, "status": response.status})
    except urllib.error.HTTPError as exc:
        record.update({"reachable": True, "status": exc.code})
    except Exception as exc:  # noqa: BLE001
        record["error_type"] = type(exc).__name__
    return record


def container_fingerprints() -> dict[str, str]:
    result = command(
        ["docker", "ps", "--all", "--format", "{{.Names}}|{{.ID}}|{{.Image}}|{{.Status}}"],
        timeout=30,
    )
    rows: dict[str, str] = {}
    if result["returncode"] == 0:
        for line in result["stdout"].splitlines():
            name = line.split("|", 1)[0]
            if name:
                rows[name] = line
    return rows


def main() -> int:
    before = container_fingerprints()
    health_before = [http_probe(*item) for item in PROTECTED_HTTP]
    errors: list[str] = []
    if any(item.get("status") != 200 for item in health_before):
        errors.append("protected_health_failed_before")

    collected = command(
        ["docker", "exec", "-i", WIX_CONTAINER, "python", "-"],
        input_text=CHILD,
        timeout=360,
    )
    proposal: dict[str, Any] = {}
    if collected["returncode"] != 0:
        errors.append("description_proposal_v2_collector_failed")
    else:
        try:
            proposal = json.loads(collected["stdout"])
        except json.JSONDecodeError:
            errors.append("description_proposal_v2_parse_failed")

    validation = proposal.get("validation") if isinstance(proposal, dict) else {}
    required_checks = (
        "all_product_ids_present",
        "all_revisions_present",
        "all_names_present",
        "all_current_hashes_present",
        "all_proposed_hashes_unique",
        "all_proposals_changed",
        "all_proposals_bounded",
        "all_titles_embedded",
        "all_variant_counts_positive",
        "all_variant_skus_present",
        "unsupported_generated_phrases_absent",
    )
    if validation.get("quality_version") != 2 or not all(
        validation.get(key) is True for key in required_checks
    ):
        errors.append("description_proposal_v2_validation_failed")

    proposal_meta: dict[str, Any] = {}
    if not errors:
        PROPOSAL_PATH.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(proposal, indent=2, sort_keys=True) + "\n"
        PROPOSAL_PATH.write_text(payload, encoding="utf-8")
        os.chmod(PROPOSAL_PATH, 0o600)
        proposal_meta = {
            "path": str(PROPOSAL_PATH),
            "size_bytes": PROPOSAL_PATH.stat().st_size,
            "sha256": hashlib.sha256(PROPOSAL_PATH.read_bytes()).hexdigest(),
            "mode": oct(PROPOSAL_PATH.stat().st_mode & 0o777),
        }

    health_after = [http_probe(*item) for item in PROTECTED_HTTP]
    after = container_fingerprints()
    unchanged = before == after
    if any(item.get("status") != 200 for item in health_after):
        errors.append("protected_health_failed_after")
    if not unchanged:
        errors.append("container_inventory_changed")

    summary = proposal.get("summary") if isinstance(proposal, dict) else {}
    success = not errors and proposal_meta.get("mode") == "0o600"
    report = {
        "alignment_stage": "wix-catalog-description-proposal-v2",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "success" if success else "failed",
        "success": success,
        "proposal_summary": summary,
        "validation": validation,
        "proposal": proposal_meta,
        "protected_health_before": health_before,
        "protected_health_after": health_after,
        "containers_unchanged": unchanged,
        "errors": errors,
        "next_gate": "Human quality review of private V2 proposal; no Wix mutation is authorized",
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
            "full_proposal_written_to_private_artifact_only": True,
            "brand_changes_proposed": False,
            "seo_changes_proposed": False,
        },
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
