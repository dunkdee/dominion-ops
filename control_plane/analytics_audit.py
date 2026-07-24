"""Build a governed storefront growth-intelligence audit from approved evidence."""
from __future__ import annotations

from decimal import Decimal
from typing import Any

from .canonical import sha256_json


def build_growth_intelligence_audit(
    market_signal: dict[str, Any],
    *,
    first_party_evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not isinstance(market_signal, dict):
        raise TypeError("market_signal must be an object")

    errors: list[str] = []
    if market_signal.get("status") != "ESTIMATED_MARKET_SIGNAL":
        errors.append("market_signal_not_usable")
    if market_signal.get("revenue_verified") is not False:
        errors.append("estimated_signal_may_not_verify_revenue")
    if market_signal.get("external_execution_authorized") is not False:
        errors.append("market_signal_may_not_authorize_execution")

    first_party_verified = False
    if first_party_evidence is not None:
        if not isinstance(first_party_evidence, dict):
            errors.append("first_party_evidence_must_be_object")
        else:
            first_party_verified = (
                first_party_evidence.get("source_kind") == "FIRST_PARTY_VERIFIED"
                and first_party_evidence.get("status") == "VERIFIED"
                and isinstance(first_party_evidence.get("evidence"), list)
                and bool(first_party_evidence.get("evidence"))
            )
            if not first_party_verified:
                errors.append("first_party_evidence_not_verified")

    metrics = market_signal.get("metrics", {}) if isinstance(market_signal.get("metrics"), dict) else {}
    findings: list[dict[str, str]] = []
    opportunities: list[dict[str, str]] = []
    if not errors:
        bounce = Decimal(str(metrics.get("bounce_rate", "0")))
        pages = Decimal(str(metrics.get("pages_per_visit", "0")))
        duration = int(metrics.get("average_visit_duration_seconds", 0))
        shares = metrics.get("channel_shares", {})
        findings.append({
            "truth_state": "VERIFIED",
            "statement": "The supplied record is a third-party estimate and does not verify revenue.",
            "evidence": market_signal.get("result_hash", ""),
        })
        if bounce >= Decimal("0.60"):
            opportunities.append({
                "priority": "HIGH",
                "type": "landing_page_friction_review",
                "basis": "Estimated bounce rate is at or above 0.60.",
            })
        if pages < Decimal("2.0"):
            opportunities.append({
                "priority": "MEDIUM",
                "type": "internal_navigation_and_merchandising_review",
                "basis": "Estimated pages per visit is below 2.0.",
            })
        if duration < 90:
            opportunities.append({
                "priority": "MEDIUM",
                "type": "message_match_and_content_depth_review",
                "basis": "Estimated average visit duration is below 90 seconds.",
            })
        if isinstance(shares, dict) and shares:
            strongest = max(shares, key=lambda key: Decimal(str(shares[key])))
            findings.append({
                "truth_state": "INFERRED",
                "statement": f"{strongest} is the largest estimated acquisition channel in the supplied snapshot.",
                "evidence": market_signal.get("result_hash", ""),
            })
        opportunities.extend([
            {
                "priority": "FOUNDATIONAL",
                "type": "connect_first_party_measurement",
                "basis": "Conversion and revenue optimization requires first-party analytics and order evidence.",
            },
            {
                "priority": "FOUNDATIONAL",
                "type": "establish_monthly_benchmark_cycle",
                "basis": "A repeated estimate series is more useful than a single point-in-time estimate.",
            },
        ])

    status = "HOLD" if errors else (
        "EVIDENCE_READY_FOR_HUMAN_REVIEW" if first_party_verified else "MARKET_SIGNAL_ONLY"
    )
    report = {
        "product_id": "storefront_growth_intelligence",
        "status": status,
        "market_signal_hash": market_signal.get("result_hash"),
        "first_party_verified": first_party_verified,
        "findings": findings,
        "opportunities": opportunities,
        "errors": sorted(set(errors)),
        "claims_boundary": {
            "revenue_claim_allowed": False,
            "guaranteed_outcome_claim_allowed": False,
            "individual_targeting_allowed": False,
            "health_sensitive_targeting_allowed": False,
        },
        "deliverables": [
            "market_and_competitor_signal_summary",
            "storefront_friction_hypotheses",
            "prioritized_measurement_plan",
            "thirty_day_test_backlog",
        ],
        "pricing_status": "UNSET_REQUIRES_HUMAN_APPROVAL",
        "external_execution_authorized": False,
        "customer_contacted": False,
        "content_published": False,
        "money_moved": False,
    }
    report["report_hash"] = sha256_json(report)
    return report
