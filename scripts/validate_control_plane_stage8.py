#!/usr/bin/env python3
"""Validate Stage 8 final Five Council release controls and approved evidence records."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from control_plane.canonical import sha256_json
from control_plane.final_release import evaluate_final_release
from control_plane.trial_capture import validate_trial_capture_plan

ERRORS: list[str] = []
RECORDS = ROOT / "runtime" / "records" / "stage8" / "similarweb_target_approval"


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
    required = [
        "control_plane/final_release.py",
        "governance/final_release_policy.json",
        "governance/five_council_policy.json",
        "governance/approvals/similarweb_target_manifest_approval.json",
        "governance/schemas/final_release_policy.schema.json",
        "governance/schemas/kdp_title_inventory.schema.json",
        "revenue/kdp/title_inventory.json",
        "runtime/records/stage8/similarweb_target_approval/release_request.json",
        "runtime/records/stage8/similarweb_target_approval/final_decision.json",
        "runtime/records/stage8/similarweb_target_approval/reviews/truth_evidence.json",
        "runtime/records/stage8/similarweb_target_approval/reviews/law_governance.json",
        "runtime/records/stage8/similarweb_target_approval/reviews/security_risk.json",
        "runtime/records/stage8/similarweb_target_approval/reviews/engineering_reliability.json",
        "runtime/records/stage8/similarweb_target_approval/reviews/business_human_impact.json",
        "architecture/STAGE8_FINAL_COUNCIL_RELEASE.md",
        "tests/test_control_plane_stage8.py",
    ]
    for item in required:
        require((ROOT / item).is_file(), f"missing required file: {item}")

    gates = load(ROOT / "governance/runtime_activation_gates.json")
    require(gates.get("stage") == 8, "activation stage must be 8")
    require(gates.get("mode") == "shadow_only", "runtime must remain shadow_only")
    require(gates.get("external_execution_enabled") is False, "external execution must remain disabled")
    require(gates.get("similarweb_target_manifest_approved") is True, "target manifest approval must be recorded")
    require(gates.get("similarweb_trial_activation_enabled") is False, "trial activation must remain disabled")
    require(gates.get("final_release_gate") == "FIVE_COUNCIL_UNANIMOUS_AFTER_HUMAN_SCOPE_AUTHORIZATION", "final release gate is incorrect")
    blocked = set(gates.get("blocked_capabilities", []))
    for capability in (
        "trial_activation_without_new_final_five_council_release",
        "consequential_release_without_human_scope_authorization",
        "consequential_release_without_all_five_independent_reviews",
        "consequential_release_before_final_council_decision",
    ):
        require(capability in blocked, f"missing Stage 8 blocked capability: {capability}")

    policy = load(ROOT / "governance/final_release_policy.json")
    require(policy.get("default_behavior") == "deny", "final release policy must default deny")
    require(policy.get("final_affirmative_gate") == "five_council", "Five Council must be the final affirmative gate")
    require(policy.get("release_sequence") == [
        "technical_readiness_verified",
        "human_scope_authorization_recorded",
        "five_council_independent_final_review",
        "release_within_approved_scope",
    ], "final release sequence is incorrect")
    require(policy.get("council_requirements", {}).get("all_five_reviews_required") is True, "all five reviews must be required")
    require(policy.get("council_requirements", {}).get("unanimous_approval_required") is True, "unanimous approval must be required")
    require(policy.get("human_authority", {}).get("may_revoke_or_emergency_stop_at_any_time") is True, "human emergency stop must remain available")
    require(policy.get("human_authority", {}).get("post_council_affirmative_click_required") is False, "Council must remain the last affirmative gate")

    council_policy = load(ROOT / "governance/five_council_policy.json")
    require(council_policy.get("final_release", {}).get("final_affirmative_gate") == "five_council", "Council policy final release setting is missing")
    require(council_policy.get("final_release", {}).get("human_scope_authorization_must_precede_reviews") is True, "human authorization ordering is missing")

    human = load(ROOT / "governance/approvals/similarweb_target_manifest_approval.json")
    require(hash_is_valid(human, "approval_hash"), "human target approval hash mismatch")
    require(human.get("approved") is True and human.get("approver") == "human_overseer", "human target approval is invalid")
    require(human.get("authorization_sequence") == 2, "human authorization sequence must be 2")
    require(human.get("external_execution_authorized") is False, "target approval may not authorize execution")

    trial_policy = load(ROOT / "governance/similarweb_trial_capture_policy.json")
    plan = load(ROOT / "runtime/plans/similarweb_7_day_capture.json")
    readiness = validate_trial_capture_plan(plan, trial_policy)
    require(plan.get("human_target_review_completed") is True, "target plan must record human review")
    require(plan.get("activation_status") == "NOT_STARTED", "trial must remain NOT_STARTED")
    require(readiness.get("status") == "READY_TO_ACTIVATE_TRIAL", "approved target plan must be technically ready")
    require(readiness.get("trial_started") is False, "readiness must not start the trial")

    request = load(RECORDS / "release_request.json")
    require(hash_is_valid(request, "release_request_hash"), "release request hash mismatch")
    require(request.get("human_authorization_hash") == human.get("approval_hash"), "release request is not bound to human approval")
    require(request.get("human_authorization_sequence") < request.get("council_review_sequence"), "Council review must follow human authorization")
    require(request.get("scope") == "target_manifest_approval_only", "release scope must remain target-only")
    require(request.get("trial_started") is False, "release request may not start trial")

    reviews = [load(path) for path in sorted((RECORDS / "reviews").glob("*.json"))]
    require(len(reviews) == 5, "exactly five final Council reviews are required")
    require(len({item.get("council_id") for item in reviews}) == 5, "final Council reviews must be unique")
    for review in reviews:
        require(hash_is_valid(review, "review_hash"), f"review hash mismatch: {review.get('council_id')}")
        require(review.get("independent") is True, f"review must be independent: {review.get('council_id')}")
        require(review.get("release_request_hash") == request.get("release_request_hash"), f"review request mismatch: {review.get('council_id')}")
        require(review.get("review_sequence", 0) > human.get("authorization_sequence", 0), f"review precedes human authorization: {review.get('council_id')}")
        require(review.get("decision") in {"APPROVE", "APPROVE_WITH_CONDITIONS"}, f"non-approving final review: {review.get('council_id')}")

    generated = evaluate_final_release(
        release_request=request,
        human_authorization=human,
        council_reviews=reviews,
        final_release_policy=policy,
        council_policy=council_policy,
        activation_gates=gates,
    )
    stored = load(RECORDS / "final_decision.json")
    require(generated == stored, "stored final Council decision is not reproducible")
    require(stored.get("decision") == "FINAL_RELEASE_APPROVED", "target manifest final Council decision must approve its narrow scope")
    require(stored.get("approved_scope") == "target_manifest_approval_only", "Council approved scope is too broad")
    require(len(stored.get("approvals", [])) == 5, "all five Council approvals must be preserved")
    require(stored.get("trial_activation_authorized") is False, "target approval may not authorize trial activation")
    require(stored.get("external_execution_authorized") is False, "target approval may not authorize external execution")

    inventory = load(ROOT / "revenue/kdp/title_inventory.json")
    require(hash_is_valid(inventory, "inventory_hash"), "KDP inventory hash mismatch")
    require(inventory.get("inventory_status") == "VISUALLY_VERIFIED_PARTIAL", "KDP inventory evidence state is incorrect")
    require(inventory.get("coverage_status") == "PARTIAL_ACCOUNT_VIEW", "KDP inventory coverage must remain partial")
    require(len(inventory.get("titles", [])) == 2, "KDP inventory must contain two observed titles")
    require(inventory.get("revenue_verified") is False, "KDP screenshots may not verify revenue")
    for title in inventory.get("titles", []):
        require(title.get("listing_status") == "LIVE", f"KDP observed listing is not live: {title.get('title_id')}")
        require(title.get("rights_status") == "UNVERIFIED", f"KDP rights must remain unverified: {title.get('title_id')}")
        require(title.get("sales_verified") is False and title.get("royalties_verified") is False, f"KDP revenue evidence overstated: {title.get('title_id')}")

    for name in ("final_release_policy.schema.json", "kdp_title_inventory.schema.json"):
        schema = load(ROOT / "governance/schemas" / name)
        require(schema.get("additionalProperties") is False, f"{name} must reject unknown root fields")

    if ERRORS:
        print("Dominion Stage 8 validation FAILED:")
        for error in ERRORS:
            print(f" - {error}")
        return 1
    print("Dominion Stage 8 validation PASSED")
    print(f"Validated {len(required)} Stage 8 controls and evidence records.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
