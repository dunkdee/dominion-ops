"""Run a proposal-bound, council-reviewed, non-contact shadow observation."""
from __future__ import annotations
from typing import Any
from .canonical import sha256_json
from .shadow_revenue import run_shadow_revenue_experiment

def run_non_contact_shadow_observation(*,adapted_snapshot:dict[str,Any],proposal_envelope:dict[str,Any],council_decision:dict[str,Any],guardrails:dict[str,Any])->dict[str,Any]:
    errors=[]
    if adapted_snapshot.get("status") not in {"VERIFIED","TEST_ONLY"}: errors.append("adapted_snapshot_not_usable")
    if proposal_envelope.get("status")!="READY_FOR_INDEPENDENT_COUNCIL_REVIEW": errors.append("proposal_envelope_not_reviewable")
    proposal_hash=proposal_envelope.get("proposal_hash")
    if council_decision.get("bound_proposal_hash")!=proposal_hash: errors.append("council_decision_proposal_mismatch")
    if council_decision.get("decision")!="APPROVE": errors.append("council_decision_not_approved")
    if council_decision.get("external_execution_authorized") is not False: errors.append("council_decision_execution_boundary_invalid")
    if adapted_snapshot.get("external_actions")!=[] or adapted_snapshot.get("source_system_mutated") is not False: errors.append("snapshot_adapter_side_effect_boundary_invalid")
    experiment={"experiment_id":f"{adapted_snapshot.get('snapshot_id')}_observation","owner_id":"revenue_operations","proposal_hash":proposal_hash,"source_snapshot":{"kind":adapted_snapshot.get("source_kind"),"as_of":adapted_snapshot.get("as_of"),"evidence":adapted_snapshot.get("evidence",[])+[f"snapshot_hash:{adapted_snapshot.get('snapshot_hash')}"]},"baseline":adapted_snapshot.get("baseline") or {},"candidate":adapted_snapshot.get("candidate") or {},"guardrails":guardrails}
    revenue_result=None
    if not errors: revenue_result=run_shadow_revenue_experiment(experiment); errors.extend(revenue_result.get("errors",[]))
    if errors: status="HOLD"; reasons=["observation_prerequisites_not_met"]
    elif revenue_result.get("decision")=="TEST_ONLY": status="TEST_ONLY"; reasons=["repository_fixture_observation_completed"]
    elif revenue_result.get("decision")=="ELIGIBLE_FOR_COUNCIL_REVIEW": status="OBSERVED_ELIGIBLE_FOR_NEXT_REVIEW"; reasons=["verified_non_contact_observation_completed"]
    else: status="CONTINUE_SHADOW"; reasons=list(revenue_result.get("reasons",[]))
    result={"mode":"SHADOW_ONLY","observation_id":experiment["experiment_id"],"proposal_hash":proposal_hash,"snapshot_hash":adapted_snapshot.get("snapshot_hash"),"council_decision_hash":council_decision.get("decision_hash"),"status":status,"reasons":reasons,"errors":sorted(set(errors)),"revenue_result":revenue_result,"external_actions":[],"money_moved":False,"customers_contacted":False,"content_published":False,"production_changes":False,"agents_promoted":False,"runtime_started":False,"external_execution_authorized":False}
    result["observation_hash"]=sha256_json(result); return result
