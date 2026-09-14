#!/usr/bin/env python3
"""Governed execution bridge for RADAH MEMSHALAH autopilot.

This module closes the operational gap between a HELD mission and an already
Founder-GRANTED authorization without creating a second authority path.

Rules:
- never grants, approves, signs, or widens authority;
- resumes only a held payload whose canonical AuthorizationLedger record is
  already GRANTED and whose payload hash still matches the stored hold;
- executes at most one granted hold per cycle;
- if nothing is resumable, delegates one normal cycle to the existing lane
  supervisor;
- records an append-only bridge receipt under the existing autopilot state
  directory;
- fails closed on malformed held state, ledger mismatch, or unexpected status.

The Founder approval surface remains the AuthorizationLedger. This bridge is
only the continuity mechanism after that approval exists.
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import lane_supervisor as base

DEFAULT_STATE_DIR = Path.home() / ".dominion" / "autopilot"
ALLOWED_RESULT_STATUSES = {
    "COMPLETE",
    "HELD",
    "BLOCKED",
    "DELIVERED_AUDIT_UNAVAILABLE",
}


class BridgeError(RuntimeError):
    pass


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if os.name == "posix":
        path.parent.chmod(0o700)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            fd = -1
            json.dump(payload, handle, ensure_ascii=False, sort_keys=True, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        if os.name == "posix":
            os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    finally:
        if fd >= 0:
            try:
                os.close(fd)
            except OSError:
                pass
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass


def _load_hold(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _candidate(operator: Any) -> tuple[dict[str, Any], dict[str, Any]] | None:
    """Return the oldest exact held payload already GRANTED by Founder authority."""
    held_dir = Path(operator.held_dir)
    if not held_dir.is_dir():
        return None

    for path in sorted(held_dir.glob("approval_*.json"), key=lambda p: (p.stat().st_mtime, p.name)):
        stored = _load_hold(path)
        if not stored:
            continue
        approval_id = str(stored.get("approval_id", ""))
        payload_hash = str(stored.get("payload_hash", ""))
        if not approval_id or not payload_hash:
            continue
        try:
            authority = operator._ledger.load(approval_id)
        except Exception:
            continue
        if not isinstance(authority, dict):
            continue
        if authority.get("status") != "GRANTED":
            continue
        if authority.get("payload_hash") != payload_hash:
            raise BridgeError(f"held_authority_mismatch:{approval_id}")
        return stored, authority
    return None


def _resume(operator: Any, stored: dict[str, Any], authority: dict[str, Any]) -> dict[str, Any]:
    approval_id = str(stored["approval_id"])
    plan = stored.get("plan")
    step_index = int(stored.get("step_index", 0) or 0)
    if not isinstance(plan, dict):
        raise BridgeError(f"held_plan_invalid:{approval_id}")
    steps = plan.get("steps")
    if not isinstance(steps, list) or step_index < 1 or step_index > len(steps):
        raise BridgeError(f"held_step_invalid:{approval_id}")

    resumed = copy.deepcopy(plan)
    resumed["steps"][step_index - 1]["authorization_id"] = approval_id
    result = operator.execute(
        resumed,
        session_id=str(stored.get("session_id") or "autopilot:resume"),
    )
    status = str(result.get("status", "BLOCKED"))
    if status not in ALLOWED_RESULT_STATUSES:
        raise BridgeError(f"unexpected_resume_status:{status}")
    return {
        "status": status,
        "mission_id": result.get("mission_id"),
        "approval_id": approval_id,
        "authorization_sequence": authority.get("authorization_sequence"),
        "receipts": result.get("receipts", []),
        "held": result.get("held"),
        "authority_granted_by_bridge": False,
    }


def run_bridge_cycle(*, execute: bool, state_dir: Path) -> dict[str, Any]:
    created_at = _utc()
    if not execute:
        return {
            "schema": "radah-governed-execution-bridge-v1",
            "created_at": created_at,
            "status": "PLANNED",
            "authority_granted_by_bridge": False,
        }
    if not base.enabled_by_environment():
        raise BridgeError("runtime activation missing: RADAH_AUTOPILOT_ENABLED=1 required")

    operator = base.resolve_buddy_operator()
    candidate = _candidate(operator)
    if candidate:
        stored, authority = candidate
        action = "RESUME_GRANTED_HOLD"
        result = _resume(operator, stored, authority)
    else:
        action = "RUN_BOUNDED_LANE_CYCLE"
        result = base.run_cycle(execute=True, state_dir=state_dir)

    receipt = {
        "schema": "radah-governed-execution-bridge-v1",
        "created_at": created_at,
        "action": action,
        "status": str(result.get("status", "BLOCKED")),
        "authority_granted_by_bridge": False,
        "result": result,
    }
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    _atomic_json(state_dir / "bridge-receipts" / f"{stamp}.json", receipt)
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description="RADAH MEMSHALAH governed execution bridge")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--execute", action="store_true")
    mode.add_argument("--plan-only", action="store_true")
    parser.add_argument("--state-dir", default=str(DEFAULT_STATE_DIR))
    args = parser.parse_args()

    try:
        receipt = run_bridge_cycle(
            execute=bool(args.execute),
            state_dir=Path(args.state_dir).expanduser(),
        )
    except Exception as exc:
        print(json.dumps({
            "RADAH_EXECUTION_BRIDGE": "BLOCKED",
            "reason": type(exc).__name__,
            "detail": str(exc)[:240],
        }, sort_keys=True))
        return 2

    print(json.dumps(receipt, ensure_ascii=False, sort_keys=True))
    print(
        "RADAH_EXECUTION_BRIDGE=" + str(receipt.get("status", "BLOCKED"))
        + " authority_granted_by_bridge=false"
    )
    return 0 if receipt.get("status") in {"PLANNED", "COMPLETE", "HELD", "BLOCKED"} else 4


if __name__ == "__main__":
    raise SystemExit(main())
