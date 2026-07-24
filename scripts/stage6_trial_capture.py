#!/usr/bin/env python3
"""CLI for validating and ingesting permitted Similarweb trial exports."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from control_plane.trial_capture import ingest_trial_capture, summarize_trial_completeness, validate_trial_capture_plan


def load(path: str) -> dict:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"{path} must contain a JSON object")
    return value


def load_records(paths: list[str]) -> list[dict]:
    records: list[dict] = []
    for path in paths:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise TypeError(f"{path} must contain a JSON object")
        records.append(value)
    return records


def write_output(value: dict, output: str | None) -> None:
    text = json.dumps(value, indent=2, sort_keys=True) + "\n"
    if output:
        Path(output).write_text(text, encoding="utf-8")
    else:
        print(text, end="")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    ready = sub.add_parser("readiness")
    ready.add_argument("--plan", required=True)
    ready.add_argument("--policy", default="governance/similarweb_trial_capture_policy.json")
    ready.add_argument("--output")

    ingest = sub.add_parser("ingest")
    ingest.add_argument("--plan", required=True)
    ingest.add_argument("--policy", default="governance/similarweb_trial_capture_policy.json")
    ingest.add_argument("--snapshot", required=True)
    ingest.add_argument("--existing-record", action="append", default=[])
    ingest.add_argument("--output")

    completeness = sub.add_parser("completeness")
    completeness.add_argument("--plan", required=True)
    completeness.add_argument("--policy", default="governance/similarweb_trial_capture_policy.json")
    completeness.add_argument("--record", action="append", default=[])
    completeness.add_argument("--output")

    args = parser.parse_args()
    plan = load(args.plan)
    policy = load(args.policy)
    if args.command == "readiness":
        result = validate_trial_capture_plan(plan, policy)
    elif args.command == "ingest":
        result = ingest_trial_capture(plan=plan, policy=policy, snapshot=load(args.snapshot), existing_records=load_records(args.existing_record))
    else:
        result = summarize_trial_completeness(plan, policy, load_records(args.record))
    write_output(result, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
