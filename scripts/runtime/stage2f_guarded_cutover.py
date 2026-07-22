#!/usr/bin/env python3
"""Guardedly cut protected containers to canonical Compose ownership.

The current containers are stopped and renamed into local rollback units rather
than deleted. New containers are created from the approved isolated images under
the `dominion-ops` Compose project while reusing the existing production network
and Wix data volumes. Any failed gate removes the new containers and restores the
original containers. Secret values and full inspect payloads remain local only.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

APPROVED_SOURCE_SHA = os.environ["APPROVED_SOURCE_SHA"]
RELEASE_ROOT = Path(os.environ["RELEASE_ROOT"])
EXPECTED_COMPOSE_SHA = os.environ["EXPECTED_COMPOSE_SHA"]
EXPECTED_ENV_SHA = os.environ["EXPECTED_ENV_SHA"]
RUN_ID = os.environ["RUN_ID"]

PROJECT_NAME = "dominion-ops"
NETWORK_NAME = "desktop-tutorial_default"
NETWORK_ID = "fce28b58ed4477fc2466285a6a80feb013061e63fece83eaaaea7236712f84e3"
WIX_DATA_VOLUME = "wix_agent_data_a33ce2044d95-29785123140-1"
WIX_LOGS_VOLUME = "wix_agent_logs_a33ce2044d95-29785123140-1"

TARGETS: dict[str, dict[str, Any]] = {
    "baby-api": {
        "container_id": "601c5388480132a0a5ef4584fcfff0dacb575db5f7001ad4f677d48a17a7d38a",
        "old_image_id": "sha256:a319b3721a52e31c166c5a311301f656affef7f4acaeb4ff047c2cc971af000d",
        "new_image": "dominion-stage2d-r4-baby-api:latest",
        "new_image_id": "sha256:089445475d96ca3630fd4821af3c0304d38de5ece89a529b3782a398e38c3c82",
        "restart": "always",
        "health": (8080, "/"),
    },
    "dominion-web": {
        "container_id": "cf8294541b1ab3c7ea29896950f6e87e38683ac32b400afb8a1850a0be6f61c5",
        "old_image_id": "sha256:3224bfc43c02ab75c9a651cd3b8988e8778cae57006a96da16a03d9b730d9810",
        "new_image": "dominion-stage2d-r4-dominion-web:latest",
        "new_image_id": "sha256:77583ed35a7537206aeae97e97fa015f21d9d3b112a3885ca50e6cdd1cc03847",
        "restart": "always",
        "health": (8090, "/"),
    },
    "wix-agent": {
        "container_id": "f0319cf37704efcd92de809994673620c77e3850ec0106551340f3ad2e2859b5",
        "old_image_id": "sha256:a5a7deff7623eac93fe40adf1c96a65e802e1c50a92bfe67e1f284a960efb0fd",
        "new_image": "dominion/wix-agent:stage2d-r4-10646094aa3a",
        "new_image_id": "sha256:ef792a2ac99184cd51192becb7ead9d0ef3b5347a57b5f41eba6ce5bd834292e",
        "restart": "unless-stopped",
        "health": (8082, "/ready"),
    },
    "baby-logger": {
        "container_id": "c3d390494b902672bd7ef1aabc0fcc4a0fe770368439933fd1a47c5b70813161",
        "old_image_id": "sha256:a2d49ea686c2adfe3c992e47dc3b5e7fa6e6b5055609400dc2acaeb241c829f4",
        "new_image": "alpine:latest",
        "new_image_id": "sha256:a2d49ea686c2adfe3c992e47dc3b5e7fa6e6b5055609400dc2acaeb241c829f4",
        "restart": "always",
        "health": None,
    },
}
CUTOVER_ORDER = ("baby-api", "dominion-web", "wix-agent", "baby-logger")

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
PROTECTED_HTTP = (
    ("baby-api", 8080, "/"),
    ("wix-agent", 8082, "/ready"),
    ("dominion-web", 8090, "/"),
    ("n8n", 5678, "/healthz"),
    ("alpha-engine", 8787, "/health"),
    ("conductor", 5060, "/health"),
)


def command(
    args: list[str],
    *,
    cwd: Path | None = None,
    timeout: int = 300,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Run a bounded command without exposing its output in the report."""
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


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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
    except Exception as exc:  # noqa: BLE001 - report only exception type
        record["error_type"] = type(exc).__name__
    return record


def wait_http(port: int, path: str, timeout: int = 90) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if http_probe("target", port, path).get("status") == 200:
            return True
        time.sleep(3)
    return False


