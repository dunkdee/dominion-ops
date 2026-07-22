#!/usr/bin/env python3
"""Diagnose the live Dominion Web container without changing production.

The report contains only sanitized container metadata, bounded error categories,
path existence, HTTP status, and unchanged-container evidence. It never includes
environment values, raw logs, customer data, secret contents, or file contents.
"""

from __future__ import annotations

import json
import subprocess
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

TARGET = "dominion-web"
TARGET_PORT = 8090
OLD_SOURCE_ROOT = Path("/home/malachisingleton8/desktop-tutorial/web")
RELEASE_ROOT = Path("/home/malachisingleton8/dominion-releases/dominion-ops-10646094aa3a")
RELEASE_WEB_ROOT = RELEASE_ROOT / "web"
KNOWN_IMAGES = (
    "desktop-tutorial-dominion-web",
    "dominion-stage2d-r4-dominion-web:latest",
)
PROTECTED_HTTP = (
    ("baby-api", 8080, "/"),
    ("wix-agent", 8082, "/ready"),
    ("n8n", 5678, "/healthz"),
    ("alpha-engine", 8787, "/health"),
    ("conductor", 5060, "/health"),
)


def command(args: list[str], timeout: int = 60) -> dict[str, Any]:
    """Run a bounded read-only command and keep output local to this process."""
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
            "stderr": "",
            "stderr_type": type(exc).__name__,
        }
    return {
        "available": True,
        "returncode": result.returncode,
        "stdout": (result.stdout or "").strip(),
        "stderr": (result.stderr or "").strip(),
        "stderr_type": None if not result.stderr else "present",
    }


def http_probe(name: str, port: int, path: str) -> dict[str, Any]:
    record: dict[str, Any] = {
        "name": name,
        "port": port,
        "path": path,
        "reachable": False,
        "status": None,
    }
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=5) as response:
            response.read(1024)
            record.update({"reachable": True, "status": response.status})
    except urllib.error.HTTPError as exc:
        record.update({"reachable": True, "status": exc.code})
    except Exception as exc:  # noqa: BLE001 - only the exception class is reported
        record["error_type"] = type(exc).__name__
    return record


def inspect_container(name: str) -> dict[str, Any]:
    result = command(["docker", "inspect", name])
    if result["returncode"] != 0:
        return {"name": name, "exists": False}
    try:
        data = json.loads(result["stdout"])[0]
    except (json.JSONDecodeError, IndexError):
        return {"name": name, "exists": True, "parse_failed": True}

    state = data.get("State") or {}
    config = data.get("Config") or {}
    host = data.get("HostConfig") or {}
    networks = (data.get("NetworkSettings") or {}).get("Networks") or {}
    labels = config.get("Labels") or {}
    return {
        "name": name,
        "exists": True,
        "container_id": data.get("Id"),
        "image_id": data.get("Image"),
        "image_reference": config.get("Image"),
        "state": state.get("Status"),
        "running": bool(state.get("Running")),
        "health": (state.get("Health") or {}).get("Status"),
        "exit_code": state.get("ExitCode"),
        "oom_killed": bool(state.get("OOMKilled")),
        "restart_count": data.get("RestartCount"),
        "started_at": state.get("StartedAt"),
        "finished_at": state.get("FinishedAt"),
        "restart_policy": (host.get("RestartPolicy") or {}).get("Name"),
        "compose_project": labels.get("com.docker.compose.project"),
        "compose_service": labels.get("com.docker.compose.service"),
        "compose_config_files": labels.get("com.docker.compose.project.config_files"),
        "ports": sorted(
            [
                {
                    "container_port": container_port,
                    "host_ip": binding.get("HostIp"),
                    "host_port": binding.get("HostPort"),
                }
                for container_port, bindings in ((data.get("NetworkSettings") or {}).get("Ports") or {}).items()
                for binding in (bindings or [])
            ],
            key=lambda item: (item.get("host_port") or "", item.get("container_port") or ""),
        ),
        "networks": sorted(
            [
                {
                    "name": network_name,
                    "network_id": details.get("NetworkID"),
                    "aliases": sorted(details.get("Aliases") or []),
                }
                for network_name, details in networks.items()
            ],
            key=lambda item: item["name"],
        ),
    }


def container_fingerprints() -> dict[str, dict[str, Any]]:
    result = command(["docker", "ps", "--all", "--format", "{{.Names}}"])
    rows: dict[str, dict[str, Any]] = {}
    if result["returncode"] != 0:
        return rows
    for name in filter(None, result["stdout"].splitlines()):
        item = inspect_container(name)
        rows[name] = {
            "container_id": item.get("container_id"),
            "image_id": item.get("image_id"),
            "state": item.get("state"),
            "restart_count": item.get("restart_count"),
        }
    return rows


