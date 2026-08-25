"""Authenticated Buddy bridge adapter for the governed revenue engine.

This module converts JSON-native request payloads into the strict revenue
engine models.  It performs no network I/O, writes no files, enrolls no
affiliate programs, and returns DRAFT_SHADOW output only.
"""

from __future__ import annotations

import json
import sys
from dataclasses import fields, is_dataclass
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from apps.revenue_engine import (  # noqa: E402
    AffiliateProgram,
    AffiliateRegistry,
    CampaignAsset,
    DraftInput,
    EvidenceState,
    KeywordEvidence,
    MetricSnapshot,
    Opportunity,
    ProgramStatus,
    run_compounding_lane,
    run_fast_cash_lane,
)


RUNTIME_SCHEMA = "radah-memshalah-revenue-runtime-v1"
MAX_PAYLOAD_BYTES = 262_144
MAX_COLLECTION_ITEMS = 1_000


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{name} must be a JSON object")
    return value


def _keys(
    value: Mapping[str, Any],
    name: str,
    *,
    required: Iterable[str],
    optional: Iterable[str] = (),
) -> None:
    required_set = set(required)
    allowed = required_set | set(optional)
    missing = sorted(required_set - set(value))
    unknown = sorted(set(value) - allowed)
    if missing:
        raise ValueError(f"{name} is missing required fields: {missing}")
    if unknown:
        raise ValueError(f"{name} contains unsupported fields: {unknown}")


def _sequence(value: Any, name: str) -> Sequence[Any]:
    if not isinstance(value, (list, tuple)):
        raise TypeError(f"{name} must be a JSON array")
    if len(value) > MAX_COLLECTION_ITEMS:
        raise ValueError(
            f"{name} exceeds the {MAX_COLLECTION_ITEMS}-item runtime limit"
        )
    return value


def _strings(value: Any, name: str) -> tuple[str, ...]:
    values = _sequence(value, name)
    if any(not isinstance(item, str) for item in values):
        raise TypeError(f"every item in {name} must be a string")
    return tuple(values)


def _enum(enum_type: type[Enum], value: Any, name: str) -> Enum:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string")
    try:
        return enum_type(value.strip().upper())
    except ValueError as exc:
        allowed = [member.value for member in enum_type]
        raise ValueError(f"{name} must be one of {allowed}") from exc


def _validate_payload(payload: Any, name: str) -> Mapping[str, Any]:
    value = _mapping(payload, name)
    try:
        encoded = json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must contain JSON-native finite values") from exc
    if len(encoded) > MAX_PAYLOAD_BYTES:
        raise ValueError(
            f"{name} exceeds the {MAX_PAYLOAD_BYTES}-byte runtime limit"
        )
    return value


def _opportunity(raw: Any) -> Opportunity:
    value = _mapping(raw, "opportunity")
    _keys(
        value,
        "opportunity",
        required=(
            "opportunity_id",
            "niche",
            "buyer_intent",
            "demand",
            "competition",
            "economics",
            "zero_capital_fit",
            "original_value_fit",
            "evidence_state",
            "evidence_refs",
        ),
    )
    return Opportunity(
        opportunity_id=value["opportunity_id"],
        niche=value["niche"],
        buyer_intent=value["buyer_intent"],
        demand=value["demand"],
        competition=value["competition"],
        economics=value["economics"],
        zero_capital_fit=value["zero_capital_fit"],
        original_value_fit=value["original_value_fit"],
        evidence_state=_enum(
            EvidenceState, value["evidence_state"], "opportunity.evidence_state"
        ),
        evidence_refs=_strings(
            value["evidence_refs"], "opportunity.evidence_refs"
        ),
    )


def _asset(raw: Any, index: int) -> CampaignAsset:
    name = f"assets[{index}]"
    value = _mapping(raw, name)
    _keys(
        value,
        name,
        required=(
            "asset_id",
            "title",
            "asset_type",
            "url_slug",
            "evidence_state",
            "evidence_refs",
        ),
        optional=("restrictions",),
    )
    return CampaignAsset(
        asset_id=value["asset_id"],
        title=value["title"],
        asset_type=value["asset_type"],
        url_slug=value["url_slug"],
        evidence_state=_enum(
            EvidenceState, value["evidence_state"], f"{name}.evidence_state"
        ),
        evidence_refs=_strings(value["evidence_refs"], f"{name}.evidence_refs"),
        restrictions=_strings(value.get("restrictions", ()), f"{name}.restrictions"),
    )


