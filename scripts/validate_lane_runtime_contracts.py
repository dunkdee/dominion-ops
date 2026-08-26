#!/usr/bin/env python3
"""Validate constitution-bound Dominion lane runtime and profitability contracts."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GUARD_PATH = ROOT / "scripts" / "autopilot" / "control_plane_guard.py"
spec = importlib.util.spec_from_file_location("control_plane_guard", GUARD_PATH)
if spec is None or spec.loader is None:
    raise SystemExit("unable to load constitutional control-plane guard")
guard = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = guard
spec.loader.exec_module(guard)


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    try:
        receipt = guard.validate_runtime_root(ROOT)
    except guard.ConstitutionalGuardError as exc:
        print(f"LANE_RUNTIME_CONTRACTS=BLOCKED reason={exc}")
        return 1

    contracts = load(ROOT / "governance" / "lane_runtime_contracts.json")["lane_contracts"]
    verticals = {
        row["id"]: row
        for row in load(ROOT / "governance" / "verticals.json")["verticals"]
    }
    profit = load(ROOT / "governance" / "profitability_lane_contracts.json")["lanes"]

    errors: list[str] = []
    for lane_id, contract in contracts.items():
        for rel in contract["implementation_paths"]:
            if not (ROOT / rel).is_file():
                errors.append(f"missing implementation path lane={lane_id} path={rel}")
        registered_dependencies = set(verticals[lane_id].get("dependencies") or [])
        runtime_dependencies = set(contract.get("dependencies") or [])
        # Runtime may add a demand/support dependency, but it may never silently
        # drop a dependency already declared by the canonical vertical registry.
        missing_dependencies = registered_dependencies - runtime_dependencies
        if missing_dependencies:
            errors.append(
                f"runtime dependency loss lane={lane_id} missing={sorted(missing_dependencies)}"
            )
        if not str(contract.get("worker_id") or "").strip():
            errors.append(f"missing worker lane={lane_id}")
        if not str(contract.get("execution_binding") or "").strip():
            errors.append(f"missing execution binding lane={lane_id}")
        if len(contract.get("input_contract") or []) < 3:
            errors.append(f"input contract too thin lane={lane_id}")
        if len(contract.get("output_contract") or []) < 3:
            errors.append(f"output contract too thin lane={lane_id}")
        if len(contract.get("health_signals") or []) < 2:
            errors.append(f"health contract too thin lane={lane_id}")
        if len(contract.get("recovery_contract") or []) < 2:
            errors.append(f"recovery contract too thin lane={lane_id}")

    for lane_id, contract in profit.items():
        if lane_id not in contracts:
            errors.append(f"profit lane has no runtime contract lane={lane_id}")
        if len(contract.get("demand_evidence") or []) < 2:
            errors.append(f"profit lane lacks demand proof contract lane={lane_id}")
        if len(contract.get("unit_economics") or []) < 3:
            errors.append(f"profit lane lacks unit economics lane={lane_id}")
        if len(contract.get("attribution") or []) < 2:
            errors.append(f"profit lane lacks attribution lane={lane_id}")
        if len(contract.get("hard_blockers") or []) < 2:
            errors.append(f"profit lane lacks hard blockers lane={lane_id}")

    if errors:
        print("LANE_RUNTIME_CONTRACTS=BLOCKED")
        for error in errors:
            print(f" - {error}")
        return 1

    print(json.dumps(receipt, sort_keys=True))
    print(
        "LANE_RUNTIME_CONTRACTS=PASS "
        f"lanes={len(contracts)} economic_lanes={len(profit)} "
        "constitution_bound=true implementation_paths=verified"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
