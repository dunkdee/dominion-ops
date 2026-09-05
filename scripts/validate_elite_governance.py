#!/usr/bin/env python3
"""Fail-closed repository governance gate for Dominion.

This is not a readiness report. It is an enforcement control. A non-zero exit
means the repository must not be described as end-to-end autonomous or merged
as an elite-governed release.

RADAH MEMSHALAH — רָדָה מֶמְשָׁלָה
EVIDENCE -> AUTHORITY -> ACTION -> RECEIPT -> MEASUREMENT -> LEARNING
"""
from __future__ import annotations

import ast
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

CONSTITUTION = ROOT / "governance" / "SYSTEM_CONSTITUTION.md"
CAPABILITY_REGISTRY = ROOT / "buddy_core" / "config" / "capability_registry.json"
OPERATOR = ROOT / "buddy_core" / "core" / "operator.py"
AUTHORIZATION = ROOT / "buddy_core" / "core" / "authorization.py"
AUTOPILOT = ROOT / "scripts" / "autopilot" / "lane_supervisor.py"

REQUIRED_CONSTITUTION_PHRASES = (
    "Applies to: every agent, workflow, service, vertical, model, integration, and production action in Dominion",
    "Independent review.",
    "Full provenance.",
    "No unreviewed self-modification.",
    "Learning is mandatory.",
    "Runtime enforcement must be added before agents receive production authority.",
)

# These patterns are forbidden in GitHub Actions and executable repository
# scripts unless a future, explicit emergency policy creates a narrowly scoped
# allowlist with independent review. There is intentionally no blanket legacy
# grandfathering.
HIGH_RISK_PATTERNS = (
    ("force_push", re.compile(r"\bgit\s+push\b[^\n]*(?:--force|-f\b)", re.I)),
    ("direct_main_push", re.compile(r"\bgit\s+push\b[^\n]*(?:origin\s+main|HEAD:main|refs/heads/main)", re.I)),
    ("hard_reset", re.compile(r"\bgit\s+reset\s+--hard\b", re.I)),
    ("forced_checkout", re.compile(r"\bgit\s+(?:checkout|switch)\b[^\n]*(?:-f\b|--force\b)", re.I)),
)

SCAN_SUFFIXES = {".yml", ".yaml", ".sh", ".ps1", ".py"}
SCAN_ROOTS = (ROOT / ".github" / "workflows", ROOT / "scripts")
EXPLICIT_SCAN_FILES = (ROOT / "build-doctor.sh",)


def read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


def line_number(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def iter_scan_files():
    seen: set[Path] = set()
    for base in SCAN_ROOTS:
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if path.is_file() and path.suffix.lower() in SCAN_SUFFIXES:
                seen.add(path)
                yield path
    for path in EXPLICIT_SCAN_FILES:
        if path.is_file() and path not in seen:
            yield path


def external_executor_bindings(source: str) -> set[str]:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return set()
    found: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        matches = any(
            isinstance(target, ast.Attribute)
            and isinstance(target.value, ast.Name)
            and target.value.id == "self"
            and target.attr == "_external_executors"
            for target in targets
        )
        if not matches or not isinstance(node.value, ast.Dict):
            continue
        for key in node.value.keys:
            if isinstance(key, ast.Constant) and isinstance(key.value, str):
                found.add(key.value)
    return found

def collect_failures() -> list[dict]:
    failures: list[dict] = []

    constitution = read(CONSTITUTION)
    if not constitution:
        failures.append({"gate": "constitution", "reason": "missing SYSTEM_CONSTITUTION.md"})
    else:
        # Markdown emphasis must not create false negatives in the invariant gate.
        constitution_plain = re.sub(r"[*_`]", "", constitution)
        for phrase in REQUIRED_CONSTITUTION_PHRASES:
            if phrase not in constitution_plain:
                failures.append({"gate": "constitution", "reason": f"missing invariant: {phrase}"})

    try:
        registry = json.loads(read(CAPABILITY_REGISTRY))
    except Exception as exc:
        failures.append({"gate": "capability_registry", "reason": f"unreadable registry: {type(exc).__name__}"})
        registry = {"capabilities": []}

    operator = read(OPERATOR)
    declared_native = {
        str(cap.get("executor"))
        for cap in registry.get("capabilities", [])
        if cap.get("enabled", True) and str(cap.get("executor", "")).startswith("native:")
    }
    wired_native = set(re.findall(r'"(native:[a-zA-Z0-9_]+)"\s*:\s*self\.', operator))
    for executor in sorted(declared_native - wired_native):
        failures.append({
            "gate": "capability_executor",
            "reason": f"enabled native executor is declared but not wired: {executor}",
        })

    enabled_external = [
        cap for cap in registry.get("capabilities", [])
        if cap.get("enabled", True) and str(cap.get("executor", "")).startswith("external:")
    ]
    wired_external = external_executor_bindings(operator)
    for cap in enabled_external:
        executor = str(cap.get("executor"))
        if executor not in wired_external:
            failures.append({
                "gate": "external_executor",
                "reason": f"enabled external capability has no governed runtime executor: {cap.get('id')} ({executor})",
            })

    authorization = read(AUTHORIZATION)
    if "class AuthorizationLedger" not in authorization or "verify_and_consume" not in authorization:
        failures.append({"gate": "authorization", "reason": "authorization ledger/consumption primitive missing"})
    if "AuthorizationLedger" not in operator or ".request(" not in operator or "verify_and_consume" not in operator:
        failures.append({
            "gate": "authorization_integration",
            "reason": "Buddy operator does not persist and redeem authorization through AuthorizationLedger",
        })

    autopilot = read(AUTOPILOT)
    if 'if bounded_cycle_ok(receipt):\n        lane_state["last_progress_at"]' in autopilot:
        failures.append({
            "gate": "truthful_progress",
            "reason": "autopilot marks structurally-valid HELD/BLOCKED cycles as progress",
        })
    if 'receipt["status"] in {"COMPLETE", "HELD"}' in autopilot:
        failures.append({
            "gate": "truthful_productivity",
            "reason": "autopilot marks HELD as productive",
        })

    for path in iter_scan_files():
        text = read(path)
        rel = path.relative_to(ROOT).as_posix()
        # Ignore this validator's regex literals themselves.
        if rel == "scripts/validate_elite_governance.py":
            continue
        for name, pattern in HIGH_RISK_PATTERNS:
            for match in pattern.finditer(text):
                failures.append({
                    "gate": "workflow_authority",
                    "reason": name,
                    "path": rel,
                    "line": line_number(text, match.start()),
                })

    return failures


def main() -> int:
    failures = collect_failures()
    result = {
        "schema": "dominion-elite-governance-gate-v1",
        "governing_name": "RADAH MEMSHALAH — רָדָה מֶמְשָׁלָה",
        "status": "PASS" if not failures else "FAIL",
        "fail_closed": True,
        "failure_count": len(failures),
        "failures": failures,
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    if failures:
        print("SYSTEM_OPERATING_AUTONOMOUSLY=NO")
        print("ELITE_GOVERNANCE=FAIL")
        return 1
    print("SYSTEM_OPERATING_AUTONOMOUSLY=ELIGIBLE_FOR_RUNTIME_PROOF")
    print("ELITE_GOVERNANCE=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
