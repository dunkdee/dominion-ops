#!/usr/bin/env python3
"""Fail-closed validator for Dominion Commercial Release 1.0 Closure Ledger.

The ledger is a claim registry, not a self-certifying authority. This validator:
- rejects missing/invalid state fields and dangling dependencies;
- rejects CLOSED as a state vocabulary shortcut;
- requires evidence for advanced release stages;
- derives STALE effective state when runtime evidence expires;
- checks final lane claims but cannot authenticate external certification evidence.

Final certification is unavailable until an independent evidence verifier is
integrated. Ledger fields, receipt URLs and claimed approvals are untrusted
inputs; structural validation cannot promote them into release authority.

Standard library only so the gate can run anywhere Python 3 is available.
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LEDGER = ROOT / "governance" / "commercial_release_1_0" / "closure_ledger.json"

STATE_FIELDS = (
    "engineering_state",
    "deployment_state",
    "runtime_state",
    "customer_state",
    "commercial_state",
    "security_state",
    "recovery_state",
)

STATES = {
    "UNKNOWN",
    "UNVERIFIED",
    "BUILT",
    "TESTED",
    "DEPLOYED",
    "VERIFIED",
    "PROVEN",
    "CERTIFIED",
    "BLOCKED",
    "STALE",
    "NOT_APPLICABLE",
    "RETIRED",
}

PROGRESSION = [
    "BUILT",
    "TESTED",
    "DEPLOYED",
    "RUNTIME_VERIFIED",
    "END_TO_END_PROVEN",
    "COMMERCIAL_OPERATIONAL_CERTIFIED",
]

SPECIAL_STAGES = {"UNKNOWN", "BLOCKED", "STALE", "RETIRED"}
ADVANCED_STAGES = {
    "TESTED",
    "DEPLOYED",
    "RUNTIME_VERIFIED",
    "END_TO_END_PROVEN",
    "COMMERCIAL_OPERATIONAL_CERTIFIED",
}
EVIDENCE_BACKED_STATES = {"VERIFIED", "PROVEN", "CERTIFIED"}
BAD_FINAL_STATES = {"UNKNOWN", "UNVERIFIED", "BLOCKED", "STALE", "BUILT", "TESTED", "DEPLOYED"}

REQUIRED_COMPONENT_FIELDS = {
    "component_id",
    "lane_id",
    "owner",
    "purpose",
    "location",
    *STATE_FIELDS,
    "release_stage",
    "dependencies",
    "deployed_sha_or_digest",
    "last_verified_at",
    "evidence_receipts",
    "current_blocker",
    "rollback_reference",
}


def parse_dt(value: str) -> datetime:
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    result = datetime.fromisoformat(normalized)
    if result.tzinfo is None:
        raise ValueError("timestamp must include timezone")
    return result.astimezone(timezone.utc)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def receipt_expiry(receipt: dict[str, Any], ttl_hours: int) -> datetime | None:
    if receipt.get("freshness") == "IMMUTABLE":
        return None
    explicit = receipt.get("expires_at")
    if explicit:
        return parse_dt(explicit)
    return parse_dt(receipt["verified_at"]) + timedelta(hours=ttl_hours)


def validate_receipt(
    receipt: Any,
    *,
    component_id: str,
    ttl_hours: int,
    now: datetime,
    errors: list[str],
) -> tuple[str | None, bool]:
    if not isinstance(receipt, dict):
        errors.append(f"{component_id}: evidence receipt must be an object")
        return None, False
    required = {"receipt_id", "kind", "reference", "verified_at", "freshness"}
    missing = sorted(required - set(receipt))
    if missing:
        errors.append(f"{component_id}: receipt missing {', '.join(missing)}")
        return receipt.get("receipt_id"), False

    receipt_id = receipt.get("receipt_id")
    if not isinstance(receipt_id, str) or not receipt_id.strip():
        errors.append(f"{component_id}: receipt_id must be non-empty")
        receipt_id = None
    for field in ("kind", "reference"):
        if not isinstance(receipt.get(field), str) or not receipt[field].strip():
            errors.append(f"{component_id}: receipt {receipt_id or '<unknown>'} has invalid {field}")
    if receipt.get("freshness") not in {"IMMUTABLE", "EXPIRING"}:
        errors.append(f"{component_id}: receipt {receipt_id or '<unknown>'} freshness must be IMMUTABLE or EXPIRING")
        return receipt_id, False

    try:
        verified_at = parse_dt(receipt["verified_at"])
    except (TypeError, ValueError) as exc:
        errors.append(f"{component_id}: receipt {receipt_id or '<unknown>'} invalid verified_at: {exc}")
        return receipt_id, False
    if verified_at > now + timedelta(minutes=5):
        errors.append(f"{component_id}: receipt {receipt_id or '<unknown>'} verified_at is in the future")

    if receipt.get("freshness") == "IMMUTABLE":
        if receipt.get("expires_at") not in (None, ""):
            errors.append(f"{component_id}: immutable receipt {receipt_id or '<unknown>'} must not expire")
        return receipt_id, False

    try:
        expiry = receipt_expiry(receipt, ttl_hours)
    except (TypeError, ValueError) as exc:
        errors.append(f"{component_id}: receipt {receipt_id or '<unknown>'} invalid expiry: {exc}")
        return receipt_id, False
    assert expiry is not None
    if expiry <= verified_at:
        errors.append(f"{component_id}: receipt {receipt_id or '<unknown>'} expiry must be after verification")
    return receipt_id, now >= expiry


def effective_component(component: dict[str, Any], *, ttl_hours: int, now: datetime) -> dict[str, Any]:
    result = copy.deepcopy(component)
    receipts = result.get("evidence_receipts", [])
    expiring = [r for r in receipts if isinstance(r, dict) and r.get("freshness") == "EXPIRING"]
    stale = False
    for receipt in expiring:
        try:
            expiry = receipt_expiry(receipt, ttl_hours)
        except (TypeError, ValueError, KeyError):
            continue
        if expiry is not None and now >= expiry:
            stale = True
            break
    if stale:
        for field in STATE_FIELDS:
            if result.get(field) in EVIDENCE_BACKED_STATES:
                result[field] = "STALE"
        if result.get("release_stage") in {
            "RUNTIME_VERIFIED",
            "END_TO_END_PROVEN",
            "COMMERCIAL_OPERATIONAL_CERTIFIED",
        }:
            result["release_stage"] = "STALE"
    return result


def validate_component(
    component: Any,
    *,
    known_ids: set[str],
    receipt_ids: set[str],
    ttl_hours: int,
    now: datetime,
    errors: list[str],
) -> None:
    if not isinstance(component, dict):
        errors.append("component entry must be an object")
        return
    component_id = component.get("component_id", "<missing-component-id>")
    missing = sorted(REQUIRED_COMPONENT_FIELDS - set(component))
    if missing:
        errors.append(f"{component_id}: missing fields: {', '.join(missing)}")
        return

    if component.get("lane_id") not in range(1, 13):
        errors.append(f"{component_id}: lane_id must be 1..12")
    for field in ("owner", "purpose", "location"):
        if not isinstance(component.get(field), str) or not component[field].strip():
            errors.append(f"{component_id}: {field} must be non-empty")

    for field in STATE_FIELDS:
        state = component.get(field)
        if state == "CLOSED":
            errors.append(f"{component_id}: CLOSED is forbidden; use evidence-backed release stages")
        elif state not in STATES:
            errors.append(f"{component_id}: invalid {field}={state!r}")

    stage = component.get("release_stage")
    if stage == "CLOSED":
        errors.append(f"{component_id}: CLOSED is forbidden; final state is COMMERCIAL_OPERATIONAL_CERTIFIED")
    elif stage not in set(PROGRESSION) | SPECIAL_STAGES:
        errors.append(f"{component_id}: invalid release_stage={stage!r}")

    dependencies = component.get("dependencies")
    if not isinstance(dependencies, list) or any(not isinstance(x, str) for x in dependencies):
        errors.append(f"{component_id}: dependencies must be a list of component IDs")
    else:
        if len(dependencies) != len(set(dependencies)):
            errors.append(f"{component_id}: dependencies contain duplicates")
        if component_id in dependencies:
            errors.append(f"{component_id}: component cannot depend on itself")
        for dep in dependencies:
            if dep not in known_ids:
                errors.append(f"{component_id}: unknown dependency {dep}")

    if stage == "BLOCKED" or any(component.get(field) == "BLOCKED" for field in STATE_FIELDS):
        blocker = component.get("current_blocker")
        if not isinstance(blocker, str) or not blocker.strip():
            errors.append(f"{component_id}: blocked state requires current_blocker")

    receipts = component.get("evidence_receipts")
    if not isinstance(receipts, list):
        errors.append(f"{component_id}: evidence_receipts must be a list")
        receipts = []
    stale_receipt_present = False
    fresh_expiring_receipt = False
    for receipt in receipts:
        receipt_id, stale = validate_receipt(
            receipt,
            component_id=component_id,
            ttl_hours=ttl_hours,
            now=now,
            errors=errors,
        )
        if receipt_id:
            if receipt_id in receipt_ids:
                errors.append(f"{component_id}: duplicate global receipt_id {receipt_id}")
            receipt_ids.add(receipt_id)
        stale_receipt_present = stale_receipt_present or stale
        if isinstance(receipt, dict) and receipt.get("freshness") == "EXPIRING" and not stale:
            fresh_expiring_receipt = True

    last_verified = component.get("last_verified_at")
    if last_verified is not None:
        try:
            parsed_last_verified = parse_dt(last_verified)
            if parsed_last_verified > now + timedelta(minutes=5):
                errors.append(f"{component_id}: last_verified_at is in the future")
        except (TypeError, ValueError) as exc:
            errors.append(f"{component_id}: invalid last_verified_at: {exc}")

    if stage in ADVANCED_STAGES and not receipts:
        errors.append(f"{component_id}: {stage} requires at least one evidence receipt")

    if stage in {"DEPLOYED", "RUNTIME_VERIFIED", "END_TO_END_PROVEN", "COMMERCIAL_OPERATIONAL_CERTIFIED"}:
        if not component.get("deployed_sha_or_digest") and component.get("deployment_state") != "NOT_APPLICABLE":
            errors.append(f"{component_id}: {stage} requires deployed_sha_or_digest unless deployment is NOT_APPLICABLE")

    if stage == "RUNTIME_VERIFIED":
        if component.get("deployment_state") != "DEPLOYED":
            errors.append(f"{component_id}: RUNTIME_VERIFIED requires deployment_state=DEPLOYED")
        if component.get("runtime_state") != "VERIFIED":
            errors.append(f"{component_id}: RUNTIME_VERIFIED requires runtime_state=VERIFIED")
        if not fresh_expiring_receipt:
            errors.append(f"{component_id}: RUNTIME_VERIFIED requires fresh EXPIRING runtime evidence")
        if not component.get("rollback_reference"):
            errors.append(f"{component_id}: RUNTIME_VERIFIED requires rollback_reference")

    if stage == "END_TO_END_PROVEN":
        if component.get("runtime_state") not in {"VERIFIED", "PROVEN", "NOT_APPLICABLE"}:
            errors.append(f"{component_id}: END_TO_END_PROVEN requires runtime evidence")
        if component.get("customer_state") not in {"PROVEN", "NOT_APPLICABLE"}:
            errors.append(f"{component_id}: END_TO_END_PROVEN requires customer_state=PROVEN or NOT_APPLICABLE")
        if component.get("commercial_state") not in {"PROVEN", "CERTIFIED", "NOT_APPLICABLE"}:
            errors.append(f"{component_id}: END_TO_END_PROVEN requires commercial proof")
        if not component.get("rollback_reference"):
            errors.append(f"{component_id}: END_TO_END_PROVEN requires rollback_reference")

    if stage == "COMMERCIAL_OPERATIONAL_CERTIFIED":
        if component.get("current_blocker"):
            errors.append(f"{component_id}: certified component cannot have current_blocker")
        for field in STATE_FIELDS:
            if component.get(field) in BAD_FINAL_STATES:
                errors.append(f"{component_id}: certified component has non-final {field}={component.get(field)}")
        if not component.get("rollback_reference"):
            errors.append(f"{component_id}: certified component requires rollback_reference")
        if component.get("runtime_state") not in {"VERIFIED", "PROVEN", "CERTIFIED", "NOT_APPLICABLE"}:
            errors.append(f"{component_id}: certified component lacks runtime proof")
        if component.get("runtime_state") != "NOT_APPLICABLE" and not fresh_expiring_receipt:
            errors.append(f"{component_id}: certified runtime component requires fresh EXPIRING evidence")

    if stale_receipt_present and stage in {
        "RUNTIME_VERIFIED",
        "COMMERCIAL_OPERATIONAL_CERTIFIED",
    }:
        errors.append(f"{component_id}: advanced runtime claim has expired evidence and is effectively STALE")


def validate_ledger(ledger: Any, *, now: datetime, require_release_certified: bool) -> tuple[list[str], dict[str, Any]]:
    errors: list[str] = []
    if not isinstance(ledger, dict):
        return ["ledger root must be an object"], {}

    required_root = {
        "release_id",
        "release_objective",
        "generated_at",
        "default_runtime_evidence_ttl_hours",
        "allowed_progression",
        "components",
    }
    missing_root = sorted(required_root - set(ledger))
    if missing_root:
        errors.append(f"ledger missing root fields: {', '.join(missing_root)}")
        return errors, ledger

    if ledger.get("release_id") != "DOMINION-COMMERCIAL-RELEASE-1.0":
        errors.append("release_id must be DOMINION-COMMERCIAL-RELEASE-1.0")
    if ledger.get("allowed_progression") != PROGRESSION:
        errors.append("allowed_progression must exactly match the six commercial release gates")
    if not isinstance(ledger.get("release_objective"), str) or not ledger["release_objective"].strip():
        errors.append("release_objective must be non-empty")
    try:
        parse_dt(ledger["generated_at"])
    except (TypeError, ValueError) as exc:
        errors.append(f"generated_at invalid: {exc}")

    ttl_hours = ledger.get("default_runtime_evidence_ttl_hours")
    if not isinstance(ttl_hours, int) or ttl_hours < 1:
        errors.append("default_runtime_evidence_ttl_hours must be a positive integer")
        ttl_hours = 24

    components = ledger.get("components")
    if not isinstance(components, list) or not components:
        errors.append("components must be a non-empty list")
        return errors, ledger

    ids = [c.get("component_id") for c in components if isinstance(c, dict)]
    known_ids = {x for x in ids if isinstance(x, str)}
    if len(ids) != len(known_ids):
        errors.append("component_id values must be present and globally unique")

    receipt_ids: set[str] = set()
    for component in components:
        validate_component(
            component,
            known_ids=known_ids,
            receipt_ids=receipt_ids,
            ttl_hours=ttl_hours,
            now=now,
            errors=errors,
        )

    effective = copy.deepcopy(ledger)
    effective["effective_as_of"] = now.isoformat()
    effective["components"] = [
        effective_component(component, ttl_hours=ttl_hours, now=now)
        if isinstance(component, dict)
        else component
        for component in components
    ]

    if require_release_certified:
        # This program has no trusted evidence resolver or release-authority
        # verifier. Fail closed even when every supplied claim looks complete.
        # Do not replace this with a ledger flag, an environment override, or
        # a receipt-presence check: all are builder-controlled assertions.
        errors.append(
            "independent release certification evidence verification is not implemented; "
            "ledger validation cannot certify a commercial release"
        )
        lane_records: dict[int, dict[str, Any]] = {}
        for component in effective["components"]:
            if not isinstance(component, dict):
                continue
            component_id = component.get("component_id", "")
            if component_id.startswith("release.lane"):
                lane_id = component.get("lane_id")
                if isinstance(lane_id, int):
                    lane_records[lane_id] = component
        missing_lanes = sorted(set(range(1, 13)) - set(lane_records))
        if missing_lanes:
            errors.append(f"final certification missing lane records: {missing_lanes}")
        for lane_id in range(1, 13):
            lane = lane_records.get(lane_id)
            if lane and lane.get("release_stage") != "COMMERCIAL_OPERATIONAL_CERTIFIED":
                errors.append(
                    f"lane {lane_id} not commercially/operationally certified: {lane.get('release_stage')}"
                )

    return errors, effective


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER)
    parser.add_argument("--as-of", help="ISO-8601 timestamp for deterministic validation")
    parser.add_argument("--effective-json", action="store_true", help="print evidence-freshness-adjusted ledger")
    parser.add_argument(
        "--require-release-certified",
        action="store_true",
        help="check final lane claims; fails closed until independent evidence verification is implemented",
    )
    args = parser.parse_args()

    now = parse_dt(args.as_of) if args.as_of else utc_now()
    try:
        ledger = json.loads(args.ledger.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"CLOSURE_LEDGER_VALIDATION=FAIL error={exc}")
        return 1

    errors, effective = validate_ledger(
        ledger,
        now=now,
        require_release_certified=args.require_release_certified,
    )
    if args.effective_json:
        print(json.dumps(effective, indent=2, sort_keys=True))

    if errors:
        print(f"CLOSURE_LEDGER_VALIDATION=FAIL errors={len(errors)}")
        for error in errors:
            print(f"ERROR: {error}")
        return 1

    components = effective.get("components", [])
    certified = sum(
        1
        for component in components
        if isinstance(component, dict)
        and component.get("release_stage") == "COMMERCIAL_OPERATIONAL_CERTIFIED"
    )
    stale = sum(
        1
        for component in components
        if isinstance(component, dict) and component.get("release_stage") == "STALE"
    )
    print(
        "CLOSURE_LEDGER_VALIDATION=PASS "
        f"components={len(components)} certified={certified} stale={stale} "
        f"release_certified={'true' if args.require_release_certified else 'not-required'}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())