def classify_logs(name: str) -> dict[str, Any]:
    """Return bounded signal booleans; never return raw log text."""
    result = command(["docker", "logs", "--tail", "120", name], timeout=30)
    text = f"{result.get('stdout', '')}\n{result.get('stderr', '')}".lower()
    patterns = {
        "address_in_use": ("address already in use", "bind() failed", "port is already allocated"),
        "file_not_found": ("no such file or directory", "not found"),
        "permission_denied": ("permission denied",),
        "configuration_error": ("configuration file", "config error", "nginx: [emerg]"),
        "exec_error": ("exec format error", "executable file not found"),
        "connection_refused": ("connection refused",),
        "oom_signal": ("out of memory", "oom"),
        "nginx_error": ("nginx: [error]", "nginx: [emerg]"),
    }
    return {
        "available": result.get("returncode") == 0,
        "nonempty": bool(text.strip()),
        "signals": {
            name_: any(pattern in text for pattern in candidates)
            for name_, candidates in patterns.items()
        },
    }


def image_metadata(reference: str) -> dict[str, Any]:
    result = command(["docker", "image", "inspect", reference])
    record: dict[str, Any] = {"reference": reference, "exists": result["returncode"] == 0}
    if result["returncode"] == 0:
        try:
            data = json.loads(result["stdout"])[0]
            record.update(
                {
                    "image_id": data.get("Id"),
                    "created": data.get("Created"),
                    "size_bytes": data.get("Size"),
                }
            )
        except (json.JSONDecodeError, IndexError):
            record["parse_failed"] = True
    return record


def port_owners(port: int) -> list[dict[str, Any]]:
    result = command(["docker", "ps", "--format", "{{.Names}}"])
    owners: list[dict[str, Any]] = []
    if result["returncode"] != 0:
        return owners
    for name in filter(None, result["stdout"].splitlines()):
        item = inspect_container(name)
        matches = [entry for entry in item.get("ports", []) if entry.get("host_port") == str(port)]
        if matches:
            owners.append({"name": name, "container_id": item.get("container_id"), "bindings": matches})
    return owners


def main() -> int:
    before = container_fingerprints()
    target = inspect_container(TARGET)
    health = http_probe(TARGET, TARGET_PORT, "/")
    protected_before = [http_probe(*item) for item in PROTECTED_HTTP]
    report = {
        "alignment_stage": "dominion-web-read-only-diagnosis",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "success",
        "success": True,
        "target": target,
        "http": health,
        "log_classification": classify_logs(TARGET) if target.get("exists") else {"available": False},
        "port_8090_owners": port_owners(TARGET_PORT),
        "images": [image_metadata(reference) for reference in KNOWN_IMAGES],
        "paths": {
            "old_source_root": {"path": str(OLD_SOURCE_ROOT), "exists": OLD_SOURCE_ROOT.is_dir()},
            "release_web_root": {"path": str(RELEASE_WEB_ROOT), "exists": RELEASE_WEB_ROOT.is_dir()},
        },
        "protected_health_before": protected_before,
        "risks": [],
        "safety": {
            "containers_changed": False,
            "containers_started": False,
            "containers_stopped": False,
            "containers_recreated": False,
            "images_built": False,
            "networks_changed": False,
            "volumes_changed": False,
            "databases_changed": False,
            "dns_changed": False,
            "repositories_changed": False,
            "environment_values_collected": False,
            "secret_values_collected": False,
            "raw_logs_collected": False,
            "customer_data_collected": False,
        },
    }

    if health.get("status") != 200:
        report["risks"].append("dominion_web_http_unavailable")
    if not target.get("exists"):
        report["risks"].append("dominion_web_container_missing")
    elif not target.get("running"):
        report["risks"].append("dominion_web_not_running")
    if isinstance(target.get("restart_count"), int) and target["restart_count"] > 0:
        report["risks"].append("dominion_web_restart_history")
    if any(item.get("status") != 200 for item in protected_before):
        report["risks"].append("other_protected_health_regression")

    protected_after = [http_probe(*item) for item in PROTECTED_HTTP]
    after = container_fingerprints()
    report["protected_health_after"] = protected_after
    report["containers_unchanged"] = before == after
    if not report["containers_unchanged"]:
        report["status"] = "failed"
        report["success"] = False
        report["risks"].append("container_inventory_changed_during_diagnosis")

    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
