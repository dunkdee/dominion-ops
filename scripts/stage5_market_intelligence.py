#!/usr/bin/env python3
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from control_plane.analytics_audit import build_growth_intelligence_audit
from control_plane.external_estimates import adapt_external_estimate

def load(path: str) -> dict:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("input must contain a JSON object")
    return value

def write(value: dict, path: str | None) -> None:
    text = json.dumps(value, indent=2, sort_keys=True) + "\n"
    if path:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(text, encoding="utf-8")
    print(text, end="")

def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    adapt = sub.add_parser("adapt")
    adapt.add_argument("--input", required=True)
    adapt.add_argument("--output")
    audit = sub.add_parser("audit")
    audit.add_argument("--input", required=True)
    audit.add_argument("--output")
    args = parser.parse_args()
    signal = adapt_external_estimate(load(args.input))
    result = signal if args.command == "adapt" else build_growth_intelligence_audit(signal)
    write(result, args.output)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
