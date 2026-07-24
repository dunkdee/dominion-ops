#!/usr/bin/env python3
"""Validate Stage 6-or-later pre-trial capture readiness and fail-closed boundaries."""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from control_plane.canonical import sha256_json
from control_plane.trial_capture import ingest_trial_capture, summarize_trial_completeness, validate_trial_capture_plan

ERRORS: list[str] = []
REQUIRED = [
    "control_plane/trial_capture.py",
    "governance/similarweb_trial_capture_policy.json",
    "governance/schemas/trial_capture_plan.schema.json",
    "governance/schemas/trial_capture_readiness.schema.json",
    "governance/schemas/trial_capture_record.schema.json",
    "governance/schemas/trial_completeness_report.schema.json",
    "runtime/plans/similarweb_7_day_capture.json",
    "runtime/examples/stage6_similarweb_export_fixture.json",
    "scripts/stage6_trial_capture.py",
    "tests/test_control_plane_stage6.py",
    "architecture/STAGE6_TRIAL_CAPTURE_READINESS.md",
    "runtime/private/similarweb/README.md",
    "runtime/private/similarweb/.gitignore",
]


def require(condition: bool, message: str) -> None:
    if not condition:
        ERRORS.append(message)


def load(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        ERRORS.append(f"cannot load {path.relative_to(ROOT)}: {exc}")
        return {}
    require(isinstance(value, dict), f"{path.relative_to(ROOT)} must contain an object")
    return value if isinstance(value, dict) else {}


def hash_is_valid(record: dict, field: str) -> bool:
    return record.get(field) == sha256_json({key: value for key, value in record.items() if key != field})


def main() -> int:
    for item in REQUIRED:
        require((ROOT / item).is_file(), f"missing required file: {item}")

    gates = load(ROOT / "governance/runtime_activation_gates.json")
    require(isinstance(gates.get("stage"), int) and gates.get("stage") >= 6, "activation stage must be 6 or later")
    require(gates.get("mode") == "shadow_only", "runtime must remain shadow_only")
    require(gates.get("external_execution_enabled") is False, "external execution must remain disabled")
    require(gates.get("registry_mutation_enabled") is False, "registry mutation must remain disabled")
    blocked = set(gates.get("blocked_capabilities", []))
    for capability in (
        "automated_similarweb_scraping",
        "trial_activation_without_readiness",
        "trial_activation_without_new_final_five_council_release",
        "trial_data_license_violation",
        "external_distribution_of_unlicensed_market_data",
        "estimated_data_revenue_verification",
    ):
        require(capability in blocked, f"blocked capability missing: {capability}")

    policy = load(ROOT / "governance/similarweb_trial_capture_policy.json")
    require(policy.get("default_behavior") == "deny", "trial capture policy must default deny")
    prohibited = set(policy.get("prohibited_methods", []))
    require({"AUTOMATED_PLATFORM_SCRAPE", "BROWSER_BOT_SCRAPE", "CREDENTIAL_SHARING", "RATE_LIMIT_BYPASS", "SECURITY_CONTROL_BYPASS"}.issubset(prohibited), "prohibited acquisition methods are incomplete")
    require(policy.get("external_execution_authorized") is False, "trial policy may not authorize execution")
    require(policy.get("external_distribution_authorized") is False, "trial policy may not authorize external distribution")

    for name in (
        "trial_capture_plan.schema.json",
        "trial_capture_readiness.schema.json",
        "trial_capture_record.schema.json",
        "trial_completeness_report.schema.json",
    ):
        schema = load(ROOT / "governance/schemas" / name)
        require(schema.get("additionalProperties") is False, f"{name} must reject unknown fields")

    plan = load(ROOT / "runtime/plans/similarweb_7_day_capture.json")
    readiness = validate_trial_capture_plan(plan, policy)
    require(readiness.get("status") == "READY_TO_ACTIVATE_TRIAL", "approved target manifest must be ready without starting the trial")
    require(readiness.get("target_count") == 15, "committed target manifest must contain 15 targets")
    require(readiness.get("trial_started") is False, "readiness validation may not start a trial")
    require(readiness.get("automated_platform_scraping_authorized") is False, "readiness may not authorize scraping")
    require(hash_is_valid(readiness, "readiness_hash"), "readiness hash mismatch")

    reviewed_plan = copy.deepcopy(plan)
    reviewed_plan["human_target_review_completed"] = True
    reviewed = validate_trial_capture_plan(reviewed_plan, policy)
    require(reviewed.get("status") == "READY_TO_ACTIVATE_TRIAL", "human-reviewed plan must be ready without starting the trial")
    require(reviewed.get("trial_started") is False, "reviewed plan may not auto-start the trial")

    fixture = load(ROOT / "runtime/examples/stage6_similarweb_export_fixture.json")
    fixture_record = ingest_trial_capture(plan=plan, policy=policy, snapshot=fixture)
    require(fixture_record.get("status") == "TEST_ONLY", "repository fixture must remain TEST_ONLY")
    require(fixture_record.get("revenue_verified") is False, "fixture may not verify revenue")
    require(fixture_record.get("automated_platform_scraping_used") is False, "fixture ingestion may not scrape")
    require(hash_is_valid(fixture_record, "record_hash"), "fixture record hash mismatch")

    actual = copy.deepcopy(fixture)
    actual.pop("test_fixture", None)
    actual["evidence"] = ["local-export:file-sha256", "provider:similarweb", "period:2026-06"]
    actual_record = ingest_trial_capture(plan=reviewed_plan, policy=policy, snapshot=actual)
    require(actual_record.get("status") == "ACCEPTED_ESTIMATED_SIGNAL", "permitted export must be accepted only as an estimated signal")
    require(actual_record.get("revenue_verified") is False, "actual Similarweb export may not verify revenue")
    require(actual_record.get("external_distribution_authorized") is False, "actual export may not authorize distribution")

    duplicate = ingest_trial_capture(plan=reviewed_plan, policy=policy, snapshot=actual, existing_records=[actual_record])
    require(duplicate.get("status") == "HOLD", "duplicate capture must hold")
    require("duplicate_capture_rejected" in duplicate.get("errors", []), "duplicate rejection evidence missing")

    completeness = summarize_trial_completeness(reviewed_plan, policy, [actual_record])
    require(completeness.get("status") == "INCOMPLETE", "single capture cannot complete a fifteen-target plan")
    require(len(completeness.get("missing_domains", [])) == 14, "completeness report must identify fourteen missing targets")
    require(hash_is_valid(completeness, "summary_hash"), "completeness report hash mismatch")

    browser_routes = (ROOT / "apps/browser-agents/agents/__init__.py").read_text(encoding="utf-8")
    require("scrape_similarweb" not in browser_routes, "Similarity platform scraping must not be routed through Browser Agents")

    if ERRORS:
        print("Dominion Stage 6 compatibility validation FAILED:")
        for error in ERRORS:
            print(f" - {error}")
        return 1
    print("Dominion Stage 6 compatibility validation PASSED")
    print(f"Validated {len(REQUIRED)} Stage 6 contracts under Stage {gates.get('stage')} gates.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
