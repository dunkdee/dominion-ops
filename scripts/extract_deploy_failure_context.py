#!/usr/bin/env python3
"""Extract a bounded, redacted context window before a deployment failure marker."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ANSI_ESCAPE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
SENSITIVE_ASSIGNMENT = re.compile(
    r"(?i)\b([A-Z0-9_]*(?:TOKEN|SECRET|PASSWORD|API[_-]?KEY|AUTHORIZATION|CREDENTIAL)[A-Z0-9_]*)"
    r"\s*[:=]\s*\S+"
)
CREDENTIAL_URL = re.compile(r"://[^/\s:@]+(?::[^/\s@]+)?@")


def sanitize_line(line: str) -> str:
    """Remove terminal escapes and redact likely credential material."""
    line = ANSI_ESCAPE.sub("", line).strip()
    line = SENSITIVE_ASSIGNMENT.sub(r"\1=[redacted]", line)
    line = CREDENTIAL_URL.sub("://[redacted]@", line)
    return line.replace("`", "'")


def extract_context(log_path: Path, *, max_lines: int = 14, max_chars: int = 900) -> str:
    """Return the final useful lines immediately preceding the last failure marker."""
    lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    failure_indexes = [
        index for index, line in enumerate(lines) if line.startswith("DEPLOY_FAILURE ")
    ]
    if not failure_indexes:
        return ""

    failure_index = failure_indexes[-1]
    context: list[str] = []
    for raw_line in lines[max(0, failure_index - 60) : failure_index]:
        line = sanitize_line(raw_line)
        if not line or line.startswith(("DEPLOY_", "::group::", "::endgroup::")):
            continue
        context.append(line)

    compact = " | ".join(context[-max_lines:])
    return compact[:max_chars]


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: extract_deploy_failure_context.py LOG_FILE", file=sys.stderr)
        return 2

    log_path = Path(sys.argv[1])
    if not log_path.is_file():
        return 0

    print(extract_context(log_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
