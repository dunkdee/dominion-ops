#!/usr/bin/env python3
"""Validate Stage 3-or-later shadow-mode contracts and safety boundaries."""
from __future__ import annotations
import json, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from control_plane.cohort import REQUIRED_BLOCKED_ACTIONS, validate_shadow_cohort
from control_plane.proposals import prepare_proposal_envelope
from control_plane.shadow_revenue import run_shadow_revenue_experiment
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
      'control_plane/cohort.py','control_plane/proposals.py','control_plane/shadow_revenue.py','governance/tool_catalog.json','governance/runtime_activation_gates.json',
      'governance/schemas/agent_cohort.schema.json','governance/schemas/proposal_envelope.schema.json','governance/schemas/bound_council_review.schema.json','governance/schemas/shadow_revenue_experiment.schema.json','governance/schemas/tool_catalog.schema.json',
      'agents/cohorts/stage3_core_shadow.json','runtime/examples/stage3_proposal.json','runtime/examples/shadow_revenue_experiment.json','tests/test_control_plane_stage3.py','architecture/STAGE3_SHADOW_OPERATIONS.md'
    ]
    for item in required: require((ROOT/item).is_file(),f'missing required file: {item}')
    gates=load(ROOT/'governance/runtime_activation_gates.json')
    require(isinstance(gates.get('stage'),int) and gates.get('stage')>=3,'activation stage must be 3 or later')
    require(gates.get('mode')=='shadow_only','runtime mode must be shadow_only')
    require(gates.get('external_execution_enabled') is False,'external execution must remain disabled')
    require(gates.get('registry_mutation_enabled') is False,'registry mutation must remain disabled')
    require(REQUIRED_BLOCKED_ACTIONS.issubset(set(gates.get('blocked_actions',[]))),'critical blocked actions are incomplete')
    for capability in ('start_obsidian_runtime','start_browser_agents','live_customer_contact','live_financial_execution','production_deployment'):
        require(capability in set(gates.get('blocked_capabilities',[])),f'blocked capability missing: {capability}')
    for name in ('agent_cohort.schema.json','proposal_envelope.schema.json','bound_council_review.schema.json','shadow_revenue_experiment.schema.json','tool_catalog.schema.json'):
        require(load(ROOT/'governance/schemas'/name).get('additionalProperties') is False,f'{name} must reject unknown fields')
    cohort=validate_shadow_cohort(load(ROOT/'agents/cohorts/stage3_core_shadow.json'),load(ROOT/'agents/registry.json'),load(ROOT/'governance/tool_catalog.json'),gates)
    require(cohort.get('status')=='ELIGIBLE_FOR_SHADOW_ASSIGNMENT_REVIEW','core cohort must pass shadow validation')
    require(cohort.get('registry_mutated') is False and cohort.get('agents_promoted') is False and cohort.get('runtime_started') is False,'cohort validation crossed a promotion boundary')
    proposal=prepare_proposal_envelope(load(ROOT/'runtime/examples/stage3_proposal.json'),load(ROOT/'agents/registry.json'),load(ROOT/'governance/authority_matrix.json'),gates)
    require(proposal.get('status')=='READY_FOR_INDEPENDENT_COUNCIL_REVIEW','example proposal must be reviewable')
    require(proposal.get('external_execution_authorized') is False,'proposal preparation cannot authorize execution')
    revenue=run_shadow_revenue_experiment(load(ROOT/'runtime/examples/shadow_revenue_experiment.json'))
    require(revenue.get('mode')=='SHADOW_ONLY' and revenue.get('decision')=='TEST_ONLY','synthetic fixture must remain TEST_ONLY')
    require(revenue.get('external_actions')==[] and revenue.get('money_moved') is False and revenue.get('customers_contacted') is False and revenue.get('promotion_authorized') is False,'shadow revenue crossed a side-effect boundary')
    if ERRORS:
        print('Dominion Stage 3 compatibility validation FAILED:')
        for error in ERRORS: print(f' - {error}')
        return 1
    print('Dominion Stage 3 compatibility validation PASSED')
    print(f'Validated {len(required)} Stage 3 contracts under Stage {gates.get("stage")} gates.')
    return 0
if __name__=='__main__': raise SystemExit(main())
