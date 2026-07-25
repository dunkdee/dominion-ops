#!/usr/bin/env python3
"""Validate constitutional amendment and emergency-recovery controls."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONSTITUTION = ROOT / "governance" / "SYSTEM_CONSTITUTION.md"
AMENDMENT = ROOT / "governance" / "constitutional_amendment_policy.json"
BREAK_GLASS = ROOT / "governance" / "break_glass_recovery_policy.json"

ERRORS: list[str] = []


def require(condition: bool, message: str) -> None:
    if not condition:
        ERRORS.append(message)


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        ERRORS.append(f"cannot load {path.relative_to(ROOT)}: {exc}")
        return {}
    require(isinstance(value, dict), f"{path.relative_to(ROOT)} must contain an object")
    return value if isinstance(value, dict) else {}


def validate_constitution() -> None:
    try:
        text = CONSTITUTION.read_text(encoding="utf-8")
    except OSError as exc:
        ERRORS.append(f"cannot load {CONSTITUTION.relative_to(ROOT)}: {exc}")
        return

    for phrase in (
        "Constitutional amendment rule",
        "Emergency recovery rule",
        "constitutional_amendment_policy.json",
        "break_glass_recovery_policy.json",
        "Missing, stale, altered, or invalid authorization must fail closed",
    ):
        require(phrase in text, f"constitution missing kernel principle: {phrase}")


def validate_amendment(policy: dict[str, Any]) -> None:
    require(policy.get("default_behavior") == "deny", "amendment policy must default deny")
    require(policy.get("unanimous_council_required") is True, "amendments require unanimous Council review")
    require(policy.get("law_veto_blocks") is True, "Law veto must block amendments")
    require(policy.get("security_veto_blocks") is True, "Security veto must block amendments")
    require(
        policy.get("human_overseer_authorization_required") is True,
        "amendments require Human Overseer authorization",
    )
    require(
        policy.get("proposal_hash_binding_required") is True,
        "amendment reviews must bind to the proposal hash",
    )
    require(
        policy.get("prior_version_must_remain_retrievable") is True,
        "prior constitutional versions must remain retrievable",
    )
    require(
        policy.get("direct_edit_to_protected_subjects_prohibited") is True,
        "direct edits to protected constitutional subjects must be prohibited",
    )
    required_domains = {
        "truth_evidence",
        "law_governance",
        "security_risk",
        "engineering_reliability",
        "business_human_impact",
    }
    require(
        set(policy.get("required_review_domains", [])) == required_domains,
        "amendment policy must require all five review domains",
    )
    emergency = policy.get("emergency_changes", {})
    require(
        emergency.get("allowed_only_through") == "break_glass_recovery_policy.json",
        "emergency constitutional changes must route through break-glass policy",
    )


def validate_break_glass(policy: dict[str, Any]) -> None:
    require(policy.get("default_behavior") == "deny", "break-glass policy must default deny")
    require(policy.get("fail_closed_on_missing_requirement") is True, "break-glass must fail closed")
    require(
        policy.get("execution_state") == "DISABLED_UNTIL_RUNTIME_IMPLEMENTED",
        "break-glass execution must remain disabled until runtime implementation",
    )
    prohibited = set(policy.get("prohibited_uses", []))
    for action in (
        "override_legal_hold",
        "override_security_veto",
        "expand_agent_permissions",
        "disable_audit_logging",
        "export_secret_values",
    ):
        require(action in prohibited, f"break-glass prohibited use missing: {action}")

    requirements = policy.get("requirements", {})
    for gate in (
        "human_overseer_required",
        "second_independent_approver_required",
        "identity_reauthentication_required",
        "incident_record_required",
        "least_privilege_required",
        "append_only_audit_required",
        "automatic_expiration_required",
        "post_action_verification_required",
        "credential_rotation_after_use_required",
        "council_review_after_containment_required",
        "root_cause_and_regression_test_required",
    ):
        require(requirements.get(gate) is True, f"break-glass requirement must be true: {gate}")

    duration = requirements.get("maximum_duration_minutes")
    require(isinstance(duration, int) and 0 < duration <= 60, "break-glass duration must be 1-60 minutes")


def main() -> int:
    for path in (CONSTITUTION, AMENDMENT, BREAK_GLASS):
        require(path.is_file(), f"missing required file: {path.relative_to(ROOT)}")

    validate_constitution()
    validate_amendment(load_json(AMENDMENT))
    validate_break_glass(load_json(BREAK_GLASS))

    if ERRORS:
        print("Dominion constitutional kernel validation FAILED:")
        for error in ERRORS:
            print(f" - {error}")
        return 1

    print("Dominion constitutional kernel validation PASSED")
    print("Validated amendment governance and disabled-by-default emergency recovery.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
