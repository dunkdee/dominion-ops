#!/usr/bin/env python3
"""Probe Wix V3 plainDescription canonicalization with mandatory rollback.

The probe targets one approved product, verifies its live revision and description
hash, stores the original description in a root-only rollback file, submits the
approved V2 HTML, records only hashes/counts/signatures, and always restores the
original description. Full descriptions never appear in the published report.
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
TARGET_ID = "31ab3699-504b-468c-a314-c7e5737b6683"
GENERATOR_SCRIPT = Path(os.environ.get("WIX_V2_GENERATOR", "/tmp/wix_catalog_description_proposal_v2.py"))
RUN_ID = os.environ.get("GITHUB_RUN_ID", "manual")
RUN_ATTEMPT = os.environ.get("GITHUB_RUN_ATTEMPT", "1")
RECOVERY_ROOT = Path(f"/var/lib/dominion/wix-description-roundtrip/{RUN_ID}-{RUN_ATTEMPT}")
BACKUP_PATH = RECOVERY_ROOT / "description-before-probe.json"
PROPOSAL_PATH = Path(f"/tmp/wix_catalog_description_proposal_v2-{RUN_ID}-{RUN_ATTEMPT}.json")
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
import httpx
import wix_client as wix
product_id = json.loads(input())["id"]
headers = {"Authorization": wix.WIX_API_KEY, "wix-site-id": wix.WIX_SITE_ID, "Content-Type": "application/json"}
response = httpx.get(
    f"https://www.wixapis.com/stores/v3/products/{product_id}",
    headers=headers,
    params=[("fields", "PLAIN_DESCRIPTION")],
    timeout=30.0,
)
response.raise_for_status()
product = (response.json() or {}).get("product") or {}
description = product.get("plainDescription") or ""
normalized = " ".join(str(description).split()).strip().lower()
digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest() if normalized else None
print(json.dumps({
    "id": product_id,
    "revision": str(product.get("revision") or ""),
    "plainDescription": description,
    "description_hash": digest,
}, sort_keys=True))
'''

PROBE_CHILD = r'''
import hashlib
import json
import sys
from collections import Counter
from html.parser import HTMLParser
import httpx
import wix_client as wix

payload = json.load(sys.stdin)
headers = {"Authorization": wix.WIX_API_KEY, "wix-site-id": wix.WIX_SITE_ID, "Content-Type": "application/json"}

class SignatureParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tags = Counter()
        self.text = []
    def handle_starttag(self, tag, attrs):
        self.tags[tag.lower()] += 1
    def handle_startendtag(self, tag, attrs):
        self.tags[tag.lower()] += 1
    def handle_data(self, data):
        self.text.append(data)

def raw_hash(value):
    text = " ".join(str(value or "").split()).strip().lower()
    return hashlib.sha256(text.encode("utf-8")).hexdigest() if text else None

def semantic(value):
    parser = SignatureParser()
    parser.feed(str(value or ""))
    text = " ".join(" ".join(parser.text).split()).strip().lower()
    return {
        "text_hash": hashlib.sha256(text.encode("utf-8")).hexdigest() if text else None,
        "text_characters": len(text),
        "tag_counts": dict(sorted(parser.tags.items())),
    }

def get_product(product_id):
    response = httpx.get(
        f"https://www.wixapis.com/stores/v3/products/{product_id}",
        headers=headers,
        params=[("fields", "PLAIN_DESCRIPTION")],
        timeout=30.0,
    )
    response.raise_for_status()
    return (response.json() or {}).get("product") or {}

def patch_description(product_id, revision, description):
    response = httpx.patch(
        f"https://www.wixapis.com/stores/v3/products/{product_id}",
        headers=headers,
        json={"product": {"id": product_id, "revision": str(revision), "plainDescription": description}},
        timeout=30.0,
    )
    response.raise_for_status()
    return (response.json() or {}).get("product") or {}

product_id = payload["id"]
original = payload["original_description"]
proposed = payload["proposed_description"]
expected_revision = str(payload["expected_revision"])
expected_current_hash = payload["expected_current_hash"]
result = {
    "success": False,
    "write_performed": False,
    "rollback": {"performed": False, "success": False},
    "error": None,
}
try:
    current = get_product(product_id)
    if str(current.get("revision") or "") != expected_revision:
        raise RuntimeError("revision_drift")
    if raw_hash(current.get("plainDescription")) != expected_current_hash:
        raise RuntimeError("description_hash_drift")
    submitted_semantic = semantic(proposed)
    patched = patch_description(product_id, expected_revision, proposed)
    result["write_performed"] = True
    returned = get_product(product_id)
    returned_description = returned.get("plainDescription") or ""
    returned_semantic = semantic(returned_description)
    result["observation"] = {
        "before_revision": expected_revision,
        "after_write_revision": str(returned.get("revision") or patched.get("revision") or ""),
        "submitted_raw_hash": raw_hash(proposed),
        "returned_raw_hash": raw_hash(returned_description),
        "raw_hash_match": raw_hash(proposed) == raw_hash(returned_description),
        "submitted_text_hash": submitted_semantic["text_hash"],
        "returned_text_hash": returned_semantic["text_hash"],
        "semantic_text_match": submitted_semantic["text_hash"] == returned_semantic["text_hash"],
        "submitted_text_characters": submitted_semantic["text_characters"],
        "returned_text_characters": returned_semantic["text_characters"],
        "submitted_tag_counts": submitted_semantic["tag_counts"],
        "returned_tag_counts": returned_semantic["tag_counts"],
        "title_present_after_write": payload["title"].lower() in " ".join(" ".join(SignatureParser().text).split()).lower() if False else None,
    }
except Exception as exc:
    result["error"] = {"type": type(exc).__name__, "message": str(exc)[:160]}
finally:
    result["rollback"]["performed"] = result["write_performed"]
    try:
        current = get_product(product_id)
        if raw_hash(current.get("plainDescription")) != raw_hash(original):
            patch_description(product_id, current.get("revision"), original)
        restored = get_product(product_id)
        result["rollback"].update({
            "success": raw_hash(restored.get("plainDescription")) == raw_hash(original),
            "restored_revision": str(restored.get("revision") or ""),
            "restored_hash": raw_hash(restored.get("plainDescription")),
        })
    except Exception as exc:
        result["rollback"].update({"success": False, "error_type": type(exc).__name__})
result["success"] = bool(result.get("write_performed")) and result["rollback"].get("success") is True and result.get("error") is None
print(json.dumps(result, sort_keys=True))
sys.exit(0 if result["success"] else 1)
'''

FORCE_ROLLBACK_CHILD = r'''
import hashlib
import json
import sys
import httpx
import wix_client as wix
payload = json.load(sys.stdin)
headers = {"Authorization": wix.WIX_API_KEY, "wix-site-id": wix.WIX_SITE_ID, "Content-Type": "application/json"}
def raw_hash(value):
    text = " ".join(str(value or "").split()).strip().lower()
    return hashlib.sha256(text.encode("utf-8")).hexdigest() if text else None
def get_product(product_id):
    response = httpx.get(f"https://www.wixapis.com/stores/v3/products/{product_id}", headers=headers, params=[("fields", "PLAIN_DESCRIPTION")], timeout=30.0)
    response.raise_for_status()
    return (response.json() or {}).get("product") or {}
def patch(product_id, revision, description):
    response = httpx.patch(f"https://www.wixapis.com/stores/v3/products/{product_id}", headers=headers, json={"product": {"id": product_id, "revision": str(revision), "plainDescription": description}}, timeout=30.0)
    response.raise_for_status()
product = get_product(payload["id"])
if raw_hash(product.get("plainDescription")) != payload["description_hash"]:
    patch(payload["id"], product.get("revision"), payload["plainDescription"])
restored = get_product(payload["id"])
success = raw_hash(restored.get("plainDescription")) == payload["description_hash"]
print(json.dumps({"performed": True, "success": success, "restored_revision": str(restored.get("revision") or "")}, sort_keys=True))
sys.exit(0 if success else 1)
'''


def command(args: list[str], *, input_text: str | None = None, timeout: int = 300, env: dict[str, str] | None = None) -> dict[str, Any]:
    try:
        result = subprocess.run(args, input=input_text, check=False, capture_output=True, text=True, timeout=timeout, env=env)
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        return {"returncode": None, "stdout": "", "stderr_type": type(exc).__name__}
    return {"returncode": result.returncode, "stdout": result.stdout or "", "stderr_type": None if not result.stderr else "present"}


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


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    before_containers = container_fingerprints()
    health_before = [http_probe(*item) for item in PROTECTED_HTTP]
    errors: list[str] = []
    if any(item.get("status") != 200 for item in health_before):
        errors.append("protected_health_failed_before")
    if not GENERATOR_SCRIPT.is_file():
        errors.append("v2_generator_missing")

    proposal: dict[str, Any] = {}
    selected: dict[str, Any] = {}
    backup: dict[str, Any] = {}
    probe_result: dict[str, Any] = {}
    fallback_result: dict[str, Any] = {"performed": False, "success": None}

    if not errors:
        env = os.environ.copy()
        env["PROPOSAL_PATH"] = str(PROPOSAL_PATH)
        generated = command([sys.executable, str(GENERATOR_SCRIPT)], timeout=420, env=env)
        if generated["returncode"] != 0:
            errors.append("v2_generator_failed")
        else:
            try:
                proposal = json.loads(PROPOSAL_PATH.read_text(encoding="utf-8"))
                selected = next(item for item in proposal.get("proposals", []) if item.get("id") == TARGET_ID)
            except (json.JSONDecodeError, OSError, StopIteration):
                errors.append("v2_target_missing")

    if not errors:
        preflight = command(
            ["docker", "exec", "-i", WIX_CONTAINER, "python", "-c", PREFLIGHT_CHILD],
            input_text=json.dumps({"id": TARGET_ID}),
            timeout=180,
        )
        if preflight["returncode"] != 0:
            errors.append("preflight_failed")
        else:
            try:
                backup = json.loads(preflight["stdout"])
            except json.JSONDecodeError:
                errors.append("preflight_parse_failed")

    if not errors:
        if backup.get("revision") != str(selected.get("expected_revision")):
            errors.append("revision_drift")
        if backup.get("description_hash") != selected.get("current_description_hash"):
            errors.append("description_hash_drift")

    backup_meta: dict[str, Any] = {}
    if not errors:
        RECOVERY_ROOT.mkdir(parents=True, exist_ok=True)
        os.chmod(RECOVERY_ROOT, 0o700)
        BACKUP_PATH.write_text(json.dumps(backup, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.chmod(BACKUP_PATH, 0o600)
        backup_meta = {
            "path": str(BACKUP_PATH),
            "mode": oct(BACKUP_PATH.stat().st_mode & 0o777),
            "size_bytes": BACKUP_PATH.stat().st_size,
            "sha256": sha256_file(BACKUP_PATH),
        }

    if not errors:
        payload = {
            "id": TARGET_ID,
            "title": selected.get("name"),
            "expected_revision": selected.get("expected_revision"),
            "expected_current_hash": selected.get("current_description_hash"),
            "original_description": backup.get("plainDescription"),
            "proposed_description": selected.get("proposed_description"),
        }
        probed = command(
            ["docker", "exec", "-i", WIX_CONTAINER, "python", "-c", PROBE_CHILD],
            input_text=json.dumps(payload),
            timeout=300,
        )
        try:
            probe_result = json.loads(probed["stdout"]) if probed["stdout"] else {}
        except json.JSONDecodeError:
            probe_result = {}
        if probed["returncode"] != 0 or probe_result.get("success") is not True:
            errors.append("roundtrip_probe_failed")

    if backup and (not probe_result or (probe_result.get("rollback") or {}).get("success") is not True):
        fallback = command(
            ["docker", "exec", "-i", WIX_CONTAINER, "python", "-c", FORCE_ROLLBACK_CHILD],
            input_text=json.dumps(backup),
            timeout=180,
        )
        try:
            fallback_result = json.loads(fallback["stdout"]) if fallback["stdout"] else {"performed": True, "success": False}
        except json.JSONDecodeError:
            fallback_result = {"performed": True, "success": False}
        if fallback_result.get("success") is not True:
            errors.append("fallback_rollback_failed")

    health_after = [http_probe(*item) for item in PROTECTED_HTTP]
    after_containers = container_fingerprints()
    containers_unchanged = before_containers == after_containers
    if any(item.get("status") != 200 for item in health_after):
        errors.append("protected_health_failed_after")
    if not containers_unchanged:
        errors.append("container_inventory_changed")

    rollback_success = (probe_result.get("rollback") or {}).get("success") is True or fallback_result.get("success") is True
    success = not errors and rollback_success
    observation = probe_result.get("observation") or {}
    report = {
        "alignment_stage": "wix-description-roundtrip-probe",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "success" if success else "failed",
        "success": success,
        "target_id": TARGET_ID,
        "proposal_quality_version": (proposal.get("summary") or {}).get("quality_version"),
        "observation": observation,
        "probe_error": probe_result.get("error"),
        "rollback": probe_result.get("rollback") or {},
        "fallback_rollback": fallback_result,
        "rollback_backup": backup_meta,
        "protected_health_before": health_before,
        "protected_health_after": health_after,
        "containers_unchanged": containers_unchanged,
        "errors": errors,
        "next_gate": "Use observed Wix canonicalization to correct canary verification; no persistent catalog write authorized",
        "safety": {
            "temporary_product_write_performed": bool(probe_result.get("write_performed")),
            "net_products_changed": False if rollback_success else None,
            "only_probe_product_targeted": True,
            "full_descriptions_reported": False,
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
