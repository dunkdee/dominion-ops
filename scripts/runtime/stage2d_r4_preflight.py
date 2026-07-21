#!/usr/bin/env python3
"""Run final governance gates and isolated image builds before production cutover.

This script must run as root so it can verify the root-only retirement backups.
It builds isolated image tags only. It never starts, stops, recreates, or replaces
production containers, and it never prints environment values or secret contents.
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

APPROVED_SOURCE_SHA = os.environ["APPROVED_SOURCE_SHA"]
RELEASE_ROOT = Path(os.environ["RELEASE_ROOT"])
RECOVERY_ROOT = Path(os.environ["RECOVERY_ROOT"])
RETIREMENT_ROOT = Path(os.environ["RETIREMENT_ROOT"])
EXPECTED_COMPOSE_SHA = os.environ["EXPECTED_COMPOSE_SHA"]
EXPECTED_ENV_SHA = os.environ["EXPECTED_ENV_SHA"]

EXPECTED_SERVICES = {
    "baby-api",
    "baby-logger",
    "browser-agents",
    "dominion-web",
    "obsidian-remote",
    "wix-agent",
}
BUILD_SERVICES = ("baby-api", "dominion-web", "wix-agent")
PROJECT_NAME = "dominion-stage2d-r4"
WIX_IMAGE = f"dominion/wix-agent:stage2d-r4-{APPROVED_SOURCE_SHA[:12]}"
EXPECTED_IMAGES = {
    "baby-api": f"{PROJECT_NAME}-baby-api:latest",
    "dominion-web": f"{PROJECT_NAME}-dominion-web:latest",
    "wix-agent": WIX_IMAGE,
}

CANONICAL_UNITS = {
    "caddy": "caddy.service",
    "alchemist": "dominion-alchemist.service",
    "alpha": "dominion-alpha.service",
    "conductor": "dominion-conductor.service",
    "gatekeeper": "dominion-gatekeeper.service",
    "guardian": "dominion-guardian.service",
    "juris": "dominion-juris.service",
    "sentinel": "dominion-sentinel.service",
    "store": "dominion-store.service",
    "gemini": "gemini-server.service",
}
RETIRED_UNITS = (
    "alchemist-api.service",
    "conductor-api.service",
    "juris-api.service",
    "dominion-port-healer.service",
)
PUBLISHING_TIMERS = (
    "conductor-autonomous.timer",
    "dominion-kdp.timer",
    "dominion-publish.timer",
    "dominion-social-poster.timer",
    "dominion-youtube.timer",
)
HEALTH_CHECKS = (
    ("baby-api", 8080, "/", False),
    ("wix-agent", 8082, "/ready", False),
    ("dominion-web", 8090, "/", False),
    ("n8n", 5678, "/healthz", False),
    ("alpha-engine", 8787, "/health", False),
    ("conductor", 5060, "/health", True),
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def command(
    args: list[str],
    *,
    cwd: Path | None = None,
    timeout: int = 1200,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    try:
        result = subprocess.run(
            args,
            cwd=str(cwd) if cwd else None,
            env=env,
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


def systemd_state(unit: str) -> dict[str, Any]:
    result = command(
        [
            "systemctl",
            "show",
            unit,
            "--property=LoadState,ActiveState,SubState,UnitFileState,NRestarts,FragmentPath",
        ],
        timeout=30,
    )
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
    enabled = command(["systemctl", "is-enabled", unit], timeout=30)
    record["is_enabled"] = enabled["stdout"].splitlines()[0] if enabled["stdout"] else None
    return record


def http_probe(name: str, port: int, path: str, include_keys: bool) -> dict[str, Any]:
    record: dict[str, Any] = {
        "name": name,
        "port": port,
        "path": path,
        "reachable": False,
        "status": None,
    }
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=5) as response:
            body = response.read(1024 * 1024)
            record.update({"reachable": True, "status": response.status})
            if include_keys:
                try:
                    data = json.loads(body.decode("utf-8"))
                    record["json_type"] = type(data).__name__
                    record["top_level_keys"] = sorted(data.keys()) if isinstance(data, dict) else []
                except Exception:
                    record["json_type"] = "unparsed"
                    record["top_level_keys"] = []
    except urllib.error.HTTPError as exc:
        record.update({"reachable": True, "status": exc.code})
    except Exception as exc:
        record["error_type"] = type(exc).__name__
    return record


def health_snapshot() -> list[dict[str, Any]]:
    return [http_probe(*item) for item in HEALTH_CHECKS]


def container_snapshot() -> list[dict[str, Any]]:
    result = command(["docker", "ps", "--all", "--format", "{{json .}}"], timeout=30)
    rows: list[dict[str, Any]] = []
    if result["returncode"] == 0:
        for line in result["stdout"].splitlines():
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            rows.append(
                {
                    "name": item.get("Names"),
                    "image": item.get("Image"),
                    "state": item.get("State"),
                    "status": item.get("Status"),
                }
            )
    return sorted(rows, key=lambda row: row.get("name") or "")


def image_record(service: str, reference: str) -> dict[str, Any]:
    result = command(["docker", "image", "inspect", reference], timeout=60)
    record: dict[str, Any] = {
        "service": service,
        "reference": reference,
        "exists": False,
        "id": None,
        "repo_tags": [],
        "size_bytes": None,
        "created": None,
    }
    if result["returncode"] != 0:
        record["stderr_type"] = result["stderr_type"]
        return record
    try:
        item = json.loads(result["stdout"])[0]
    except (json.JSONDecodeError, IndexError, TypeError):
        record["parse_failed"] = True
        return record
    record.update(
        {
            "exists": True,
            "id": item.get("Id"),
            "repo_tags": sorted(item.get("RepoTags") or []),
            "size_bytes": item.get("Size"),
            "created": item.get("Created"),
        }
    )
    return record


def main() -> int:
    errors: list[str] = []
    risks: list[str] = []

    if os.geteuid() != 0:
        print(
            json.dumps(
                {
                    "alignment_stage": "2D-R4-preflight",
                    "status": "failed",
                    "success": False,
                    "errors": ["root_required_for_retirement_backup_verification"],
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 1

    marker_path = RELEASE_ROOT / ".dominion-release.json"
    compose_path = RELEASE_ROOT / "docker-compose.yml"
    env_path = RELEASE_ROOT / ".env"
    recovery_env = RECOVERY_ROOT / "old-root.env"
    recovery_compose = RECOVERY_ROOT / "old-root.docker-compose.yml"

    marker: dict[str, Any] = {}
    if marker_path.is_file():
        try:
            marker = json.loads(marker_path.read_text(encoding="utf-8"))
        except Exception as exc:
            errors.append(f"release_marker_{type(exc).__name__}")
    else:
        errors.append("release_marker_missing")

    compose_hash = sha256_file(compose_path) if compose_path.is_file() else None
    env_hash = sha256_file(env_path) if env_path.is_file() and not env_path.is_symlink() else None
    env_mode = oct(env_path.stat().st_mode & 0o777) if env_path.is_file() else None
    recovery_env_hash = sha256_file(recovery_env) if recovery_env.is_file() else None
    recovery_compose_hash = sha256_file(recovery_compose) if recovery_compose.is_file() else None

    before_containers = container_snapshot()
    disk_before = shutil.disk_usage(RELEASE_ROOT) if RELEASE_ROOT.exists() else None

    build_env = os.environ.copy()
    build_env["WIX_AGENT_IMAGE"] = WIX_IMAGE
    compose_base = [
        "docker",
        "compose",
        "--project-name",
        PROJECT_NAME,
        "--env-file",
        ".env",
        "-f",
        "docker-compose.yml",
    ]

    compose_services: list[str] = []
    compose_valid = False
    if RELEASE_ROOT.is_dir() and compose_path.is_file() and env_path.is_file() and shutil.which("docker"):
        valid = command(compose_base + ["config", "--quiet"], cwd=RELEASE_ROOT, timeout=60, env=build_env)
        services = command(compose_base + ["config", "--services"], cwd=RELEASE_ROOT, timeout=60, env=build_env)
        compose_valid = valid["returncode"] == 0
        if services["returncode"] == 0:
            compose_services = sorted(filter(None, services["stdout"].splitlines()))
    else:
        errors.append("compose_preconditions_missing")

    health_before = health_snapshot()
    canonical_before = {name: systemd_state(unit) for name, unit in CANONICAL_UNITS.items()}
    restart_start = {name: record.get("n_restarts") for name, record in canonical_before.items()}
    retired_states = {unit: systemd_state(unit) for unit in RETIRED_UNITS}
    timer_states = {unit: systemd_state(unit) for unit in PUBLISHING_TIMERS}
    retirement_backups = {
        unit: {
            "path": str(RETIREMENT_ROOT / unit),
            "exists": (RETIREMENT_ROOT / unit).is_file(),
            "sha256": sha256_file(RETIREMENT_ROOT / unit) if (RETIREMENT_ROOT / unit).is_file() else None,
            "size_bytes": (RETIREMENT_ROOT / unit).stat().st_size if (RETIREMENT_ROOT / unit).is_file() else None,
        }
        for unit in RETIRED_UNITS
    }
    watchmen_status = http_probe("conductor-watchmen-status", 5060, "/watchmen/status", True)

    gates: dict[str, dict[str, Any]] = {}
    gates["runtime"] = {
        "pass": all(item.get("status") == 200 for item in health_before),
        "evidence": health_before,
    }
    gates["secrets"] = {
        "pass": env_path.is_file() and not env_path.is_symlink() and env_mode == "0o600" and env_hash == EXPECTED_ENV_SHA,
        "evidence": {
            "path": str(env_path),
            "regular_file": env_path.is_file() and not env_path.is_symlink(),
            "mode": env_mode,
            "sha256": env_hash,
            "git_metadata_present": (RELEASE_ROOT / ".git").exists(),
        },
    }
    gates["deployment"] = {
        "pass": (
            RELEASE_ROOT.is_dir()
            and marker.get("source_sha") == APPROVED_SOURCE_SHA
            and compose_hash == EXPECTED_COMPOSE_SHA
            and compose_valid
            and set(compose_services) == EXPECTED_SERVICES
        ),
        "evidence": {
            "release_root": str(RELEASE_ROOT),
            "marker_source_sha": marker.get("source_sha"),
            "compose_sha256": compose_hash,
            "compose_valid": compose_valid,
            "services": compose_services,
        },
    }
    gates["rollback"] = {
        "pass": (
            recovery_env_hash == EXPECTED_ENV_SHA
            and recovery_compose_hash == EXPECTED_COMPOSE_SHA
            and all(item.get("exists") and item.get("sha256") for item in retirement_backups.values())
        ),
        "evidence": {
            "recovery_root": str(RECOVERY_ROOT),
            "env_backup_sha256": recovery_env_hash,
            "compose_backup_sha256": recovery_compose_hash,
            "retirement_root": str(RETIREMENT_ROOT),
            "retirement_backups": retirement_backups,
        },
    }
    gates["governance"] = {
        "pass": (
            all(
                record.get("active_state") == "inactive"
                and record.get("load_state") == "masked"
                and record.get("is_enabled") == "masked"
                for record in retired_states.values()
            )
            and all(
                record.get("active_state") != "active"
                and record.get("is_enabled") == "disabled"
                for record in timer_states.values()
            )
        ),
        "evidence": {
            "retired_units": retired_states,
            "publishing_timers": timer_states,
        },
    }
    gates["agent_runtime"] = {
        "pass": all(
            canonical_before[name].get("active_state") == "active"
            and canonical_before[name].get("sub_state") == "running"
            for name in ("conductor", "guardian", "sentinel", "juris")
        )
        and watchmen_status.get("status") == 200,
        "evidence": {
            "agents": {name: canonical_before[name] for name in ("conductor", "guardian", "sentinel", "juris")},
            "watchmen_status": watchmen_status,
        },
    }

    build: dict[str, Any] = {
        "attempted": False,
        "returncode": None,
        "stderr_type": None,
        "isolated_project": PROJECT_NAME,
        "services": list(BUILD_SERVICES),
        "expected_images": EXPECTED_IMAGES,
        "images": [],
    }

    prerequisites = ("runtime", "secrets", "deployment", "rollback", "governance", "agent_runtime")
    if all(gates[name]["pass"] for name in prerequisites) and not errors:
        if disk_before is None or disk_before.free < 2 * 1024 * 1024 * 1024:
            errors.append("insufficient_disk_for_isolated_build")
        else:
            result = command(
                compose_base + ["build", *BUILD_SERVICES],
                cwd=RELEASE_ROOT,
                timeout=1800,
                env=build_env,
            )
            build.update(
                {
                    "attempted": True,
                    "returncode": result["returncode"],
                    "stderr_type": result["stderr_type"],
                }
            )
            if result["returncode"] == 0:
                build["images"] = [image_record(service, reference) for service, reference in EXPECTED_IMAGES.items()]
    else:
        risks.append("isolated_build_skipped_due_to_failed_gate")

    time.sleep(30)
    health_after = health_snapshot()
    canonical_after = {name: systemd_state(unit) for name, unit in CANONICAL_UNITS.items()}
    restart_deltas: dict[str, dict[str, Any]] = {}
    for name, record in canonical_after.items():
        start = restart_start.get(name)
        end = record.get("n_restarts")
        restart_deltas[name] = {
            "unit": record.get("unit"),
            "start": start,
            "end": end,
            "delta": end - start if isinstance(start, int) and isinstance(end, int) else None,
        }

    after_containers = container_snapshot()
    containers_unchanged = before_containers == after_containers
    build_pass = (
        build["attempted"]
        and build["returncode"] == 0
        and len(build["images"]) == len(EXPECTED_IMAGES)
        and all(item.get("exists") and item.get("id") for item in build["images"])
    )
    gates["build"] = {"pass": build_pass, "evidence": build}
    gates["post_build_stability"] = {
        "pass": (
            containers_unchanged
            and all(item.get("status") == 200 for item in health_after)
            and all(record.get("delta") in {0, None} for record in restart_deltas.values())
        ),
        "evidence": {
            "containers_unchanged": containers_unchanged,
            "health_after": health_after,
            "restart_deltas": restart_deltas,
        },
    }

    council = [
        {"seat": "runtime", "result": "pass" if gates["runtime"]["pass"] else "fail"},
        {"seat": "secrets", "result": "pass" if gates["secrets"]["pass"] else "fail"},
        {"seat": "deployment", "result": "pass" if gates["deployment"]["pass"] else "fail"},
        {"seat": "rollback", "result": "pass" if gates["rollback"]["pass"] else "fail"},
        {"seat": "governance", "result": "pass" if gates["governance"]["pass"] else "fail"},
    ]

    failed_gates = sorted(name for name, gate in gates.items() if not gate["pass"])
    success = not errors and not failed_gates
    disk_after = shutil.disk_usage(RELEASE_ROOT) if RELEASE_ROOT.exists() else None

    payload = {
        "alignment_stage": "2D-R4-preflight",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "success" if success else "failed",
        "success": success,
        "approved_source_sha": APPROVED_SOURCE_SHA,
        "release_root": str(RELEASE_ROOT),
        "agent_reports": [
            {
                "agent": name,
                "duty": {
                    "conductor": "orchestration and Watchmen interface",
                    "guardian": "runtime drift detection",
                    "sentinel": "independent runtime verification",
                    "juris": "governance and legal boundary service",
                }[name],
                "evidence": canonical_after[name],
                "result": "verified_running"
                if canonical_after[name].get("active_state") == "active"
                and canonical_after[name].get("sub_state") == "running"
                else "unverified",
                "risks": [],
                "next_action": "remain observe-only; no cutover in R4",
                "human_approval_required": True,
            }
            for name in ("conductor", "guardian", "sentinel", "juris")
        ],
        "deterministic_five_council": council,
        "gates": gates,
        "failed_gates": failed_gates,
        "build": build,
        "before_containers": before_containers,
        "after_containers": after_containers,
        "containers_unchanged": containers_unchanged,
        "disk_before": {
            "total_bytes": disk_before.total,
            "used_bytes": disk_before.used,
            "free_bytes": disk_before.free,
        }
        if disk_before
        else None,
        "disk_after": {
            "total_bytes": disk_after.total,
            "used_bytes": disk_after.used,
            "free_bytes": disk_after.free,
        }
        if disk_after
        else None,
        "errors": errors,
        "risks": sorted(set(risks)),
        "safety": {
            "automated_council_is_deterministic_checks": True,
            "production_containers_started": False,
            "production_containers_stopped": False,
            "production_containers_recreated": False,
            "production_volumes_changed": False,
            "production_networks_changed": False,
            "databases_changed": False,
            "dns_changed": False,
            "secret_values_collected": False,
            "secret_file_uploaded": False,
            "browser_agents_started": False,
            "obsidian_started": False,
            "cutover_performed": False,
            "isolated_images_built_only": True,
        },
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
