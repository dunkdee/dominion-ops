#!/usr/bin/env python3
"""Deploy reviewed Dominion Healing static files with fail-closed rollback."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

RUN_ID = os.environ.get("GITHUB_RUN_ID", "manual")
RUN_ATTEMPT = os.environ.get("GITHUB_RUN_ATTEMPT", "1")
SOURCE_DIR = Path(os.environ.get("SITE_SOURCE_DIR", "/tmp/dominion-site-hardening-source"))
WEBROOT = Path(os.environ.get("DOMINION_SITE_WEBROOT", str(Path.home() / "aura-ecosystem/agency-website")))
BACKUP_ROOT = Path.home() / ".dominion-recovery" / "site-hardening" / f"{RUN_ID}-{RUN_ATTEMPT}"
FILES = ("index.html", "store.html", "site.css", "shipping.html", "returns.html", "privacy.html", "terms.html")
PUBLIC_CHECKS = (
    ("https://dominionhealing.org/", "About Dominion Healing"),
    ("https://dominionhealing.org/store.html", "Checkout hardening in progress"),
    ("https://dominionhealing.org/site.css", "@media(max-width:700px)"),
    ("https://dominionhealing.org/shipping.html", "Shipping and Digital Delivery"),
    ("https://dominionhealing.org/returns.html", "Returns and Refunds"),
    ("https://dominionhealing.org/privacy.html", "Privacy Policy"),
    ("https://dominionhealing.org/terms.html", "Terms of Use"),
)
PROTECTED_HTTP = (
    ("baby-api", 8080, "/"),
    ("wix-agent", 8082, "/ready"),
    ("dominion-web", 8090, "/"),
    ("n8n", 5678, "/healthz"),
    ("alpha-engine", 8787, "/health"),
    ("conductor", 5060, "/health"),
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def command(args: list[str], timeout: int = 30) -> dict[str, Any]:
    try:
        result = subprocess.run(args, capture_output=True, text=True, check=False, timeout=timeout)
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        return {"returncode": None, "stdout": "", "stderr_type": type(exc).__name__}
    return {"returncode": result.returncode, "stdout": result.stdout or "", "stderr_type": None if not result.stderr else "present"}


def container_fingerprints() -> dict[str, str]:
    result = command(["docker", "ps", "--all", "--format", "{{.Names}}|{{.ID}}|{{.Image}}|{{.Status}}"])
    rows: dict[str, str] = {}
    if result["returncode"] == 0:
        for line in result["stdout"].splitlines():
            name = line.split("|", 1)[0]
            if name:
                rows[name] = line
    return rows


def local_probe(name: str, port: int, path: str) -> dict[str, Any]:
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


def public_probe(url: str, marker: str) -> dict[str, Any]:
    row: dict[str, Any] = {"url": url, "status": None, "marker_present": False}
    cache_busted = f"{url}{'&' if '?' in url else '?'}deploy={RUN_ID}-{RUN_ATTEMPT}"
    last_error = None
    for attempt in range(1, 7):
        try:
            request = urllib.request.Request(cache_busted, headers={"User-Agent": "DominionSiteHardening/1.0"})
            with urllib.request.urlopen(request, timeout=15) as response:
                body = response.read(2_000_000).decode("utf-8", errors="replace")
                row.update({"status": response.status, "marker_present": marker in body, "attempt": attempt})
                if response.status == 200 and marker in body:
                    return row
        except urllib.error.HTTPError as exc:
            row.update({"status": exc.code, "attempt": attempt})
            last_error = type(exc).__name__
        except Exception as exc:  # noqa: BLE001
            row["attempt"] = attempt
            last_error = type(exc).__name__
        time.sleep(3)
    if last_error:
        row["error_type"] = last_error
    return row


def validate_source() -> None:
    for name in FILES:
        path = SOURCE_DIR / name
        if not path.is_file() or path.stat().st_size < 200:
            raise RuntimeError(f"source_missing_or_small:{name}")
    combined = "\n".join((SOURCE_DIR / name).read_text(encoding="utf-8") for name in FILES)
    forbidden = ("STRIPE_BOOK_LINK", "STRIPE_PROTOCOL_LINK", "STRIPE_LEGAL_LINK", "STRIPE_MEMBERSHIP_LINK", "STRIPE_BLUEPRINT_LINK")
    if any(token in combined for token in forbidden):
        raise RuntimeError("unresolved_checkout_placeholder")
    if "no questions asked" in combined.lower():
        raise RuntimeError("unsupported_refund_promise")
    for name in ("index.html", "store.html"):
        text = (SOURCE_DIR / name).read_text(encoding="utf-8")
        if '<meta name="description"' not in text or '<link rel="canonical"' not in text:
            raise RuntimeError(f"metadata_missing:{name}")
    index = (SOURCE_DIR / "index.html").read_text(encoding="utf-8")
    store = (SOURCE_DIR / "store.html").read_text(encoding="utf-8")
    for required in ("/shipping.html", "/returns.html", "/privacy.html", "/terms.html"):
        if required not in index or required not in store:
            raise RuntimeError(f"policy_link_missing:{required}")
    css = (SOURCE_DIR / "site.css").read_text(encoding="utf-8")
    if "@media(max-width:700px)" not in css or "overflow-x:hidden" not in css:
        raise RuntimeError("responsive_css_gate_failed")


def backup_current() -> list[dict[str, Any]]:
    BACKUP_ROOT.mkdir(parents=True, exist_ok=False)
    os.chmod(BACKUP_ROOT, 0o700)
    rows: list[dict[str, Any]] = []
    for name in FILES:
        target = WEBROOT / name
        existed = target.is_file()
        row: dict[str, Any] = {"name": name, "existed_before": existed}
        if existed:
            destination = BACKUP_ROOT / name
            shutil.copy2(target, destination)
            os.chmod(destination, 0o600)
            row.update({"before_sha256": sha256(destination), "before_size": destination.stat().st_size})
        rows.append(row)
    (BACKUP_ROOT / "manifest.json").write_text(json.dumps(rows, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.chmod(BACKUP_ROOT / "manifest.json", 0o600)
    return rows


def install_files(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    WEBROOT.mkdir(parents=True, exist_ok=True)
    by_name = {row["name"]: row for row in rows}
    for name in FILES:
        source = SOURCE_DIR / name
        target = WEBROOT / name
        temporary = WEBROOT / f".{name}.deploy-{RUN_ID}-{RUN_ATTEMPT}"
        shutil.copy2(source, temporary)
        os.chmod(temporary, 0o644)
        os.replace(temporary, target)
        by_name[name].update({"after_sha256": sha256(target), "after_size": target.stat().st_size})
        if by_name[name]["after_sha256"] != sha256(source):
            raise RuntimeError(f"installed_hash_mismatch:{name}")
    return rows


def restore(rows: list[dict[str, Any]]) -> dict[str, Any]:
    restored: list[str] = []
    errors: list[dict[str, str]] = []
    for row in rows:
        name = row["name"]
        target = WEBROOT / name
        try:
            if row.get("existed_before"):
                source = BACKUP_ROOT / name
                temporary = WEBROOT / f".{name}.rollback-{RUN_ID}-{RUN_ATTEMPT}"
                shutil.copy2(source, temporary)
                os.chmod(temporary, 0o644)
                os.replace(temporary, target)
            else:
                target.unlink(missing_ok=True)
            restored.append(name)
        except Exception as exc:  # noqa: BLE001
            errors.append({"name": name, "error_type": type(exc).__name__})
    return {"performed": True, "success": not errors, "restored": restored, "errors": errors}


def main() -> int:
    before_containers = container_fingerprints()
    health_before = [local_probe(*item) for item in PROTECTED_HTTP]
    rows: list[dict[str, Any]] = []
    rollback = {"performed": False, "success": True, "restored": [], "errors": []}
    errors: list[str] = []
    public_after: list[dict[str, Any]] = []
    try:
        if any(item.get("status") != 200 for item in health_before):
            raise RuntimeError("protected_health_failed_before")
        validate_source()
        rows = backup_current()
        install_files(rows)
        public_after = [public_probe(url, marker) for url, marker in PUBLIC_CHECKS]
        if any(item.get("status") != 200 or item.get("marker_present") is not True for item in public_after):
            raise RuntimeError("public_validation_failed")
    except Exception as exc:  # noqa: BLE001
        errors.append(str(exc)[:180])
        if rows:
            rollback = restore(rows)
    after_containers = container_fingerprints()
    health_after = [local_probe(*item) for item in PROTECTED_HTTP]
    containers_unchanged = before_containers == after_containers
    if any(item.get("status") != 200 for item in health_after):
        errors.append("protected_health_failed_after")
        if rows and not rollback.get("performed"):
            rollback = restore(rows)
    if not containers_unchanged:
        errors.append("container_inventory_changed")
        if rows and not rollback.get("performed"):
            rollback = restore(rows)
    success = not errors and len(rows) == len(FILES) and not rollback.get("performed")
    report = {
        "alignment_stage": "dominion-site-hardening-deploy",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "success" if success else "failed",
        "success": success,
        "webroot": str(WEBROOT),
        "files": rows,
        "backup": {
            "path": str(BACKUP_ROOT) if rows else None,
            "mode": oct(BACKUP_ROOT.stat().st_mode & 0o777) if BACKUP_ROOT.exists() else None,
        },
        "public_after": public_after,
        "protected_health_before": health_before,
        "protected_health_after": health_after,
        "containers_unchanged": containers_unchanged,
        "rollback": rollback,
        "errors": errors,
        "next_gate": "Run public desktop/mobile storefront audit and verify contact-form behavior before activating direct checkout links",
        "safety": {
            "site_files_changed": success,
            "site_files_changed_count": len(FILES) if success else 0,
            "only_reviewed_static_files_targeted": True,
            "wix_mutations_performed": False,
            "products_changed": False,
            "inventory_changed": False,
            "orders_changed": False,
            "customer_data_collected": False,
            "order_data_collected": False,
            "secret_values_collected": False,
            "environment_values_collected": False,
            "raw_logs_collected": False,
            "containers_changed": False,
            "databases_changed": False,
            "networks_changed": False,
            "volumes_changed": False,
            "dns_changed": False,
            "caddy_changed": False,
        },
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
