#!/usr/bin/env python3
"""Create a private, revision-locked Wix duplicate-description proposal.

The collector runs inside the existing Wix Agent container. It reads current Wix V3
product content and produces proposed replacement descriptions only for products
whose normalized descriptions are duplicated. Proposed text is deliberately bounded
to facts visible in the product title and live listing structure. No Wix mutation
endpoint is called. Full proposal content is written only to a private artifact.
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
PROPOSAL_PATH = Path(os.environ.get("PROPOSAL_PATH", "/tmp/wix_catalog_description_proposal.json"))
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

import wix_client as wix


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


def category_sentence(name):
    value = name.lower()
    if any(token in value for token in ("case", "cover", "bumper", "folio", "wallet case")):
        return "Designed as a protective accessory for the device model identified in the product title."
    if any(token in value for token in ("screen protector", "tempered glass", "hydrogel")):
        return "Designed as a screen-protection accessory for the device model identified in the product title."
    if any(token in value for token in ("charger", "charging cable", "usb cable", "lightning cable", "type-c", "usb-c", "cable")):
        return "Intended for charging compatible devices using the connector, length, and power rating stated in the product title."
    if any(token in value for token in ("speaker", "earbud", "headset", "headphone", "karaoke")):
        return "Intended for compatible audio use according to the connection type and features stated in the product title."
    if any(token in value for token in ("mount", "holder", "stand", "docking station")):
        return "Designed to hold a compatible device in the mounting or storage position identified in the product title."
    if any(token in value for token in ("camera", "projector", "drone")):
        return "This listing covers the device and feature set identified in the product title."
    if any(token in value for token in ("memory card", "sd card", "hub", "dock", "drive", "adapter")):
        return "This listing covers the accessory type, capacity, connector, or compatibility identified in the product title."
    return "This listing covers the product and specifications identified in the product title."


def proposed_description(name):
    safe_name = html.escape(normalize(name), quote=False)
    category = category_sentence(name)
    return (
        f"<p><strong>{safe_name}</strong></p>"
        f"<p>{category}</p>"
        "<p>Review the product images, selected option, SKU, and current price on this page to confirm the exact model, color, size, connector, and included components before ordering.</p>"
        "<p>Specifications are limited to the product title, images, and available options. Contact the store before purchase when compatibility is uncertain.</p>"
    )


version = wix.detect_catalog_version()
products = wix.get_all_products(version)
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
    records.append({
        "id": product_id,
        "revision": revision,
        "name": name,
        "current_description_hash": current_hash,
        "current_description_characters": len(current),
        "visible": first(product, "visible", "isVisible"),
    })

by_id = {item["id"]: item for item in records}
duplicate_groups = [
    {"current_description_hash": key, "product_ids": sorted(ids), "count": len(ids)}
    for key, ids in groups.items() if len(ids) > 1
]
duplicate_groups.sort(key=lambda item: (-item["count"], item["current_description_hash"]))

proposal = []
for group in duplicate_groups:
    for product_id in group["product_ids"]:
        item = by_id[product_id]
        proposed = proposed_description(item["name"])
        proposal.append({
            "id": product_id,
            "expected_revision": item["revision"],
            "name": item["name"],
            "visible": item["visible"],
            "current_description_hash": item["current_description_hash"],
            "current_description_characters": item["current_description_characters"],
            "proposed_description": proposed,
            "proposed_description_hash": digest(proposed),
            "proposed_description_characters": len(proposed),
            "reason": "duplicate_description",
            "brand_change_proposed": False,
            "seo_change_proposed": False,
        })

proposed_hashes = [item["proposed_description_hash"] for item in proposal]
validation = {
    "proposal_count": len(proposal),
    "all_product_ids_present": all(item["id"] for item in proposal),
    "all_revisions_present": all(item["expected_revision"] for item in proposal),
    "all_names_present": all(item["name"] for item in proposal),
    "all_current_hashes_present": all(item["current_description_hash"] for item in proposal),
    "all_proposed_hashes_unique": len(proposed_hashes) == len(set(proposed_hashes)),
    "all_proposals_changed": all(item["proposed_description_hash"] != item["current_description_hash"] for item in proposal),
    "all_proposals_bounded": all(250 <= item["proposed_description_characters"] <= 900 for item in proposal),
}

print(json.dumps({
    "catalog_version": version,
    "generated_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
    "summary": {
        "products_total": len(records),
        "duplicate_description_groups": len(duplicate_groups),
        "duplicate_description_products": len(proposal),
        "proposal_count": len(proposal),
        "brand_changes_proposed": 0,
        "seo_changes_proposed": 0,
    },
    "validation": validation,
    "duplicate_groups": duplicate_groups,
    "proposals": proposal,
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

    collected = command(["docker", "exec", "-i", WIX_CONTAINER, "python", "-"], input_text=CHILD, timeout=300)
    proposal: dict[str, Any] = {}
    if collected["returncode"] != 0:
        errors.append("description_proposal_collector_failed")
    else:
        try:
            proposal = json.loads(collected["stdout"])
        except json.JSONDecodeError:
            errors.append("description_proposal_parse_failed")

    validation = proposal.get("validation") if isinstance(proposal, dict) else {}
    required_checks = (
        "all_product_ids_present",
        "all_revisions_present",
        "all_names_present",
        "all_current_hashes_present",
        "all_proposed_hashes_unique",
        "all_proposals_changed",
        "all_proposals_bounded",
    )
    if not all(validation.get(key) is True for key in required_checks):
        errors.append("description_proposal_validation_failed")

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
        "alignment_stage": "wix-catalog-description-proposal",
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
        "next_gate": "Human review of private proposal; no Wix mutation is authorized",
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