def _draft_input(raw: Any, index: int) -> DraftInput:
    name = f"draft_inputs[{index}]"
    value = _mapping(raw, name)
    _keys(
        value,
        name,
        required=("asset_id", "channel", "proposed_text", "cta", "evidence_refs"),
        optional=(
            "has_affiliate_links",
            "affiliate_program_id",
            "original_value_signals",
        ),
    )
    return DraftInput(
        asset_id=value["asset_id"],
        channel=value["channel"],
        proposed_text=value["proposed_text"],
        cta=value["cta"],
        evidence_refs=_strings(value["evidence_refs"], f"{name}.evidence_refs"),
        has_affiliate_links=value.get("has_affiliate_links", False),
        affiliate_program_id=value.get("affiliate_program_id"),
        original_value_signals=_strings(
            value.get("original_value_signals", ()),
            f"{name}.original_value_signals",
        ),
    )


def _program(raw: Any, index: int) -> AffiliateProgram:
    name = f"affiliate_programs[{index}]"
    value = _mapping(raw, name)
    _keys(
        value,
        name,
        required=(
            "program_id",
            "name",
            "status",
            "commission_rate",
            "cookie_days",
            "payout_threshold",
            "evidence_state",
            "evidence_refs",
        ),
        optional=("tracking_url", "terms_ref", "restrictions"),
    )
    return AffiliateProgram(
        program_id=value["program_id"],
        name=value["name"],
        status=_enum(ProgramStatus, value["status"], f"{name}.status"),
        commission_rate=value["commission_rate"],
        cookie_days=value["cookie_days"],
        payout_threshold=value["payout_threshold"],
        tracking_url=value.get("tracking_url"),
        terms_ref=value.get("terms_ref"),
        evidence_state=_enum(
            EvidenceState, value["evidence_state"], f"{name}.evidence_state"
        ),
        evidence_refs=_strings(value["evidence_refs"], f"{name}.evidence_refs"),
        restrictions=_strings(value.get("restrictions", ()), f"{name}.restrictions"),
    )


def _keyword_evidence(raw: Any, index: int) -> KeywordEvidence:
    name = f"keyword_evidence[{index}]"
    value = _mapping(raw, name)
    _keys(
        value,
        name,
        required=(
            "head_term",
            "variants",
            "buyer_intent_score",
            "evidence_state",
            "evidence_refs",
            "verified_at",
            "ttl_seconds",
        ),
    )
    return KeywordEvidence(
        head_term=value["head_term"],
        variants=_strings(value["variants"], f"{name}.variants"),
        buyer_intent_score=value["buyer_intent_score"],
        evidence_state=_enum(
            EvidenceState, value["evidence_state"], f"{name}.evidence_state"
        ),
        evidence_refs=_strings(value["evidence_refs"], f"{name}.evidence_refs"),
        verified_at=value["verified_at"],
        ttl_seconds=value["ttl_seconds"],
    )


def _metrics(raw: Any) -> MetricSnapshot:
    value = _mapping(raw, "prior_metrics")
    _keys(
        value,
        "prior_metrics",
        required=(
            "opportunity_id",
            "impressions",
            "visits",
            "affiliate_clicks",
            "conversions",
            "commission_accrued",
            "payout_received",
            "click_through_rate",
            "conversion_rate",
            "earnings_per_click",
            "revenue_per_visit",
            "evidence_state",
            "evidence_refs",
        ),
    )
    return MetricSnapshot(
        opportunity_id=value["opportunity_id"],
        impressions=value["impressions"],
        visits=value["visits"],
        affiliate_clicks=value["affiliate_clicks"],
        conversions=value["conversions"],
        commission_accrued=value["commission_accrued"],
        payout_received=value["payout_received"],
        click_through_rate=value["click_through_rate"],
        conversion_rate=value["conversion_rate"],
        earnings_per_click=value["earnings_per_click"],
        revenue_per_visit=value["revenue_per_visit"],
        evidence_state=_enum(
            EvidenceState, value["evidence_state"], "prior_metrics.evidence_state"
        ),
        evidence_refs=_strings(
            value["evidence_refs"], "prior_metrics.evidence_refs"
        ),
    )


