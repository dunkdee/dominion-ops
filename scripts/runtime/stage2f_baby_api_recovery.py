#!/usr/bin/env python3
"""Recover Baby API after a failed Stage-2F rollback.

The failing original container is preserved locally under a unique stopped name.
The already-approved canonical Baby API image is started through the canonical
`dominion-ops` Compose project on the existing production network. Reports contain
only metadata and classified error signals—never logs, environment values, secrets,
or customer data.
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
OLD_CONTAINER_ID = "601c5388480132a0a5ef4584fcfff0dacb575db5f7001ad4f677d48a17a7d38a"
OLD_IMAGE_ID = "sha256:a319b3721a52e31c166c5a311301f656affef7f4acaeb4ff047c2cc971af000d"
NEW_IMAGE = "dominion-stage2d-r4-baby-api:latest"
NEW_IMAGE_ID = "sha256:089445475d96ca3630fd4821af3c0304d38de5ece89a529b3782a398e38c3c82"
FAILED_NAME = f"baby-api-failed-stage2f-{RUN_ID}"
RECOVERY_ROOT = Path("/var/lib/dominion/cutovers") / f"stage2f-baby-recovery-{RUN_ID}"

OTHER_HEALTH = (
    ("wix-agent", 8082, "/ready"),
    ("dominion-web", 8090, "/"),
    ("n8n", 5678, "/healthz"),
    ("alpha-engine", 8787, "/health"),
    ("conductor", 5060, "/health"),
)
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


def command(
    args: list[str],
    *,
    cwd: Path | None = None,
    timeout: int = 300,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Run a bounded command and retain output locally only."""
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
            "stderr": "",
            "error_type": type(exc).__name__,
        }
    return {
        "available": True,
        "returncode": result.returncode,
        "stdout": result.stdout or "",
        "stderr": result.stderr or "",
        "error_type": None,
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
    except Exception as exc:  # noqa: BLE001
        record["error_type"] = type(exc).__name__
    return record


def wait_http(port: int, path: str, timeout: int = 120) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if http_probe("baby-api", port, path).get("status") == 200:
            return True
        time.sleep(3)
    return False


def inspect_raw(name: str) -> dict[str, Any] | None:
    result = command(["docker", "inspect", name], timeout=60)
    if result["returncode"] != 0:
        return None
    try:
        rows = json.loads(result["stdout"])
    except json.JSONDecodeError:
        return None
    return rows[0] if rows else None


def sanitized_container(name: str) -> dict[str, Any]:
    data = inspect_raw(name)
    if not data:
        return {"name": name, "exists": False}
    state = data.get("State") or {}
    config = data.get("Config") or {}
    host = data.get("HostConfig") or {}
    labels = config.get("Labels") or {}
    networks = (data.get("NetworkSettings") or {}).get("Networks") or {}
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
        "state_error_present": bool(state.get("Error")),
        "restart_policy": (host.get("RestartPolicy") or {}).get("Name"),
        "compose_project": labels.get("com.docker.compose.project"),
        "compose_service": labels.get("com.docker.compose.service"),
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
            key=lambda item: (item.get("host_port") or "", item.get("container_port") or ""),
        ),
    }


def unit_state(unit: str) -> dict[str, Any]:
    result = command([
        "systemctl",
        "show",
        unit,
        "--property=LoadState,ActiveState,SubState,UnitFileState",
    ])
    record = {
        "unit": unit,
        "load_state": None,
        "active_state": None,
        "sub_state": None,
        "unit_file_state": None,
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
    return record


def classify_logs(name: str) -> dict[str, Any]:
    """Classify recent logs without emitting log text."""
    result = command(["docker", "logs", "--tail", "200", name], timeout=30)
    text = f"{result.get('stdout', '')}\n{result.get('stderr', '')}".lower()
    patterns = {
        "traceback": "traceback" in text,
        "module_not_found": "modulenotfounderror" in text,
        "import_error": "importerror" in text,
        "file_not_found": "filenotfounderror" in text or "no such file or directory" in text,
        "permission_denied": "permission denied" in text,
        "address_in_use": "address already in use" in text,
        "connection_refused": "connection refused" in text,
        "syntax_error": "syntaxerror" in text,
        "key_error": "keyerror" in text,
        "missing_environment": "environment variable" in text and ("missing" in text or "required" in text),
        "database_error": any(token in text for token in ("database error", "operationalerror", "psycopg")),
    }
    return {
        "available": result.get("returncode") == 0,
        "signals": patterns,
        "nonempty": bool(text.strip()),
    }


def container_fingerprints(exclude: set[str]) -> dict[str, dict[str, Any]]:
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
        }
    return rows


