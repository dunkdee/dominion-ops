#!/usr/bin/env python3
"""Apply a three-product Wix V3 description canary with fail-closed rollback.

The script regenerates the approved V2 proposal from live Wix data, verifies exact
product revisions and current-description hashes, stores a root-only rollback copy,
updates exactly three approved products, verifies the resulting hashes/revisions,
and rolls back every applied change if any gate fails. Full descriptions remain on
the VM and are never printed in the public report.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

WIX_CONTAINER = "wix-agent"
GENERATOR_SCRIPT = Path(os.environ.get("WIX_V2_GENERATOR", "/tmp/wix_catalog_description_proposal_v2.py"))
RUN_ID = os.environ.get("GITHUB_RUN_ID", "manual")
RUN_ATTEMPT = os.environ.get("GITHUB_RUN_ATTEMPT", "1")
ROLLBACK_ROOT = Path(f"/var/lib/dominion/wix-catalog-canary/{RUN_ID}-{RUN_ATTEMPT}")
PROPOSAL_PATH = Path(f"/tmp/wix_catalog_description_proposal_v2-{RUN_ID}-{RUN_ATTEMPT}.json")
CANARY_IDS = (
    "31ab3699-504b-468c-a314-c7e5737b6683",
    "0951cafe-1669-4e01-a8bf-7ca5cdc0e51c",
    "09ecaf7f-9054-48d4-a7c6-9071b872cbd1",
)
PROTECTED_HTTP = (
    ("baby-api", 8080, "/"),
    ("wix-agent", 8082, "/ready"),
    ("dominion-web", 8090, "/"),
    ("n8n", 5678, "/healthz"),
    ("alpha-engine", 8787, "/health"),
    ("conductor", 5060, "/health"),
)

PREFLIGHT_CHILD = r'''
import hashlib
import json
import sys
import httpx
import wix_client as wix
payload = json.load(sys.stdin)
headers = {"Authorization": wix.WIX_API_KEY, "wix-site-id": wix.WIX_SITE_ID, "Content-Type": "application/json"}
rows = []
for item in payload["products"]:
    product_id = item["id"]
    response = httpx.get(f"https://www.wixapis.com/stores/v3/products/{product_id}", headers=headers, params=[("fields", "PLAIN_DESCRIPTION")], timeout=30.0)
    response.raise_for_status()
    product = (response.json() or {}).get("product") or {}
    description = product.get("plainDescription") or ""
    normalized = " ".join(str(description).split()).strip().lower()
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest() if normalized else None
    rows.append({"id": product_id, "revision": str(product.get("revision") or ""), "plainDescription": description, "description_hash": digest, "visible": product.get("visible")})
print(json.dumps({"products": rows}, sort_keys=True))
'''

APPLY_CHILD = r'''
import hashlib
import json
import sys
import httpx
import wix_client as wix
payload = json.load(sys.stdin)
headers = {"Authorization": wix.WIX_API_KEY, "wix-site-id": wix.WIX_SITE_ID, "Content-Type": "application/json"}
def normalized_hash(value):
    text = " ".join(str(value or "").split()).strip().lower()
    return hashlib.sha256(text.encode("utf-8")).hexdigest() if text else None
def get_product(product_id):
    response = httpx.get(f"https://www.wixapis.com/stores/v3/products/{product_id}", headers=headers, params=[("fields", "PLAIN_DESCRIPTION")], timeout=30.0)
    response.raise_for_status()
    return (response.json() or {}).get("product") or {}
def patch_description(product_id, revision, description):
    response = httpx.patch(f"https://www.wixapis.com/stores/v3/products/{product_id}", headers=headers, json={"product": {"id": product_id, "revision": str(revision), "plainDescription": description}}, timeout=30.0)
    response.raise_for_status()
    return (response.json() or {}).get("product") or {}
updated = []
rollback = {"performed": False, "success": True, "restored": [], "errors": []}
error = None
try:
    for item in payload["products"]:
        current = get_product(item["id"])
        if str(current.get("revision") or "") != str(item["expected_revision"]):
            raise RuntimeError(f"revision_drift:{item['id']}")
        if normalized_hash(current.get("plainDescription")) != item["current_description_hash"]:
            raise RuntimeError(f"description_hash_drift:{item['id']}")
        result = patch_description(item["id"], item["expected_revision"], item["proposed_description"])
        update_row = {"id": item["id"], "before_revision": str(item["expected_revision"]), "after_revision": str(result.get("revision") or ""), "proposed_description_hash": item["proposed_description_hash"]}
        updated.append(update_row)
        verified = get_product(item["id"])
        update_row["after_revision"] = str(verified.get("revision") or result.get("revision") or "")
        if normalized_hash(verified.get("plainDescription")) != item["proposed_description_hash"]:
            raise RuntimeError(f"post_write_hash_mismatch:{item['id']}")
        if str(verified.get("revision") or "") == str(item["expected_revision"]):
            raise RuntimeError(f"revision_not_incremented:{item['id']}")
except Exception as exc:
    error = {"type": type(exc).__name__, "message": str(exc)[:200]}
if error:
    rollback["performed"] = True
    backups = {item["id"]: item for item in payload["backups"]}
    for row in reversed(updated):
        product_id = row["id"]
        backup = backups[product_id]
        try:
            current = get_product(product_id)
            patch_description(product_id, current.get("revision"), backup["plainDescription"])
            restored = get_product(product_id)
            if normalized_hash(restored.get("plainDescription")) != backup["description_hash"]:
                raise RuntimeError("rollback_hash_mismatch")
            rollback["restored"].append(product_id)
        except Exception as exc:
            rollback["success"] = False
            rollback["errors"].append({"id": product_id, "type": type(exc).__name__, "message": str(exc)[:160]})
success = error is None and len(updated) == len(payload["products"])
print(json.dumps({"success": success, "updated": updated, "error": error, "rollback": rollback}, sort_keys=True))
sys.exit(0 if success else 1)
'''

ROLLBACK_CHILD = r'''
import hashlib
import json
import sys
import httpx
import wix_client as wix
payload = json.load(sys.stdin)
headers = {"Authorization": wix.WIX_API_KEY, "wix-site-id": wix.WIX_SITE_ID, "Content-Type": "application/json"}
def normalized_hash(value):
    text = " ".join(str(value or "").split()).strip().lower()
    return hashlib.sha256(text.encode("utf-8")).hexdigest() if text else None
def get_product(product_id):
    response = httpx.get(f"https://www.wixapis.com/stores/v3/products/{product_id}", headers=headers, params=[("fields", "PLAIN_DESCRIPTION")], timeout=30.0)
    response.raise_for_status()
    return (response.json() or {}).get("product") or {}
def patch_description(product_id, revision, description):
    response = httpx.patch(f"https://www.wixapis.com/stores/v3/products/{product_id}", headers=headers, json={"product": {"id": product_id, "revision": str(revision), "plainDescription": description}}, timeout=30.0)
    response.raise_for_status()
restored = []
errors = []
for backup in reversed(payload["backups"]):
    try:
        current = get_product(backup["id"])
        if normalized_hash(current.get("plainDescription")) == backup["description_hash"]:
            restored.append(backup["id"])
            continue
        patch_description(backup["id"], current.get("revision"), backup["plainDescription"])
        verified = get_product(backup["id"])
        if normalized_hash(verified.get("plainDescription")) != backup["description_hash"]:
            raise RuntimeError("rollback_hash_mismatch")
        restored.append(backup["id"])
    except Exception as exc:
        errors.append({"id": backup["id"], "type": type(exc).__name__, "message": str(exc)[:160]})
print(json.dumps({"performed": True, "success": not errors, "restored": restored, "errors": errors}, sort_keys=True))
sys.exit(0 if not errors else 1)
'''

def command(args: list[str], *, input_text: str | None = None, timeout: int = 300, env: dict[str, str] | None = None) -> dict[str, Any]:
    try:
        result = subprocess.run(args, input=input_text, check=False, capture_output=True, text=True, timeout=timeout, env=env)
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        return {"returncode": None, "stdout": "", "stderr_type": type(exc).__name__}
    return {"returncode": result.returncode, "stdout": result.stdout or "", "stderr_type": None if not result.stderr else "present"}

def http_probe(name: str, port: int, path: str) -> dict[str, Any]:
    record: dict[str, Any] = {"name": name, "port": port, "path": path, "reachable": False, "status": None}
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=5) as response:
            response.read(1024)
            record.update({"reachable": True, "status": response.status})
    except urllib.error.HTTPError as exc:
        record.update({"reachable": True, "status": exc.code})
    except Exception as exc:
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

def digest_bytes(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main() -> int:
    before_containers = container_fingerprints()
    health_before = [http_probe(*item) for item in PROTECTED_HTTP]
    errors: list[str] = []
    if any(item.get("status") != 200 for item in health_before):
        errors.append("protected_health_failed_before")
    if not GENERATOR_SCRIPT.is_file():
        errors.append("v2_generator_missing")
    proposal_report: dict[str, Any] = {}
    proposal: dict[str, Any] = {}
    selected: list[dict[str, Any]] = []
    backups: list[dict[str, Any]] = []
    apply_result: dict[str, Any] = {}
    rollback_meta: dict[str, Any] = {}
    if not errors:
        env = os.environ.copy()
        env["PROPOSAL_PATH"] = str(PROPOSAL_PATH)
        generated = command([sys.executable, str(GENERATOR_SCRIPT)], timeout=420, env=env)
        if generated["returncode"] != 0:
            errors.append("v2_generator_failed")
        else:
            try:
                proposal_report = json.loads(generated["stdout"])
                proposal = json.loads(PROPOSAL_PATH.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                errors.append("v2_proposal_parse_failed")
    if not errors and (proposal_report.get("success") is not True or (proposal.get("summary") or {}).get("quality_version") != 2):
        errors.append("v2_quality_gate_failed")
    if not errors:
        by_id = {item.get("id"): item for item in proposal.get("proposals", [])}
        missing = [product_id for product_id in CANARY_IDS if product_id not in by_id]
        if missing:
            errors.append("canary_products_missing_from_v2")
        else:
            selected = [by_id[product_id] for product_id in CANARY_IDS]
            if len({item.get("category") for item in selected}) != 3:
                errors.append("canary_category_coverage_failed")
    if not errors:
        preflight = command(["docker", "exec", "-i", WIX_CONTAINER, "python", "-c", PREFLIGHT_CHILD], input_text=json.dumps({"products": [{"id": item["id"]} for item in selected]}), timeout=180)
        if preflight["returncode"] != 0:
            errors.append("canary_preflight_api_failed")
        else:
            try:
                backups = json.loads(preflight["stdout"]).get("products", [])
            except json.JSONDecodeError:
                errors.append("canary_preflight_parse_failed")
    if not errors:
        backup_by_id = {item.get("id"): item for item in backups}
        for item in selected:
            backup = backup_by_id.get(item["id"])
            if not backup:
                errors.append("canary_backup_missing")
                break
            if str(backup.get("revision") or "") != str(item.get("expected_revision") or ""):
                errors.append("canary_revision_drift")
                break
            if backup.get("description_hash") != item.get("current_description_hash"):
                errors.append("canary_description_hash_drift")
                break
    if not errors:
        try:
            ROLLBACK_ROOT.mkdir(parents=True, exist_ok=False)
            os.chmod(ROLLBACK_ROOT, 0o700)
            backup_path = ROLLBACK_ROOT / "descriptions-before-canary.json"
            backup_path.write_text(json.dumps({"products": backups}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            os.chmod(backup_path, 0o600)
            rollback_meta = {"path": str(backup_path), "mode": oct(backup_path.stat().st_mode & 0o777), "size_bytes": backup_path.stat().st_size, "sha256": digest_bytes(backup_path)}
        except OSError:
            errors.append("rollback_backup_create_failed")
    if not errors:
        payload = {"products": selected, "backups": backups}
        applied = command(["docker", "exec", "-i", WIX_CONTAINER, "python", "-c", APPLY_CHILD], input_text=json.dumps(payload), timeout=300)
        try:
            apply_result = json.loads(applied["stdout"])
        except json.JSONDecodeError:
            apply_result = {"success": False, "error": {"type": "ResultParseError"}}
        if applied["returncode"] != 0 or not apply_result.get("success"):
            errors.append("canary_apply_failed")
            if (apply_result.get("rollback") or {}).get("performed") and not (apply_result.get("rollback") or {}).get("success"):
                errors.append("canary_rollback_failed")
    health_after = [http_probe(*item) for item in PROTECTED_HTTP]
    after_containers = container_fingerprints()
    containers_unchanged = before_containers == after_containers
    post_apply_gate_failed = apply_result.get("success") is True and (any(item.get("status") != 200 for item in health_after) or not containers_unchanged)
    if post_apply_gate_failed:
        errors.append("post_apply_gate_failed")
        rolled_back = command(["docker", "exec", "-i", WIX_CONTAINER, "python", "-c", ROLLBACK_CHILD], input_text=json.dumps({"backups": backups}), timeout=300)
        try:
            rollback_result = json.loads(rolled_back["stdout"])
        except json.JSONDecodeError:
            rollback_result = {"performed": True, "success": False, "errors": [{"type": "ResultParseError"}]}
        apply_result["rollback"] = rollback_result
        apply_result["success"] = False
        if rolled_back["returncode"] != 0 or not rollback_result.get("success"):
            errors.append("post_apply_rollback_failed")
        health_after = [http_probe(*item) for item in PROTECTED_HTTP]
        after_containers = container_fingerprints()
        containers_unchanged = before_containers == after_containers
    if any(item.get("status") != 200 for item in health_after):
        errors.append("protected_health_failed_after")
    if not containers_unchanged:
        errors.append("container_inventory_changed")
    success = not errors and apply_result.get("success") is True
    rollback = apply_result.get("rollback") or {}
    report = {
        "alignment_stage": "wix-description-canary-apply",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "success" if success else "failed",
        "success": success,
        "canary_product_ids": list(CANARY_IDS),
        "categories": [item.get("category") for item in selected],
        "updated": apply_result.get("updated", []),
        "rollback": rollback,
        "apply_error": apply_result.get("error"),
        "rollback_backup": rollback_meta,
        "proposal_source": {"quality_version": (proposal.get("summary") or {}).get("quality_version"), "proposal_sha256": digest_bytes(PROPOSAL_PATH) if PROPOSAL_PATH.is_file() else None, "generator_success": proposal_report.get("success")},
        "protected_health_before": health_before,
        "protected_health_after": health_after,
        "containers_unchanged": containers_unchanged,
        "errors": errors,
        "next_gate": "Read-only canary rendering and duplicate-hash verification before any larger rollout",
        "safety": {
            "products_changed": success or (bool(apply_result.get("updated")) and not rollback.get("success")),
            "products_changed_count": len(apply_result.get("updated", [])) if success else 0,
            "only_canary_products_targeted": True,
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
            "full_descriptions_reported": False,
        },
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    try:
        PROPOSAL_PATH.unlink(missing_ok=True)
    except OSError:
        pass
    return 0 if success else 1

if __name__ == "__main__":
    raise SystemExit(main())
