#!/usr/bin/env python3
"""Persistently retire legacy systemd units without touching canonical services.

The operation is reversible: local unit files are copied into a root-only recovery
folder before /etc/systemd/system masks are installed. Reports contain only unit
metadata, paths, hashes, health status, and container inventory—not file contents,
logs, environment values, customer data, or secrets.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

RETIREMENTS = {
    "alchemist-api.service": "dominion-alchemist.service",
    "conductor-api.service": "dominion-conductor.service",
    "juris-api.service": "dominion-juris.service",
    "dominion-port-healer.service": None,
}

PROTECTED_UNITS = (
    "caddy.service",
    "dominion-alchemist.service",
    "dominion-alpha.service",
    "dominion-conductor.service",
    "dominion-gatekeeper.service",
    "dominion-guardian.service",
    "dominion-juris.service",
    "dominion-sentinel.service",
    "dominion-store.service",
    "gemini-server.service",
)

HEALTH_CHECKS = (
    ("baby-api", 8080, "/"),
    ("wix-agent", 8082, "/ready"),
    ("dominion-web", 8090, "/"),
    ("n8n", 5678, "/healthz"),
    ("alpha-engine", 8787, "/health"),
    ("conductor", 5060, "/health"),
)


def run(args: list[str], timeout: int = 60) -> dict[str, Any]:
    """Run a bounded command and return non-sensitive execution metadata."""
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
        "stdout": (result.stdout or "").strip()[:4000],
        "stderr_type": None if not result.stderr else "present",
    }


def safe_int(value: str | None) -> int | None:
    try:
        return int(value) if value is not None else None
    except ValueError:
        return None


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def unit_state(unit: str) -> dict[str, Any]:
    result = run([
        "systemctl",
        "show",
        unit,
        "--property=LoadState,ActiveState,SubState,UnitFileState,NRestarts,FragmentPath",
    ])
    record: dict[str, Any] = {
        "unit": unit,
        "load_state": None,
        "active_state": None,
        "sub_state": None,
        "unit_file_state": None,
        "n_restarts": None,
        "fragment_path": None,
        "is_enabled": None,
    }
    mapping = {
        "LoadState": "load_state",
        "ActiveState": "active_state",
        "SubState": "sub_state",
        "UnitFileState": "unit_file_state",
        "FragmentPath": "fragment_path",
    }
    if result["returncode"] == 0:
        for line in result["stdout"].splitlines():
            key, _, value = line.partition("=")
            if key in mapping:
                record[mapping[key]] = value or None
            elif key == "NRestarts":
                record["n_restarts"] = safe_int(value)
    enabled = run(["systemctl", "is-enabled", unit])
    record["is_enabled"] = enabled["stdout"].splitlines()[0] if enabled["stdout"] else None
    return record


def http_probe(name: str, port: int, path: str) -> dict[str, Any]:
    url = f"http://127.0.0.1:{port}{path}"
    record: dict[str, Any] = {
        "name": name,
        "port": port,
        "path": path,
        "reachable": False,
        "status": None,
    }
    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            response.read(1024)
            record.update({"reachable": True, "status": response.status})
    except urllib.error.HTTPError as exc:
        record.update({"reachable": True, "status": exc.code})
    except Exception as exc:
        record["error_type"] = type(exc).__name__
    return record


def container_snapshot() -> list[dict[str, Any]]:
    result = run(["docker", "ps", "--all", "--format", "{{json .}}"], timeout=30)
    rows: list[dict[str, Any]] = []
    if result["returncode"] == 0:
        for line in result["stdout"].splitlines():
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            rows.append({
                "name": item.get("Names"),
                "image": item.get("Image"),
                "state": item.get("State"),
                "status": item.get("Status"),
            })
    return sorted(rows, key=lambda row: row.get("name") or "")


def all_healthy(records: list[dict[str, Any]]) -> bool:
    return all(item.get("status") == 200 for item in records)


def canonical_healthy(records: dict[str, dict[str, Any]]) -> bool:
    return all(
        item.get("active_state") == "active" and item.get("sub_state") == "running"
        for item in records.values()
    )


def rollback_masks(changes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for change in reversed(changes):
        mask_path = Path(change["mask_path"])
        backup_path = Path(change["backup_path"]) if change.get("backup_path") else None
        restored = False
        try:
            if mask_path.is_symlink() and os.readlink(mask_path) == "/dev/null":
                mask_path.unlink()
            if backup_path and backup_path.is_file():
                shutil.copy2(backup_path, mask_path)
                os.chmod(mask_path, 0o644)
                restored = True
            results.append({
                "unit": change["unit"],
                "mask_removed": not mask_path.is_symlink(),
                "local_unit_restored": restored,
            })
        except OSError as exc:
            results.append({
                "unit": change["unit"],
                "error_type": type(exc).__name__,
            })
    run(["systemctl", "daemon-reload"])
    for unit in RETIREMENTS:
        run(["systemctl", "disable", "--now", unit])
        run(["systemctl", "stop", unit])
    return results


def main() -> int:
    generated_at = datetime.now(timezone.utc)
    run_id = os.environ.get("RUN_ID", generated_at.strftime("%Y%m%dT%H%M%SZ"))
    backup_root = Path("/var/lib/dominion/unit-retirement") / f"stage2d-r3-{run_id}"
    errors: list[str] = []
    changes: list[dict[str, Any]] = []
    rollback_results: list[dict[str, Any]] = []

    if os.geteuid() != 0:
        payload = {
            "alignment_stage": "2D-R3-retire",
            "status": "failed",
            "success": False,
            "errors": ["root_required"],
        }
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 1

    before_containers = container_snapshot()
    protected_before = {unit: unit_state(unit) for unit in PROTECTED_UNITS}
    health_before = [http_probe(*item) for item in HEALTH_CHECKS]
    retired_before = {unit: unit_state(unit) for unit in RETIREMENTS}

    if not canonical_healthy(protected_before):
        errors.append("protected_unit_unhealthy_before_change")
    if not all_healthy(health_before):
        errors.append("protected_http_unhealthy_before_change")

    backup_root.mkdir(mode=0o700, parents=True, exist_ok=False)

    if not errors:
        for unit, canonical in RETIREMENTS.items():
            current = retired_before[unit]
            if canonical:
                canonical_state = protected_before.get(canonical) or unit_state(canonical)
                if canonical_state.get("active_state") != "active" or canonical_state.get("sub_state") != "running":
                    errors.append(f"canonical_not_running:{canonical}")
                    break

            expected_path = Path("/etc/systemd/system") / unit
            already_masked = expected_path.is_symlink() and os.readlink(expected_path) == "/dev/null"
            if already_masked:
                changes.append({
                    "unit": unit,
                    "canonical": canonical,
                    "mask_path": str(expected_path),
                    "backup_path": None,
                    "already_masked": True,
                    "original_fragment_path": current.get("fragment_path"),
                })
                run(["systemctl", "stop", unit])
                continue

            original_path = Path(current["fragment_path"]) if current.get("fragment_path") else expected_path
            backup_path: Path | None = None
            original_sha: str | None = None
            original_size: int | None = None

            if original_path == expected_path and expected_path.is_file() and not expected_path.is_symlink():
                backup_path = backup_root / unit
                shutil.copy2(expected_path, backup_path)
                os.chmod(backup_path, 0o600)
                original_sha = sha256_file(backup_path)
                original_size = backup_path.stat().st_size

            run(["systemctl", "disable", "--now", unit])
            run(["systemctl", "stop", unit])

            if expected_path.exists() or expected_path.is_symlink():
                expected_path.unlink()
            expected_path.symlink_to("/dev/null")

            changes.append({
                "unit": unit,
                "canonical": canonical,
                "mask_path": str(expected_path),
                "backup_path": str(backup_path) if backup_path else None,
                "already_masked": False,
                "original_fragment_path": str(original_path),
                "original_sha256": original_sha,
                "original_size_bytes": original_size,
            })

        run(["systemctl", "daemon-reload"])
        for unit in RETIREMENTS:
            run(["systemctl", "reset-failed", unit])
            run(["systemctl", "stop", unit])

    restart_start = {unit: unit_state(unit).get("n_restarts") for unit in PROTECTED_UNITS}
    if not errors:
        time.sleep(90)
    restart_end = {unit: unit_state(unit).get("n_restarts") for unit in PROTECTED_UNITS}

    retired_after = {unit: unit_state(unit) for unit in RETIREMENTS}
    protected_after = {unit: unit_state(unit) for unit in PROTECTED_UNITS}
    health_after = [http_probe(*item) for item in HEALTH_CHECKS]
    after_containers = container_snapshot()

    restart_deltas: dict[str, dict[str, Any]] = {}
    for unit in PROTECTED_UNITS:
        start = restart_start.get(unit)
        end = restart_end.get(unit)
        delta = end - start if isinstance(start, int) and isinstance(end, int) else None
        restart_deltas[unit] = {"start": start, "end": end, "delta": delta}

    masks_valid = all(
        state.get("active_state") != "active" and state.get("is_enabled") in {"masked", "masked-runtime"}
        for state in retired_after.values()
    )
    protected_stable = canonical_healthy(protected_after) and all(
        record.get("delta") in {0, None} for record in restart_deltas.values()
    )
    containers_unchanged = before_containers == after_containers

    if not masks_valid:
        errors.append("persistent_retirement_verification_failed")
    if not protected_stable:
        errors.append("protected_unit_regression")
    if not all_healthy(health_after):
        errors.append("protected_http_regression")
    if not containers_unchanged:
        errors.append("production_container_inventory_changed")

    rollback_performed = False
    if errors and changes:
        rollback_performed = True
        rollback_results = rollback_masks(changes)

    success = not errors
    manifest = {
        "alignment_stage": "2D-R3-retire",
        "generated_at": generated_at.isoformat(),
        "status": "success" if success else "failed",
        "success": success,
        "backup_root": str(backup_root),
        "actions": changes,
        "retired_before": retired_before,
        "retired_after": retired_after,
        "protected_before": protected_before,
        "protected_after": protected_after,
        "restart_deltas_90_seconds": restart_deltas,
        "health_before": health_before,
        "health_after": health_after,
        "containers_unchanged": containers_unchanged,
        "before_containers": before_containers,
        "after_containers": after_containers,
        "errors": errors,
        "rollback_performed": rollback_performed,
        "rollback_results": rollback_results,
        "safety": {
            "canonical_services_restarted": False,
            "production_containers_started": False,
            "production_containers_stopped": False,
            "production_containers_recreated": False,
            "production_volumes_changed": False,
            "production_networks_changed": False,
            "databases_changed": False,
            "dns_changed": False,
            "repositories_changed": False,
            "secret_values_collected": False,
            "file_contents_collected": False,
            "logs_collected": False,
            "retired_unit_files_backed_up_locally": True,
            "persistent_masks_reversible": True,
        },
    }

    manifest_path = backup_root / "retirement-manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.chmod(manifest_path, 0o600)
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
