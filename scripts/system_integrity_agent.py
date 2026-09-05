#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib import error, request


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def atomic_json(path: Path, data: dict[str, Any], mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return default


def load_contract(path: Path) -> dict[str, Any]:
    contract = load_json(path, {})
    if contract.get("schema") != "dominion-system-integrity-agent-v1":
        raise ValueError("invalid system integrity contract schema")
    if int(contract.get("cadence_seconds", 0)) != 89:
        raise ValueError("system integrity cadence must remain Fibonacci-89 seconds")
    authority = contract.get("authority") or {}
    prohibited = (
        "may_restart_services",
        "may_patch_source",
        "may_deploy",
        "may_change_credentials",
        "may_change_networking",
        "may_publish",
        "may_spend",
        "may_trade",
        "may_file_legal",
    )
    if any(bool(authority.get(key)) for key in prohibited):
        raise ValueError("system integrity agent authority exceeds single-responsibility boundary")
    return contract


def run(argv: list[str], timeout: int = 8) -> tuple[int, str]:
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=timeout, check=False)
        return proc.returncode, (proc.stdout or proc.stderr or "").strip()
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 127, type(exc).__name__


def http_json(url: str, *, method: str = "GET", payload: dict[str, Any] | None = None, timeout: int = 8) -> tuple[int, Any]:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = request.Request(url, data=data, headers={"Content-Type": "application/json"}, method=method)
    try:
        with request.urlopen(req, timeout=timeout) as response:
            body = response.read().decode("utf-8")
            parsed: Any = None
            if body:
                try:
                    parsed = json.loads(body)
                except json.JSONDecodeError:
                    parsed = body
            return int(response.status), parsed
    except error.HTTPError as exc:
        return int(exc.code), None
    except (error.URLError, TimeoutError, OSError):
        return 0, None


def check_record(check_id: str, ok: bool, detail: str, *, severity: str = "critical") -> dict[str, Any]:
    return {"id": check_id, "ok": bool(ok), "severity": severity, "detail": detail}


def parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


def git_sha(repo: Path) -> str:
    rc, out = run(["git", "-C", str(repo), "rev-parse", "HEAD"])
    return out if rc == 0 and len(out) == 40 else ""


def unit_state(unit: str) -> tuple[str, str]:
    _, active = run(["systemctl", "is-active", unit])
    _, enabled = run(["systemctl", "is-enabled", unit])
    return active or "unknown", enabled or "unknown"


