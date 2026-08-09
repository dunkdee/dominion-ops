#!/usr/bin/env python3
"""Fail closed if governed Dominion Brain inputs look like they contain secret values.

The scanner reports only source path and rule label; it never prints matched values.
"""

from __future__ import annotations

import re

import render_dominion_brain as renderer

TOKEN_PATTERNS = (
    ("private_key_header", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
    ("stripe_live_secret", re.compile(r"\b(?:sk|rk)_live_[A-Za-z0-9]{16,}\b")),
    ("github_token", re.compile(r"\b(?:ghp_|github_pat_)[A-Za-z0-9_]{20,}\b")),
    ("google_api_key", re.compile(r"\bAIza[A-Za-z0-9_-]{20,}\b")),
    ("aws_access_key", re.compile(r"\bAKIA[A-Z0-9]{16}\b")),
)
ASSIGNMENT = re.compile(
    r"(?im)^\s*([A-Z0-9_]*(?:PASSWORD|SECRET|TOKEN|API_KEY|PRIVATE_KEY)[A-Z0-9_]*)\s*[:=]\s*([^\s#]+)"
)
SAFE_PREFIXES = ("${", "{{", "<", "REDACTED", "redacted", "example", "EXAMPLE", "YOUR_", "***")


def main() -> int:
    findings: list[tuple[str, str]] = []
    for path in renderer.GOVERNED_SOURCES:
        text = path.read_text(encoding="utf-8", errors="replace")
        rel = path.relative_to(renderer.REPO).as_posix()
        for label, pattern in TOKEN_PATTERNS:
            if pattern.search(text):
                findings.append((rel, label))
        for match in ASSIGNMENT.finditer(text):
            value = match.group(2).strip("'\"")
            if len(value) >= 12 and not value.startswith(SAFE_PREFIXES):
                findings.append((rel, "credential_assignment"))
    if findings:
        for rel, label in sorted(set(findings)):
            print(f"BRAIN_INPUT_SECRET_GATE=FAIL source={rel} rule={label}")
        return 1
    print(f"BRAIN_INPUT_SECRET_GATE=PASS sources={len(renderer.GOVERNED_SOURCES)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())