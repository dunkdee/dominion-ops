#!/usr/bin/env python3
"""RADAH MEMSHALAH governed production lane supervisor.

This runner keeps every registered Dominion lane productive without granting
itself external authority. It selects one due lane per cycle, asks the existing
Buddy operator to perform the lane's bounded internal mission, verifies that
all planned capabilities are either explicitly allowed internal capabilities or
Founder-held external capabilities, and writes an auditable receipt.

Activation is separate from code deployment. The runner is inert unless
RADAH_AUTOPILOT_ENABLED=1 is present in its runtime environment.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = REPO_ROOT / "governance" / "radah_memshalah_autopilot_policy.json"
VERTICALS_PATH = REPO_ROOT / "governance" / "verticals.json"
DEFAULT_STATE_DIR = Path.home() / ".dominion" / "autopilot"


class AutopilotError(RuntimeError):
    pass


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime | None = None) -> str:
    return (dt or utc_now()).isoformat()


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise AutopilotError(f"expected JSON object: {path}")
    return data


def atomic_json_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.parent.chmod(0o700)
    fd, tmp_name = tempfile.mkstemp(prefix=path.name + ".", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
        os.chmod(tmp_name, 0o600)
        os.replace(tmp_name, path)
    finally:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass


def parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def enabled_by_environment() -> bool:
    return os.getenv("RADAH_AUTOPILOT_ENABLED", "0").strip().lower() in {
        "1", "true", "yes", "on"
    }


@dataclass(frozen=True)
class Lane:
    lane_id: str
    priority: int
    status: str
    mode: str
    objective: str
    stale_after_hours: int
    group: str


def validate_policy(policy: dict[str, Any], verticals: dict[str, Any]) -> list[Lane]:
    if policy.get("schema") != "radah-memshalah-autopilot-v1":
        raise AutopilotError("unexpected autopilot policy schema")
    if policy.get("max_primary_revenue_verticals") != 2:
        raise AutopilotError("primary revenue wave must remain capped at exactly two")

    rows = verticals.get("verticals")
    if not isinstance(rows, list) or not rows:
        raise AutopilotError("vertical registry is empty")

    ids = [str(row.get("id", "")) for row in rows]
    if len(ids) != len(set(ids)) or any(not lane_id for lane_id in ids):
        raise AutopilotError("vertical registry contains blank or duplicate ids")

    objectives = policy.get("lane_objectives") or {}
    if set(objectives) != set(ids):
        missing = sorted(set(ids) - set(objectives))
        extra = sorted(set(objectives) - set(ids))
        raise AutopilotError(f"lane objective mismatch missing={missing} extra={extra}")

    primary = list(policy.get("primary_wave") or [])
    support = list(policy.get("support_wave") or [])
    if len(primary) != 2 or len(set(primary)) != 2:
        raise AutopilotError("primary_wave must contain two unique lanes")
    if not set(primary).issubset(ids):
        raise AutopilotError("primary_wave references unknown lane")
    if set(primary) & set(support):
        raise AutopilotError("primary and support waves must not overlap")

    default_hours = int(policy.get("default_stale_after_hours", 12))
    primary_hours = int(policy.get("primary_stale_after_hours", 2))
    support_hours = int(policy.get("support_stale_after_hours", 6))
    if min(default_hours, primary_hours, support_hours) < 1:
        raise AutopilotError("lane stale thresholds must be >= 1 hour")

    lanes: list[Lane] = []
    for row in rows:
        lane_id = str(row["id"])
        if lane_id in primary:
            group = "primary"
            stale = primary_hours
        elif lane_id in support:
            group = "support"
            stale = support_hours
        else:
            group = "standard"
            stale = default_hours
        lanes.append(Lane(
            lane_id=lane_id,
            priority=int(row.get("priority", 999)),
            status=str(row.get("status", "unknown")),
            mode=str(row.get("mode", "unknown")),
            objective=str(objectives[lane_id]),
            stale_after_hours=stale,
            group=group,
        ))
    return sorted(lanes, key=lambda lane: (lane.priority, lane.lane_id))


def load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"schema": "radah-autopilot-state-v1", "lanes": {}, "cycles": 0}
    state = load_json(path)
    if state.get("schema") != "radah-autopilot-state-v1":
        raise AutopilotError("unexpected autopilot state schema")
    if not isinstance(state.get("lanes"), dict):
        raise AutopilotError("invalid autopilot lane state")
    return state


def lane_due_score(lane: Lane, lane_state: dict[str, Any], now: datetime) -> tuple[float, int, str]:
    # Schedule by last attempt, not only success, so one blocked lane cannot
    # monopolize every cycle and starve the remaining production lanes.
    last = parse_time(lane_state.get("last_attempt_at"))
    if last is None:
        age_hours = 10_000.0
    else:
        age_hours = max(0.0, (now - last).total_seconds() / 3600.0)
    overdue_ratio = age_hours / float(lane.stale_after_hours)
    return overdue_ratio, -lane.priority, lane.lane_id


def select_lane(lanes: list[Lane], state: dict[str, Any], now: datetime) -> Lane:
    lane_state = state.get("lanes", {})
    ranked = sorted(
        lanes,
        key=lambda lane: lane_due_score(lane, lane_state.get(lane.lane_id, {}), now),
        reverse=True,
    )
    if not ranked:
        raise AutopilotError("no registered lanes")
    return ranked[0]


def resolve_buddy_operator():
    candidates = []
    configured = os.getenv("DOMINION_BUDDY_ROOT", "").strip()
    if configured:
        candidates.append(Path(configured).expanduser())
    candidates.extend([
        Path.home() / "buddy_core",
        REPO_ROOT / "buddy_core",
    ])

    errors: list[str] = []
    for root in candidates:
        operator_file = root / "core" / "operator.py"
        if not operator_file.is_file():
            continue
        sys.path.insert(0, str(root))
        try:
            from core.operator import get_operator  # type: ignore
            return get_operator()
        except Exception as exc:  # pragma: no cover - runtime diagnostic path
            errors.append(f"{root}:{type(exc).__name__}")
        finally:
            try:
                sys.path.remove(str(root))
            except ValueError:
                pass
    raise AutopilotError("Buddy operator unavailable: " + ",".join(errors or ["not_found"]))


def validate_plan(plan: dict[str, Any], operator: Any, policy: dict[str, Any]) -> None:
    allowed = set(policy.get("allowed_automatic_capabilities") or [])
    external_prefixes = tuple(policy.get("held_external_prefixes") or [])
    if not external_prefixes:
        raise AutopilotError("no held external prefixes configured")

    steps = plan.get("steps")
    if not isinstance(steps, list) or not steps:
        raise AutopilotError("Buddy produced an empty plan")

    for step in steps:
        cap_id = str(step.get("capability", ""))
        cap = operator.capabilities.get(cap_id)
        if cap is None:
            raise AutopilotError(f"unregistered Buddy capability: {cap_id}")
        if cap_id in allowed:
            if cap.get("auth_required") or cap.get("classification") in {"privileged_write", "destructive"}:
                raise AutopilotError(f"allowed internal capability unexpectedly privileged: {cap_id}")
            continue
        if cap_id.startswith(external_prefixes):
            if not cap.get("auth_required") and cap.get("classification") not in {"privileged_write", "destructive"}:
                raise AutopilotError(f"external capability would not be held: {cap_id}")
            continue
        raise AutopilotError(f"capability outside autopilot authority: {cap_id}")


def policy_digest(policy: dict[str, Any]) -> str:
    encoded = json.dumps(policy, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def run_cycle(*, execute: bool, state_dir: Path) -> dict[str, Any]:
    policy = load_json(POLICY_PATH)
    verticals = load_json(VERTICALS_PATH)
    lanes = validate_policy(policy, verticals)
    now = utc_now()
    state_path = state_dir / "state.json"
    state = load_state(state_path)
    lane = select_lane(lanes, state, now)

    base_receipt: dict[str, Any] = {
        "schema": "radah-autopilot-receipt-v1",
        "governing_name": policy.get("governing_name"),
        "created_at": iso(now),
        "policy_sha256": policy_digest(policy),
        "lane": lane.lane_id,
        "lane_priority": lane.priority,
        "lane_status": lane.status,
        "lane_mode": lane.mode,
        "lane_group": lane.group,
        "objective": lane.objective,
        "execution_requested": bool(execute),
        "external_actions_authorized": False,
    }

    if not execute:
        return {**base_receipt, "status": "PLANNED"}

    if not enabled_by_environment():
        raise AutopilotError("runtime activation missing: RADAH_AUTOPILOT_ENABLED=1 required")

    operator = resolve_buddy_operator()
    plan = operator.plan(lane.objective)
    validate_plan(plan, operator, policy)
    result = operator.execute(plan, session_id=f"autopilot:{lane.lane_id}")

    receipt = {
        **base_receipt,
        "status": str(result.get("status", "BLOCKED")),
        "mission_id": result.get("mission_id"),
        "held": result.get("held"),
        "receipts": result.get("receipts", []),
    }

    lane_state = state.setdefault("lanes", {}).setdefault(lane.lane_id, {})
    lane_state["last_attempt_at"] = iso(now)
    lane_state["last_status"] = receipt["status"]
    lane_state["last_mission_id"] = receipt.get("mission_id")
    if receipt["status"] in {"COMPLETE", "HELD"}:
        lane_state["last_productive_at"] = iso(now)
    state["cycles"] = int(state.get("cycles", 0)) + 1
    state["updated_at"] = iso(now)

    receipt_dir = state_dir / "receipts"
    receipt_name = now.strftime("%Y%m%dT%H%M%SZ") + f"-{lane.lane_id}.json"
    atomic_json_write(receipt_dir / receipt_name, receipt)
    atomic_json_write(state_path, state)
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description="RADAH MEMSHALAH Dominion lane supervisor")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--execute", action="store_true", help="execute one bounded internal production mission")
    mode.add_argument("--plan-only", action="store_true", help="select and print the next lane without mutation")
    parser.add_argument("--state-dir", default=str(DEFAULT_STATE_DIR))
    args = parser.parse_args()

    execute = bool(args.execute)
    try:
        receipt = run_cycle(execute=execute, state_dir=Path(args.state_dir).expanduser())
    except AutopilotError as exc:
        print(json.dumps({"RADAH_AUTOPILOT": "BLOCKED", "reason": str(exc)}, sort_keys=True))
        return 2
    except Exception as exc:  # fail closed without leaking exception internals
        print(json.dumps({"RADAH_AUTOPILOT": "BLOCKED", "reason": type(exc).__name__}, sort_keys=True))
        return 3

    print(json.dumps(receipt, ensure_ascii=False, sort_keys=True))
    print(f"RADAH_AUTOPILOT={receipt['status']} lane={receipt['lane']}")
    return 0 if receipt["status"] in {"PLANNED", "COMPLETE", "HELD"} else 4


if __name__ == "__main__":
    raise SystemExit(main())
