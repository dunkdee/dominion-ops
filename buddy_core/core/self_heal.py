"""Governed self-healing for Buddy and core Dominion runtime services.

The repair engine is intentionally recipe-based. It can repair routine internal,
reversible faults covered by the Founder's standing authorization, but it does
not accept arbitrary shell commands and cannot modify credentials, firewall,
public ingress, governance files, money/trading state, or binding submissions.
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

# Only these fixed systemd units may be restarted by this module. No user input
# can become a service name or shell command.
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

# Canonical source only. Runtime data, generated media, logs, .env, credentials,
# and durable evidence are deliberately excluded.
TRACKED_RUNTIME_FILES = (
    "core/brain.py",
    "core/brain_router.py",
    "core/operator.py",
    "core/learning_engine.py",
    "core/autonomous_learning.py",
    "core/revenue_runtime.py",
    "core/capability_health.py",
    "core/mcp_client.py",
    "core/self_heal.py",
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
    # sudo is fixed and non-interactive; if the VM has not authorized this exact
    # operation the repair fails visibly rather than hanging for a password.
    cp = _run(["sudo", "-n", "systemctl", "restart", unit], timeout=30)
    active = _service_active(unit) if cp.returncode == 0 else False
    return {
        "unit": unit,
        "returncode": cp.returncode,
        "active": active,
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


def diagnose() -> dict[str, Any]:
    """Diagnose Buddy plus registered core runtime dependencies without mutation."""
    disk = shutil.disk_usage(Path.home())
    services = {}
    issues: list[dict[str, Any]] = []

    for name, recipe in SERVICE_RECIPES.items():
        unit = recipe["unit"]
        exists = _service_exists(unit)
        active = _service_active(unit) if exists else False
        probe = _probe(recipe.get("health"), set(recipe.get("accepted_http", set())))
        health_ok = probe.get("healthy")
        if health_ok is None:
            healthy = active if exists else None
        else:
            healthy = bool(active and health_ok)
        services[name] = {
            "unit": unit,
            "exists": exists,
            "active": active,
            "probe": probe,
            "healthy": healthy,
        }
        if exists and healthy is False:
            issues.append({"id": f"service:{name}", "repair": "restart_allowlisted_service"})

    try:
        mcp = mcp_client.health()
        mcp_state = {"healthy": True, "detail": mcp}
    except Exception as exc:
        mcp_state = {"healthy": False, "error": type(exc).__name__}
        issues.append({"id": "mcp:unhealthy", "repair": "restart_mcp_cli"})

    repo = _repo_state()
    source = _source_state() if repo.get("available") else {"checked": 0, "mismatches": [], "files": []}
    mutable_mismatches = [
        rel for rel in source.get("mismatches", []) if rel not in PROTECTED_GOVERNANCE_FILES
    ]
    protected_mismatches = [
        rel for rel in source.get("mismatches", []) if rel in PROTECTED_GOVERNANCE_FILES
    ]
    if mutable_mismatches:
        issues.append({"id": "source:runtime_drift", "repair": "restore_tracked_runtime_source", "files": mutable_mismatches})
    if protected_mismatches:
        issues.append({"id": "source:protected_governance_drift", "repair": "fresh_founder_review_required", "files": protected_mismatches})

    free_bytes = disk.free
    if free_bytes < 256 * 1024 * 1024:
        issues.append({"id": "disk:critically_low", "repair": "cleanup_disposable_buddy_artifacts"})
    elif free_bytes < 1024 * 1024 * 1024:
        issues.append({"id": "disk:low", "repair": "cleanup_disposable_buddy_artifacts"})

    return {
        "schema": "dominion-buddy-self-diagnosis-v1",
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
        "mcp": mcp_state,
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

    try:
        issue_ids = {row.get("id") for row in before.get("issues", [])}
        if "disk:critically_low" in issue_ids or "disk:low" in issue_ids:
            actions.append({"action": "cleanup_disposable_buddy_artifacts", "result": _cleanup_disposable()})

        drift = next((row for row in before.get("issues", []) if row.get("id") == "source:runtime_drift"), None)
        if drift:
            result = _restore_tracked_source(list(drift.get("files") or []))
            rollback_snapshot = Path(result["backup"])
            actions.append({"action": "restore_tracked_runtime_source", "result": result})

        for name, state in before.get("services", {}).items():
            if state.get("exists") and state.get("healthy") is False:
                unit = SERVICE_RECIPES[name]["unit"]
                result = _restart_service(unit)
                actions.append({"action": "restart_allowlisted_service", "service": name, "result": result})

        # MCP may be unhealthy even if systemd still reports active.
        if before.get("mcp", {}).get("healthy") is False:
            unit = SERVICE_RECIPES["mcp_cli"]["unit"]
            if not any(a.get("service") == "mcp_cli" for a in actions):
                actions.append({"action": "restart_mcp_cli", "service": "mcp_cli", "result": _restart_service(unit)})

        after = diagnose()
        unresolved = [row for row in after.get("issues", []) if row.get("repair") != "fresh_founder_review_required"]
        status = "REPAIRED" if not unresolved else "BLOCKED"

        if status == "BLOCKED" and rollback_snapshot is not None:
            _restore_snapshot(rollback_snapshot)
            actions.append({"action": "rollback_tracked_runtime_source", "backup": str(rollback_snapshot)})
            for name in ("buddy_web", "buddy_bridge"):
                unit = SERVICE_RECIPES[name]["unit"]
                if _service_exists(unit):
                    actions.append({"action": "restart_after_rollback", "service": name, "result": _restart_service(unit)})
            after = diagnose()

        payload = {
            "schema": "dominion-buddy-self-heal-receipt-v1",
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
            "schema": "dominion-buddy-self-heal-receipt-v1",
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


__all__ = ["SelfHealError", "diagnose", "repair_safe", "SERVICE_RECIPES"]