def unit_state(unit: str) -> dict[str, Any]:
    result = command([
        "systemctl",
        "show",
        unit,
        "--property=LoadState,ActiveState,SubState,UnitFileState,NRestarts",
    ])
    record: dict[str, Any] = {
        "unit": unit,
        "load_state": None,
        "active_state": None,
        "sub_state": None,
        "unit_file_state": None,
        "n_restarts": None,
    }
    mapping = {
        "LoadState": "load_state",
        "ActiveState": "active_state",
        "SubState": "sub_state",
        "UnitFileState": "unit_file_state",
    }
    if result["returncode"] == 0:
        for line in result["stdout"].splitlines():
            key, _, value = line.partition("=")
            if key in mapping:
                record[mapping[key]] = value or None
            elif key == "NRestarts":
                record["n_restarts"] = int(value) if value.isdigit() else None
    return record


def inspect_raw(name: str) -> dict[str, Any] | None:
    result = command(["docker", "inspect", name], timeout=60)
    if result["returncode"] != 0:
        return None
    try:
        data = json.loads(result["stdout"])
    except json.JSONDecodeError:
        return None
    return data[0] if data else None


def sanitized_container(name: str) -> dict[str, Any]:
    data = inspect_raw(name)
    if not data:
        return {"name": name, "exists": False}
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
        "restart_policy": (host.get("RestartPolicy") or {}).get("Name"),
        "read_only_rootfs": bool(host.get("ReadonlyRootfs")),
        "memory_bytes": host.get("Memory"),
        "nano_cpus": host.get("NanoCpus"),
        "pids_limit": host.get("PidsLimit"),
        "cap_drop": sorted(host.get("CapDrop") or []),
        "security_opt": sorted(host.get("SecurityOpt") or []),
        "compose_project": labels.get("com.docker.compose.project"),
        "compose_service": labels.get("com.docker.compose.service"),
        "compose_config_files": labels.get("com.docker.compose.project.config_files"),
        "mounts": sorted(
            [
                {
                    "type": item.get("Type"),
                    "name": item.get("Name"),
                    "source": item.get("Source"),
                    "destination": item.get("Destination"),
                    "rw": item.get("RW"),
                }
                for item in (data.get("Mounts") or [])
            ],
            key=lambda item: item.get("destination") or "",
        ),
        "networks": sorted(
            [
                {
                    "name": network_name,
                    "network_id": item.get("NetworkID"),
                    "aliases": sorted(item.get("Aliases") or []),
                }
                for network_name, item in networks.items()
            ],
            key=lambda item: item["name"],
        ),
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
            key=lambda item: (item["host_port"] or "", item["container_port"]),
        ),
    }


def all_container_fingerprints(exclude: set[str]) -> dict[str, dict[str, Any]]:
    result = command(["docker", "ps", "--all", "--format", "{{.Names}}"], timeout=30)
    rows: dict[str, dict[str, Any]] = {}
    if result["returncode"] != 0:
        return rows
    for name in filter(None, result["stdout"].splitlines()):
        if name in exclude:
            continue
        item = sanitized_container(name)
        rows[name] = {
            "container_id": item.get("container_id"),
            "image_id": item.get("image_id"),
            "state": item.get("state"),
        }
    return rows


def save_local_inspects(root: Path) -> None:
    for name in TARGETS:
        path = root / f"{name}.inspect.json"
        with path.open("wb") as handle:
            result = subprocess.run(
                ["docker", "inspect", name],
                check=False,
                stdout=handle,
                stderr=subprocess.DEVNULL,
                timeout=60,
            )
        if result.returncode != 0:
            raise RuntimeError(f"inspect_backup_failed:{name}")
        os.chmod(path, 0o600)


def write_override(path: Path) -> None:
    content = f"""services:
  baby-api:
    image: {TARGETS['baby-api']['new_image']}
  dominion-web:
    image: {TARGETS['dominion-web']['new_image']}
  wix-agent:
    image: {TARGETS['wix-agent']['new_image']}

networks:
  default:
    external: true
    name: {NETWORK_NAME}

volumes:
  wix_agent_data:
    external: true
    name: {WIX_DATA_VOLUME}
  wix_agent_logs:
    external: true
    name: {WIX_LOGS_VOLUME}
"""
    path.write_text(content, encoding="utf-8")
    os.chmod(path, 0o600)


