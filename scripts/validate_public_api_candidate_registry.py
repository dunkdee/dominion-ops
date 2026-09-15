#!/usr/bin/env python3
"""Fail-closed validation for Dominion's public API candidate registry.

The candidate registry is discovery metadata only. It must never become an
alternate runtime connector registry, credential store, or arbitrary URL
execution surface.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

EXPECTED_SCHEMA = "dominion-public-api-candidate-registry-v1"
EXPECTED_GOVERNING_NAME = "RADAH MEMSHALAH — רָדָה מֶמְשָׁלָה"
EXPECTED_RUNTIME_REGISTRY = "governance/mcp_connector_registry.json"
CANDIDATE_ID = re.compile(r"^[a-z0-9][a-z0-9_.-]{1,79}$")
ALLOWED_STATES = {
    "QUARANTINED",
    "REVIEWING",
    "VERIFIED_READ_ONLY",
    "APPROVED_FOR_RUNTIME",
}
ALLOWED_RISK = {"LOW", "MEDIUM", "HIGH"}
FORBIDDEN_CANDIDATE_KEYS = {
    "api_key",
    "apikey",
    "authorization",
    "bearer_token",
    "credential",
    "credentials",
    "endpoint",
    "headers",
    "password",
    "secret",
    "target",
    "token",
}


class RegistryValidationError(ValueError):
    """Raised when the candidate registry violates a fail-closed invariant."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise RegistryValidationError(message)


def _forbidden_keys(value: Any, path: str = "root") -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = str(key).lower().replace("-", "_")
            if normalized in FORBIDDEN_CANDIDATE_KEYS:
                found.append(f"{path}.{key}")
            found.extend(_forbidden_keys(child, f"{path}.{key}"))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found.extend(_forbidden_keys(child, f"{path}[{index}]"))
    return found


def validate_registry(data: dict[str, Any]) -> dict[str, Any]:
    _require(isinstance(data, dict), "registry_must_be_object")
    _require(data.get("schema") == EXPECTED_SCHEMA, "registry_schema_invalid")
    _require(data.get("governing_name") == EXPECTED_GOVERNING_NAME, "governing_name_invalid")
    _require(data.get("runtime_registry") == EXPECTED_RUNTIME_REGISTRY, "runtime_registry_target_invalid")
    _require(data.get("default_candidate_state") == "QUARANTINED", "registry_must_default_to_quarantine")
    _require(data.get("external_mutation_enabled") is False, "external_mutation_must_be_disabled")
    _require(data.get("automatic_activation_enabled") is False, "automatic_activation_must_be_disabled")
    _require(data.get("credential_values_allowed_in_registry") is False, "credential_values_must_be_forbidden")

    authority = data.get("authority")
    _require(isinstance(authority, dict), "authority_missing")
    for key in (
        "candidate_listing_is_not_approval",
        "runtime_promotion_requires_review",
        "runtime_promotion_requires_fixed_target",
        "runtime_promotion_requires_read_only_first",
        "runtime_promotion_requires_terms_review",
        "runtime_promotion_requires_free_tier_or_cost_review",
        "runtime_promotion_requires_rate_limit_review",
        "runtime_promotion_requires_auth_review",
        "runtime_promotion_requires_three_probe_runtime_evidence",
        "runtime_promotion_requires_receipts",
        "secrets_must_remain_server_side",
    ):
        _require(authority.get(key) is True, f"authority_required:{key}")
    _require(authority.get("arbitrary_url_invocation") is False, "arbitrary_url_invocation_must_be_disabled")
    _require(authority.get("arbitrary_scraping_activation") is False, "arbitrary_scraping_activation_must_be_disabled")

    qualification = data.get("qualification")
    _require(isinstance(qualification, dict), "qualification_missing")
    _require(qualification.get("first_runtime_effect") == "read_only", "first_runtime_effect_must_be_read_only")
    _require(qualification.get("promotion_target") == EXPECTED_RUNTIME_REGISTRY, "promotion_target_invalid")
    required_checks = qualification.get("required_checks")
    _require(isinstance(required_checks, list) and len(required_checks) >= 10, "qualification_checks_incomplete")
    for required in (
        "official_documentation",
        "terms_of_service",
        "pricing_or_free_tier",
        "authentication_method",
        "rate_limits",
        "data_rights_and_usage_restrictions",
        "three_probe_runtime_evidence",
        "provenance_mapping",
        "duplicate_capability_check",
    ):
        _require(required in required_checks, f"qualification_check_missing:{required}")

    candidates = data.get("candidates")
    _require(isinstance(candidates, dict) and candidates, "candidates_missing")
    high_priority = 0
    for candidate_id, spec in candidates.items():
        _require(bool(CANDIDATE_ID.fullmatch(candidate_id)), f"candidate_id_invalid:{candidate_id}")
        _require(isinstance(spec, dict), f"candidate_spec_invalid:{candidate_id}")
        _require(bool(str(spec.get("title") or "").strip()), f"candidate_title_missing:{candidate_id}")
        _require(bool(str(spec.get("lane") or "").strip()), f"candidate_lane_missing:{candidate_id}")
        _require(bool(str(spec.get("use_case") or "").strip()), f"candidate_use_case_missing:{candidate_id}")
        _require(spec.get("state") in ALLOWED_STATES, f"candidate_state_invalid:{candidate_id}")
        _require(spec.get("risk_level") in ALLOWED_RISK, f"candidate_risk_invalid:{candidate_id}")
        _require(spec.get("effect_ceiling") == "read_only", f"candidate_effect_not_read_only:{candidate_id}")
        score = spec.get("priority_score")
        _require(isinstance(score, int) and not isinstance(score, bool) and 0 <= score <= 100, f"candidate_score_invalid:{candidate_id}")
        high_priority += int(score >= 80)
        discovery_url = spec.get("discovery_url")
        _require(isinstance(discovery_url, str) and discovery_url.startswith("https://"), f"candidate_discovery_url_invalid:{candidate_id}")
        if spec.get("state") == "QUARANTINED":
            _require(spec.get("runtime_verified") is False, f"quarantined_candidate_cannot_be_runtime_verified:{candidate_id}")
        forbidden = _forbidden_keys(spec, f"candidates.{candidate_id}")
        _require(not forbidden, f"candidate_contains_runtime_or_secret_fields:{candidate_id}:{','.join(forbidden)}")

    _require(high_priority >= 1, "registry_has_no_high_priority_candidates")
    return {
        "schema": data["schema"],
        "candidate_count": len(candidates),
        "high_priority_count": high_priority,
        "status": "PASS",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "path",
        nargs="?",
        default="governance/public_api_candidate_registry.json",
        help="Path to the candidate registry JSON.",
    )
    args = parser.parse_args()
    path = Path(args.path)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        result = validate_registry(data)
    except (OSError, json.JSONDecodeError, RegistryValidationError) as exc:
        print(f"PUBLIC_API_CANDIDATE_REGISTRY=FAIL detail={exc}")
        return 1
    print(
        "PUBLIC_API_CANDIDATE_REGISTRY=PASS "
        f"candidates={result['candidate_count']} high_priority={result['high_priority_count']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
