#!/usr/bin/env python3
"""Map Wix published site and product URLs without mutations or secret disclosure."""
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
SAMPLE_SLUGS = (
    "esoulk-black-18w-pd-charger-amp-usb-a-3ft-c-to-iphone-cable",
    "samsung-s10e-triangle-package-case",
    "portable-wireless-bluetooth-speaker-with-tws-function-rechargeable-bluetooth-s",
)

CHILD = r'''
import json
from urllib.parse import quote
import httpx
import wix_client as wix

headers = {
    "Authorization": wix.WIX_API_KEY,
    "wix-site-id": wix.WIX_SITE_ID,
    "Content-Type": "application/json",
}
slugs = json.loads(input()).get("slugs") or []
errors = []
urls = []
site = {}
products = []
try:
    response = httpx.get(
        "https://www.wixapis.com/urls-server/v2/published-site-urls",
        headers=headers,
        timeout=30.0,
    )
    response.raise_for_status()
    payload = response.json() or {}
    for item in payload.get("urls") or []:
        if not isinstance(item, dict) or not item.get("url"):
            continue
        urls.append({
            "url": str(item.get("url")),
            "primary": item.get("primary") is True,
            "url_type": item.get("urlType"),
            "language_code": ((item.get("multilingualInfo") or {}).get("languageCode")),
            "default_language": ((item.get("multilingualInfo") or {}).get("defaultLanguage")) is True,
        })
except Exception as exc:
    errors.append({"operation": "list_published_site_urls", "error_type": type(exc).__name__})
try:
    response = httpx.get(
        "https://www.wixapis.com/site-properties/v4/properties",
        headers=headers,
        timeout=30.0,
    )
    response.raise_for_status()
    props = (response.json() or {}).get("properties") or {}
    site = {
        "site_display_name": props.get("siteDisplayName"),
        "business_name": props.get("businessName"),
        "description_present": bool(props.get("description")),
        "contact_email_present": bool(props.get("email")),
        "contact_phone_present": bool(props.get("phone")),
        "language": props.get("language"),
        "payment_currency": props.get("paymentCurrency"),
        "time_zone": props.get("timeZone"),
    }
except Exception as exc:
    errors.append({"operation": "get_site_properties", "error_type": type(exc).__name__})
for slug in slugs:
    row = {"requested_slug": slug, "found": False, "public_url": None, "visible": None}
    try:
        response = httpx.get(
            f"https://www.wixapis.com/stores/v3/products/slug/{quote(slug, safe='')}",
            headers=headers,
            params=[("fields", "URL")],
            timeout=30.0,
        )
        response.raise_for_status()
        product = (response.json() or {}).get("product") or {}
        page_url = product.get("url")
        if isinstance(page_url, dict):
            page_url = page_url.get("url") or page_url.get("relativePath")
        row.update({
            "found": bool(product.get("id")),
            "id": product.get("id"),
            "name": product.get("name"),
            "slug": product.get("slug"),
            "visible": product.get("visible"),
            "public_url": page_url,
        })
    except Exception as exc:
        row["error_type"] = type(exc).__name__
    products.append(row)
print(json.dumps({"published_urls": urls, "site": site, "products": products, "errors": errors}, sort_keys=True))
'''


def command(args: list[str], *, input_text: str | None = None, timeout: int = 300) -> dict[str, Any]:
    try:
        result = subprocess.run(args, input=input_text, capture_output=True, text=True, check=False, timeout=timeout)
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        return {"returncode": None, "stdout": "", "stderr_type": type(exc).__name__}
    return {
        "returncode": result.returncode,
        "stdout": result.stdout or "",
        "stderr_type": None if not result.stderr else "present",
    }


def http_probe(name: str, port: int, path: str) -> dict[str, Any]:
    row: dict[str, Any] = {"name": name, "port": port, "path": path, "reachable": False, "status": None}
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=5) as response:
            response.read(1024)
            row.update({"reachable": True, "status": response.status})
    except urllib.error.HTTPError as exc:
        row.update({"reachable": True, "status": exc.code})
    except Exception as exc:  # noqa: BLE001
        row["error_type"] = type(exc).__name__
    return row


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
    collected = command(
        ["docker", "exec", "-i", WIX_CONTAINER, "python", "-c", CHILD],
        input_text=json.dumps({"slugs": SAMPLE_SLUGS}),
        timeout=300,
    )
    routing: dict[str, Any] = {}
    if collected["returncode"] != 0:
        errors.append("wix_routing_collector_failed")
    else:
        try:
            routing = json.loads(collected["stdout"])
        except json.JSONDecodeError:
            errors.append("wix_routing_parse_failed")
    after = container_fingerprints()
    health_after = [http_probe(*item) for item in PROTECTED_HTTP]
    unchanged = before == after
    if any(item.get("status") != 200 for item in health_after):
        errors.append("protected_health_failed_after")
    if not unchanged:
        errors.append("container_inventory_changed")
    published = routing.get("published_urls") or []
    product_urls = [item for item in routing.get("products") or [] if item.get("public_url")]
    if not published:
        errors.append("no_published_wix_url_returned")
    if not product_urls:
        errors.append("no_public_product_urls_returned")
    primary = next((item.get("url") for item in published if item.get("primary")), None)
    success = not errors
    report = {
        "alignment_stage": "wix-published-routing-map",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "success" if success else "failed",
        "success": success,
        "primary_url": primary,
        "routing": routing,
        "protected_health_before": health_before,
        "protected_health_after": health_after,
        "containers_unchanged": unchanged,
        "errors": errors,
        "next_gate": "Use returned Wix public URLs for storefront navigation; do not construct Wix product URLs on dominionhealing.org",
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
            "databases_changed": False,
            "networks_changed": False,
            "volumes_changed": False,
            "dns_changed": False,
        },
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
