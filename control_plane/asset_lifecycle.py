"""Dominion adaptive asset lifecycle control.

One shared brain evaluates assets across every revenue lane. This module is
pure/deterministic: it scores evidence and emits governed dispositions; it does
not publish, spend, contact customers, move money, or mutate external systems.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
from hashlib import sha256
import json
from typing import Iterable


class Disposition(str, Enum):
    SCALE = "SCALE"
    HOLD = "HOLD"
    REPAIR = "REPAIR"
    PIVOT = "PIVOT"
    HARVEST = "HARVEST"
    RETIRE = "RETIRE"


@dataclass(frozen=True)
class AssetObservation:
    asset_id: str
    lane: str
    observed_at: str
    evidence_class: str
    demand: float
    buyer_intent: float
    conversion: float
    contribution_margin: float
    strategic_fit: float
    reliability: float
    confidence: float
    sample_size: int
    evidence_refs: tuple[str, ...] = ()


@dataclass(frozen=True)
class AssetAssessment:
    asset_id: str
    lane: str
    score: float
    confidence: float
    sample_size: int
    threshold_state: str
    council_required: bool
    recommended_disposition: str
    reasons: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    assessed_at: str


WEIGHTS = {
    "demand": 0.18,
    "buyer_intent": 0.17,
    "conversion": 0.16,
    "contribution_margin": 0.22,
    "strategic_fit": 0.10,
    "reliability": 0.09,
    "confidence": 0.08,
}


def _bounded(value: float) -> float:
    return max(0.0, min(100.0, float(value)))


def score(observation: AssetObservation) -> float:
    return round(sum(_bounded(getattr(observation, key)) * weight for key, weight in WEIGHTS.items()), 2)


def assess(
    observation: AssetObservation,
    *,
    lower_threshold: float = 45.0,
    upper_threshold: float = 78.0,
    min_confidence: float = 60.0,
    min_sample_size: int = 30,
) -> AssetAssessment:
    value = score(observation)
    sufficient = observation.confidence >= min_confidence and observation.sample_size >= min_sample_size
    reasons: list[str] = []

    if not sufficient:
        state, council, disposition = "INSUFFICIENT_EVIDENCE", False, Disposition.HOLD
        reasons.append("Minimum confidence/sample gate not met; do not infer lifecycle change from noise.")
    elif value < lower_threshold:
        state, council, disposition = "BELOW_FEASIBILITY", True, Disposition.REPAIR
        reasons.append("Feasibility score is below the governed lower threshold; Council review required.")
    elif value >= upper_threshold:
        state, council, disposition = "SCALE_CANDIDATE", True, Disposition.SCALE
        reasons.append("Score exceeds the governed scale threshold; Council should evaluate resource expansion.")
    else:
        state, council, disposition = "OPERATE", False, Disposition.HOLD
        reasons.append("Score remains inside the governed operating band.")

    if observation.contribution_margin < lower_threshold:
        reasons.append("Contribution-margin signal is weak relative to the feasibility threshold.")
    if observation.demand >= upper_threshold and observation.conversion < lower_threshold:
        reasons.append("Demand is strong while conversion is weak; diagnose offer/funnel before abandoning demand.")

    return AssetAssessment(
        asset_id=observation.asset_id,
        lane=observation.lane,
        score=value,
        confidence=_bounded(observation.confidence),
        sample_size=max(0, observation.sample_size),
        threshold_state=state,
        council_required=council,
        recommended_disposition=disposition.value,
        reasons=tuple(reasons),
        evidence_refs=observation.evidence_refs,
        assessed_at=datetime.now(timezone.utc).isoformat(),
    )


def persistent_breach(assessments: Iterable[AssetAssessment], *, periods: int = 3) -> bool:
    recent = list(assessments)[-periods:]
    return len(recent) == periods and all(item.threshold_state == "BELOW_FEASIBILITY" for item in recent)


def decision_receipt(assessment: AssetAssessment, *, decision: str, why: str, approver: str) -> dict:
    if decision not in {item.value for item in Disposition}:
        raise ValueError("invalid governed disposition")
    payload = {
        "schema": "dominion-asset-decision-v1",
        "asset_id": assessment.asset_id,
        "lane": assessment.lane,
        "score": assessment.score,
        "threshold_state": assessment.threshold_state,
        "recommended_disposition": assessment.recommended_disposition,
        "decision": decision,
        "why": why,
        "approver": approver,
        "evidence_refs": list(assessment.evidence_refs),
        "decided_at": datetime.now(timezone.utc).isoformat(),
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    payload["receipt_sha256"] = sha256(canonical).hexdigest()
    return payload


def as_record(assessment: AssetAssessment) -> dict:
    return asdict(assessment)
