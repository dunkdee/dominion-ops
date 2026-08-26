#!/usr/bin/env python3
"""Fail-closed constitutional guard for RADAH MEMSHALAH lane execution.

This module grants no authority. It proves that the runtime copy of Dominion's
constitutional chain and lane contracts are mutually consistent before the
scheduler may plan or execute work.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class ConstitutionalGuardError(RuntimeError):
    pass


REQUIRED_CONSTITUTION_PHRASES = (
    "Evidence before assertion",
    "No autonomous authority expansion",
    "Human final authority",
    "Five Council",
    "Incident-learning rule",
    "Every consequential execution path must obtain a policy decision",
)

REQUIRED_RUNTIME_FIELDS = {
    "principal_agent",
    "worker_id",
    "execution_binding",
    "dependencies",
    "implementation_paths",
    "input_contract",
    "output_contract",
    "work_queue",
    "failure_queue",
    "health_signals",
    "evidence_location",
    "metrics",
    "recovery_contract",
    "escalation_to",
}

REQUIRED_PROFIT_FIELDS = {
    "demand_evidence",
    "buyer_definition",
    "offer",
    "acquisition",
    "conversion",
    "transaction",
    "delivery",
    "unit_economics",
    "attribution",
    "support_and_refunds",
    "retention_or_repeatability",
    "profit_kpis",
    "hard_blockers",
    "revenue_proof_gate",
}

ECONOMIC_LANES = {
    "commerce_fulfillment",
    "kdp_publishing",
    "analytics_services",
    "digital_products",
    "services_lead_generation",
    "content_traffic",
    "surplus",
    "trading",
}


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ConstitutionalGuardError(f"missing constitutional runtime file: {path.name}") from exc
    except json.JSONDecodeError as exc:
        raise ConstitutionalGuardError(f"invalid constitutional runtime JSON: {path.name}") from exc
    if not isinstance(value, dict):
        raise ConstitutionalGuardError(f"constitutional runtime file must be an object: {path.name}")
    return value


def _nonempty_sequence(value: Any) -> bool:
    return isinstance(value, list) and bool(value) and all(isinstance(v, str) and v.strip() for v in value)


def validate_runtime_root(runtime_root: Path) -> dict[str, Any]:
    governance = runtime_root / "governance"
    agents = runtime_root / "agents"

    constitution_path = governance / "SYSTEM_CONSTITUTION.md"
    try:
        constitution = constitution_path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise ConstitutionalGuardError("SYSTEM_CONSTITUTION.md missing from runtime") from exc
    for phrase in REQUIRED_CONSTITUTION_PHRASES:
        if phrase not in constitution:
            raise ConstitutionalGuardError(f"constitution invariant missing: {phrase}")

    authority = _load_json(governance / "authority_matrix.json")
    council = _load_json(governance / "five_council_policy.json")
    incident = _load_json(governance / "incident_learning_policy.json")
    legal = _load_json(governance / "legal_evidence_policy.json")
    amendment = _load_json(governance / "constitutional_amendment_policy.json")
    registry = _load_json(agents / "registry.json")
    verticals = _load_json(governance / "verticals.json")
    access = _load_json(governance / "lane_access_policy.json")
    contracts = _load_json(governance / "lane_runtime_contracts.json")
    profit = _load_json(governance / "profitability_lane_contracts.json")

    if authority.get("default_behavior") != "deny":
        raise ConstitutionalGuardError("authority matrix is not default-deny")
    if authority.get("human_final_authority") != "human_overseer":
        raise ConstitutionalGuardError("human_overseer is not final authority")
    if authority.get("independent_veto_domains") != ["law_governance", "security_risk"]:
        raise ConstitutionalGuardError("constitutional veto domains drifted")

    councils = {row.get("id") for row in council.get("councils", []) if isinstance(row, dict)}
    if councils != {
        "truth_evidence",
        "law_governance",
        "security_risk",
        "engineering_reliability",
        "business_human_impact",
    }:
        raise ConstitutionalGuardError("Five Council membership drifted")

    closure = incident.get("closure_gates") or {}
    for gate in (
        "root_cause_required",
        "control_change_required",
        "regression_test_required",
        "verification_required",
        "recurrence_monitor_required",
    ):
        if closure.get(gate) is not True:
            raise ConstitutionalGuardError(f"incident-learning closure gate disabled: {gate}")
    self_mod = incident.get("self_modification") or {}
    if self_mod.get("agent_may_activate") is not False or self_mod.get("requires_version_control") is not True:
        raise ConstitutionalGuardError("incident-learning self-modification boundary drifted")

    if legal.get("default_legal_status") != "UNRESOLVED":
        raise ConstitutionalGuardError("legal evidence policy must default to UNRESOLVED")
    fail_closed = set(legal.get("fail_closed_statuses") or [])
    if not {"CONFLICTED", "UNRESOLVED", "REQUIRES_COUNSEL"}.issubset(fail_closed):
        raise ConstitutionalGuardError("legal fail-closed states are incomplete")
    if legal.get("hold_response") != {"legal_status": "UNRESOLVED", "action": "HOLD"}:
        raise ConstitutionalGuardError("legal hold response drifted")

    if amendment.get("default_behavior") != "deny":
        raise ConstitutionalGuardError("constitutional amendment policy is not default-deny")
    if amendment.get("direct_edit_to_protected_subjects_prohibited") is not True:
        raise ConstitutionalGuardError("protected constitutional direct edits are not prohibited")
    if amendment.get("unanimous_council_required") is not True:
        raise ConstitutionalGuardError("constitutional amendments must require unanimous Council")
    if amendment.get("human_overseer_authorization_required") is not True:
        raise ConstitutionalGuardError("constitutional amendments must require Human Overseer authorization")

    agent_rows = registry.get("agents") or []
    agents_by_id = {
        str(row.get("id")): row
        for row in agent_rows
        if isinstance(row, dict) and row.get("id")
    }
    if "human_overseer" not in agents_by_id or "governor" not in agents_by_id:
        raise ConstitutionalGuardError("constitutional principals missing from registry")

    vertical_rows = verticals.get("verticals") or []
    vertical_ids = {
        str(row.get("id"))
        for row in vertical_rows
        if isinstance(row, dict) and row.get("id")
    }
    lane_access = access.get("lanes") or {}
    lane_contracts = contracts.get("lane_contracts") or {}
    profit_lanes = profit.get("lanes") or {}

    if len(vertical_ids) != 11:
        raise ConstitutionalGuardError(f"expected 11 registered lanes; got {len(vertical_ids)}")
    if set(lane_access) != vertical_ids:
        raise ConstitutionalGuardError("lane access registry does not exactly match vertical registry")
    if set(lane_contracts) != vertical_ids:
        raise ConstitutionalGuardError("lane runtime contracts do not exactly match vertical registry")
    if set(profit_lanes) != ECONOMIC_LANES:
        missing = sorted(ECONOMIC_LANES - set(profit_lanes))
        extra = sorted(set(profit_lanes) - ECONOMIC_LANES)
        raise ConstitutionalGuardError(f"profitability lane mismatch missing={missing} extra={extra}")

    for lane_id, access_rule in lane_access.items():
        if not isinstance(access_rule, dict):
            raise ConstitutionalGuardError(f"invalid access contract: {lane_id}")
        if access_rule.get("internal_work_open") is not True or access_rule.get("scheduler_eligible") is not True:
            raise ConstitutionalGuardError(f"lane is not open and scheduler eligible: {lane_id}")

    for lane_id, contract in lane_contracts.items():
        if not isinstance(contract, dict):
            raise ConstitutionalGuardError(f"invalid runtime contract: {lane_id}")
        missing = REQUIRED_RUNTIME_FIELDS - set(contract)
        if missing:
            raise ConstitutionalGuardError(f"runtime contract incomplete lane={lane_id} missing={sorted(missing)}")
        principal = str(contract.get("principal_agent") or "")
        if principal not in agents_by_id:
            raise ConstitutionalGuardError(f"lane principal is not registered lane={lane_id} principal={principal}")
        for field in (
            "dependencies",
            "implementation_paths",
            "input_contract",
            "output_contract",
            "health_signals",
            "metrics",
            "recovery_contract",
        ):
            if not _nonempty_sequence(contract.get(field)) and not (field == "dependencies" and contract.get(field) == []):
                raise ConstitutionalGuardError(f"runtime contract field empty lane={lane_id} field={field}")
        dependencies = set(contract.get("dependencies") or [])
        unknown_dependencies = dependencies - vertical_ids
        if unknown_dependencies:
            raise ConstitutionalGuardError(
                f"unknown lane dependencies lane={lane_id} dependencies={sorted(unknown_dependencies)}"
            )
        if str(contract.get("work_queue") or "").strip() == str(contract.get("failure_queue") or "").strip():
            raise ConstitutionalGuardError(f"work and failure queue collide lane={lane_id}")

    required_stack = profit.get("required_profit_stack") or []
    if set(required_stack) != REQUIRED_PROFIT_FIELDS:
        raise ConstitutionalGuardError("canonical profitability stack drifted")
    portfolio_rules = profit.get("portfolio_rules") or {}
    for flag in (
        "profit_claim_requires_verified_posted_revenue",
        "profit_claim_requires_positive_contribution_margin",
        "profit_claim_requires_reconciled_delivery",
        "profit_claim_requires_repeatability",
    ):
        if portfolio_rules.get(flag) is not True:
            raise ConstitutionalGuardError(f"profit truth gate disabled: {flag}")
    if portfolio_rules.get("live_trading_authorized") is not False:
        raise ConstitutionalGuardError("live trading cannot be activated by profitability contract")

    for lane_id, contract in profit_lanes.items():
        if not isinstance(contract, dict):
            raise ConstitutionalGuardError(f"invalid profitability contract: {lane_id}")
        missing = REQUIRED_PROFIT_FIELDS - set(contract)
        if missing:
            raise ConstitutionalGuardError(f"profitability contract incomplete lane={lane_id} missing={sorted(missing)}")
        for field in REQUIRED_PROFIT_FIELDS - {"revenue_proof_gate"}:
            if not _nonempty_sequence(contract.get(field)):
                raise ConstitutionalGuardError(f"profitability field empty lane={lane_id} field={field}")
        if not str(contract.get("revenue_proof_gate") or "").strip():
            raise ConstitutionalGuardError(f"revenue proof gate missing lane={lane_id}")

    return {
        "schema": "dominion-constitutional-runtime-guard-v1",
        "status": "PASS",
        "registered_lanes": len(vertical_ids),
        "runtime_contracts": len(lane_contracts),
        "economic_profitability_contracts": len(profit_lanes),
        "default_deny": True,
        "human_final_authority": "human_overseer",
        "five_council": True,
        "incident_learning": True,
        "legal_fail_closed": True,
        "constitutional_amendment_guard": True,
        "live_trading_authorized": False
    }
