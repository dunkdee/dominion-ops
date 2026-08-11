from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "revenue" / "impact_pipeline" / "contract.json"
VALIDATOR_PATH = ROOT / "scripts" / "validate_ethical_revenue_impact_pipeline.py"


class EthicalRevenueImpactPipelineTests(unittest.TestCase):
    def test_contract_is_staged_and_has_no_external_authority(self) -> None:
        contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
        self.assertEqual(contract["status"], "STAGED_NOT_ACTIVATED")
        self.assertFalse(contract["authority"]["external_execution_authorized"])
        self.assertFalse(contract["authority"]["money_movement_authorized"])
        self.assertFalse(contract["authority"]["publication_authorized"])
        self.assertFalse(contract["authority"]["customer_or_prospect_contact_authorized"])
        self.assertFalse(contract["authority"]["pricing_authorized"])
        self.assertFalse(contract["authority"]["credential_change_authorized"])

    def test_contract_preserves_current_vertical_modes_and_human_gate(self) -> None:
        contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
        self.assertEqual(
            contract["scope"]["allowed_vertical_modes"],
            {
                "commerce_fulfillment": "record_only",
                "content_traffic": "draft_only",
                "analytics_services": "shadow_only",
            },
        )
        stages = {item["stage"]: item for item in contract["workflow"]}
        self.assertEqual(list(stages), ["measure", "draft", "human_approval", "record_outcomes"])
        self.assertFalse(stages["human_approval"]["agent_may_approve"])
        self.assertTrue(all(item["external_effects"] is False for item in contract["workflow"]))

    def test_validator_passes(self) -> None:
        result = subprocess.run(
            [sys.executable, str(VALIDATOR_PATH)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("validation PASSED", result.stdout)


if __name__ == "__main__":
    unittest.main()
