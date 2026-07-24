#!/usr/bin/env python3
"""Validate Stage 4 historical adapters, council records, and shadow observations."""
from __future__ import annotations
import copy, json, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from control_plane.canonical import sha256_json
from control_plane.historical_sources import adapt_historical_snapshot
from control_plane.proposals import aggregate_bound_reviews
from control_plane.shadow_observation import run_non_contact_shadow_observation
ERRORS=[]
def require(condition:bool,message:str)->None:
    if not condition: ERRORS.append(message)
def load(path:Path)->dict:
    try: value=json.loads(path.read_text(encoding='utf-8'))
    except Exception as exc: ERRORS.append(f'cannot load {path.relative_to(ROOT)}: {exc}'); return {}
    require(isinstance(value,dict),f'{path.relative_to(ROOT)} must contain an object')
    return value if isinstance(value,dict) else {}
def main()->int:
    required=[
      'control_plane/historical_sources.py','control_plane/shadow_observation.py',
      'governance/schemas/historical_revenue_snapshot.schema.json','governance/schemas/historical_adapter_result.schema.json','governance/schemas/shadow_observation.schema.json',
      'runtime/examples/stage4_historical_fixture.json','runtime/examples/stage4_guardrails.json','runtime/records/stage4/proposal.json','runtime/records/stage4/proposal_envelope.json','runtime/records/stage4/council_decision.json','runtime/records/stage4/adapted_snapshot.json','runtime/records/stage4/shadow_observation.json','runtime/records/stage4/README.md',
      'runtime/records/stage4/reviews/truth_evidence.json','runtime/records/stage4/reviews/law_governance.json','runtime/records/stage4/reviews/security_risk.json','runtime/records/stage4/reviews/engineering_reliability.json','runtime/records/stage4/reviews/business_human_impact.json',
      'tests/test_control_plane_stage4.py','architecture/STAGE4_HISTORICAL_SHADOW.md','scripts/stage4_shadow.py'
    ]
    for item in required: require((ROOT/item).is_file(),f'missing required file: {item}')
    gates=load(ROOT/'governance/runtime_activation_gates.json')
    require(gates.get('stage')==4,'activation stage must be 4')
    require(gates.get('mode')=='shadow_only','runtime must remain shadow_only')
    require(gates.get('external_execution_enabled') is False,'external execution must remain disabled')
    require(gates.get('registry_mutation_enabled') is False,'registry mutation must remain disabled')
    require({'actual_historical_source_connected','first_non_contact_actual_observation_completed','human_overseer_approval_recorded'}.issubset(set(gates.get('promotion_requirements',[]))),'Stage 4 promotion requirements are incomplete')
    for name in ('historical_revenue_snapshot.schema.json','historical_adapter_result.schema.json','shadow_observation.schema.json'):
        require(load(ROOT/'governance/schemas'/name).get('additionalProperties') is False,f'{name} must reject unknown fields')
    fixture=load(ROOT/'runtime/examples/stage4_historical_fixture.json')
    adapted=adapt_historical_snapshot(fixture)
    require(adapted.get('status')=='TEST_ONLY' and adapted.get('source_kind')=='SYNTHETIC_TEST','repository fixture must remain TEST_ONLY')
    require(adapted.get('external_actions')==[] and adapted.get('source_system_mutated') is False,'adapter crossed a side-effect boundary')
    require(adapted==load(ROOT/'runtime/records/stage4/adapted_snapshot.json'),'stored adapted snapshot is not reproducible')
    envelope=load(ROOT/'runtime/records/stage4/proposal_envelope.json')
    reviews=[load(path) for path in sorted((ROOT/'runtime/records/stage4/reviews').glob('*.json'))]
    require(len(reviews)==5,'exactly five bound council records are required')
    decision=aggregate_bound_reviews(envelope,reviews,council_policy=load(ROOT/'governance/five_council_policy.json'))
    require(decision.get('decision')=='APPROVE','fixture proposal must be approved for shadow testing')
    require(decision.get('external_execution_authorized') is False,'council approval may not authorize execution')
    require(decision==load(ROOT/'runtime/records/stage4/council_decision.json'),'stored council decision is not reproducible')
    guardrails=load(ROOT/'runtime/examples/stage4_guardrails.json')
    observation=run_non_contact_shadow_observation(adapted_snapshot=adapted,proposal_envelope=envelope,council_decision=decision,guardrails=guardrails)
    require(observation.get('status')=='TEST_ONLY','fixture observation must remain TEST_ONLY')
    require(observation.get('external_actions')==[] and observation.get('money_moved') is False and observation.get('customers_contacted') is False and observation.get('external_execution_authorized') is False,'observation crossed a side-effect boundary')
    require(observation==load(ROOT/'runtime/records/stage4/shadow_observation.json'),'stored observation is not reproducible')
    actual=copy.deepcopy(fixture); actual['source_system']='WIX_EXPORT'; actual['business_data_status']='ACTUAL_BUSINESS_HISTORY'; actual['evidence']=['export:wix-orders-example','verification:hash-period-and-funnel-check']
    actual_adapted=adapt_historical_snapshot(actual)
    require(actual_adapted.get('status')=='VERIFIED','valid actual-history export must be verifiable')
    actual_observation=run_non_contact_shadow_observation(adapted_snapshot=actual_adapted,proposal_envelope=envelope,council_decision=decision,guardrails=guardrails)
    require(actual_observation.get('status')=='OBSERVED_ELIGIBLE_FOR_NEXT_REVIEW','actual history may only advance to next review')
    require(actual_observation.get('external_execution_authorized') is False,'actual-history observation may not authorize execution')
    for path,field in ((ROOT/'runtime/records/stage4/adapted_snapshot.json','adapter_result_hash'),(ROOT/'runtime/records/stage4/shadow_observation.json','observation_hash')):
        record=load(path); require(record.get(field)==sha256_json({k:v for k,v in record.items() if k!=field}),f'{path.name} hash mismatch')
    if ERRORS:
        print('Dominion Stage 4 validation FAILED:')
        for error in ERRORS: print(f' - {error}')
        return 1
    print('Dominion Stage 4 validation PASSED')
    print(f'Validated {len(required)} Stage 4 contracts and records.')
    return 0
if __name__=='__main__': raise SystemExit(main())
