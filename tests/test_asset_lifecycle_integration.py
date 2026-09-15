import tempfile
import unittest
from pathlib import Path

from control_plane.asset_lifecycle import AssetObservation, assess
from control_plane.asset_lifecycle_integration import (
    activation_contract,
    council_case,
    record_assessment,
)
from control_plane.ledger import AppendOnlyLedger


def low_assessment(idx: int):
    return assess(AssetObservation(
        asset_id="asset-001",
        lane="youtube",
        observed_at=f"2026-08-28T00:0{idx}:00Z",
        evidence_class="FIRST_PARTY_VERIFIED",
        demand=10,
        buyer_intent=10,
        conversion=10,
        contribution_margin=10,
        strategic_fit=20,
        reliability=70,
        confidence=90,
        sample_size=100,
        evidence_refs=(f"receipt:{idx}",),
    ))


class AssetLifecycleIntegrationTests(unittest.TestCase):
    def test_assessment_appends_to_existing_hash_chain(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = AppendOnlyLedger(Path(tmp) / "ledger.jsonl")
            record = record_assessment(ledger, low_assessment(1))
            self.assertEqual(record["event_type"], "asset_lifecycle_assessment")
            verified = ledger.verify()
            self.assertTrue(verified["valid"])
            self.assertEqual(verified["record_count"], 1)

    def test_council_case_only_after_persistent_breach(self):
        history = [low_assessment(1), low_assessment(2)]
        self.assertIsNone(council_case(
            history, proposer_id="dominion_intelligence",
            requested_action="review_asset_lifecycle", risk="medium",
        ))
        history.append(low_assessment(3))
        proposal = council_case(
            history, proposer_id="dominion_intelligence",
            requested_action="review_asset_lifecycle", risk="medium",
        )
        self.assertIsNotNone(proposal)
        self.assertFalse(proposal["external_effects"])
        self.assertIn("do not disable", proposal["rollback_plan"]["procedure"])

    def test_activation_contract_forbids_off_on_deployment(self):
        contract = activation_contract()
        self.assertEqual(contract["deployment_mode"], "ADDITIVE")
        self.assertTrue(contract["service_continuity_required"])
        self.assertFalse(contract["disable_existing_before_install"])
        self.assertFalse(contract["reenable_existing_after_install"])
        self.assertEqual(len(contract["contract_hash"]), 64)


if __name__ == "__main__":
    unittest.main()
