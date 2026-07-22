#!/usr/bin/env python3
"""Map exact live Docker ownership for a reversible canonical cutover.

This script is read-only. It reports container/image IDs, Compose ownership labels,
ports, mounts, volume metadata, network metadata, restart policy, health state, and
resource controls. It never returns environment values, commands, logs, customer
data, or secret contents.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

TARGET_CONTAINERS = ("baby-api", "baby-logger", "dominion-web", "wix-agent")
EXPECTED_IMAGES = {
    "baby-api": "dominion-stage2d-r4-baby-api:latest",
    "dominion-web": "dominion-stage2d-r4-dominion-web:latest",
    "wix-agent": "dominion/wix-agent:stage2d-r4-10646094aa3a",
}
RELEASE_ROOT = Path("/home/malachisingleton8/dominion-releases/dominion-ops-10646094aa3a")
EXPECTED_COMPOSE_SHA = "42e2e90c41e9c154bf96f3ba2dc277811f873626af41b747474fcea6a494c8eb"


def command(args: list[str], timeout: int = 60) -> dict[str, Any]:
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


def compose_labels(labels: dict[str, Any] | None) -> dict[str, str]:
    labels = labels or {}
    return {
        key: str(value)
        for key, value in sorted(labels.items())
        if key.startswith("com.docker.compose.")
    }


def port_bindings(item: dict[str, Any]) -> list[dict[str, Any]]:
    bindings = item.get("HostConfig", {}).get("PortBindings") or {}
    records: list[dict[str, Any]] = []
    for container_port, hosts in sorted(bindings.items()):
        if not hosts:
            records.append({
                "container_port": container_port,
                "host_ip": None,
                "host_port": None,
            })
            continue
        for host in hosts:
            records.append({
                "container_port": container_port,
                "host_ip": host.get("HostIp"),
                "host_port": host.get("HostPort"),
            })
    return records


def mount_records(item: dict[str, Any]) -> list[dict[str, Any]]:
    records = []
    for mount in item.get("Mounts") or []:
        records.append({
            "type": mount.get("Type"),
            "name": mount.get("Name"),
            "source": mount.get("Source"),
            "destination": mount.get("Destination"),
            "rw": mount.get("RW"),
            "propagation": mount.get("Propagation"),
        })
    return sorted(records, key=lambda row: (row.get("destination") or "", row.get("source") or ""))


def network_records(item: dict[str, Any]) -> list[dict[str, Any]]:
    networks = item.get("NetworkSettings", {}).get("Networks") or {}
    records = []
    for name, data in sorted(networks.items()):
        records.append({
            "name": name,
            "network_id": data.get("NetworkID"),
            "aliases": sorted(set(data.get("Aliases") or [])),
        })
    return records


def inspect_container(name: str) -> dict[str, Any]:
    result = command(["docker", "inspect", name])
    record: dict[str, Any] = {
        "name": name,
        "exists": False,
        "inspect_returncode": result["returncode"],
    }
    if result["returncode"] != 0:
        return record
    try:
        item = json.loads(result["stdout"])[0]
    except (json.JSONDecodeError, IndexError, TypeError):
        record["parse_error"] = True
        return record

    state = item.get("State") or {}
    health = state.get("Health") or {}
    host = item.get("HostConfig") or {}
    config = item.get("Config") or {}
    record.update({
        "exists": True,
        "container_id": item.get("Id"),
        "created": item.get("Created"),
        "image_reference": config.get("Image"),
        "image_id": item.get("Image"),
        "state": state.get("Status"),
        "running": state.get("Running"),
        "health": health.get("Status"),
        "started_at": state.get("StartedAt"),
        "restart_policy": host.get("RestartPolicy"),
        "read_only_rootfs": host.get("ReadonlyRootfs"),
        "memory_bytes": host.get("Memory"),
        "nano_cpus": host.get("NanoCpus"),
        "pids_limit": host.get("PidsLimit"),
        "cap_drop": sorted(host.get("CapDrop") or []),
        "security_opt": sorted(host.get("SecurityOpt") or []),
        "ports": port_bindings(item),
        "mounts": mount_records(item),
        "networks": network_records(item),
        "compose_labels": compose_labels(config.get("Labels")),
    })
    return record


def inspect_image(reference: str) -> dict[str, Any]:
    result = command(["docker", "image", "inspect", reference])
    record: dict[str, Any] = {
        "reference": reference,
        "exists": False,
        "inspect_returncode": result["returncode"],
    }
    if result["returncode"] != 0:
        return record
    try:
        item = json.loads(result["stdout"])[0]
    except (json.JSONDecodeError, IndexError, TypeError):
        record["parse_error"] = True
        return record
    record.update({
        "exists": True,
        "image_id": item.get("Id"),
        "created": item.get("Created"),
        "size_bytes": item.get("Size"),
        "repo_tags": sorted(item.get("RepoTags") or []),
        "repo_digests": sorted(item.get("RepoDigests") or []),
    })
    return record


def inspect_volume(name: str) -> dict[str, Any]:
    result = command(["docker", "volume", "inspect", name])
    record: dict[str, Any] = {"name": name, "exists": False}
    if result["returncode"] != 0:
        return record
    try:
        item = json.loads(result["stdout"])[0]
    except (json.JSONDecodeError, IndexError, TypeError):
        record["parse_error"] = True
        return record
    record.update({
        "exists": True,
        "driver": item.get("Driver"),
        "scope": item.get("Scope"),
        "mountpoint": item.get("Mountpoint"),
        "compose_labels": compose_labels(item.get("Labels")),
    })
    return record


def inspect_network(name: str, target_ids: set[str]) -> dict[str, Any]:
    result = command(["docker", "network", "inspect", name])
    record: dict[str, Any] = {"name": name, "exists": False}
    if result["returncode"] != 0:
        return record
    try:
        item = json.loads(result["stdout"])[0]
    except (json.JSONDecodeError, IndexError, TypeError):
        record["parse_error"] = True
        return record
    attached = []
    for container_id, data in (item.get("Containers") or {}).items():
        if container_id in target_ids:
            attached.append({
                "container_id": container_id,
                "name": data.get("Name"),
            })
    record.update({
        "exists": True,
        "network_id": item.get("Id"),
        "driver": item.get("Driver"),
        "scope": item.get("Scope"),
        "internal": item.get("Internal"),
        "attachable": item.get("Attachable"),
        "compose_labels": compose_labels(item.get("Labels")),
        "attached_targets": sorted(attached, key=lambda row: row.get("name") or ""),
    })
    return record


def compose_projects() -> list[dict[str, Any]]:
    result = command(["docker", "compose", "ls", "--format", "json"])
    if result["returncode"] != 0 or not result["stdout"]:
        return []
    try:
        data = json.loads(result["stdout"])
    except json.JSONDecodeError:
        return []
    rows = data if isinstance(data, list) else [data]
    return sorted([
        {
            "name": row.get("Name"),
            "status": row.get("Status"),
            "config_files": row.get("ConfigFiles"),
        }
        for row in rows if isinstance(row, dict)
    ], key=lambda row: row.get("name") or "")


def compose_sha() -> str | None:
    path = RELEASE_ROOT / "docker-compose.yml"
    if not path.is_file():
        return None
    import hashlib
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    before = command(["docker", "ps", "--all", "--format", "{{json .}}"])
    containers = {name: inspect_container(name) for name in TARGET_CONTAINERS}
    images = {service: inspect_image(reference) for service, reference in EXPECTED_IMAGES.items()}

    volume_names = sorted({
        mount["name"]
        for container in containers.values()
        for mount in container.get("mounts", [])
        if mount.get("type") == "volume" and mount.get("name")
    })
    volumes = {name: inspect_volume(name) for name in volume_names}

    target_ids = {
        container["container_id"]
        for container in containers.values()
        if container.get("container_id")
    }
    network_names = sorted({
        network["name"]
        for container in containers.values()
        for network in container.get("networks", [])
        if network.get("name")
    })
    networks = {name: inspect_network(name, target_ids) for name in network_names}

    after = command(["docker", "ps", "--all", "--format", "{{json .}}"])
    containers_unchanged = before["returncode"] == 0 and before["stdout"] == after["stdout"]

    port_owners: dict[str, list[str]] = {}
    for name, container in containers.items():
        for port in container.get("ports", []):
            host_key = f"{port.get('host_ip')}:{port.get('host_port')}"
            port_owners.setdefault(host_key, []).append(name)

    compose_owners = {
        name: {
            "project": container.get("compose_labels", {}).get("com.docker.compose.project"),
            "service": container.get("compose_labels", {}).get("com.docker.compose.service"),
            "config_files": container.get("compose_labels", {}).get("com.docker.compose.project.config_files"),
            "working_dir": container.get("compose_labels", {}).get("com.docker.compose.project.working_dir"),
        }
        for name, container in containers.items()
    }

    errors = []
    if not shutil.which("docker"):
        errors.append("docker_unavailable")
    if any(not item.get("exists") for item in containers.values()):
        errors.append("target_container_missing")
    if any(not item.get("exists") for item in images.values()):
        errors.append("approved_image_missing")
    if compose_sha() != EXPECTED_COMPOSE_SHA:
        errors.append("release_compose_hash_mismatch")
    if not containers_unchanged:
        errors.append("container_inventory_changed_during_map")

    risks = []
    projects = {owner.get("project") for owner in compose_owners.values() if owner.get("project")}
    if len(projects) > 1:
        risks.append("target_containers_have_multiple_compose_owners")
    if any(not owner.get("project") for owner in compose_owners.values()):
        risks.append("one_or_more_target_containers_unmanaged")
    if any(len(owners) > 1 for owners in port_owners.values()):
        risks.append("duplicate_host_port_ownership")

    payload = {
        "alignment_stage": "2E-cutover-map",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "success" if not errors else "failed",
        "success": not errors,
        "release_root": str(RELEASE_ROOT),
        "release_compose_sha256": compose_sha(),
        "containers": containers,
        "approved_images": images,
        "compose_ownership": compose_owners,
        "active_compose_projects": compose_projects(),
        "volumes": volumes,
        "networks": networks,
        "port_owners": {key: sorted(value) for key, value in sorted(port_owners.items())},
        "rollback_manifest": {
            name: {
                "container_id": container.get("container_id"),
                "image_reference": container.get("image_reference"),
                "image_id": container.get("image_id"),
                "ports": container.get("ports", []),
                "mounts": container.get("mounts", []),
                "networks": container.get("networks", []),
                "restart_policy": container.get("restart_policy"),
                "compose_labels": container.get("compose_labels", {}),
            }
            for name, container in containers.items()
        },
        "collision_analysis": {
            "target_names_currently_occupied": sorted(name for name, item in containers.items() if item.get("exists")),
            "host_port_owners": {key: sorted(value) for key, value in sorted(port_owners.items())},
            "named_volumes_in_use": volume_names,
            "networks_in_use": network_names,
        },
        "containers_unchanged": containers_unchanged,
        "errors": errors,
        "risks": sorted(set(risks)),
        "safety": {
            "containers_started": False,
            "containers_stopped": False,
            "containers_recreated": False,
            "images_built": False,
            "volumes_changed": False,
            "networks_changed": False,
            "repositories_changed": False,
            "databases_changed": False,
            "dns_changed": False,
            "environment_values_collected": False,
            "commands_collected": False,
            "logs_collected": False,
            "secret_values_collected": False,
            "customer_data_collected": False,
        },
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
