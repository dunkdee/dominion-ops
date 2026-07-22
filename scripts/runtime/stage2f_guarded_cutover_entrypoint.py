#!/usr/bin/env python3
"""Safety entrypoint for the Stage-2F guarded cutover engine.

It adds five controls without duplicating the underlying cutover logic:
1. a failed old-container rename immediately restarts the original container;
2. stopped rollback containers are disconnected from the production network so
   their old service aliases cannot compete with the new containers;
3. rollback reconnects the exact service aliases before originals are started;
4. target port bindings are treated as a hard container-health contract;
5. Wix data and logs receive local quiescent snapshots before the new image starts,
   and Wix data is restored before the original container starts during rollback.
"""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
import shutil
import tarfile
from pathlib import Path

import stage2f_guarded_cutover as engine

_ORIGINAL_COMMAND = engine.command
_ORIGINAL_SANITIZED = engine.sanitized_container
CUTOVER_ROOT = Path("/var/lib/dominion/cutovers") / f"stage2f-{engine.RUN_ID}"
WIX_DATA_SOURCE = Path("/var/lib/docker/volumes") / engine.WIX_DATA_VOLUME / "_data"
WIX_LOGS_SOURCE = Path("/var/lib/docker/volumes") / engine.WIX_LOGS_VOLUME / "_data"
WIX_DATA_ARCHIVE = CUTOVER_ROOT / "wix-data-before-cutover.tar.gz"
WIX_LOGS_ARCHIVE = CUTOVER_ROOT / "wix-logs-before-cutover.tar.gz"
WIX_DATA_RESTORED = False

PORT_CONTRACTS = {
    "baby-api": {("public", "8080", "8080/tcp")},
    "dominion-web": {("public", "8090", "80/tcp")},
    "wix-agent": {("loopback", "8082", "8000/tcp")},
    "baby-logger": set(),
}


