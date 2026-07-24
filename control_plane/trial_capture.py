"""Compliant seven-day market-intelligence trial capture planning and offline ingestion."""
from __future__ import annotations

import re
from collections import Counter
from typing import Any
from urllib.parse import urlsplit

from .canonical import sha256_json
from .external_estimates import adapt_external_estimate

DOMAIN_PATTERN = re.compile(r"^(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$")
APPROVED_ACQUISITION_METHODS = {"LOCAL_EXPORT", "MANUAL_RECORDED", "SIMILARWEB_DATA_EXPORTER", "SIMILARWEB_API_ENTITLED"}
PROHIBITED_ACQUISITION_METHODS = {"AUTOMATED_PLATFORM_SCRAPE", "BROWSER_BOT_SCRAPE", "CREDENTIAL_SHARING", "RATE_LIMIT_BYPASS", "SECURITY_CONTROL_BYPASS"}
ALLOWED_METRICS = {"estimated_visits", "bounce_rate", "pages_per_visit", "average_visit_duration_seconds", "channel_shares", "geography_shares", "search_keywords", "referral_domains", "audience_interests", "technology_signals"}
REQUIRED_CORE_METRICS = {"estimated_visits", "bounce_rate", "pages_per_visit", "average_visit_duration_seconds", "channel_shares"}


