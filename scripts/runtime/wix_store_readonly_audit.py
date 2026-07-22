#!/usr/bin/env python3
"""Audit the live Wix store without mutating Wix or production state.

The script reads the current production Wix Agent health/readiness endpoints and
executes the repository's read-only catalog audit inside the existing container.
Only aggregate order counts are reported. Customer data, order identifiers,
secret values, environment contents, and raw logs are never emitted.
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


def command(args: list[str], timeout: int = 180) -> dict[str, Any]:
    """Run a bounded command and retain output locally for parsing only."""
    try:
        result = subprocess.run(
            args,
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


def http_json(port: int, path: str) -> dict[str, Any]:
    """Fetch a local JSON endpoint without including response headers."""
    record: dict[str, Any] = {
        "port": port,
        "path": path,
        "reachable": False,
        "status": None,
        "json": None,
    }
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=10) as response:
            raw = response.read(1024 * 1024)
            record.update(
                {
                    "reachable": True,
                    "status": response.status,
                    "json": json.loads(raw.decode("utf-8")),
                }
            )
    except urllib.error.HTTPError as exc:
        raw = exc.read(1024 * 1024)
        payload = None
        try:
            payload = json.loads(raw.decode("utf-8"))
        except Exception:
            payload = None
        record.update({"reachable": True, "status": exc.code, "json": payload})
    except Exception as exc:  # noqa: BLE001 - report only exception class
        record["error_type"] = type(exc).__name__
    return record


def http_status(name: str, port: int, path: str) -> dict[str, Any]:
    """Return only bounded health status for protected services."""
    result = http_json(port, path)
    return {
        "name": name,
        "port": port,
        "path": path,
        "reachable": result.get("reachable"),
        "status": result.get("status"),
    }


def container_identity(name: str) -> dict[str, Any]:
    """Return sanitized identity and state for one container."""
    result = command(["docker", "inspect", name], timeout=30)
    if result["returncode"] != 0:
        return {"name": name, "exists": False}
    try:
        data = json.loads(result["stdout"])[0]
    except (json.JSONDecodeError, IndexError):
        return {"name": name, "exists": False, "parse_failed": True}
    state = data.get("State") or {}
    config = data.get("Config") or {}
    labels = config.get("Labels") or {}
    return {
        "name": name,
        "exists": True,
        "container_id": data.get("Id"),
        "image_id": data.get("Image"),
        "image_reference": config.get("Image"),
        "running": bool(state.get("Running")),
        "state": state.get("Status"),
        "health": (state.get("Health") or {}).get("Status"),
        "restart_count": state.get("RestartCount"),
        "compose_project": labels.get("com.docker.compose.project"),
        "compose_service": labels.get("com.docker.compose.service"),
    }


def live_store_audit() -> dict[str, Any]:
    """Execute only read-only Wix API calls inside the current container."""
    code = r'''
import json
import main
import store_setup as store
import wix_client as wix

catalog_version = main._catalog_version()
store_audit = store.audit_store(catalog_version)
unfulfilled_orders = wix.get_orders(fulfillment_status="NOT_FULFILLED")
print(json.dumps({
    "catalog_version": catalog_version,
    "store_audit": store_audit,
    "orders": {
        "unfulfilled_count": len(unfulfilled_orders),
        "details_collected": False,
    },
}, sort_keys=True))
'''
    result = command(["docker", "exec", WIX_CONTAINER, "python", "-c", code], timeout=180)
    if result["returncode"] != 0:
        return {
            "success": False,
            "error": "container_read_only_audit_failed",
            "stderr_type": result.get("stderr_type"),
        }
    lines = [line for line in result["stdout"].splitlines() if line.strip()]
    for line in reversed(lines):
        try:
            payload = json.loads(line)
            return {"success": True, **payload}
        except json.JSONDecodeError:
            continue
    return {"success": False, "error": "audit_json_missing"}


def main() -> int:
    generated_at = datetime.now(timezone.utc).isoformat()
    wix_before = container_identity(WIX_CONTAINER)
    protected_before = [http_status(*item) for item in PROTECTED_HTTP]
    health = http_json(8082, "/health")
    readiness = http_json(8082, "/ready")
    catalog = live_store_audit()
    wix_after = container_identity(WIX_CONTAINER)
    protected_after = [http_status(*item) for item in PROTECTED_HTTP]

    errors: list[str] = []
    if not wix_before.get("running"):
        errors.append("production_wix_not_running_before")
    if health.get("status") != 200:
        errors.append("production_wix_health_failed")
    if readiness.get("status") != 200:
        errors.append("production_wix_readiness_failed")
    if not catalog.get("success"):
        errors.append(str(catalog.get("error") or "catalog_audit_failed"))
    if wix_before != wix_after:
        errors.append("production_wix_identity_changed")
    if any(item.get("status") != 200 for item in protected_before):
        errors.append("protected_health_failed_before")
    if any(item.get("status") != 200 for item in protected_after):
        errors.append("protected_health_failed_after")

    readiness_json = readiness.get("json") if isinstance(readiness.get("json"), dict) else {}
    health_json = health.get("json") if isinstance(health.get("json"), dict) else {}
    payload = {
        "alignment_stage": "wix-store-read-only-audit",
        "generated_at": generated_at,
        "status": "success" if not errors else "failed",
        "success": not errors,
        "production_wix": wix_after,
        "store": {
            "health_status": health.get("status"),
            "readiness_status": readiness.get("status"),
            "service_status": health_json.get("status"),
            "version": health_json.get("version"),
            "ready": readiness_json.get("ready"),
            "blockers": readiness_json.get("blockers", []),
            "database": readiness_json.get("database"),
            "catalog": readiness_json.get("catalog"),
            "fulfillment": readiness_json.get("fulfillment"),
            "integrations_configured": readiness_json.get("integrations"),
            "catalog_audit": catalog,
        },
        "protected_health_before": protected_before,
        "protected_health_after": protected_after,
        "errors": errors,
        "manual_verification_still_required": [
            "published storefront pages and navigation",
            "business contact identity shown to customers",
            "shipping regions, rates, and delivery estimates",
            "return, refund, warranty, privacy, and terms pages",
            "enabled payment methods and a Wix owner test order",
            "exact supplier facts and fulfillment variant mappings",
        ],
        "safety": {
            "wix_mutations_performed": False,
            "products_changed": False,
            "inventory_changed": False,
            "orders_changed": False,
            "customer_data_collected": False,
            "order_identifiers_collected": False,
            "secret_values_collected": False,
            "environment_values_collected": False,
            "raw_logs_collected": False,
            "containers_changed": False,
            "volumes_changed": False,
            "databases_changed": False,
            "dns_changed": False,
        },
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
