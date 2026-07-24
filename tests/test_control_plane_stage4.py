from __future__ import annotations
import copy, json, unittest
from pathlib import Path
from control_plane.canonical import sha256_json
from control_plane.historical_sources import adapt_historical_snapshot
from control_plane.proposals import aggregate_bound_reviews
from control_plane.shadow_observation import run_non_contact_shadow_observation
ROOT=Path(__file__).resolve().parents[1]
class Stage4Tests(unittest.TestCase):
    def setUp(self):
        self.fixture=json.loads((ROOT/'runtime/examples/stage4_historical_fixture.json').read_text())
        self.council=json.loads((ROOT/'governance/five_council_policy.json').read_text())
    def test_repository_fixture_is_test_only(self):
        result=adapt_historical_snapshot(self.fixture)
        self.assertEqual(result['status'],'TEST_ONLY'); self.assertEqual(result['source_kind'],'SYNTHETIC_TEST'); self.assertEqual(result['external_actions'],[])
    def test_actual_verified_export_can_be_verified(self):
        snapshot=copy.deepcopy(self.fixture); snapshot['source_system']='WIX_EXPORT'; snapshot['business_data_status']='ACTUAL_BUSINESS_HISTORY'; snapshot['evidence']=['export:wix-orders-2026-07','verification:hash-and-period-check']
        result=adapt_historical_snapshot(snapshot)
        self.assertEqual(result['status'],'VERIFIED'); self.assertEqual(result['source_kind'],'HISTORICAL_VERIFIED')
    def test_payload_hash_mismatch_holds(self):
        snapshot=copy.deepcopy(self.fixture); snapshot['periods']['candidate']['visitors']+=1
        result=adapt_historical_snapshot(snapshot)
        self.assertEqual(result['status'],'HOLD'); self.assertIn('payload_hash_mismatch',result['errors'])
    def test_personal_or_secret_material_holds(self):
        for field in ('contains_personal_data','contains_secret_material'):
            snapshot=copy.deepcopy(self.fixture); snapshot[field]=True
            self.assertEqual(adapt_historical_snapshot(snapshot)['status'],'HOLD')
    def test_nonmonotonic_funnel_holds(self):
        snapshot=copy.deepcopy(self.fixture); snapshot['periods']['baseline']['leads']=1200; snapshot['payload_hash']=sha256_json(snapshot['periods'])
        result=adapt_historical_snapshot(snapshot)
        self.assertEqual(result['status'],'HOLD'); self.assertIn('baseline_funnel_counts_not_monotonic',result['errors'])
    def test_stored_five_council_records_are_bound_and_approved(self):
        envelope=json.loads((ROOT/'runtime/records/stage4/proposal_envelope.json').read_text()); reviews=[json.loads(p.read_text()) for p in sorted((ROOT/'runtime/records/stage4/reviews').glob('*.json'))]
        self.assertEqual(len(reviews),5)
        decision=aggregate_bound_reviews(envelope,reviews,council_policy=self.council)
        self.assertEqual(decision['decision'],'APPROVE'); self.assertFalse(decision['external_execution_authorized'])
        self.assertEqual(decision,json.loads((ROOT/'runtime/records/stage4/council_decision.json').read_text()))
    def test_fixture_observation_is_test_only_and_noncontact(self):
        adapted=json.loads((ROOT/'runtime/records/stage4/adapted_snapshot.json').read_text()); envelope=json.loads((ROOT/'runtime/records/stage4/proposal_envelope.json').read_text()); decision=json.loads((ROOT/'runtime/records/stage4/council_decision.json').read_text()); guardrails=json.loads((ROOT/'runtime/examples/stage4_guardrails.json').read_text())
        result=run_non_contact_shadow_observation(adapted_snapshot=adapted,proposal_envelope=envelope,council_decision=decision,guardrails=guardrails)
        self.assertEqual(result['status'],'TEST_ONLY'); self.assertFalse(result['customers_contacted']); self.assertFalse(result['money_moved']); self.assertFalse(result['external_execution_authorized'])
    def test_observation_fails_closed_on_proposal_mismatch(self):
        adapted=json.loads((ROOT/'runtime/records/stage4/adapted_snapshot.json').read_text()); envelope=json.loads((ROOT/'runtime/records/stage4/proposal_envelope.json').read_text()); decision=json.loads((ROOT/'runtime/records/stage4/council_decision.json').read_text()); decision['bound_proposal_hash']='0'*64
        result=run_non_contact_shadow_observation(adapted_snapshot=adapted,proposal_envelope=envelope,council_decision=decision,guardrails=json.loads((ROOT/'runtime/examples/stage4_guardrails.json').read_text()))
        self.assertEqual(result['status'],'HOLD'); self.assertIn('council_decision_proposal_mismatch',result['errors'])
    def test_stored_observation_hash_is_valid(self):
        record=json.loads((ROOT/'runtime/records/stage4/shadow_observation.json').read_text()); expected=sha256_json({k:v for k,v in record.items() if k!='observation_hash'}); self.assertEqual(record['observation_hash'],expected)
if __name__=='__main__': unittest.main()
