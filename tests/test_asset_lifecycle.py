import unittest

from control_plane.asset_lifecycle import (
    AssetObservation,
    Disposition,
    assess,
    decision_receipt,
    persistent_breach,
)


def obs(**overrides):
    values = dict(
        asset_id="asset-001", lane="youtube", observed_at="2026-08-28T00:00:00Z",
        evidence_class="FIRST_PARTY_VERIFIED", demand=70, buyer_intent=70,
        conversion=70, contribution_margin=70, strategic_fit=70, reliability=70,
        confidence=80, sample_size=100, evidence_refs=("receipt:1",),
    )
    values.update(overrides)
    return AssetObservation(**values)


class AssetLifecycleTests(unittest.TestCase):
    def test_noise_holds_without_council_escalation(self):
        result = assess(obs(confidence=20, sample_size=2, contribution_margin=0))
        self.assertEqual(result.threshold_state, "INSUFFICIENT_EVIDENCE")
        self.assertFalse(result.council_required)

    def test_low_feasibility_escalates_to_council(self):
        result = assess(obs(demand=20, buyer_intent=20, conversion=15, contribution_margin=10,
                            strategic_fit=30, reliability=50))
        self.assertEqual(result.threshold_state, "BELOW_FEASIBILITY")
        self.assertTrue(result.council_required)
        self.assertEqual(result.recommended_disposition, "REPAIR")

    def test_high_score_requires_council_before_scale(self):
        result = assess(obs(demand=95, buyer_intent=95, conversion=90, contribution_margin=90,
                            strategic_fit=90, reliability=90, confidence=95))
        self.assertEqual(result.threshold_state, "SCALE_CANDIDATE")
        self.assertTrue(result.council_required)

    def test_persistent_breach_requires_three_periods(self):
        low = assess(obs(demand=10, buyer_intent=10, conversion=10, contribution_margin=10,
                         strategic_fit=10, reliability=50))
        self.assertFalse(persistent_breach([low, low], periods=3))
        self.assertTrue(persistent_breach([low, low, low], periods=3))

    def test_receipt_is_hashed_and_governed(self):
        result = assess(obs())
        receipt = decision_receipt(result, decision=Disposition.HOLD.value,
                                   why="Continue measurement", approver="COUNCIL")
        self.assertEqual(len(receipt["receipt_sha256"]), 64)
        with self.assertRaises(ValueError):
            decision_receipt(result, decision="DELETE_NOW", why="x", approver="x")


if __name__ == "__main__":
    unittest.main()
