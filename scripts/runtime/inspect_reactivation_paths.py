#!/usr/bin/env python3
"""Inspect suspected retired-unit reactivation paths without changing runtime state.

Only whitelisted systemd directives, redacted process arguments, file paths,
hashes, and matching line numbers are emitted. Environment values, logs,
secret values, and unrelated file contents are excluded.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

RETIRED = (
    "alchemist-api.service",
    "conductor-api.service",
    "juris-api.service",
)

SUSPECT_UNITS = (
    "conductor-scheduler.service",
    "conductor-worker.service",
    "dominion-port-healer.service",
    "dominion-monitor.service",
    "dominion-guardian.service",
    "dominion-sentinel.service",
    "dominion-healthcheck.service",
    "dominion-watchdog.service",
)

SAFE_DIRECTIVES = {
    "Description",
    "After",
    "Before",
    "Wants",
    "Requires",
    "PartOf",
    "BindsTo",
    "Conflicts",
    "OnFailure",
    "ExecStart",
    "ExecStartPre",
    "ExecStartPost",
    "Restart",
    "RestartSec",
    "WorkingDirectory",
    "User",
}

SCAN_ROOTS = (
    Path("/etc/systemd/system"),
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
SENSITIVE_OPTION = re.compile(
    r"^(?:--?(?:api[-_]?key|token|secret|password|passwd|credential|private[-_]?key)|-p)$",
    re.IGNORECASE,
)
SENSITIVE_ASSIGNMENT = re.compile(
    r"(?i)\b([A-Za-z0-9_]*(?:token|secret|password|passwd|api_?key|private_?key)[A-Za-z0-9_]*)=([^\s]+)"
)
URL_CREDENTIALS = re.compile(r"(https?://)[^/@\s]+@", re.IGNORECASE)


def run(args: list[str], timeout: int = 30) -> dict[str, Any]:
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


def sanitize_text(value: str) -> str:
    value = URL_CREDENTIALS.sub(r"\1<redacted>@", value)
    value = SENSITIVE_ASSIGNMENT.sub(lambda match: f"{match.group(1)}=<redacted>", value)
    try:
        tokens = shlex.split(value, posix=True)
    except ValueError:
        tokens = value.split()
    clean: list[str] = []
    redact_next = False
    for token in tokens:
        if redact_next:
            clean.append("<redacted>")
            redact_next = False
            continue
        if SENSITIVE_OPTION.match(token):
            clean.append(token)
            redact_next = True
            continue
        if any(marker in token.lower() for marker in ("token=", "secret=", "password=", "passwd=", "api_key=", "apikey=")):
            key = token.split("=", 1)[0]
            clean.append(f"{key}=<redacted>")
            continue
        clean.append(token)
    return " ".join(clean)[:4000]


def systemd_state(unit: str) -> dict[str, Any]:
    props = run([
        "systemctl", "show", unit,
        "--property=LoadState,ActiveState,SubState,UnitFileState,NRestarts,MainPID,FragmentPath",
    ])
    record: dict[str, Any] = {
        "unit": unit,
        "load_state": None,
        "active_state": None,
        "sub_state": None,
        "unit_file_state": None,
        "n_restarts": None,
        "main_pid": None,
        "fragment_path": None,
    }
    mapping = {
        "LoadState": "load_state",
        "ActiveState": "active_state",
        "SubState": "sub_state",
        "UnitFileState": "unit_file_state",
        "FragmentPath": "fragment_path",
    }
    if props["returncode"] == 0:
        for line in props["stdout"].splitlines():
            key, _, value = line.partition("=")
            if key in mapping:
                record[mapping[key]] = value or None
            elif key == "NRestarts":
                record["n_restarts"] = safe_int(value)
            elif key == "MainPID":
                record["main_pid"] = safe_int(value)
    return record


def whitelisted_directives(path: Path) -> list[dict[str, Any]]:
    if not path.is_file() or path.is_symlink() or path.stat().st_size > MAX_BYTES:
        return []
    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError:
        return []
    rows: list[dict[str, Any]] = []
    for number, raw in enumerate(lines, start=1):
        stripped = raw.strip()
        if not stripped or stripped.startswith(("#", ";")) or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        if key not in SAFE_DIRECTIVES:
            continue
        rows.append({
            "line": number,
            "directive": key,
            "value": sanitize_text(value),
            "mentions_retired_unit": any(unit in value for unit in RETIRED),
            "mentions_port_healer": "port_healer" in value.lower(),
        })
    return rows


def process_cmdline(pid: int | None) -> dict[str, Any] | None:
    if not pid or pid <= 0:
        return None
    path = Path("/proc") / str(pid) / "cmdline"
    try:
        raw = path.read_bytes()
    except OSError:
        return None
    text = " ".join(part.decode("utf-8", errors="ignore") for part in raw.split(b"\0") if part)
    return {
        "pid": pid,
        "command": sanitize_text(text),
        "mentions_retired_unit": any(unit in text for unit in RETIRED),
        "mentions_port_healer": "port_healer" in text.lower(),
    }


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


def reference_matches(path: Path) -> dict[str, Any] | None:
    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError:
        return None
    rows: list[dict[str, Any]] = []
    for number, line in enumerate(lines, start=1):
        lower = line.lower()
        matched = [unit for unit in RETIRED if unit in line]
        if "port_healer.py" in lower:
            matched.append("port_healer.py")
        if not matched:
            continue
        rows.append({
            "line": number,
            "matched": sorted(set(matched)),
            "sanitized": sanitize_text(line.strip()),
        })
        if len(rows) >= 100:
            break
    if not rows:
        return None
    return {
        "path": str(path),
        "sha256": sha256_file(path),
        "size_bytes": path.stat().st_size,
        "matches": rows,
    }


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


def main() -> int:
    before = container_snapshot()
    units: dict[str, Any] = {}
    for unit in SUSPECT_UNITS:
        state = systemd_state(unit)
        fragment = Path(state["fragment_path"]) if state.get("fragment_path") else None
        units[unit] = {
            "state": state,
            "directives": whitelisted_directives(fragment) if fragment else [],
            "process": process_cmdline(state.get("main_pid")),
        }

    scanned: set[Path] = set()
    references: list[dict[str, Any]] = []

    def inspect(path: Path) -> None:
        if len(scanned) >= MAX_FILES or path in scanned or not eligible(path):
            return
        scanned.add(path)
        result = reference_matches(path)
        if result:
            references.append(result)

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

    after = container_snapshot()
    unchanged = before == after
    payload = {
        "alignment_stage": "2D-R2-inspect",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "success" if unchanged else "failed",
        "success": unchanged,
        "suspect_units": units,
        "reference_matches": sorted(references, key=lambda row: row["path"]),
        "scan_summary": {
            "files_scanned": len(scanned),
            "max_files": MAX_FILES,
            "max_file_bytes": MAX_BYTES,
            "roots_considered": [str(path) for path in SCAN_ROOTS],
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
            "environment_values_collected": False,
            "logs_collected": False,
            "secret_values_collected": False,
            "only_whitelisted_directives_collected": True,
            "process_arguments_redacted": True,
        },
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if unchanged else 1


if __name__ == "__main__":
    raise SystemExit(main())
