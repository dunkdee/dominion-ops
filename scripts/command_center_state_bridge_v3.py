#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path

BASE_PATH = Path(__file__).with_name("command_center_state_bridge_v2.py")
spec = importlib.util.spec_from_file_location("command_center_state_bridge_v2", BASE_PATH)
if not spec or not spec.loader:
    raise RuntimeError("command_center_state_bridge_v2_import_failed")
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)


def _integrity_state(root: Path) -> dict:
    latest = base.load_json(root / "system-integrity/latest.json")
    if not isinstance(latest, dict):
        return {"ok": False, "status": "UNVERIFIED", "observed_at": None, "defect_count": None, "cycle": None}
    observed_at = latest.get("observed_at")
    age = None
    try:
        observed = datetime.fromisoformat(str(observed_at).replace("Z", "+00:00")).astimezone(timezone.utc)
        age = max(0.0, (datetime.now(timezone.utc) - observed).total_seconds())
    except (TypeError, ValueError):
        pass
    fresh = age is not None and age <= 240
    return {
        "ok": latest.get("ok") is True and latest.get("status") == "PASS" and fresh,
        "status": latest.get("status") if fresh else "STALE",
        "observed_at": observed_at,
        "age_seconds": None if age is None else int(age),
        "defect_count": latest.get("defect_count"),
        "cycle": latest.get("cycle"),
        "authority": latest.get("authority"),
    }


def build_state(repo: Path, root: Path):
    state = base.build_state(repo, root)
    systems = state.setdefault("systems", {})
    systems["mcp_cli"] = base.http("http://127.0.0.1:8390/health")
    systems["system_integrity"] = _integrity_state(root)
    return state


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default=str(Path.home() / "dominion-ops"))
    parser.add_argument("--dominion-root", default=str(Path.home() / ".dominion"))
    parser.add_argument("--output", default=str(Path.home() / ".dominion/command-center/runtime-state.json"))
    parser.add_argument("--daily-state", default="")
    args = parser.parse_args()

    repo = Path(args.repo)
    root = Path(args.dominion_root)
    state = build_state(repo, root)
    base.atomic_write(Path(args.output), json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    if args.daily_state:
        base.atomic_write(Path(args.daily_state), base.daily_markdown(state), 0o600)

    lanes = state["lanes"]
    revenue = state["revenue"]
    mcp = state.get("systems", {}).get("mcp_cli", {})
    integrity = state.get("systems", {}).get("system_integrity", {})
    print(
        f"COMMAND_CENTER_STATE=PASS lanes={lanes['open']}/{lanes['registered']} "
        f"revenue_connected={str(revenue['connected']).lower()} constraint={revenue['constraint']} "
        f"mcp_cli={str(bool(mcp.get('ok'))).lower()} "
        f"system_integrity={str(bool(integrity.get('ok'))).lower()} "
        f"receipts={len(state['latest_receipts'])}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
