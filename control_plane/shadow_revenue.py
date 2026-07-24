"""Verified-input shadow revenue analysis with no external side effects."""

from __future__ import annotations

import re
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from .canonical import sha256_json
from .revenue_simulation import simulate_revenue_funnel

HASH_PATTERN = re.compile(r"^[0-9a-f]{64}$")
VALID_SOURCE_KINDS = {"SYNTHETIC_TEST", "HISTORICAL_VERIFIED"}
MONEY = Decimal("0.01")


def _decimal(value: Any, field: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except Exception as exc:
        raise ValueError(f"{field} must be numeric") from exc
    if not result.is_finite():
        raise ValueError(f"{field} must be finite")
    return result


def run_shadow_revenue_experiment(experiment: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(experiment, dict):
        raise TypeError("experiment must be an object")

    errors: list[str] = []
    required = {
        "experiment_id",
        "owner_id",
        "proposal_hash",
        "source_snapshot",
        "baseline",
        "candidate",
        "guardrails",
    }
    errors.extend(f"missing_field:{field}" for field in sorted(required - set(experiment)))

    proposal_hash = experiment.get("proposal_hash")
    if not isinstance(proposal_hash, str) or not HASH_PATTERN.fullmatch(proposal_hash):
        errors.append("invalid_proposal_hash")
    if experiment.get("owner_id") != "revenue_operations":
        errors.append("revenue_operations_must_own_experiment")

    source = experiment.get("source_snapshot", {})
    if not isinstance(source, dict):
        errors.append("source_snapshot_must_be_object")
        source = {}
    source_kind = source.get("kind")
    if source_kind not in VALID_SOURCE_KINDS:
        errors.append("invalid_source_kind")
    evidence = source.get("evidence", [])
    if not isinstance(evidence, list) or not evidence or not all(isinstance(item, str) and item for item in evidence):
        errors.append("source_evidence_must_be_nonempty_string_list")
    if not isinstance(source.get("as_of"), str) or not source.get("as_of"):
        errors.append("source_as_of_required")

    try:
        baseline = simulate_revenue_funnel(experiment.get("baseline", {}))
        candidate = simulate_revenue_funnel(experiment.get("candidate", {}))
    except (TypeError, ValueError) as exc:
        errors.append(f"invalid_funnel:{exc}")
        baseline = None
        candidate = None

    guardrails = experiment.get("guardrails", {})
    if not isinstance(guardrails, dict):
        errors.append("guardrails_must_be_object")
        guardrails = {}
    try:
        min_visitors = int(guardrails.get("minimum_visitors", 0))
        min_margin = _decimal(guardrails.get("minimum_gross_margin", 0), "minimum_gross_margin")
        min_profit_delta = _decimal(guardrails.get("minimum_gross_profit_delta", 0), "minimum_gross_profit_delta")
        max_fixed_cost = _decimal(guardrails.get("maximum_fixed_cost", 0), "maximum_fixed_cost")
        if min_visitors < 1:
            errors.append("minimum_visitors_must_be_positive")
        if min_margin < -1 or min_margin > 1:
            errors.append("minimum_gross_margin_out_of_range")
        if max_fixed_cost < 0:
            errors.append("maximum_fixed_cost_must_be_nonnegative")
    except (TypeError, ValueError) as exc:
        errors.append(f"invalid_guardrail:{exc}")
        min_visitors = 0
        min_margin = Decimal("0")
        min_profit_delta = Decimal("0")
        max_fixed_cost = Decimal("0")

    metrics: dict[str, Any] = {}
    decision = "HOLD"
    reasons: list[str] = []
    if errors or baseline is None or candidate is None:
        reasons = ["invalid_or_incomplete_experiment"]
    else:
        baseline_profit = Decimal(baseline["economics"]["gross_profit"])
        candidate_profit = Decimal(candidate["economics"]["gross_profit"])
        candidate_margin = Decimal(candidate["economics"]["gross_margin"])
        candidate_fixed = Decimal(candidate["economics"]["fixed_cost"])
        profit_delta = candidate_profit - baseline_profit
        visitors = int(experiment["candidate"]["visitors"])
        metrics = {
            "gross_profit_delta": str(profit_delta.quantize(MONEY, rounding=ROUND_HALF_UP)),
            "candidate_gross_margin": str(candidate_margin.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)),
            "candidate_visitors": visitors,
            "candidate_fixed_cost": str(candidate_fixed.quantize(MONEY, rounding=ROUND_HALF_UP)),
        }
        if source_kind == "SYNTHETIC_TEST":
            decision = "TEST_ONLY"
            reasons = ["synthetic_inputs_cannot_support_business_promotion"]
        elif visitors < min_visitors:
            decision = "CONTINUE_SHADOW"
            reasons = ["minimum_observation_volume_not_met"]
        elif candidate_margin < min_margin:
            decision = "CONTINUE_SHADOW"
            reasons = ["minimum_margin_not_met"]
        elif profit_delta < min_profit_delta:
            decision = "CONTINUE_SHADOW"
            reasons = ["minimum_profit_delta_not_met"]
        elif candidate_fixed > max_fixed_cost:
            decision = "CONTINUE_SHADOW"
            reasons = ["maximum_fixed_cost_exceeded"]
        else:
            decision = "ELIGIBLE_FOR_COUNCIL_REVIEW"
            reasons = ["shadow_guardrails_satisfied"]

    result = {
        "mode": "SHADOW_ONLY",
        "experiment_id": experiment.get("experiment_id"),
        "experiment_hash": sha256_json(experiment),
        "proposal_hash": proposal_hash,
        "source_kind": source_kind,
        "decision": decision,
        "reasons": reasons,
        "errors": sorted(set(errors)),
        "metrics": metrics,
        "baseline_result": baseline,
        "candidate_result": candidate,
        "external_actions": [],
        "money_moved": False,
        "customers_contacted": False,
        "content_published": False,
        "production_changes": False,
        "promotion_authorized": False,
    }
    result["result_hash"] = sha256_json(result)
    return result