def port_open(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", int(port)), timeout=1.5):
            return True
    except OSError:
        return False


def evaluate(
    contract: dict[str, Any],
    repo: Path,
    previous: dict[str, Any],
    *,
    force_deep_probe: bool = False,
) -> dict[str, Any]:
    cycle = int(previous.get("cycle") or 0) + 1
    checks: list[dict[str, Any]] = []
    observed_at = utc_now()

    for item in contract.get("http_checks", []):
        code, _ = http_json(str(item["url"]))
        expected = int(item["expected_status"])
        checks.append(check_record(f"http:{item['id']}", code == expected, f"expected={expected} actual={code or 0} url={item['url']}"))

    repairable_units = set((contract.get("repair_delegation") or {}).get("allowlisted_services") or [])
    for unit in contract.get("active_units", []):
        active, enabled = unit_state(str(unit))
        checks.append(check_record(f"unit:{unit}", active == "active", f"active={active} enabled={enabled}"))

    for unit in contract.get("containment_holds", []):
        active, enabled = unit_state(str(unit))
        held = active != "active" and enabled in {"disabled", "masked"}
        checks.append(check_record(f"hold:{unit}", held, f"active={active} enabled={enabled}"))

    for port in contract.get("absent_listeners", []):
        opened = port_open(int(port))
        checks.append(check_record(f"hold:port:{port}", not opened, f"listener={'present' if opened else 'absent'}"))

    truth_cfg = contract.get("command_center_truth") or {}
    status_code, status = http_json(str(truth_cfg.get("url", "")))
    truth_ok = status_code == 200 and isinstance(status, dict)
    detail_parts = [f"http={status_code or 0}"]
    expected_sha = git_sha(repo)
    if truth_ok:
        truth = status.get("truth") or {}
        lane_summary = status.get("lane_summary") or {}
        revenue = status.get("revenue") or {}
        autopilot = status.get("autopilot") or {}
        systems = status.get("systems") or {}
        mcp_state = systems.get("mcp_cli")
        mcp_online = (
            mcp_state == "online"
            or (isinstance(mcp_state, dict) and mcp_state.get("ok") is True)
        )
        observed = parse_time(truth.get("observed_at"))
        age = None if observed is None else max(0.0, (datetime.now(timezone.utc) - observed).total_seconds())
        required_lanes = int(truth_cfg.get("required_open_lanes", 11))
        predicates = [
            truth.get("connected") is True,
            bool(expected_sha) and truth.get("release_sha") == expected_sha,
            lane_summary.get("open") == required_lanes,
            lane_summary.get("registered") == required_lanes,
            lane_summary.get("all_open") is True,
            (not truth_cfg.get("require_revenue_runtime")) or revenue.get("runtime_connected") is True,
            (not truth_cfg.get("require_autopilot")) or autopilot.get("connected") is True,
            (not truth_cfg.get("require_mcp")) or mcp_online,
            (not truth_cfg.get("require_receipt")) or bool(status.get("latest_receipts")),
            age is not None and age <= int(truth_cfg.get("max_age_seconds", 180)),
        ]
        truth_ok = all(predicates)
        detail_parts.extend([
            f"release_sha={truth.get('release_sha')}",
            f"repo_sha={expected_sha or 'unknown'}",
            f"lanes={lane_summary.get('open')}/{lane_summary.get('registered')}",
            f"truth_age_seconds={None if age is None else int(age)}",
        ])
    checks.append(check_record("command-center:truth", truth_ok, " ".join(detail_parts)))

    deep_every = max(1, int(contract.get("deep_probe_every_cycles", 10)))
    deep_due = force_deep_probe or cycle == 1 or cycle % deep_every == 0
    if deep_due:
        probe = contract.get("intelligence_probe") or {}
        code, body = http_json(str(probe.get("url", "")), method="POST", payload={"message": probe.get("message", "SYSTEM_INTEGRITY_HEALTH_PROBE")}, timeout=70)
        source = body.get("source") if isinstance(body, dict) else None
        answer = body.get("answer") if isinstance(body, dict) else None
        accepted = set(probe.get("accepted_sources") or [])
        ok = code == 200 and source in accepted and bool(str(answer or "").strip())
        checks.append(check_record("intelligence:end-to-end", ok, f"http={code or 0} source={source or 'none'} answer_present={bool(answer)}"))
    else:
        checks.append(check_record("intelligence:end-to-end", True, f"deferred cycle={cycle} next_interval={deep_every}", severity="informational"))

    usage = shutil.disk_usage("/")
    disk_percent = round((usage.used / usage.total) * 100.0, 2) if usage.total else 0.0
    checks.append(check_record("capacity:root-disk", disk_percent < 90.0, f"used_percent={disk_percent}"))

    defects = [item for item in checks if not item["ok"] and item["severity"] == "critical"]
    repair_requests: list[dict[str, Any]] = []
    for defect in defects:
        if defect["id"].startswith("unit:"):
            unit = defect["id"].split(":", 1)[1]
            if unit in repairable_units:
                repair_requests.append({
                    "service": unit,
                    "action": "REQUEST_BOUNDED_RECOVERY",
                    "owner": ".github/workflows/fix-buddy-brains.yml",
                    "reason": defect["detail"],
                })

    return {
        "schema": "dominion-system-integrity-state-v1",
        "agent": contract["agent_id"],
        "single_responsibility": contract["single_responsibility"],
        "governing_name": contract["governing_name"],
        "cycle": cycle,
        "observed_at": observed_at,
        "status": "PASS" if not defects else "DEGRADED",
        "ok": not defects,
        "deep_probe_executed": deep_due,
        "checks_total": len(checks),
        "defect_count": len(defects),
        "checks": checks,
        "defects": defects,
        "repair_requests": repair_requests,
        "authority": "OBSERVE_VERIFY_REQUEST_RECOVERY",
        "founder_final_authority": True,
        "self_mutation": False,
    }


def persist(state_root: Path, state: dict[str, Any]) -> None:
    receipts = state_root / "receipts"
    latest = state_root / "latest.json"
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    atomic_json(receipts / f"{stamp}-integrity-cycle-{int(state['cycle']):06d}.json", state)
    atomic_json(latest, state)
    request_path = state_root / "recovery-request.json"
    if state.get("repair_requests"):
        atomic_json(request_path, {
            "schema": "dominion-system-integrity-recovery-request-v1",
            "status": "PENDING",
            "created_at": state["observed_at"],
            "requests": state["repair_requests"],
            "rule": "Request only. No repair action was executed by the System Integrity Agent.",
        })
    elif request_path.exists():
        request_path.unlink()


def main() -> int:
    parser = argparse.ArgumentParser(description="Dominion System Integrity Agent")
    parser.add_argument("--contract", default=str(Path.home() / ".config/dominion/system-integrity-agent.json"))
    parser.add_argument("--repo", default=str(Path.home() / "dominion-ops"))
    parser.add_argument("--state-root", default=str(Path.home() / ".dominion/system-integrity"))
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--force-deep-probe", action="store_true")
    args = parser.parse_args()

    contract = load_contract(Path(args.contract))
    if args.self_test:
        print("SYSTEM_INTEGRITY_AGENT_SELF_TEST=PASS cadence=89 authority=observe_verify_request_recovery")
        return 0

    state_root = Path(args.state_root)
    previous = load_json(state_root / "latest.json", {})
    state = evaluate(
        contract,
        Path(args.repo),
        previous,
        force_deep_probe=args.force_deep_probe,
    )
    persist(state_root, state)
    print(
        f"SYSTEM_INTEGRITY_AGENT={state['status']} cycle={state['cycle']} "
        f"checks={state['checks_total']} defects={state['defect_count']} "
        f"deep_probe={str(state['deep_probe_executed']).lower()}"
    )
    return 0 if state["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