def _normalize_domain(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    candidate = value.strip().lower()
    if "://" in candidate:
        candidate = urlsplit(candidate).hostname or ""
    return candidate.rstrip(".")


def _valid_domain(value: Any) -> bool:
    return bool(DOMAIN_PATTERN.fullmatch(_normalize_domain(value)))


def validate_trial_capture_plan(plan: dict[str, Any], policy: dict[str, Any]) -> dict[str, Any]:
    """Validate a pre-trial plan without starting the trial or accessing Similarweb."""
    if not isinstance(plan, dict):
        raise TypeError("plan must be an object")
    if not isinstance(policy, dict):
        raise TypeError("policy must be an object")

    errors: list[str] = []
    warnings: list[str] = []
    required = {"plan_id", "provider", "trial_window_days", "activation_status", "acquisition_methods", "targets", "daily_schedule", "storage", "billing_control", "quality_gates", "credit_control"}
    errors.extend(f"missing_field:{field}" for field in sorted(required - set(plan)))

    if plan.get("provider") != "SIMILARWEB":
        errors.append("provider_must_be_similarweb")
    if plan.get("trial_window_days") != 7:
        errors.append("trial_window_must_be_seven_days")
    if plan.get("activation_status") != "NOT_STARTED":
        errors.append("pretrial_plan_must_not_be_active")

    methods = plan.get("acquisition_methods", [])
    if not isinstance(methods, list) or not methods:
        errors.append("acquisition_methods_must_be_nonempty_list")
        methods = []
    else:
        methods = [str(item) for item in methods]
        prohibited = sorted(set(methods) & PROHIBITED_ACQUISITION_METHODS)
        errors.extend(f"prohibited_acquisition_method:{item}" for item in prohibited)
        unknown = sorted(set(methods) - APPROVED_ACQUISITION_METHODS - PROHIBITED_ACQUISITION_METHODS)
        errors.extend(f"unknown_acquisition_method:{item}" for item in unknown)
        if not set(methods) & APPROVED_ACQUISITION_METHODS:
            errors.append("no_approved_acquisition_method")
        if "SIMILARWEB_API_ENTITLED" in methods and plan.get("credit_control", {}).get("api_entitlement_required") is not True:
            errors.append("api_method_requires_entitlement_gate")

    targets = plan.get("targets", [])
    normalized_targets: list[dict[str, Any]] = []
    if not isinstance(targets, list) or not targets:
        errors.append("targets_must_be_nonempty_list")
        targets = []
    seen_domains: set[str] = set()
    priorities: list[int] = []
    for index, target in enumerate(targets):
        if not isinstance(target, dict):
            errors.append(f"target_not_object:{index}")
            continue
        domain = _normalize_domain(target.get("domain"))
        if not _valid_domain(domain):
            errors.append(f"invalid_target_domain:{index}")
        elif domain in seen_domains:
            errors.append(f"duplicate_target_domain:{domain}")
        else:
            seen_domains.add(domain)
        priority = target.get("priority")
        if isinstance(priority, bool) or not isinstance(priority, int) or priority < 1:
            errors.append(f"invalid_target_priority:{domain or index}")
        else:
            priorities.append(priority)
        metrics = target.get("metrics")
        if not isinstance(metrics, list) or not metrics:
            errors.append(f"target_metrics_required:{domain or index}")
            metrics = []
        else:
            unknown_metrics = sorted(set(metrics) - ALLOWED_METRICS)
            errors.extend(f"unsupported_metric:{domain}:{metric}" for metric in unknown_metrics)
            missing_core = sorted(REQUIRED_CORE_METRICS - set(metrics))
            errors.extend(f"missing_core_metric:{domain}:{metric}" for metric in missing_core)
        countries = target.get("countries")
        if not isinstance(countries, list) or not countries or not all(isinstance(item, str) and len(item) in {2, 3} for item in countries):
            errors.append(f"target_countries_invalid:{domain or index}")
        purpose = target.get("purpose")
        if purpose not in {"OWNED_BASELINE", "DIRECT_BENCHMARK", "CATEGORY_LEADER", "SERVICE_PRODUCT_BENCHMARK"}:
            errors.append(f"target_purpose_invalid:{domain or index}")
        normalized_targets.append({"domain": domain, "vertical_id": target.get("vertical_id"), "priority": priority, "purpose": purpose, "countries": countries if isinstance(countries, list) else [], "metrics": sorted(set(metrics)) if isinstance(metrics, list) else []})
    if priorities and len(priorities) != len(set(priorities)):
        errors.append("target_priorities_must_be_unique")

    daily = plan.get("daily_schedule", [])
    if not isinstance(daily, list) or len(daily) != 8:
        errors.append("daily_schedule_must_cover_preflight_and_seven_days")
    else:
        expected_days = list(range(0, 8))
        actual_days = [item.get("day") for item in daily if isinstance(item, dict)]
        if actual_days != expected_days:
            errors.append("daily_schedule_days_must_be_zero_through_seven")
        for item in daily:
            if not isinstance(item, dict) or not isinstance(item.get("tasks"), list) or not item.get("tasks"):
                errors.append("daily_schedule_tasks_required")
                break

    storage = plan.get("storage", {})
    required_storage = {"raw_export_path", "normalized_path", "manifest_path", "evidence_ledger_path"}
    if not isinstance(storage, dict) or not required_storage.issubset(storage):
        errors.append("storage_paths_incomplete")
    elif any(not isinstance(storage.get(key), str) or not storage.get(key).strip() for key in required_storage):
        errors.append("storage_paths_must_be_nonempty")

    billing = plan.get("billing_control", {})
    if not isinstance(billing, dict):
        errors.append("billing_control_must_be_object")
    else:
        if billing.get("auto_billing_acknowledged") is not True:
            errors.append("auto_billing_must_be_acknowledged")
        if billing.get("cancellation_checkpoint_day") not in {5, 6}:
            errors.append("cancellation_checkpoint_must_be_day_five_or_six")
        if billing.get("owner") != "human_overseer":
            errors.append("billing_owner_must_be_human_overseer")
        if billing.get("automatic_cancellation") is not False:
            errors.append("automatic_cancellation_not_authorized")

    credit = plan.get("credit_control", {})
    if not isinstance(credit, dict):
        errors.append("credit_control_must_be_object")
    else:
        if credit.get("discover_capabilities_before_paid_queries") is not True:
            errors.append("capability_discovery_required_before_queries")
        reserve = credit.get("reserve_percent")
        if isinstance(reserve, bool) or not isinstance(reserve, int) or not 0 <= reserve <= 50:
            errors.append("credit_reserve_percent_out_of_range")
        rate = credit.get("max_requests_per_second")
        if isinstance(rate, bool) or not isinstance(rate, int) or not 1 <= rate <= 10:
            errors.append("request_rate_must_be_between_one_and_ten")

    quality = plan.get("quality_gates", [])
    required_gates = {"source_evidence_recorded", "domain_and_period_validated", "duplicate_capture_rejected", "estimated_data_not_revenue_verified", "daily_completeness_reported", "no_automated_platform_scraping"}
    if not isinstance(quality, list):
        errors.append("quality_gates_must_be_list")
    else:
        missing = sorted(required_gates - set(quality))
        errors.extend(f"missing_quality_gate:{item}" for item in missing)

    if policy.get("default_behavior") != "deny":
        errors.append("policy_must_default_deny")
    policy_prohibited = set(policy.get("prohibited_methods", []))
    if not PROHIBITED_ACQUISITION_METHODS.issubset(policy_prohibited):
        errors.append("policy_prohibited_methods_incomplete")
    if len(targets) > int(policy.get("maximum_trial_targets", 100)):
        errors.append("target_count_exceeds_policy_limit")
    if len(targets) < int(policy.get("minimum_trial_targets", 1)):
        errors.append("target_count_below_policy_minimum")
    if plan.get("human_target_review_completed") is not True:
        warnings.append("human_target_review_required_before_trial_activation")

    status = "READY_TO_ACTIVATE_TRIAL" if not errors and not warnings else "READY_FOR_HUMAN_TARGET_REVIEW" if not errors else "HOLD"
    result = {"plan_id": plan.get("plan_id"), "plan_hash": sha256_json(plan), "status": status, "errors": sorted(set(errors)), "warnings": sorted(set(warnings)), "target_count": len(normalized_targets), "targets": sorted(normalized_targets, key=lambda item: (item.get("priority") or 9999, item.get("domain") or "")), "approved_acquisition_methods": sorted(set(methods) & APPROVED_ACQUISITION_METHODS), "automated_platform_scraping_authorized": False, "trial_started": False, "external_execution_authorized": False, "external_distribution_authorized": False, "external_actions": []}
    result["readiness_hash"] = sha256_json(result)
    return result


def ingest_trial_capture(*, plan: dict[str, Any], policy: dict[str, Any], snapshot: dict[str, Any], existing_records: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Ingest one permitted export or manual/API record without network access."""
    readiness = validate_trial_capture_plan(plan, policy)
    errors: list[str] = []
    if readiness["status"] not in {"READY_TO_ACTIVATE_TRIAL", "READY_FOR_HUMAN_TARGET_REVIEW"}:
        errors.append("capture_plan_not_ready")
    method = snapshot.get("acquisition_method") if isinstance(snapshot, dict) else None
    if method not in readiness.get("approved_acquisition_methods", []):
        errors.append("snapshot_acquisition_method_not_in_plan")
    if method in PROHIBITED_ACQUISITION_METHODS:
        errors.append("automated_platform_scraping_forbidden")
    domain = _normalize_domain(snapshot.get("domain") if isinstance(snapshot, dict) else None)
    target_domains = {item.get("domain") for item in readiness.get("targets", [])}
    if domain not in target_domains:
        errors.append("snapshot_domain_not_in_target_plan")
    adapted = adapt_external_estimate(snapshot) if isinstance(snapshot, dict) else {"status": "HOLD", "errors": ["snapshot_not_object"]}
    if adapted.get("status") != "ESTIMATED_MARKET_SIGNAL":
        errors.append("external_estimate_adapter_hold")
    fingerprint_payload = {"provider": snapshot.get("provider") if isinstance(snapshot, dict) else None, "domain": domain, "period_start": snapshot.get("period_start") if isinstance(snapshot, dict) else None, "period_end": snapshot.get("period_end") if isinstance(snapshot, dict) else None, "metrics": adapted.get("metrics")}
    fingerprint = sha256_json(fingerprint_payload)
    existing_records = existing_records or []
    if fingerprint in {item.get("capture_fingerprint") for item in existing_records if isinstance(item, dict)}:
        errors.append("duplicate_capture_rejected")
    target = next((item for item in readiness.get("targets", []) if item.get("domain") == domain), {})
    fixture_only = bool(snapshot.get("test_fixture")) if isinstance(snapshot, dict) else False
    record = {"capture_id": snapshot.get("snapshot_id") if isinstance(snapshot, dict) else None, "capture_fingerprint": fingerprint, "plan_id": plan.get("plan_id"), "plan_hash": readiness.get("plan_hash"), "domain": domain, "vertical_id": target.get("vertical_id"), "priority": target.get("priority"), "acquisition_method": method, "status": "TEST_ONLY" if fixture_only and not errors else "ACCEPTED_ESTIMATED_SIGNAL" if not errors else "HOLD", "errors": sorted(set(errors)), "source_record": adapted, "fixture_only": fixture_only, "revenue_verified": False, "automated_platform_scraping_used": False, "external_execution_authorized": False, "external_actions": [], "source_system_mutated": False, "external_distribution_authorized": False, "license_status": "INTERNAL_USE_ONLY_UNLESS_SEPARATELY_LICENSED"}
    record["record_hash"] = sha256_json(record)
    return record


def summarize_trial_completeness(plan: dict[str, Any], policy: dict[str, Any], records: list[dict[str, Any]]) -> dict[str, Any]:
    """Produce a deterministic gap report for the seven-day collection window."""
    readiness = validate_trial_capture_plan(plan, policy)
    expected = [item.get("domain") for item in readiness.get("targets", [])]
    accepted = [item.get("domain") for item in records if isinstance(item, dict) and item.get("status") == "ACCEPTED_ESTIMATED_SIGNAL"]
    counts = Counter(accepted)
    missing = sorted(domain for domain in expected if counts.get(domain, 0) == 0)
    duplicates = sorted(domain for domain, count in counts.items() if count > 1)
    held = sorted(item.get("capture_id") or "unknown" for item in records if isinstance(item, dict) and item.get("status") != "ACCEPTED_ESTIMATED_SIGNAL")
    status = "COMPLETE_FOR_REVIEW" if not missing and not duplicates and not held and readiness["status"] == "READY_TO_ACTIVATE_TRIAL" else "INCOMPLETE"
    result = {"plan_id": plan.get("plan_id"), "status": status, "expected_target_count": len(expected), "accepted_target_count": len(set(accepted)), "accepted_record_count": len(accepted), "missing_domains": missing, "duplicate_domains": duplicates, "held_capture_ids": held, "ready_for_trial_activation": readiness["status"] == "READY_TO_ACTIVATE_TRIAL", "revenue_verified": False, "automated_platform_scraping_authorized": False, "external_execution_authorized": False, "external_distribution_authorized": False, "external_actions": []}
    result["summary_hash"] = sha256_json(result)
    return result
