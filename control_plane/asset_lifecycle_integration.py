"""Integration helpers for the adaptive asset lifecycle.

This layer connects the new scoring core to Dominion's existing append-only
ledger and Five Council proposal machinery without changing or restarting any
live service. It is intentionally additive and safe to exercise in shadow/read-
only mode before runtime activation.
"""
from __future__ import annotations

from typing import Iterable

from .asset_lifecycle import AssetAssessment, as_record, persistent_breach
from .canonical import sha256_json
from .ledger import AppendOnlyLedger


def record_assessment(
    ledger: AppendOnlyLedger,
    assessment: AssetAssessment,
    *,
    actor: str = "dominion_intelligence",
) -> dict:
    """Append an assessment to the existing hash-chained evidence ledger."""
    return ledger.append(
        event_type="asset_lifecycle_assessment",
        actor=actor,
        payload=as_record(assessment),
        timestamp=assessment.assessed_at,
    )


def council_case(
    assessments: Iterable[AssetAssessment],
    *,
    proposer_id: str,
    requested_action: str,
    risk: str,
    periods: int = 3,
) -> dict | None:
    """Build a canonical shadow Council proposal after persistent degradation.

    This helper does not submit a review or authorize execution. It only creates
    the proposal object expected by the existing proposal/council system.
    """
    history = list(assessments)
    if not persistent_breach(history, periods=periods):
        return None
    latest = history[-1]
    evidence = list(dict.fromkeys(ref for item in history[-periods:] for ref in item.evidence_refs))
    if not evidence:
        evidence = [f"assessment:{sha256_json(as_record(latest))}"]
    proposal_id = f"asset_{latest.asset_id.replace('-', '_')}_lifecycle"
    return {
        "proposal_id": proposal_id[:96],
        "proposer_id": proposer_id,
        "objective": f"Evaluate lifecycle disposition for {latest.asset_id} after persistent feasibility degradation.",
        "requested_action": requested_action,
        "risk": risk,
        "evidence": evidence,
        "assumptions": [
            "The score is decision evidence, not execution authority.",
            "No live asset is disabled solely because a threshold was crossed.",
        ],
        "unknowns": [
            "Whether repair, pivot, harvest, or retirement produces the best expected value.",
        ],
        "rollback_plan": {
            "trigger": "Council rejects the proposed lifecycle change or new evidence reverses the assessment.",
            "procedure": "Preserve current live state; continue measurement; do not disable or re-enable the existing asset/service.",
        },
        "success_criteria": [
            "Council disposition is evidence-backed and recorded.",
            "Existing live runtime remains uninterrupted until an explicitly authorized change is ready.",
        ],
        "external_effects": False,
        "asset_lifecycle": {
            "asset_id": latest.asset_id,
            "lane": latest.lane,
            "score": latest.score,
            "threshold_state": latest.threshold_state,
            "recommended_disposition": latest.recommended_disposition,
            "periods_below_threshold": periods,
        },
    }


def activation_contract() -> dict:
    """Machine-readable deployment rule for additive, no-toggle activation."""
    contract = {
        "schema": "dominion-adaptive-lifecycle-activation-v1",
        "deployment_mode": "ADDITIVE",
        "service_continuity_required": True,
        "disable_existing_before_install": False,
        "reenable_existing_after_install": False,
        "shadow_first": True,
        "required_sequence": [
            "preflight_existing_runtime",
            "deploy_new_files_side_by_side",
            "run_read_only_shadow_acceptance",
            "verify_existing_runtime_unchanged",
            "enable_new_consumer_only_after_acceptance",
            "verify_post_activation_receipts",
        ],
        "forbidden": [
            "turn_off_live_system_to_make_room_for_new_code",
            "destructive_replace_without_verified_rollback",
            "claim_production_without_runtime_receipts",
        ],
    }
    contract["contract_hash"] = sha256_json(contract)
    return contract
