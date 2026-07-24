"""Deterministic, side-effect-free revenue funnel simulation."""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from .canonical import sha256_json

RATE_FIELDS = (
    "visitor_to_lead_rate",
    "lead_to_qualified_rate",
    "qualified_to_proposal_rate",
    "proposal_to_purchase_rate",
)
MONEY = Decimal("0.01")


def _decimal(value: Any, field: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except Exception as exc:
        raise ValueError(f"{field} must be numeric") from exc
    if not result.is_finite():
        raise ValueError(f"{field} must be finite")
    return result


def simulate_revenue_funnel(scenario: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(scenario, dict):
        raise TypeError("scenario must be an object")

    visitors_value = scenario.get("visitors", 0)
    if isinstance(visitors_value, bool) or not isinstance(visitors_value, int):
        raise ValueError("visitors must be an integer")
    visitors = visitors_value
    if visitors < 0:
        raise ValueError("visitors must be nonnegative")

    rates: dict[str, Decimal] = {}
    for field in RATE_FIELDS:
        rate = _decimal(scenario.get(field, 0), field)
        if rate < 0 or rate > 1:
            raise ValueError(f"{field} must be between 0 and 1")
        rates[field] = rate

    average_order_value = _decimal(scenario.get("average_order_value", 0), "average_order_value")
    variable_cost = _decimal(scenario.get("variable_cost_per_purchase", 0), "variable_cost_per_purchase")
    fixed_cost = _decimal(scenario.get("fixed_cost", 0), "fixed_cost")
    for field, value in (("average_order_value", average_order_value), ("variable_cost_per_purchase", variable_cost), ("fixed_cost", fixed_cost)):
        if value < 0:
            raise ValueError(f"{field} must be nonnegative")

    leads = visitors * rates["visitor_to_lead_rate"]
    qualified = leads * rates["lead_to_qualified_rate"]
    proposals = qualified * rates["qualified_to_proposal_rate"]
    purchases = proposals * rates["proposal_to_purchase_rate"]
    revenue = purchases * average_order_value
    variable_total = purchases * variable_cost
    total_cost = variable_total + fixed_cost
    gross_profit = revenue - total_cost
    gross_margin = Decimal("0") if revenue == 0 else gross_profit / revenue

    def quantity(value: Decimal) -> str:
        return str(value.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP))

    def money(value: Decimal) -> str:
        return str(value.quantize(MONEY, rounding=ROUND_HALF_UP))

    result = {
        "mode": "SIMULATION_ONLY",
        "scenario_hash": sha256_json(scenario),
        "funnel": {
            "visitors": visitors,
            "leads": quantity(leads),
            "qualified_leads": quantity(qualified),
            "proposals": quantity(proposals),
            "purchases": quantity(purchases),
        },
        "economics": {
            "revenue": money(revenue),
            "variable_cost": money(variable_total),
            "fixed_cost": money(fixed_cost),
            "total_cost": money(total_cost),
            "gross_profit": money(gross_profit),
            "gross_margin": quantity(gross_margin),
        },
        "external_actions": [],
        "money_moved": False,
        "customers_contacted": False,
        "content_published": False,
    }
    result["result_hash"] = sha256_json(result)
    return result