def sha256_file(path):
    """Return a bounded-file SHA-256 without exposing contents."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def binding_scope(host_ip):
    """Normalize equivalent Docker host-bind representations."""
    if host_ip in {"127.0.0.1", "::1"}:
        return "loopback"
    return "public"


def archive_volume(source, archive):
    """Create a root-only local archive of a stopped volume."""
    source = Path(source)
    archive = Path(archive)
    if not source.is_dir() or not CUTOVER_ROOT.is_dir():
        raise RuntimeError("volume_backup_precondition_failed")
    with tarfile.open(archive, "w:gz") as handle:
        handle.add(source, arcname=".", recursive=True)
    os.chmod(archive, 0o600)
    if not archive.is_file() or archive.stat().st_size <= 0:
        raise RuntimeError("volume_backup_empty")


def backup_wix_volumes():
    """Snapshot Wix volumes only after the container is stopped."""
    archive_volume(WIX_DATA_SOURCE, WIX_DATA_ARCHIVE)
    archive_volume(WIX_LOGS_SOURCE, WIX_LOGS_ARCHIVE)


def safe_restore_wix_data():
    """Restore the quiescent Wix data archive without path traversal."""
    global WIX_DATA_RESTORED
    if not WIX_DATA_ARCHIVE.is_file() or not WIX_DATA_SOURCE.is_dir():
        raise RuntimeError("wix_data_restore_precondition_failed")

    destination = WIX_DATA_SOURCE.resolve()
    with tarfile.open(WIX_DATA_ARCHIVE, "r:gz") as handle:
        members = handle.getmembers()
        for member in members:
            if member.issym() or member.islnk():
                raise RuntimeError("wix_data_restore_link_rejected")
            target = (destination / member.name).resolve()
            if target != destination and destination not in target.parents:
                raise RuntimeError("wix_data_restore_path_escape")

        for child in destination.iterdir():
            if child.is_dir() and not child.is_symlink():
                shutil.rmtree(child)
            else:
                child.unlink()
        handle.extractall(destination)

    WIX_DATA_RESTORED = True


def guarded_command(args, *, cwd=None, timeout=300, env=None):
    """Add rename recovery, volume snapshots, and network isolation."""
    result = _ORIGINAL_COMMAND(args, cwd=cwd, timeout=timeout, env=env)

    if (
        result.get("returncode") != 0
        and len(args) == 4
        and args[:2] == ["docker", "rename"]
        and args[2] in engine.TARGETS
        and "-rollback-stage2f-" in args[3]
    ):
        _ORIGINAL_COMMAND(["docker", "start", args[2]], timeout=90)

    if (
        result.get("returncode") == 0
        and len(args) == 5
        and args[:4] == ["docker", "stop", "--time", "20"]
        and args[4] == "wix-agent"
    ):
        try:
            backup_wix_volumes()
        except Exception as exc:  # noqa: BLE001 - return only the type
            _ORIGINAL_COMMAND(["docker", "start", "wix-agent"], timeout=90)
            return {
                "available": True,
                "returncode": 1,
                "stdout": "",
                "stderr_type": f"wix_volume_backup_{type(exc).__name__}",
            }

    if (
        result.get("returncode") == 0
        and len(args) == 4
        and args[:3] == ["docker", "update", "--restart=no"]
    ):
        rollback_name = args[3]
        if "-rollback-stage2f-" in rollback_name:
            disconnect = _ORIGINAL_COMMAND(
                ["docker", "network", "disconnect", "--force", engine.NETWORK_NAME, rollback_name],
                timeout=30,
            )
            if disconnect.get("returncode") != 0:
                return {
                    "available": True,
                    "returncode": 1,
                    "stdout": "",
                    "stderr_type": "rollback_network_disconnect_failed",
                }
    return result


def guarded_sanitized(name):
    """Mark a target unhealthy when its host-port contract is not exact."""
    item = _ORIGINAL_SANITIZED(name)
    if name in PORT_CONTRACTS and item.get("exists"):
        actual = {
            (
                binding_scope(port.get("host_ip")),
                port.get("host_port") or "",
                port.get("container_port") or "",
            )
            for port in item.get("ports", [])
        }
        valid = actual == PORT_CONTRACTS[name]
        item["port_contract_valid"] = valid
        if not valid:
            item["running"] = False
    return item


def guarded_rollback(migrated, rollback_names):
    """Restore names, data, aliases, restart policies, and health."""
    actions = []
    errors = []
    for service in reversed(migrated):
        remove = _ORIGINAL_COMMAND(["docker", "rm", "--force", service], timeout=90)
        actions.append({"service": service, "new_removed": remove.get("returncode") == 0})

    for service in reversed(migrated):
        rollback_name = rollback_names[service]
        rename = _ORIGINAL_COMMAND(["docker", "rename", rollback_name, service], timeout=30)
        if rename.get("returncode") != 0:
            errors.append(f"rollback_rename_failed:{service}")
            continue

        if service == "wix-agent":
            try:
                safe_restore_wix_data()
            except Exception as exc:  # noqa: BLE001 - report only the type
                errors.append(f"rollback_wix_data_restore_{type(exc).__name__}")

        connect_args = ["docker", "network", "connect"]
        if service in {"baby-api", "baby-logger", "dominion-web"}:
            connect_args.extend(["--alias", service])
        connect_args.extend([engine.NETWORK_NAME, service])
        connect = _ORIGINAL_COMMAND(connect_args, timeout=30)
        if connect.get("returncode") != 0:
            restored = _ORIGINAL_SANITIZED(service)
            if not any(network.get("network_id") == engine.NETWORK_ID for network in restored.get("networks", [])):
                errors.append(f"rollback_network_connect_failed:{service}")
                continue

        policy = _ORIGINAL_COMMAND(
            ["docker", "update", f"--restart={engine.TARGETS[service]['restart']}", service],
            timeout=30,
        )
        start = _ORIGINAL_COMMAND(["docker", "start", service], timeout=90)
        if policy.get("returncode") != 0 or start.get("returncode") != 0:
            errors.append(f"rollback_start_failed:{service}")
            continue

        health = engine.TARGETS[service]["health"]
        if health and not engine.wait_http(health[0], health[1], timeout=90):
            errors.append(f"rollback_health_failed:{service}")

    final_health = [engine.http_probe(*item) for item in engine.PROTECTED_HTTP]
    if any(item.get("status") != 200 for item in final_health):
        errors.append("rollback_protected_http_failed")
    return {
        "success": not errors,
        "errors": errors,
        "actions": actions,
        "health": final_health,
        "wix_data_restored": WIX_DATA_RESTORED,
    }


def backup_metadata():
    """Return hashes and sizes only; archive contents remain local."""
    records = {}
    for label, path in {
        "wix_data": WIX_DATA_ARCHIVE,
        "wix_logs": WIX_LOGS_ARCHIVE,
    }.items():
        if path.is_file():
            records[label] = {
                "path": str(path),
                "size_bytes": path.stat().st_size,
                "sha256": sha256_file(path),
                "mode": oct(path.stat().st_mode & 0o777),
            }
    return records


def run_main():
    """Enrich the engine report with local snapshot metadata."""
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        returncode = engine.main()
    raw = buffer.getvalue().strip()
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        print(raw)
        return returncode
    payload["local_volume_backups"] = backup_metadata()
    payload.setdefault("safety", {})["wix_volume_archives_uploaded"] = False
    payload["safety"]["wix_volume_contents_collected_in_report"] = False
    print(json.dumps(payload, indent=2, sort_keys=True))
    return returncode


engine.command = guarded_command
engine.sanitized_container = guarded_sanitized
engine.rollback = guarded_rollback

if __name__ == "__main__":
    raise SystemExit(run_main())
