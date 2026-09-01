"""Governed self-healing for Buddy and core Dominion runtime services.

The repair engine is recipe-based. It can diagnose every connector in the
reviewed read-only MCP fabric and repair routine internal, reversible faults
covered by the Founder's standing authorization. It never accepts arbitrary
shell commands, service names, container names, URLs, or privileged policy
changes from a prompt.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

try:
    from core import mcp_client
except ImportError:
    from buddy_core.core import mcp_client

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config"
AUTH_FILE = CONFIG / "standing_authorizations.json"
STATE = Path(os.getenv("BUDDY_STATE_DIR", str(Path.home() / ".dominion" / "buddy")))
REPO = Path(os.getenv("DOMINION_REPO_ROOT", str(Path.home() / "dominion-ops"))).expanduser()
RUNTIME = Path(os.getenv("BUDDY_RUNTIME_ROOT", str(Path.home() / "buddy_core"))).expanduser()
SELF_HEAL_STATE = STATE / "self-heal"

# Fixed reviewed systemd targets. No prompt text can become a unit name.
SERVICE_RECIPES: dict[str, dict[str, Any]] = {
    "buddy_web": {
        "unit": "dominion-buddy-web.service",
        "health": "http://127.0.0.1:5070/buddy",
        "accepted_http": {200, 401, 403},
    },
    "buddy_bridge": {
        "unit": "buddy-bridge.service",
        "health": "http://127.0.0.1:5052/health",
        "accepted_http": {200},
    },
    "mcp_cli": {
        "unit": "dominion-mcp-cli.service",
        "health": "http://127.0.0.1:8390/health",
        "accepted_http": {200},
    },
    "conductor": {
        "unit": "dominion-conductor.service",
        "health": "http://127.0.0.1:5060/health",
        "accepted_http": {200},
    },
    "alpha": {
        "unit": "dominion-alpha.service",
        "health": "http://127.0.0.1:8787/health",
        "accepted_http": {200},
    },
    "revenue_runtime": {
        "unit": "dominion-revenue-runtime.service",
        "health": None,
        "accepted_http": set(),
    },
    "radah_autopilot": {
        "unit": "dominion-radah-autopilot.timer",
        "health": None,
        "accepted_http": set(),
    },
}

# Fixed reviewed Docker targets. These are canonical container names already
# used by Dominion deployment/runtime evidence. No dynamic name is accepted.
CONTAINER_RECIPES: dict[str, dict[str, Any]] = {
    "command_center": {
        "container": "dominion-command-center",
        "health": "http://127.0.0.1:8091/health",
        "accepted_http": {200},
    },
    "dominion_web": {
        "container": "dominion-web",
        "health": "http://127.0.0.1:8090/",
        "accepted_http": {200},
    },
    "n8n": {
        "container": "n8n",
        "health": "http://127.0.0.1:5678/healthz",
        "accepted_http": {200},
    },
    "wix_agent": {
        "container": "wix-agent",
        "health": "http://127.0.0.1:8082/ready",
        "accepted_http": {200},
    },
}

# Every connector in governance/mcp_connector_registry.json maps to a reviewed
# repair target. This lets diagnosis cover the whole current connector fabric.
MCP_REPAIR_MAP: dict[str, tuple[str, str]] = {
    "alpha_engine_health": ("service", "alpha"),
    "command_center_status": ("container", "command_center"),
    "conductor_health": ("service", "conductor"),
    "dominion_web_health": ("container", "dominion_web"),
    "n8n_health": ("container", "n8n"),
    "radah_autopilot_timer": ("service", "radah_autopilot"),
    "revenue_runtime_service": ("service", "revenue_runtime"),
    "wix_agent_health": ("container", "wix_agent"),
}

# Canonical source only. Runtime data, generated media, logs, .env, credentials,
# and durable evidence are deliberately excluded.
TRACKED_RUNTIME_FILES = (
    "core/__init__.py",
    "core/brain.py",
    "core/brain_router.py",
    "core/operator.py",
    "core/operator_extensions.py",
    "core/learning_engine.py",
    "core/autonomous_learning.py",
    "core/revenue_runtime.py",
    "core/capability_health.py",
    "core/mcp_client.py",
    "core/self_heal.py",
    "config/capability_registry.json",
    "config/capability_extensions.json",
    "config/BUDDY_CONSTITUTION.md",
    "config/FOUNDER_OPERATING_CONTEXT.md",
    "config/standing_authorizations.json",
    "buddy_bridge_api.py",
    "buddy_web.py",
)

PROTECTED_GOVERNANCE_FILES = {
    "config/BUDDY_CONSTITUTION.md",
    "config/standing_authorizations.json",
}


class SelfHealError(RuntimeError):
    pass


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def _run(argv: list[str], timeout: int = 20) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv,
        shell=False,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
        env={"PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin")},
    )


def _service_exists(unit: str) -> bool:
    cp = _run(["systemctl", "cat", unit], timeout=8)
    return cp.returncode == 0


def _service_active(unit: str) -> bool:
    cp = _run(["systemctl", "is-active", "--quiet", unit], timeout=8)
    return cp.returncode == 0


def _restart_service(unit: str) -> dict[str, Any]:
    cp = _run(["sudo", "-n", "systemctl", "restart", unit], timeout=30)
    active = _service_active(unit) if cp.returncode == 0 else False
    return {
        "unit": unit,
        "returncode": cp.returncode,
        "active": active,
        "stderr": cp.stderr[-500:] if cp.stderr else "",
    }


def _container_exists(name: str) -> bool:
    cp = _run(["docker", "inspect", name], timeout=10)
    return cp.returncode == 0


def _container_running(name: str) -> bool:
    cp = _run(["docker", "inspect", "--format", "{{.State.Running}}", name], timeout=10)
    return cp.returncode == 0 and cp.stdout.strip().lower() == "true"


def _restart_container(name: str) -> dict[str, Any]:
    cp = _run(["docker", "restart", name], timeout=45)
    running = _container_running(name) if cp.returncode == 0 else False
    return {
        "container": name,
        "returncode": cp.returncode,
        "running": running,
        "stderr": cp.stderr[-500:] if cp.stderr else "",
    }


def _probe(url: str | None, accepted: set[int]) -> dict[str, Any]:
    if not url:
        return {"configured": False, "healthy": None}
    if not (url.startswith("http://127.0.0.1:") or url.startswith("http://localhost:")):
        return {"configured": True, "healthy": False, "error": "non_loopback_health_url"}
    try:
        response = requests.get(url, timeout=4, allow_redirects=False)
        return {
            "configured": True,
            "healthy": response.status_code in accepted,
            "http_status": response.status_code,
        }
    except requests.RequestException as exc:
        return {"configured": True, "healthy": False, "error": type(exc).__name__}


def _load_authorization() -> dict[str, Any]:
    try:
        data = json.loads(AUTH_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError) as exc:
        raise SelfHealError(f"standing_authorization_unavailable:{type(exc).__name__}") from exc
    for auth in data.get("authorizations", []):
        if auth.get("id") == "founder-safe-internal-self-heal-v1" and auth.get("status") == "ACTIVE":
            return auth
    raise SelfHealError("safe_internal_self_heal_not_authorized")


def _repo_state() -> dict[str, Any]:
    if not (REPO / ".git").is_dir():
        return {"available": False, "reason": "canonical_repo_missing"}
    head = _run(["git", "-C", str(REPO), "rev-parse", "HEAD"], timeout=8)
    branch = _run(["git", "-C", str(REPO), "branch", "--show-current"], timeout=8)
    dirty = _run(
        ["git", "-C", str(REPO), "status", "--porcelain", "--untracked-files=no"],
        timeout=10,
    )
    return {
        "available": head.returncode == 0,
        "head": head.stdout.strip() if head.returncode == 0 else None,
        "branch": branch.stdout.strip() if branch.returncode == 0 else None,
        "tracked_dirty": bool(dirty.stdout.strip()) if dirty.returncode == 0 else None,
    }


def _source_state() -> dict[str, Any]:
    rows = []
    for rel in TRACKED_RUNTIME_FILES:
        repo_file = REPO / "buddy_core" / rel
        runtime_file = RUNTIME / rel
        repo_sha = _sha(repo_file)
        runtime_sha = _sha(runtime_file)
        rows.append(
            {
                "path": rel,
                "repo_sha256": repo_sha,
                "runtime_sha256": runtime_sha,
                "match": bool(repo_sha) and repo_sha == runtime_sha,
                "protected_governance": rel in PROTECTED_GOVERNANCE_FILES,
            }
        )
    mismatches = [row["path"] for row in rows if not row["match"]]
    return {"checked": len(rows), "mismatches": mismatches, "files": rows}


def _mcp_result_healthy(payload: dict[str, Any]) -> tuple[bool, str]:
    """Interpret a read-only MCP result without retaining response bodies."""
    if payload.get("status") != "PASS":
        return False, "mcp_status_not_pass"
    result = payload.get("result")
    if not isinstance(result, dict):
        return False, "mcp_result_missing"
    if "returncode" in result:
        try:
            return int(result.get("returncode")) == 0, "exec_returncode"
        except (TypeError, ValueError):
            return False, "exec_returncode_invalid"
    if "status" in result:
        try:
            status = int(result.get("status"))
        except (TypeError, ValueError):
            return False, "http_status_invalid"
        return 200 <= status < 400, "http_status"
    return True, "pass_contract"


def _mcp_connector_state() -> dict[str, Any]:
    """Probe every currently registered MCP connector and retain only metadata."""
    try:
        registry = mcp_client.list_connectors()
    except Exception as exc:
        return {
            "available": False,
            "error": type(exc).__name__,
            "registered": 0,
            "healthy": 0,
            "failed": 0,
            "connectors": [],
        }

    connectors = registry.get("connectors", [])
    rows: list[dict[str, Any]] = []
    for item in connectors:
        if not isinstance(item, dict) or not item.get("id"):
            continue
        connector_id = str(item["id"])
        row = {
            "id": connector_id,
            "adapter": item.get("adapter"),
            "effect": item.get("effect"),
        }
        try:
            result = mcp_client.invoke(connector_id, {})
            healthy, evidence_kind = _mcp_result_healthy(result)
            row.update(
                {
                    "healthy": healthy,
                    "status": "PASS" if healthy else "FAIL",
                    "elapsed_ms": result.get("elapsed_ms"),
                    "evidence_kind": evidence_kind,
                }
            )
        except Exception as exc:
            row.update(
                {
                    "healthy": False,
                    "status": "FAIL",
                    "error": type(exc).__name__,
                }
            )
        rows.append(row)

    failed = sum(1 for row in rows if row.get("healthy") is False)
    return {
        "available": True,
        "registered": len(rows),
        "healthy": len(rows) - failed,
        "failed": failed,
        "all_healthy": bool(rows) and failed == 0,
        "connectors": rows,
    }


def diagnose() -> dict[str, Any]:
    """Diagnose Buddy and all currently registered governed runtime signals."""
    disk = shutil.disk_usage(Path.home())
    services: dict[str, Any] = {}
    containers: dict[str, Any] = {}
    issues: list[dict[str, Any]] = []

    for name, recipe in SERVICE_RECIPES.items():
        unit = recipe["unit"]
        exists = _service_exists(unit)
        active = _service_active(unit) if exists else False
        probe = _probe(recipe.get("health"), set(recipe.get("accepted_http", set())))
        health_ok = probe.get("healthy")
        healthy = active if health_ok is None else bool(active and health_ok)
        services[name] = {
            "unit": unit,
            "exists": exists,
            "active": active,
            "probe": probe,
            "healthy": healthy if exists else None,
        }
        if exists and healthy is False:
            issues.append(
                {
                    "id": f"service:{name}",
                    "repair": "restart_allowlisted_service",
                    "target_kind": "service",
                    "target": name,
                }
            )

    for name, recipe in CONTAINER_RECIPES.items():
        container = recipe["container"]
        exists = _container_exists(container)
        running = _container_running(container) if exists else False
        probe = _probe(recipe.get("health"), set(recipe.get("accepted_http", set())))
        health_ok = probe.get("healthy")
        healthy = running if health_ok is None else bool(running and health_ok)
        containers[name] = {
            "container": container,
            "exists": exists,
            "running": running,
            "probe": probe,
            "healthy": healthy if exists else None,
        }
        if exists and healthy is False:
            issues.append(
                {
                    "id": f"container:{name}",
                    "repair": "restart_allowlisted_container",
                    "target_kind": "container",
                    "target": name,
                }
            )

    try:
        mcp = mcp_client.health()
        mcp_state = {"healthy": True, "detail": mcp}
        connector_state = _mcp_connector_state()
    except Exception as exc:
        mcp_state = {"healthy": False, "error": type(exc).__name__}
        connector_state = {
            "available": False,
            "error": "mcp_server_unhealthy",
            "registered": 0,
            "healthy": 0,
            "failed": 0,
            "connectors": [],
        }
        issues.append(
            {
                "id": "mcp:unhealthy",
                "repair": "restart_mcp_cli",
                "target_kind": "service",
                "target": "mcp_cli",
            }
        )

    for row in connector_state.get("connectors", []):
        if row.get("healthy") is not False:
            continue
        connector_id = str(row.get("id") or "")
        target = MCP_REPAIR_MAP.get(connector_id)
        if target is None:
            issues.append(
                {
                    "id": f"mcp_connector:{connector_id}",
                    "repair": "diagnosis_only_no_auto_recipe",
                }
            )
            continue
        target_kind, target_name = target
        issues.append(
            {
                "id": f"mcp_connector:{connector_id}",
                "repair": (
                    "restart_allowlisted_service"
                    if target_kind == "service"
                    else "restart_allowlisted_container"
                ),
                "target_kind": target_kind,
                "target": target_name,
            }
        )

    repo = _repo_state()
    source = _source_state() if repo.get("available") else {"checked": 0, "mismatches": [], "files": []}
    mutable_mismatches = [
        rel for rel in source.get("mismatches", []) if rel not in PROTECTED_GOVERNANCE_FILES
    ]
    protected_mismatches = [
        rel for rel in source.get("mismatches", []) if rel in PROTECTED_GOVERNANCE_FILES
    ]
    if mutable_mismatches:
        issues.append(
            {
                "id": "source:runtime_drift",
                "repair": "restore_tracked_runtime_source",
                "files": mutable_mismatches,
            }
        )
    if protected_mismatches:
        issues.append(
            {
                "id": "source:protected_governance_drift",
                "repair": "fresh_founder_review_required",
                "files": protected_mismatches,
            }
        )

    free_bytes = disk.free
    if free_bytes < 256 * 1024 * 1024:
        issues.append({"id": "disk:critically_low", "repair": "cleanup_disposable_buddy_artifacts"})
    elif free_bytes < 1024 * 1024 * 1024:
        issues.append({"id": "disk:low", "repair": "cleanup_disposable_buddy_artifacts"})

    return {
        "schema": "dominion-buddy-self-diagnosis-v2",
        "observed_at": _utc(),
        "repo": repo,
        "runtime_root": str(RUNTIME),
        "disk": {
            "total_bytes": disk.total,
            "used_bytes": disk.used,
            "free_bytes": free_bytes,
            "free_percent": round((free_bytes / disk.total) * 100, 2) if disk.total else 0.0,
        },
        "services": services,
        "containers": containers,
        "mcp": mcp_state,
        "mcp_connectors": connector_state,
        "source": source,
        "issues": issues,
        "healthy": not issues,
    }


def _cleanup_disposable() -> dict[str, Any]:
    removed: list[str] = []
    freed = 0
    backups = STATE / "deploy-backups"
    if backups.is_dir():
        for path in backups.glob("*.tgz"):
            try:
                size = path.stat().st_size
                path.unlink()
                removed.append(str(path))
                freed += size
            except OSError:
                continue
    if RUNTIME.is_dir():
        for path in RUNTIME.rglob("__pycache__"):
            if not path.is_dir() or path.is_symlink():
                continue
            try:
                size = sum(p.stat().st_size for p in path.rglob("*") if p.is_file())
                shutil.rmtree(path)
                removed.append(str(path))
                freed += size
            except OSError:
                continue
    return {"removed": removed, "freed_bytes": freed}


def _snapshot_runtime_files(files: list[str]) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = SELF_HEAL_STATE / "backups" / stamp
    (backup / "files").mkdir(parents=True, exist_ok=False)
    absent = []
    for rel in files:
        live = RUNTIME / rel
        if live.is_file():
            dst = backup / "files" / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(live, dst)
        else:
            absent.append(rel)
    (backup / "absent.json").write_text(json.dumps(absent, sort_keys=True), encoding="utf-8")
    return backup


def _restore_snapshot(backup: Path) -> None:
    files = backup / "files"
    if files.is_dir():
        for src in files.rglob("*"):
            if not src.is_file():
                continue
            rel = src.relative_to(files)
            dst = RUNTIME / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
    absent_file = backup / "absent.json"
    if absent_file.is_file():
        for rel in json.loads(absent_file.read_text(encoding="utf-8")):
            target = RUNTIME / rel
            if target.is_file() or target.is_symlink():
                target.unlink()


def _restore_tracked_source(files: list[str]) -> dict[str, Any]:
    disallowed = sorted(set(files) & PROTECTED_GOVERNANCE_FILES)
    if disallowed:
        raise SelfHealError(f"protected_governance_requires_fresh_authorization:{','.join(disallowed)}")
    repo = _repo_state()
    if not repo.get("available") or repo.get("branch") != "main" or repo.get("tracked_dirty") is not False:
        raise SelfHealError("canonical_repo_not_clean_main")
    available = []
    for rel in files:
        src = REPO / "buddy_core" / rel
        if not src.is_file():
            raise SelfHealError(f"canonical_source_missing:{rel}")
        available.append(rel)
    backup = _snapshot_runtime_files(available)
    try:
        for rel in available:
            src = REPO / "buddy_core" / rel
            dst = RUNTIME / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
        compile_files = [str(RUNTIME / rel) for rel in available if rel.endswith(".py")]
        if compile_files:
            cp = _run(["python3", "-m", "py_compile", *compile_files], timeout=30)
            if cp.returncode != 0:
                raise SelfHealError("restored_source_compile_failed")
    except Exception:
        _restore_snapshot(backup)
        raise
    return {"restored": available, "backup": str(backup), "repo_head": repo.get("head")}


def _write_receipt(payload: dict[str, Any]) -> str:
    receipts = SELF_HEAL_STATE / "receipts"
    receipts.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    path = receipts / f"{stamp}-repair.json"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    os.chmod(path, 0o600)
    return str(path)


def repair_safe() -> dict[str, Any]:
    """Apply only standing-authorized reversible repair recipes."""
    auth = _load_authorization()
    before = diagnose()
    actions: list[dict[str, Any]] = []
    rollback_snapshot: Path | None = None
    restarted_services: set[str] = set()
    restarted_containers: set[str] = set()

    try:
        issue_ids = {row.get("id") for row in before.get("issues", [])}
        if "disk:critically_low" in issue_ids or "disk:low" in issue_ids:
            actions.append(
                {
                    "action": "cleanup_disposable_buddy_artifacts",
                    "result": _cleanup_disposable(),
                }
            )

        drift = next(
            (row for row in before.get("issues", []) if row.get("id") == "source:runtime_drift"),
            None,
        )
        if drift:
            result = _restore_tracked_source(list(drift.get("files") or []))
            rollback_snapshot = Path(result["backup"])
            actions.append({"action": "restore_tracked_runtime_source", "result": result})

        # Correlate both direct health failures and MCP connector failures to
        # the fixed reviewed repair targets, de-duplicating repeated evidence.
        for issue in before.get("issues", []):
            repair = issue.get("repair")
            target_kind = issue.get("target_kind")
            target = issue.get("target")
            if repair == "restart_allowlisted_service" and target_kind == "service":
                if target in SERVICE_RECIPES and target not in restarted_services:
                    unit = SERVICE_RECIPES[target]["unit"]
                    result = _restart_service(unit)
                    restarted_services.add(target)
                    actions.append(
                        {
                            "action": "restart_allowlisted_service",
                            "service": target,
                            "trigger": issue.get("id"),
                            "result": result,
                        }
                    )
            elif repair == "restart_allowlisted_container" and target_kind == "container":
                if target in CONTAINER_RECIPES and target not in restarted_containers:
                    container = CONTAINER_RECIPES[target]["container"]
                    result = _restart_container(container)
                    restarted_containers.add(target)
                    actions.append(
                        {
                            "action": "restart_allowlisted_container",
                            "container": target,
                            "trigger": issue.get("id"),
                            "result": result,
                        }
                    )

        if before.get("mcp", {}).get("healthy") is False and "mcp_cli" not in restarted_services:
            result = _restart_service(SERVICE_RECIPES["mcp_cli"]["unit"])
            restarted_services.add("mcp_cli")
            actions.append(
                {
                    "action": "restart_mcp_cli",
                    "service": "mcp_cli",
                    "result": result,
                }
            )

        after = diagnose()
        held = [
            row for row in after.get("issues", [])
            if row.get("repair") == "fresh_founder_review_required"
        ]
        unresolved = [
            row for row in after.get("issues", [])
            if row.get("repair") != "fresh_founder_review_required"
        ]
        if unresolved:
            status = "BLOCKED"
        elif held:
            status = "HELD"
        elif actions:
            status = "REPAIRED"
        else:
            status = "HEALTHY"

        if status == "BLOCKED" and rollback_snapshot is not None:
            _restore_snapshot(rollback_snapshot)
            actions.append(
                {
                    "action": "rollback_tracked_runtime_source",
                    "backup": str(rollback_snapshot),
                }
            )
            for name in ("buddy_web", "buddy_bridge"):
                unit = SERVICE_RECIPES[name]["unit"]
                if _service_exists(unit):
                    actions.append(
                        {
                            "action": "restart_after_rollback",
                            "service": name,
                            "result": _restart_service(unit),
                        }
                    )
            after = diagnose()

        payload = {
            "schema": "dominion-buddy-self-heal-receipt-v2",
            "observed_at": _utc(),
            "authorization_id": auth["id"],
            "status": status,
            "before": before,
            "actions": actions,
            "after": after,
        }
        payload["receipt"] = _write_receipt(payload)
        return payload
    except Exception as exc:
        if rollback_snapshot is not None:
            try:
                _restore_snapshot(rollback_snapshot)
            except Exception:
                pass
        payload = {
            "schema": "dominion-buddy-self-heal-receipt-v2",
            "observed_at": _utc(),
            "authorization_id": auth.get("id"),
            "status": "BLOCKED",
            "error": type(exc).__name__,
            "detail": str(exc)[:500],
            "before": before,
            "actions": actions,
        }
        payload["receipt"] = _write_receipt(payload)
        return payload


__all__ = [
    "SelfHealError",
    "diagnose",
    "repair_safe",
    "SERVICE_RECIPES",
    "CONTAINER_RECIPES",
    "MCP_REPAIR_MAP",
    "PROTECTED_GOVERNANCE_FILES",
]
