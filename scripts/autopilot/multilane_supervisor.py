#!/usr/bin/env python3
"""RADAH MEMSHALAH coordinated multi-lane production supervisor.

The existing lane worker remains the authority boundary for each mission. This
supervisor changes orchestration, not permissions: one systemd activation can
advance multiple due lanes in a bounded sweep while each lane still receives
its own mission, receipts, rotation state, and fail-closed validation.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import revenue_workplane_supervisor as revenue

base = revenue.base


def select_sweep_lanes(
    lanes: list[base.Lane],
    state: dict[str, Any],
    now: datetime,
    limit: int,
) -> list[base.Lane]:
    if limit < 2:
        raise base.AutopilotError("multi-lane sweep size must be >= 2")
    lane_state = state.get("lanes", {})
    ranked = sorted(
        lanes,
        key=lambda lane: base.lane_due_score(lane, lane_state.get(lane.lane_id, {}), now),
        reverse=True,
    )
    return ranked[: min(limit, len(ranked))]


def _summary_path(state_dir: Path, now: datetime) -> Path:
    return state_dir / "sweeps" / (now.strftime("%Y%m%dT%H%M%SZ") + "-multilane.json")


def run_sweep(
    *,
    execute: bool,
    state_dir: Path,
    sweep_size: int | None = None,
) -> dict[str, Any]:
    policy = base.load_json(base.POLICY_PATH)
    verticals = base.load_json(base.VERTICALS_PATH)
    access = revenue.validate_all_lanes_open(verticals)
    lanes = base.validate_policy(policy, verticals)
    configured_size = int(policy.get("max_missions_per_cycle", 1))
    selected_size = int(sweep_size or configured_size)
    if configured_size < 2:
        raise base.AutopilotError("policy does not authorize a multi-lane sweep")
    if selected_size < 2 or selected_size > configured_size:
        raise base.AutopilotError(
            f"sweep size {selected_size} outside policy maximum {configured_size}"
        )

    now = base.utc_now()
    state = base.load_state(state_dir / "state.json")
    selected = select_sweep_lanes(lanes, state, now, selected_size)

    if not execute:
        plans = [
            revenue.run_cycle(
                execute=False,
                state_dir=state_dir,
                lane_id=lane.lane_id,
            )
            for lane in selected
        ]
        return {
            "schema": "radah-multilane-sweep-v1",
            "governing_name": policy.get("governing_name"),
            "created_at": base.iso(now),
            "status": "PLANNED",
            "execution_requested": False,
            "external_actions_authorized": False,
            "registered_lanes": len(lanes),
            "open_lanes": len(access.get("lanes") or {}),
            "selected_count": len(selected),
            "selected_lanes": [lane.lane_id for lane in selected],
            "lane_results": plans,
        }

    if not base.enabled_by_environment():
        raise base.AutopilotError("runtime activation missing: RADAH_AUTOPILOT_ENABLED=1 required")

    results: list[dict[str, Any]] = []
    for lane in selected:
        # Each lane execution is isolated and persisted by the existing governed
        # worker. A degraded lane cannot erase another lane's valid receipts.
        result = revenue.run_cycle(
            execute=True,
            state_dir=state_dir,
            lane_id=lane.lane_id,
        )
        results.append(result)

    healthy_flags = [base.bounded_cycle_ok(result) for result in results]
    healthy = all(healthy_flags)
    productive = sum(1 for r in results if str(r.get("status")) in {"COMPLETE", "HELD"})
    blocked = sum(1 for r in results if str(r.get("status")) == "BLOCKED")
    summary = {
        "schema": "radah-multilane-sweep-v1",
        "governing_name": policy.get("governing_name"),
        "created_at": base.iso(now),
        "status": "HEALTHY" if healthy else "DEGRADED",
        "execution_requested": True,
        "external_actions_authorized": False,
        "registered_lanes": len(lanes),
        "open_lanes": len(access.get("lanes") or {}),
        "selected_count": len(selected),
        "selected_lanes": [lane.lane_id for lane in selected],
        "healthy_lane_cycles": sum(1 for flag in healthy_flags if flag),
        "productive_lane_cycles": productive,
        "blocked_lane_cycles": blocked,
        "lane_results": results,
    }

    base.atomic_json_write(_summary_path(state_dir, now), summary)
    base.atomic_json_write(state_dir / "latest_sweep.json", summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(
        description="RADAH MEMSHALAH coordinated multi-lane production sweep"
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--execute", action="store_true")
    mode.add_argument("--plan-only", action="store_true")
    parser.add_argument("--state-dir", default=str(base.DEFAULT_STATE_DIR))
    parser.add_argument("--sweep-size", type=int, default=None)
    args = parser.parse_args()

    try:
        summary = run_sweep(
            execute=bool(args.execute),
            state_dir=Path(args.state_dir).expanduser(),
            sweep_size=args.sweep_size,
        )
    except base.AutopilotError as exc:
        print(json.dumps({"RADAH_MULTILANE_SWEEP": "BLOCKED", "reason": str(exc)}, sort_keys=True))
        return 2
    except Exception as exc:
        print(json.dumps({"RADAH_MULTILANE_SWEEP": "BLOCKED", "reason": type(exc).__name__}, sort_keys=True))
        return 3

    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    print(
        f"RADAH_MULTILANE_SWEEP={summary['status']} "
        f"selected={summary['selected_count']} "
        f"lanes={','.join(summary['selected_lanes'])}"
    )
    return 0 if summary["status"] in {"PLANNED", "HEALTHY"} else 4


if __name__ == "__main__":
    raise SystemExit(main())
