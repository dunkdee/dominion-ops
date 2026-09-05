from __future__ import annotations

import argparse
import json
import re
import sys
from typing import Any

AUTO_SENTINEL = "DEPLOYED"
SHA40_RE = re.compile(r"^[0-9a-fA-F]{40}$")


def _is_sha40(value: str) -> bool:
    return bool(SHA40_RE.fullmatch(value))


def resolve_expected_sha(expected_sha: str, receipt: dict[str, Any] | None = None) -> str:
    requested = expected_sha.strip()
    if requested and requested != AUTO_SENTINEL:
        if not _is_sha40(requested):
            raise ValueError("A full 40-character SHA is required (or DEPLOYED).")
        return requested

    if not isinstance(receipt, dict):
        raise ValueError("DEPLOYED mode requires a valid deployed_release.json object.")
    deployed_sha = str(receipt.get("release_sha") or "").strip()
    if not _is_sha40(deployed_sha):
        raise ValueError("DEPLOYED mode could not resolve a valid 40-character release_sha.")
    return deployed_sha


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--expected-sha", default=AUTO_SENTINEL)
    parser.add_argument("--receipt-stdin", action="store_true")
    args = parser.parse_args()

    receipt = None
    if args.receipt_stdin:
        raw = sys.stdin.read()
        try:
            receipt = json.loads(raw)
        except (TypeError, ValueError) as exc:
            print(f"Invalid deployed_release.json payload: {exc}", file=sys.stderr)
            return 1

    try:
        resolved = resolve_expected_sha(args.expected_sha, receipt)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(resolved)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