def write_override(path: Path) -> None:
    path.write_text(
        f"""services:\n  baby-api:\n    image: {NEW_IMAGE}\n\nnetworks:\n  default:\n    external: true\n    name: {NETWORK_NAME}\n""",
        encoding="utf-8",
    )
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


def fallback_original() -> dict[str, Any]:
    actions: list[dict[str, Any]] = []
    errors: list[str] = []
    command(["docker", "rm", "--force", "baby-api"], timeout=90)
    if command(["docker", "inspect", FAILED_NAME], timeout=30)["returncode"] != 0:
        errors.append("failed_original_missing")
        return {"success": False, "errors": errors, "actions": actions}
    rename = command(["docker", "rename", FAILED_NAME, "baby-api"], timeout=30)
    actions.append({"rename_original": rename["returncode"] == 0})
    if rename["returncode"] != 0:
        errors.append("fallback_rename_failed")
        return {"success": False, "errors": errors, "actions": actions}
    connect = command(["docker", "network", "connect", "--alias", "baby-api", NETWORK_NAME, "baby-api"], timeout=30)
    restored = sanitized_container("baby-api")
    if connect["returncode"] != 0 and not any(
        network.get("network_id") == NETWORK_ID for network in restored.get("networks", [])
    ):
        errors.append("fallback_network_failed")
    command(["docker", "update", "--restart=always", "baby-api"], timeout=30)
    start = command(["docker", "start", "baby-api"], timeout=90)
    actions.append({"start_original": start["returncode"] == 0})
    if start["returncode"] != 0:
        errors.append("fallback_start_failed")
    healthy = wait_http(8080, "/", timeout=60)
    if not healthy:
        errors.append("fallback_health_failed")
    return {
        "success": not errors,
        "errors": errors,
        "actions": actions,
        "health": http_probe("baby-api", 8080, "/"),
    }