def _as_of(value: Any) -> datetime:
    if not isinstance(value, str):
        raise TypeError("as_of must be an ISO-8601 string")
    raw = value.strip()
    iso_value = raw[:-1] + "+00:00" if raw.endswith("Z") else raw
    try:
        parsed = datetime.fromisoformat(iso_value)
    except ValueError as exc:
        raise ValueError("as_of must be a valid ISO-8601 datetime") from exc
    if parsed.utcoffset() is None:
        raise ValueError("as_of must include timezone information")
    return parsed.astimezone(timezone.utc)


def _jsonable(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return {field.name: _jsonable(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_jsonable(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise TypeError(f"runtime result contains unsupported type: {type(value)!r}")


def _envelope(lane: str, result: Any) -> dict[str, Any]:
    publication_state = getattr(result, "publication_state", None)
    if publication_state != "DRAFT_SHADOW":
        raise RuntimeError("revenue runtime refused non-DRAFT_SHADOW output")
    envelope = {
        "schema": RUNTIME_SCHEMA,
        "governance": "RADAH MEMSHALAH",
        "lane": lane,
        "publication_state": "DRAFT_SHADOW",
        "external_actions_executed": False,
        "review_hold": bool(getattr(result, "review_hold", False)),
        "result": _jsonable(result),
    }
    json.dumps(envelope, allow_nan=False, sort_keys=True)
    return envelope


def run_fast_cash_payload(payload: Any) -> dict[str, Any]:
    """Execute the FAST CASH simulation from a strict JSON-native payload."""

    value = _validate_payload(payload, "FAST CASH payload")
    _keys(
        value,
        "FAST CASH payload",
        required=("opportunity", "assets", "draft_inputs"),
        optional=(
            "affiliate_programs",
            "extra_evidence_refs",
            "measurement_definitions",
        ),
    )
    opportunity = _opportunity(value["opportunity"])
    assets = tuple(
        _asset(raw, index)
        for index, raw in enumerate(_sequence(value["assets"], "assets"))
    )
    draft_inputs = tuple(
        _draft_input(raw, index)
        for index, raw in enumerate(
            _sequence(value["draft_inputs"], "draft_inputs")
        )
    )
    programs = tuple(
        _program(raw, index)
        for index, raw in enumerate(
            _sequence(value.get("affiliate_programs", ()), "affiliate_programs")
        )
    )
    registry = None
    if programs:
        registry = AffiliateRegistry()
        for program in programs:
            registry.register(program)
    result = run_fast_cash_lane(
        opportunity,
        assets,
        draft_inputs,
        affiliate_registry=registry,
        extra_evidence_refs=_strings(
            value.get("extra_evidence_refs", ()), "extra_evidence_refs"
        ),
        measurement_definitions=_strings(
            value.get("measurement_definitions", ()), "measurement_definitions"
        ),
    )
    return _envelope("FAST_CASH", result)


def run_compounding_payload(payload: Any) -> dict[str, Any]:
    """Execute the COMPOUNDING simulation from a strict JSON-native payload."""

    value = _validate_payload(payload, "COMPOUNDING payload")
    _keys(
        value,
        "COMPOUNDING payload",
        required=(
            "opportunity",
            "affiliate_programs",
            "keyword_evidence",
            "consent_mechanism",
            "value_exchange",
            "email_evidence_refs",
            "as_of",
        ),
        optional=("prior_metrics",),
    )
    opportunity = _opportunity(value["opportunity"])
    programs = tuple(
        _program(raw, index)
        for index, raw in enumerate(
            _sequence(value["affiliate_programs"], "affiliate_programs")
        )
    )
    keyword_evidence = tuple(
        _keyword_evidence(raw, index)
        for index, raw in enumerate(
            _sequence(value["keyword_evidence"], "keyword_evidence")
        )
    )
    prior_metrics = (
        _metrics(value["prior_metrics"])
        if value.get("prior_metrics") is not None
        else None
    )
    result = run_compounding_lane(
        opportunity,
        programs,
        keyword_evidence,
        consent_mechanism=value["consent_mechanism"],
        value_exchange=value["value_exchange"],
        email_evidence_refs=_strings(
            value["email_evidence_refs"], "email_evidence_refs"
        ),
        prior_metrics=prior_metrics,
        as_of=_as_of(value["as_of"]),
    )
    return _envelope("COMPOUNDING", result)


__all__ = [
    "MAX_PAYLOAD_BYTES",
    "RUNTIME_SCHEMA",
    "run_compounding_payload",
    "run_fast_cash_payload",
]