def compose_base(override_path: Path) -> list[str]:
    return [
        "docker",
        "compose",
        "--project-name",
        PROJECT_NAME,
        "--env-file",
        ".env",
        "-f",
        "docker-compose.yml",
        "-f",
        str(override_path),
    ]


def rollback(migrated: list[str], rollback_names: dict[str, str]) -> dict[str, Any]:
    actions: list[dict[str, Any]] = []
    errors: list[str] = []
    for service in reversed(migrated):
        remove = command(["docker", "rm", "--force", service], timeout=90)
        actions.append({"service": service, "new_removed": remove["returncode"] == 0})
    for service in reversed(migrated):
        rollback_name = rollback_names[service]
        rename = command(["docker", "rename", rollback_name, service], timeout=30)
        if rename["returncode"] != 0:
            errors.append(f"rollback_rename_failed:{service}")
            continue
        policy = command(["docker", "update", f"--restart={TARGETS[service]['restart']}", service], timeout=30)
        start = command(["docker", "start", service], timeout=90)
        if policy["returncode"] != 0 or start["returncode"] != 0:
            errors.append(f"rollback_start_failed:{service}")
        health = TARGETS[service]["health"]
        if health and not wait_http(health[0], health[1], timeout=90):
            errors.append(f"rollback_health_failed:{service}")
    final_health = [http_probe(*item) for item in PROTECTED_HTTP]
    if any(item.get("status") != 200 for item in final_health):
        errors.append("rollback_protected_http_failed")
    return {
        "success": not errors,
        "errors": errors,
        "actions": actions,
        "health": final_health,
    }


