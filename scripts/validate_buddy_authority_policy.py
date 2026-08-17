#!/usr/bin/env python3
"""Validate the canonical Buddy authority policy without external dependencies."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


REQUIRED_REPAIR_SERVICES = {
    "dominion-buddy-web.service",
    "dominion-proposal-queue.service",
    "dominion-sentinel.service",
}
REQUIRED_EXTERNAL_CLASSES = {
    "PUBLISH",
    "OUTREACH_OR_MESSAGE",
    "SPEND_OR_MOVE_MONEY",
    "LIVE_TRADE",
    "SIGN_OR_FILE",
    "CHANGE_CREDENTIALS",
    "CHANGE_FIREWALL",
    "OPEN_PUBLIC_INGRESS",
    "ACTIVATE_QUARANTINED_AGENT",
}
REQUIRED_AUTH_SOURCES = {
    "DIRECT_FOUNDER_INSTRUCTION",
    "ACTIVE_STANDING_FOUNDER_POLICY",
}
REQUIRED_RECEIPT_FIELDS = {
    "authorization_reference",
    "scope",
    "result",
    "evidence",
    "rollback_or_remediation",
}


class PolicyError(ValueError):
    """Raised when the policy violates a canonical invariant."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise PolicyError(message)


def _mapping(value: Any, name: str) -> dict[str, Any]:
    _require(isinstance(value, dict), f"{name} must be an object")
    return value


def _set(value: Any, name: str) -> set[str]:
    _require(isinstance(value, list), f"{name} must be an array")
    _require(all(isinstance(item, str) and item for item in value), f"{name} must contain non-empty strings")
    _require(len(value) == len(set(value)), f"{name} must not contain duplicates")
    return set(value)


def validate(policy: dict[str, Any]) -> None:
    _require(policy.get("schema") == "dominion-buddy-authority-v1", "schema mismatch")

    identity = _mapping(policy.get("identity"), "identity")
    _require(identity.get("agent_id") == "buddy", "identity.agent_id must be buddy")
    _require(identity.get("role") == "PRIMARY_PERSONAL_AI", "Buddy must be PRIMARY_PERSONAL_AI")
    _require(identity.get("principal") == "Dewayne Singleton", "principal mismatch")
    _require(identity.get("authority_model") == "FOUNDER_DIRECTED", "authority must be FOUNDER_DIRECTED")

    modes = _mapping(policy.get("operating_modes"), "operating_modes")
    expected_modes = {
        "learning": "ENABLED",
        "evolution": "PROPOSE_TEST_VERSION_ROLLBACK",
        "delegation": "ENABLED",
        "self_repair": "ENABLED",
        "external_actions": "FOUNDER_AUTHORIZED",
    }
    _require(modes == expected_modes, "operating_modes do not match the canonical Buddy model")

    auth = _mapping(policy.get("authorization"), "authorization")
    _require(_set(auth.get("accepted_sources"), "authorization.accepted_sources") == REQUIRED_AUTH_SOURCES,
             "authorization sources must be direct or standing Founder authorization")
    _require(auth.get("must_not_infer_authorization") is True, "inferred authorization must be prohibited")
    _require(auth.get("must_not_self_expand_authority") is True, "self-expanded authority must be prohibited")

    repair = _mapping(policy.get("self_repair"), "self_repair")
    _require(_set(repair.get("allowed_services"), "self_repair.allowed_services") == REQUIRED_REPAIR_SERVICES,
             "self-repair service allowlist changed")
    _require(isinstance(repair.get("max_attempts"), int) and 1 <= repair["max_attempts"] <= 3,
             "self_repair.max_attempts must be between 1 and 3")
    _require(isinstance(repair.get("cooldown_seconds"), int) and repair["cooldown_seconds"] >= 60,
             "self_repair.cooldown_seconds must be at least 60")
    _require(repair.get("independent_verifier") == "sentinel", "Sentinel must verify repair completion")
    _require(repair.get("on_exhaustion") == "STOP_AND_REPORT_BLOCKED", "repair must fail blocked")
    _require(repair.get("scope_expansion_requires_founder_authorization") is True,
             "repair scope expansion must require Founder authorization")

    evolution = _mapping(policy.get("evolution"), "evolution")
    _require(evolution.get("inference_must_be_labeled") is True, "agent inference must be labeled")
    founder_review = _set(evolution.get("founder_authorization_required_for"),
                          "evolution.founder_authorization_required_for")
    _require({"IDENTITY_CHANGE", "AUTHORITY_CHANGE", "EXTERNAL_REPRESENTATION_CHANGE"} <= founder_review,
             "identity, authority, and representation changes require Founder authorization")

    external = _mapping(policy.get("external_actions"), "external_actions")
    _require(external.get("mode") == "FOUNDER_AUTHORIZED", "external actions must be FOUNDER_AUTHORIZED")
    _require(_set(external.get("classes"), "external_actions.classes") == REQUIRED_EXTERNAL_CLASSES,
             "external action classes changed")
    _require(external.get("receipt_required") is True, "external action receipts are required")
    _require(_set(external.get("receipt_fields"), "external_actions.receipt_fields") == REQUIRED_RECEIPT_FIELDS,
             "external action receipt fields changed")

    representation = _mapping(policy.get("representation"), "representation")
    _require(representation.get("may_act_in_founder_style") is True, "Buddy must be allowed to act in Founder style")
    _require(representation.get("may_claim_founder_legal_identity") is False,
             "Buddy must not claim the Founder's legal identity")

    audit = _mapping(policy.get("audit"), "audit")
    _require(audit.get("append_only") is True, "audit records must be append-only")
    _require(audit.get("redact_secrets_and_personal_data") is True, "audit records must redact sensitive data")
    _require(audit.get("self_report_is_not_completion_evidence") is True,
             "self-report must not be completion evidence")

    conformance = _mapping(policy.get("live_conformance"), "live_conformance")
    _require(conformance.get("status") in {"UNVERIFIED", "VERIFIED"}, "invalid live conformance status")
    if conformance.get("source_state") == "VM_ONLY_UNRECONCILED":
        _require(conformance.get("status") == "UNVERIFIED",
                 "VM-only unreconciled source cannot be marked VERIFIED")


def load_and_validate(path: Path) -> None:
    try:
        policy = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PolicyError(f"cannot read policy: {exc}") from exc
    _require(isinstance(policy, dict), "policy root must be an object")
    validate(policy)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("policy", type=Path)
    args = parser.parse_args()
    try:
        load_and_validate(args.policy)
    except PolicyError as exc:
        print(f"BUDDY_POLICY=FAIL reason={exc}")
        return 1
    print("BUDDY_POLICY=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