def main() -> int:
    generated_at = datetime.now(timezone.utc)
    errors: list[str] = []
    risks: list[str] = []
    actions: list[dict[str, Any]] = []
    fallback_result: dict[str, Any] | None = None
    original_preserved = False

    if os.geteuid() != 0:
        print(json.dumps({"alignment_stage": "2F-baby-recovery", "status": "failed", "success": False, "errors": ["root_required"]}, indent=2))
        return 1

    compose_path = RELEASE_ROOT / "docker-compose.yml"
    env_path = RELEASE_ROOT / ".env"
    marker_path = RELEASE_ROOT / ".dominion-release.json"
    marker: dict[str, Any] = {}
    try:
        marker = json.loads(marker_path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        errors.append(f"release_marker_{type(exc).__name__}")

    if not compose_path.is_file() or sha256_file(compose_path) != EXPECTED_COMPOSE_SHA:
        errors.append("compose_hash_mismatch")
    if not env_path.is_file() or env_path.is_symlink() or sha256_file(env_path) != EXPECTED_ENV_SHA:
        errors.append("env_hash_mismatch")
    elif oct(env_path.stat().st_mode & 0o777) != "0o600":
        errors.append("env_mode_mismatch")
    if marker.get("source_sha") != APPROVED_SOURCE_SHA:
        errors.append("release_source_mismatch")

    image = command(["docker", "image", "inspect", NEW_IMAGE], timeout=30)
    if image["returncode"] != 0:
        errors.append("approved_image_missing")
    else:
        try:
            if json.loads(image["stdout"])[0].get("Id") != NEW_IMAGE_ID:
                errors.append("approved_image_id_mismatch")
        except (json.JSONDecodeError, IndexError):
            errors.append("approved_image_parse_failed")

    network = command(["docker", "network", "inspect", NETWORK_NAME], timeout=30)
    if network["returncode"] != 0:
        errors.append("production_network_missing")
    else:
        try:
            if json.loads(network["stdout"])[0].get("Id") != NETWORK_ID:
                errors.append("production_network_id_mismatch")
        except (json.JSONDecodeError, IndexError):
            errors.append("production_network_parse_failed")

    before = sanitized_container("baby-api")
    log_classification = classify_logs("baby-api") if before.get("exists") else {"available": False, "signals": {}, "nonempty": False}

    if before.get("image_id") == NEW_IMAGE_ID and before.get("running") and http_probe("baby-api", 8080, "/").get("status") == 200:
        success_payload = {
            "alignment_stage": "2F-baby-recovery",
            "generated_at": generated_at.isoformat(),
            "status": "success",
            "success": True,
            "already_recovered": True,
            "baby_api": before,
            "health": http_probe("baby-api", 8080, "/"),
            "errors": [],
            "risks": [],
        }
        print(json.dumps(success_payload, indent=2, sort_keys=True))
        return 0

    if not before.get("exists"):
        errors.append("baby_api_missing")
    elif before.get("container_id") != OLD_CONTAINER_ID:
        errors.append("baby_api_container_drift")
    elif before.get("image_id") != OLD_IMAGE_ID:
        errors.append("baby_api_image_drift")

    if command(["docker", "inspect", FAILED_NAME], timeout=15)["returncode"] == 0:
        errors.append("failed_preservation_name_occupied")

    retired = {unit: unit_state(unit) for unit in RETIRED_UNITS}
    timers = {unit: unit_state(unit) for unit in PUBLISHING_TIMERS}
    if any(item.get("load_state") != "masked" or item.get("active_state") == "active" for item in retired.values()):
        errors.append("retired_unit_governance_failed")
    if any(item.get("active_state") != "inactive" or item.get("unit_file_state") != "disabled" for item in timers.values()):
        errors.append("publishing_timer_governance_failed")

    other_health_before = [http_probe(*item) for item in OTHER_HEALTH]
    if any(item.get("status") != 200 for item in other_health_before):
        errors.append("other_protected_health_failed_before")

    excluded = {"baby-api", FAILED_NAME}
    unaffected_before = container_fingerprints(excluded)
    override_path = RECOVERY_ROOT / "baby-recovery.override.yml"

    try:
        if not errors:
            RECOVERY_ROOT.mkdir(mode=0o700, parents=True, exist_ok=False)
            inspect_path = RECOVERY_ROOT / "baby-api-before.inspect.json"
            inspect = command(["docker", "inspect", "baby-api"], timeout=60)
            if inspect["returncode"] != 0:
                raise RuntimeError("inspect_backup_failed")
            inspect_path.write_text(inspect["stdout"], encoding="utf-8")
            os.chmod(inspect_path, 0o600)
            write_override(override_path)

            stop = command(["docker", "stop", "--time", "20", "baby-api"], timeout=60)
            if stop["returncode"] != 0:
                raise RuntimeError("stop_failed")
            rename = command(["docker", "rename", "baby-api", FAILED_NAME], timeout=30)
            if rename["returncode"] != 0:
                command(["docker", "start", "baby-api"], timeout=90)
                raise RuntimeError("rename_failed")
            original_preserved = True
            actions.append({"original_renamed": FAILED_NAME})
            policy = command(["docker", "update", "--restart=no", FAILED_NAME], timeout=30)
            if policy["returncode"] != 0:
                raise RuntimeError("freeze_original_failed")
            disconnect = command(["docker", "network", "disconnect", "--force", NETWORK_NAME, FAILED_NAME], timeout=30)
            if disconnect["returncode"] != 0:
                raise RuntimeError("disconnect_original_failed")

            compose = compose_base(override_path)
            config = command(compose + ["config", "--quiet"], cwd=RELEASE_ROOT, timeout=60)
            if config["returncode"] != 0:
                raise RuntimeError("recovery_compose_invalid")
            up = command(
                compose + ["up", "-d", "--no-deps", "--no-build", "--force-recreate", "baby-api"],
                cwd=RELEASE_ROOT,
                timeout=300,
            )
            if up["returncode"] != 0:
                raise RuntimeError("canonical_start_failed")
            actions.append({"canonical_started": True})
            if not wait_http(8080, "/", timeout=120):
                raise RuntimeError("canonical_health_failed")

            recovered = sanitized_container("baby-api")
            mounts = {item.get("destination"): item for item in recovered.get("mounts", [])}
            public_8080 = any(
                item.get("host_port") == "8080" and item.get("container_port") == "8080/tcp"
                for item in recovered.get("ports", [])
            )
            if recovered.get("image_id") != NEW_IMAGE_ID:
                raise RuntimeError("canonical_image_failed")
            if recovered.get("compose_project") != PROJECT_NAME or recovered.get("compose_service") != "baby-api":
                raise RuntimeError("canonical_ownership_failed")
            if not any(item.get("network_id") == NETWORK_ID for item in recovered.get("networks", [])):
                raise RuntimeError("canonical_network_failed")
            if mounts.get("/app", {}).get("source") != str(RELEASE_ROOT / "api"):
                raise RuntimeError("canonical_app_mount_failed")
            if mounts.get("/vault", {}).get("source") != "/home/malachisingleton8/vault":
                raise RuntimeError("canonical_vault_mount_failed")
            if not public_8080:
                raise RuntimeError("canonical_port_failed")

            time.sleep(60)
            if http_probe("baby-api", 8080, "/").get("status") != 200:
                raise RuntimeError("canonical_stability_failed")
    except Exception as exc:  # noqa: BLE001
        errors.append(f"recovery_{type(exc).__name__}:{exc}")

    if errors and original_preserved:
        fallback_result = fallback_original()

    after = sanitized_container("baby-api")
    other_health_after = [http_probe(*item) for item in OTHER_HEALTH]
    unaffected_after = container_fingerprints(excluded)
    unaffected_unchanged = unaffected_before == unaffected_after

    if not errors:
        if http_probe("baby-api", 8080, "/").get("status") != 200:
            errors.append("baby_api_postcheck_failed")
        if any(item.get("status") != 200 for item in other_health_after):
            errors.append("other_protected_health_failed_after")
        if not unaffected_unchanged:
            errors.append("unaffected_container_identity_changed")

    success = not errors and after.get("image_id") == NEW_IMAGE_ID and after.get("running")
    payload = {
        "alignment_stage": "2F-baby-recovery",
        "generated_at": generated_at.isoformat(),
        "status": "success" if success else "failed",
        "success": success,
        "approved_source_sha": APPROVED_SOURCE_SHA,
        "release_root": str(RELEASE_ROOT),
        "recovery_root": str(RECOVERY_ROOT),
        "failed_original_name": FAILED_NAME if original_preserved else None,
        "before": before,
        "after": after,
        "log_classification": log_classification,
        "other_health_before": other_health_before,
        "other_health_after": other_health_after,
        "unaffected_containers_unchanged": unaffected_unchanged,
        "actions": actions,
        "fallback_result": fallback_result,
        "errors": errors,
        "risks": risks,
        "governance": {"retired_units": retired, "publishing_timers": timers},
        "safety": {
            "failing_original_deleted": False,
            "failing_original_preserved_locally": original_preserved,
            "only_baby_api_changed": True,
            "databases_changed": False,
            "dns_changed": False,
            "network_definition_changed": False,
            "existing_network_reused": True,
            "volumes_changed": False,
            "secret_values_collected": False,
            "secret_file_uploaded": False,
            "raw_logs_collected_in_report": False,
            "full_inspect_saved_locally_only": True,
            "repository_checkout_changed": False,
        },
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