def main() -> int:
    generated_at = datetime.now(timezone.utc)
    cutover_root = Path("/var/lib/dominion/cutovers") / f"stage2f-{RUN_ID}"
    override_path = cutover_root / "cutover.override.yml"
    errors: list[str] = []
    risks: list[str] = []
    migrated: list[str] = []
    rollback_names = {service: f"{service}-rollback-stage2f-{RUN_ID}" for service in TARGETS}
    rollback_performed = False
    rollback_result: dict[str, Any] | None = None

    if os.geteuid() != 0:
        print(json.dumps({"alignment_stage": "2F-cutover", "status": "failed", "success": False, "errors": ["root_required"]}, indent=2))
        return 1

    compose_path = RELEASE_ROOT / "docker-compose.yml"
    env_path = RELEASE_ROOT / ".env"
    marker_path = RELEASE_ROOT / ".dominion-release.json"

    marker: dict[str, Any] = {}
    if marker_path.is_file():
        try:
            marker = json.loads(marker_path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            errors.append(f"release_marker_{type(exc).__name__}")
    else:
        errors.append("release_marker_missing")

    if not compose_path.is_file() or sha256_file(compose_path) != EXPECTED_COMPOSE_SHA:
        errors.append("compose_hash_mismatch")
    if not env_path.is_file() or env_path.is_symlink() or sha256_file(env_path) != EXPECTED_ENV_SHA:
        errors.append("env_hash_mismatch")
    elif oct(env_path.stat().st_mode & 0o777) != "0o600":
        errors.append("env_mode_mismatch")
    if marker.get("source_sha") != APPROVED_SOURCE_SHA:
        errors.append("release_source_mismatch")

    network = command(["docker", "network", "inspect", NETWORK_NAME], timeout=30)
    if network["returncode"] != 0:
        errors.append("production_network_missing")
    else:
        try:
            network_data = json.loads(network["stdout"])[0]
            if network_data.get("Id") != NETWORK_ID:
                errors.append("production_network_id_mismatch")
        except (json.JSONDecodeError, IndexError):
            errors.append("production_network_parse_failed")

    for volume in (WIX_DATA_VOLUME, WIX_LOGS_VOLUME):
        if command(["docker", "volume", "inspect", volume], timeout=30)["returncode"] != 0:
            errors.append(f"volume_missing:{volume}")

    current: dict[str, dict[str, Any]] = {}
    for service, expected in TARGETS.items():
        item = sanitized_container(service)
        current[service] = item
        if not item.get("exists") or not item.get("running"):
            errors.append(f"target_not_running:{service}")
            continue
        if item.get("container_id") != expected["container_id"]:
            errors.append(f"target_container_drift:{service}")
        if item.get("image_id") != expected["old_image_id"]:
            errors.append(f"target_image_drift:{service}")
        if command(["docker", "inspect", rollback_names[service]], timeout=15)["returncode"] == 0:
            errors.append(f"rollback_name_occupied:{service}")

    for service, expected in TARGETS.items():
        image = command(["docker", "image", "inspect", expected["new_image"]], timeout=30)
        if image["returncode"] != 0:
            errors.append(f"approved_image_missing:{service}")
            continue
        try:
            image_id = json.loads(image["stdout"])[0].get("Id")
        except (json.JSONDecodeError, IndexError):
            image_id = None
        if image_id != expected["new_image_id"]:
            errors.append(f"approved_image_id_mismatch:{service}")

    retired_before = {unit: unit_state(unit) for unit in RETIRED_UNITS}
    timers_before = {unit: unit_state(unit) for unit in PUBLISHING_TIMERS}
    canonical_before = {name: unit_state(unit) for name, unit in CANONICAL_UNITS.items()}
    health_before = [http_probe(*item) for item in PROTECTED_HTTP]
    if any(state.get("load_state") != "masked" or state.get("active_state") == "active" for state in retired_before.values()):
        errors.append("retired_unit_governance_failed")
    if any(state.get("active_state") != "inactive" or state.get("unit_file_state") != "disabled" for state in timers_before.values()):
        errors.append("publishing_timer_governance_failed")
    if any(state.get("active_state") != "active" or state.get("sub_state") != "running" for state in canonical_before.values()):
        errors.append("canonical_unit_precheck_failed")
    if any(item.get("status") != 200 for item in health_before):
        errors.append("protected_http_precheck_failed")

    excluded = set(TARGETS) | set(rollback_names.values())
    unaffected_before = all_container_fingerprints(excluded)

    if not errors:
        cutover_root.mkdir(mode=0o700, parents=True, exist_ok=False)
        save_local_inspects(cutover_root)
        write_override(override_path)
        compose = compose_base(override_path)
        config = command(compose + ["config", "--quiet"], cwd=RELEASE_ROOT, timeout=60)
        services = command(compose + ["config", "--services"], cwd=RELEASE_ROOT, timeout=60)
        if config["returncode"] != 0:
            errors.append("cutover_compose_invalid")
        elif not set(TARGETS).issubset(set(filter(None, services["stdout"].splitlines()))):
            errors.append("cutover_services_missing")

    restart_start = {name: state.get("n_restarts") for name, state in canonical_before.items()}

    try:
        if not errors:
            compose = compose_base(override_path)
            for service in CUTOVER_ORDER:
                rollback_name = rollback_names[service]
                stop = command(["docker", "stop", "--time", "20", service], timeout=60)
                if stop["returncode"] != 0:
                    errors.append(f"stop_failed:{service}")
                    break
                rename = command(["docker", "rename", service, rollback_name], timeout=30)
                if rename["returncode"] != 0:
                    errors.append(f"rename_failed:{service}")
                    break
                migrated.append(service)
                policy = command(["docker", "update", "--restart=no", rollback_name], timeout=30)
                if policy["returncode"] != 0:
                    errors.append(f"rollback_policy_failed:{service}")
                    break
                up = command(
                    compose + ["up", "-d", "--no-deps", "--no-build", "--force-recreate", service],
                    cwd=RELEASE_ROOT,
                    timeout=300,
                )
                if up["returncode"] != 0:
                    errors.append(f"compose_up_failed:{service}")
                    break
                health = TARGETS[service]["health"]
                if health and not wait_http(health[0], health[1], timeout=120):
                    errors.append(f"new_health_failed:{service}")
                    break
                item = sanitized_container(service)
                if not item.get("running") or item.get("image_id") != TARGETS[service]["new_image_id"]:
                    errors.append(f"new_container_verification_failed:{service}")
                    break
    except Exception as exc:  # noqa: BLE001
        errors.append(f"cutover_exception:{type(exc).__name__}")

    if errors and migrated:
        rollback_performed = True
        rollback_result = rollback(migrated, rollback_names)

    if not errors:
        time.sleep(60)

    canonical_after = {name: unit_state(unit) for name, unit in CANONICAL_UNITS.items()}
    restart_deltas: dict[str, dict[str, Any]] = {}
    for name, state in canonical_after.items():
        start = restart_start.get(name)
        end = state.get("n_restarts")
        restart_deltas[name] = {
            "unit": state.get("unit"),
            "start": start,
            "end": end,
            "delta": end - start if isinstance(start, int) and isinstance(end, int) else None,
        }

    final_targets = {service: sanitized_container(service) for service in TARGETS}
    health_after = [http_probe(*item) for item in PROTECTED_HTTP]
    retired_after = {unit: unit_state(unit) for unit in RETIRED_UNITS}
    timers_after = {unit: unit_state(unit) for unit in PUBLISHING_TIMERS}
    unaffected_after = all_container_fingerprints(excluded)
    unaffected_unchanged = unaffected_before == unaffected_after

    if not errors:
        for service, item in final_targets.items():
            expected = TARGETS[service]
            if not item.get("running") or item.get("image_id") != expected["new_image_id"]:
                errors.append(f"final_image_failed:{service}")
            if item.get("compose_project") != PROJECT_NAME or item.get("compose_service") != service:
                errors.append(f"final_compose_ownership_failed:{service}")
            if not any(network.get("network_id") == NETWORK_ID for network in item.get("networks", [])):
                errors.append(f"final_network_failed:{service}")

        baby_mounts = {item["destination"]: item for item in final_targets["baby-api"].get("mounts", [])}
        if baby_mounts.get("/app", {}).get("source") != str(RELEASE_ROOT / "api"):
            errors.append("baby_api_release_mount_failed")
        if baby_mounts.get("/vault", {}).get("source") != "/home/malachisingleton8/vault":
            errors.append("baby_api_vault_mount_failed")

        wix_mounts = {item["destination"]: item for item in final_targets["wix-agent"].get("mounts", [])}
        if wix_mounts.get("/data", {}).get("name") != WIX_DATA_VOLUME:
            errors.append("wix_data_volume_failed")
        if wix_mounts.get("/app/logs", {}).get("name") != WIX_LOGS_VOLUME:
            errors.append("wix_logs_volume_failed")
        wix = final_targets["wix-agent"]
        if not wix.get("read_only_rootfs") or wix.get("pids_limit") != 256 or wix.get("memory_bytes") != 536870912:
            errors.append("wix_hardening_failed")
        if "ALL" not in wix.get("cap_drop", []) or "no-new-privileges" not in wix.get("security_opt", []):
            errors.append("wix_security_options_failed")

        if any(item.get("status") != 200 for item in health_after):
            errors.append("protected_http_postcheck_failed")
        if any(state.get("active_state") != "active" or state.get("sub_state") != "running" for state in canonical_after.values()):
            errors.append("canonical_unit_postcheck_failed")
        if any(record.get("delta") not in {0, None} for record in restart_deltas.values()):
            errors.append("canonical_restart_regression")
        if any(state.get("load_state") != "masked" or state.get("active_state") == "active" for state in retired_after.values()):
            errors.append("retired_unit_postcheck_failed")
        if any(state.get("active_state") != "inactive" or state.get("unit_file_state") != "disabled" for state in timers_after.values()):
            errors.append("publishing_timer_postcheck_failed")
        if not unaffected_unchanged:
            errors.append("unaffected_container_drift")

    if errors and migrated and not rollback_performed:
        rollback_performed = True
        rollback_result = rollback(migrated, rollback_names)

    success = not errors and not rollback_performed
    payload = {
        "alignment_stage": "2F-cutover",
        "generated_at": generated_at.isoformat(),
        "status": "success" if success else "failed",
        "success": success,
        "approved_source_sha": APPROVED_SOURCE_SHA,
        "release_root": str(RELEASE_ROOT),
        "cutover_root": str(cutover_root),
        "compose_project": PROJECT_NAME,
        "production_network": {"name": NETWORK_NAME, "network_id": NETWORK_ID},
        "wix_volumes": {"data": WIX_DATA_VOLUME, "logs": WIX_LOGS_VOLUME},
        "rollback_names": rollback_names,
        "migrated_services": migrated,
        "rollback_performed": rollback_performed,
        "rollback_result": rollback_result,
        "health_before": health_before,
        "health_after": health_after,
        "canonical_restart_deltas_60_seconds": restart_deltas,
        "retired_after": retired_after,
        "publishing_timers_after": timers_after,
        "final_targets": final_targets,
        "unaffected_containers_unchanged": unaffected_unchanged,
        "errors": errors,
        "risks": risks,
        "safety": {
            "old_containers_deleted": False,
            "old_containers_preserved_as_stopped_rollback_units": success,
            "browser_agents_started": False,
            "obsidian_started": False,
            "databases_changed": False,
            "dns_changed": False,
            "network_definition_changed": False,
            "existing_network_reused": True,
            "volume_definitions_changed": False,
            "existing_wix_volumes_reused": True,
            "volume_contents_collected": False,
            "secret_values_collected": False,
            "secret_file_uploaded": False,
            "full_container_inspects_saved_locally_only": True,
            "repository_checkout_changed": False,
        },
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
