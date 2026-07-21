#!/usr/bin/env python3
"""Trace what can reactivate retired systemd units without changing runtime state.

The report contains systemd metadata, executable/file paths, hashes, matched unit
names, and line numbers. It never emits matched source lines, environment values,
logs, customer data, or secret values.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

RETIRED = (
    "alchemist-api.service",
    "conductor-api.service",
    "juris-api.service",
)

MONITORS = (
    "dominion-guardian.service",
    "dominion-sentinel.service",
    "dominion-monitor.service",
    "dominion-healthcheck.service",
    "dominion-watchdog.service",
    "dominion-executor.service",
    "dominion-port-healer.service",
    "dominion-n8n-watchdog.service",
    "conductor-scheduler.service",
    "conductor-worker.service",
)

SCAN_ROOTS = (
    Path("/etc/systemd/system"),
    Path("/lib/systemd/system"),
    Path("/usr/lib/systemd/system"),
    Path("/etc/cron.d"),
    Path("/etc/cron.daily"),
    Path("/etc/cron.hourly"),
    Path("/etc/cron.weekly"),
    Path("/home/malachisingleton8/buddy_core"),
    Path("/home/malachisingleton8/conductor"),
    Path("/home/malachisingleton8/dominion"),
    Path("/usr/local/bin"),
    Path("/opt/dominion"),
)

ALLOWED_SUFFIXES = {
    ".py", ".sh", ".service", ".timer", ".socket", ".target",
    ".conf", ".cfg", ".ini", ".toml", ".yaml", ".yml", ".txt",
}
SKIP_PARTS = {
    ".git", "node_modules", "__pycache__", ".venv", "venv",
    "vault", "secrets", "private", "certs", "keys",
}
MAX_FILES = 6000
MAX_BYTES = 1024 * 1024


def run(args: list[str], timeout: int = 30) -> dict[str, Any]:
    """Run a read-only command and return bounded metadata."""
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


def words(value: str) -> list[str]:
    return sorted(set(filter(None, re.split(r"\s+", value.strip()))))


def executables(value: str) -> list[str]:
    matches = re.findall(r"(?:^|[;{ ])path=([^ ;}]+)", value or "")
    if not matches:
        matches = re.findall(r"argv\[\]=([^ ;}]+)", value or "")
    return sorted(set(matches))


def systemd_record(unit: str) -> dict[str, Any]:
    """Return non-secret systemd ownership and dependency metadata."""
    properties = (
        "LoadState,ActiveState,SubState,UnitFileState,NRestarts,Restart,"
        "RestartUSec,FragmentPath,SourcePath,Triggers,TriggeredBy,Wants,"
        "Requires,PartOf,BindsTo,Conflicts,OnFailure,ExecStart,MainPID"
    )
    result = run(["systemctl", "show", unit, f"--property={properties}"])
    record: dict[str, Any] = {
        "unit": unit,
        "load_state": None,
        "active_state": None,
        "sub_state": None,
        "unit_file_state": None,
        "n_restarts": None,
        "restart": None,
        "restart_usec": None,
        "fragment_path": None,
        "source_path": None,
        "triggers": [],
        "triggered_by": [],
        "wants": [],
        "requires": [],
        "part_of": [],
        "binds_to": [],
        "conflicts": [],
        "on_failure": [],
        "executables": [],
        "main_pid": None,
        "reverse_dependencies": [],
    }
    field_map = {
        "LoadState": "load_state",
        "ActiveState": "active_state",
        "SubState": "sub_state",
        "UnitFileState": "unit_file_state",
        "Restart": "restart",
        "RestartUSec": "restart_usec",
        "FragmentPath": "fragment_path",
        "SourcePath": "source_path",
    }
    list_map = {
        "Triggers": "triggers",
        "TriggeredBy": "triggered_by",
        "Wants": "wants",
        "Requires": "requires",
        "PartOf": "part_of",
        "BindsTo": "binds_to",
        "Conflicts": "conflicts",
        "OnFailure": "on_failure",
    }
    if result["returncode"] == 0:
        for line in result["stdout"].splitlines():
            key, _, value = line.partition("=")
            if key in field_map:
                record[field_map[key]] = value or None
            elif key in list_map:
                record[list_map[key]] = words(value)
            elif key == "NRestarts":
                record["n_restarts"] = safe_int(value)
            elif key == "MainPID":
                record["main_pid"] = safe_int(value)
            elif key == "ExecStart":
                record["executables"] = executables(value)

    reverse = run([
        "systemctl", "list-dependencies", "--reverse", "--plain",
        "--no-pager", unit,
    ])
    if reverse["returncode"] == 0:
        dependencies = []
        for raw in reverse["stdout"].splitlines():
            normalized = raw.strip().lstrip("●").strip()
            if normalized and normalized != unit and " " not in normalized:
                dependencies.append(normalized)
        record["reverse_dependencies"] = sorted(set(dependencies))
    return record


def container_snapshot() -> list[dict[str, Any]]:
    result = run(["docker", "ps", "--all", "--format", "{{json .}}"])
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


def eligible(path: Path) -> bool:
    try:
        resolved = path.resolve()
        stat = resolved.stat()
    except (OSError, RuntimeError):
        return False
    if not resolved.is_file() or path.is_symlink() or stat.st_size > MAX_BYTES:
        return False
    if {part.lower() for part in resolved.parts} & SKIP_PARTS:
        return False
    name = resolved.name.lower()
    if name in {".env", "environment", "credentials", "authorized_keys"}:
        return False
    if any(token in name for token in ("secret", "private_key", "id_rsa", "id_ed25519")):
        return False
    cron_parent = resolved.parent in {
        Path("/etc/cron.d"), Path("/etc/cron.daily"),
        Path("/etc/cron.hourly"), Path("/etc/cron.weekly"),
    }
    return resolved.suffix.lower() in ALLOWED_SUFFIXES or cron_parent or resolved.parent == Path("/usr/local/bin")


def scan_file(path: Path) -> dict[str, Any] | None:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return None
    matches: dict[str, list[int]] = {}
    lines = text.splitlines()
    for token in RETIRED:
        numbers = [index for index, line in enumerate(lines, start=1) if token in line]
        if numbers:
            matches[token] = numbers[:100]
    if not matches:
        return None
    return {
        "path": str(path),
        "sha256": sha256_file(path),
        "size_bytes": path.stat().st_size,
        "matches": matches,
    }


def main() -> int:
    before = container_snapshot()
    all_units = RETIRED + MONITORS
    records = {unit: systemd_record(unit) for unit in all_units}

    candidate_paths: set[Path] = set()
    for record in records.values():
        for key in ("fragment_path", "source_path"):
            if record.get(key):
                candidate_paths.add(Path(record[key]))
        candidate_paths.update(Path(item) for item in record.get("executables", []))

    scanned: set[Path] = set()
    matches: list[dict[str, Any]] = []

    def inspect(path: Path) -> None:
        if len(scanned) >= MAX_FILES or path in scanned or not eligible(path):
            return
        scanned.add(path)
        result = scan_file(path)
        if result:
            matches.append(result)

    for path in sorted(candidate_paths, key=str):
        inspect(path)

    for root in SCAN_ROOTS:
        if len(scanned) >= MAX_FILES or not root.exists():
            continue
        if root.is_file():
            inspect(root)
            continue
        for current, dirs, files in os.walk(root):
            dirs[:] = [name for name in dirs if name.lower() not in SKIP_PARTS]
            for name in files:
                inspect(Path(current) / name)
                if len(scanned) >= MAX_FILES:
                    break
            if len(scanned) >= MAX_FILES:
                break

    crontab_matches = []
    crontab = run(["crontab", "-l"])
    if crontab["returncode"] == 0:
        lines = crontab["stdout"].splitlines()
        for token in RETIRED:
            numbers = [index for index, line in enumerate(lines, start=1) if token in line]
            if numbers:
                crontab_matches.append({
                    "source": "user_crontab",
                    "matched_unit": token,
                    "line_numbers": numbers[:100],
                })

    after = container_snapshot()
    unchanged = before == after
    payload = {
        "alignment_stage": "2D-R-trace",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "success" if unchanged else "failed",
        "success": unchanged,
        "retired_units": {unit: records[unit] for unit in RETIRED},
        "monitor_units": {unit: records[unit] for unit in MONITORS},
        "candidate_file_matches": sorted(matches, key=lambda row: row["path"]),
        "user_crontab_matches": crontab_matches,
        "scan_summary": {
            "files_scanned": len(scanned),
            "max_files": MAX_FILES,
            "max_file_bytes": MAX_BYTES,
            "roots_considered": [str(path) for path in SCAN_ROOTS],
            "candidate_paths_considered": sorted(str(path) for path in candidate_paths),
        },
        "containers_unchanged": unchanged,
        "before_containers": before,
        "after_containers": after,
        "safety": {
            "services_changed": False,
            "timers_changed": False,
            "cron_changed": False,
            "production_containers_changed": False,
            "databases_changed": False,
            "dns_changed": False,
            "repositories_changed": False,
            "file_contents_collected": False,
            "file_contents_scanned_locally_for_retired_unit_names": True,
            "environment_values_collected": False,
            "logs_collected": False,
            "secret_values_collected": False,
        },
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if unchanged else 1


if __name__ == "__main__":
    raise SystemExit(main())
