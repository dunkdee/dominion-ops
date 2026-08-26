from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from typing import Any


class RevenueRuntimeError(RuntimeError):
    pass


def deterministic_variant(experiment_id: str, visitor_id: str, treatment_pct: int = 50) -> str:
    """Stable 0-9999 bucket assignment; no mutable assignment service required."""
    if not experiment_id or not visitor_id:
        raise RevenueRuntimeError("experiment_id and visitor_id are required")
    if treatment_pct < 1 or treatment_pct > 99:
        raise RevenueRuntimeError("treatment_pct must be between 1 and 99")
    digest = hashlib.sha256(f"{experiment_id}:{visitor_id}".encode("utf-8")).digest()
    bucket = int.from_bytes(digest[:8], "big") % 10_000
    return "treatment" if bucket < treatment_pct * 100 else "control"


def normal_cdf(z: float) -> float:
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


@dataclass(frozen=True)
class Evaluation:
    decision: str
    confidence: float
    control_rate: float
    treatment_rate: float
    relative_lift: float
    control_rpv_cents: float
    treatment_rpv_cents: float
    reason: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision,
            "confidence": round(self.confidence, 6),
            "control_rate": round(self.control_rate, 8),
            "treatment_rate": round(self.treatment_rate, 8),
            "relative_lift": round(self.relative_lift, 8),
            "control_rpv_cents": round(self.control_rpv_cents, 4),
            "treatment_rpv_cents": round(self.treatment_rpv_cents, 4),
            "reason": self.reason,
        }


def evaluate_treatment(metrics: dict[str, dict[str, int]], policy: dict[str, Any]) -> Evaluation:
    """One-sided two-proportion winner gate with a revenue-per-visitor guardrail."""
    c = metrics.get("control", {})
    t = metrics.get("treatment", {})
    n0, n1 = int(c.get("visitors", 0)), int(t.get("visitors", 0))
    x0, x1 = int(c.get("conversions", 0)), int(t.get("conversions", 0))
    r0, r1 = int(c.get("revenue_cents", 0)), int(t.get("revenue_cents", 0))

    stats = policy["statistics"]
    min_visitors = int(stats["min_visitors_per_variant"])
    min_total_conversions = int(stats["min_total_conversions"])
    min_confidence = float(stats["min_confidence"])
    min_lift = float(stats["min_relative_lift"])
    min_rpv_ratio = float(stats["min_revenue_per_visitor_ratio"])

    p0 = x0 / n0 if n0 else 0.0
    p1 = x1 / n1 if n1 else 0.0
    rpv0 = r0 / n0 if n0 else 0.0
    rpv1 = r1 / n1 if n1 else 0.0
    relative_lift = ((p1 - p0) / p0) if p0 > 0 else (1.0 if p1 > 0 else 0.0)

    if n0 < min_visitors or n1 < min_visitors:
        return Evaluation("KEEP_RUNNING", 0.0, p0, p1, relative_lift, rpv0, rpv1, "MIN_VISITORS")
    if x0 + x1 < min_total_conversions:
        return Evaluation("KEEP_RUNNING", 0.0, p0, p1, relative_lift, rpv0, rpv1, "MIN_CONVERSIONS")
    if p1 <= p0:
        return Evaluation("KEEP_CONTROL", 0.0, p0, p1, relative_lift, rpv0, rpv1, "TREATMENT_NOT_BETTER")
    if relative_lift < min_lift:
        return Evaluation("KEEP_RUNNING", 0.0, p0, p1, relative_lift, rpv0, rpv1, "LIFT_BELOW_THRESHOLD")

    pooled = (x0 + x1) / (n0 + n1)
    variance = pooled * (1.0 - pooled) * ((1.0 / n0) + (1.0 / n1))
    if variance <= 0:
        return Evaluation("KEEP_RUNNING", 0.0, p0, p1, relative_lift, rpv0, rpv1, "ZERO_VARIANCE")
    z = (p1 - p0) / math.sqrt(variance)
    confidence = normal_cdf(z)

    if confidence < min_confidence:
        return Evaluation("KEEP_RUNNING", confidence, p0, p1, relative_lift, rpv0, rpv1, "CONFIDENCE_BELOW_THRESHOLD")
    if r0 > 0 and rpv1 < rpv0 * min_rpv_ratio:
        return Evaluation("KEEP_CONTROL", confidence, p0, p1, relative_lift, rpv0, rpv1, "REVENUE_GUARDRAIL")

    return Evaluation("PROMOTE_TREATMENT", confidence, p0, p1, relative_lift, rpv0, rpv1, "WINNER_GATE_PASS")
