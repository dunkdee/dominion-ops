"""Fail-closed adapter for third-party estimated market intelligence exports."""
from __future__ import annotations
import re
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import urlsplit
from .canonical import sha256_json

PROVIDERS = {"SIMILARWEB_EXPORT", "PUBLIC_WEB_ESTIMATE", "OTHER_APPROVED_ESTIMATE"}
ACQUISITION_METHODS = {"LOCAL_EXPORT", "MANUAL_RECORDED", "SIMILARWEB_DATA_EXPORTER", "SIMILARWEB_API_ENTITLED"}
SENSITIVE_KEYS = {
    "email", "phone", "name", "full_name", "address", "customer_id", "user_id",
    "cookie", "cookie_id", "device_id", "ip", "ip_address", "health_condition",
    "diagnosis", "medication", "access_token", "api_key", "secret", "password",
}
DOMAIN_PATTERN = re.compile(r"^(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$")
REQUIRED_METRICS = {"estimated_visits", "bounce_rate", "pages_per_visit", "average_visit_duration_seconds", "channel_shares"}

def _decimal(value: Any, field: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError(f"{field} must be numeric") from exc
    if not result.is_finite():
        raise ValueError(f"{field} must be finite")
    return result

def _contains_sensitive_key(value: Any) -> bool:
    if isinstance(value, dict):
        for key, item in value.items():
            if str(key).lower() in SENSITIVE_KEYS or _contains_sensitive_key(item):
                return True
    elif isinstance(value, list):
        return any(_contains_sensitive_key(item) for item in value)
    return False

def _valid_domain(value: Any) -> bool:
    if not isinstance(value, str): return False
    candidate = value.strip().lower()
    if "://" in candidate:
        parsed = urlsplit(candidate); candidate = parsed.hostname or ""
    return bool(DOMAIN_PATTERN.fullmatch(candidate))

def adapt_external_estimate(snapshot: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(snapshot, dict): raise TypeError("snapshot must be an object")
    errors: list[str] = []
    required = {"snapshot_id", "source_kind", "provider", "acquisition_method", "domain", "period_start", "period_end", "as_of", "evidence", "metrics"}
    errors.extend(f"missing_field:{field}" for field in sorted(required - set(snapshot)))
    if snapshot.get("source_kind") != "EXTERNAL_ESTIMATED": errors.append("source_kind_must_be_external_estimated")
    if snapshot.get("provider") not in PROVIDERS: errors.append("provider_not_approved")
    if snapshot.get("acquisition_method") not in ACQUISITION_METHODS: errors.append("acquisition_method_not_approved")
    if not _valid_domain(snapshot.get("domain")): errors.append("invalid_domain")
    try:
        start = date.fromisoformat(str(snapshot.get("period_start"))); end = date.fromisoformat(str(snapshot.get("period_end")))
        if start > end: errors.append("period_start_after_period_end")
    except ValueError: errors.append("invalid_period_date")
    evidence = snapshot.get("evidence")
    if not isinstance(evidence, list) or not evidence or not all(isinstance(item, str) and item.strip() for item in evidence): errors.append("evidence_must_be_nonempty_string_list")
    if _contains_sensitive_key(snapshot): errors.append("sensitive_or_secret_material_forbidden")
    metrics = snapshot.get("metrics"); normalized_metrics: dict[str, Any] = {}
    if not isinstance(metrics, dict): errors.append("metrics_must_be_object")
    else:
        errors.extend(f"missing_metric:{field}" for field in sorted(REQUIRED_METRICS - set(metrics)))
        try:
            visits = int(metrics.get("estimated_visits", -1))
            if isinstance(metrics.get("estimated_visits"), bool) or visits < 0: errors.append("estimated_visits_must_be_nonnegative_integer")
            bounce = _decimal(metrics.get("bounce_rate"), "bounce_rate")
            pages = _decimal(metrics.get("pages_per_visit"), "pages_per_visit")
            duration = int(metrics.get("average_visit_duration_seconds", -1))
            if not Decimal("0") <= bounce <= Decimal("1"): errors.append("bounce_rate_out_of_range")
            if pages < 0: errors.append("pages_per_visit_must_be_nonnegative")
            if isinstance(metrics.get("average_visit_duration_seconds"), bool) or duration < 0: errors.append("average_visit_duration_seconds_must_be_nonnegative_integer")
            shares = metrics.get("channel_shares")
            if not isinstance(shares, dict) or not shares: errors.append("channel_shares_must_be_nonempty_object"); shares = {}
            normalized_shares = {}; total = Decimal("0")
            for key, raw in sorted(shares.items()):
                share = _decimal(raw, f"channel_shares.{key}")
                if share < 0 or share > 1: errors.append(f"channel_share_out_of_range:{key}")
                total += share; normalized_shares[str(key)] = str(share.quantize(Decimal("0.0001")))
            if shares and abs(total - Decimal("1")) > Decimal("0.01"): errors.append("channel_shares_must_sum_to_one")
            normalized_metrics = {"estimated_visits": visits, "bounce_rate": str(bounce.quantize(Decimal("0.0001"))), "pages_per_visit": str(pages.quantize(Decimal("0.0001"))), "average_visit_duration_seconds": duration, "channel_shares": normalized_shares}
        except (ValueError, TypeError) as exc: errors.append(f"invalid_metric:{exc}")
    status = "HOLD" if errors else "ESTIMATED_MARKET_SIGNAL"
    result = {"snapshot_id": snapshot.get("snapshot_id"), "snapshot_hash": sha256_json(snapshot), "status": status, "source_kind": snapshot.get("source_kind"), "provider": snapshot.get("provider"), "domain": snapshot.get("domain"), "period_start": snapshot.get("period_start"), "period_end": snapshot.get("period_end"), "as_of": snapshot.get("as_of"), "metrics": normalized_metrics, "errors": sorted(set(errors)), "confidence": "ESTIMATED_NOT_FIRST_PARTY" if not errors else "UNUSABLE", "permitted_use": ["market_benchmark", "competitor_context", "scenario_input"], "prohibited_use": ["verify_revenue", "identify_individuals", "guarantee_outcomes", "authorize_external_execution"], "revenue_verified": False, "external_execution_authorized": False, "external_actions": [], "source_system_mutated": False}
    result["result_hash"] = sha256_json(result)
    return result
