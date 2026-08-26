from __future__ import annotations

import importlib.util
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GUARD_PATH = ROOT / "scripts" / "autopilot" / "control_plane_guard.py"
spec = importlib.util.spec_from_file_location("control_plane_guard", GUARD_PATH)
assert spec and spec.loader
guard = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = guard
spec.loader.exec_module(guard)


class LaneRuntimeContractTests(unittest.TestCase):
    def load(self, rel: str) -> dict:
        return json.loads((ROOT / rel).read_text(encoding="utf-8"))

    def test_constitutional_guard_passes_repository_contracts(self):
        receipt = guard.validate_runtime_root(ROOT)
        self.assertEqual(receipt["status"], "PASS")
        self.assertEqual(receipt["registered_lanes"], 11)
        self.assertEqual(receipt["runtime_contracts"], 11)
        self.assertEqual(receipt["economic_profitability_contracts"], 8)
        self.assertTrue(receipt["default_deny"])
        self.assertEqual(receipt["human_final_authority"], "human_overseer")
        self.assertTrue(receipt["incident_learning"])
        self.assertTrue(receipt["legal_fail_closed"])
        self.assertFalse(receipt["live_trading_authorized"])

    def test_every_lane_has_complete_runtime_contract_and_real_implementation_paths(self):
        contracts = self.load("governance/lane_runtime_contracts.json")["lane_contracts"]
        verticals = {row["id"]: row for row in self.load("governance/verticals.json")["verticals"]}
        self.assertEqual(set(contracts), set(verticals))
        for lane_id, contract in contracts.items():
            self.assertTrue(guard.REQUIRED_RUNTIME_FIELDS.issubset(contract), lane_id)
            self.assertNotEqual(contract["work_queue"], contract["failure_queue"], lane_id)
            self.assertGreaterEqual(len(contract["input_contract"]), 3, lane_id)
            self.assertGreaterEqual(len(contract["output_contract"]), 3, lane_id)
            self.assertGreaterEqual(len(contract["health_signals"]), 2, lane_id)
            self.assertGreaterEqual(len(contract["recovery_contract"]), 2, lane_id)
            for rel in contract["implementation_paths"]:
                self.assertTrue((ROOT / rel).is_file(), f"{lane_id}:{rel}")

    def test_every_economic_lane_has_full_profit_stack(self):
        profitability = self.load("governance/profitability_lane_contracts.json")
        lanes = profitability["lanes"]
        self.assertEqual(set(lanes), guard.ECONOMIC_LANES)
        self.assertEqual(set(profitability["required_profit_stack"]), guard.REQUIRED_PROFIT_FIELDS)
        for lane_id, contract in lanes.items():
            self.assertTrue(guard.REQUIRED_PROFIT_FIELDS.issubset(contract), lane_id)
            for field in guard.REQUIRED_PROFIT_FIELDS - {"revenue_proof_gate"}:
                self.assertIsInstance(contract[field], list, f"{lane_id}:{field}")
                self.assertTrue(contract[field], f"{lane_id}:{field}")
            self.assertTrue(contract["revenue_proof_gate"].strip(), lane_id)

    def test_profit_truth_cannot_be_weakened(self):
        rules = self.load("governance/profitability_lane_contracts.json")["portfolio_rules"]
        self.assertTrue(rules["profit_claim_requires_verified_posted_revenue"])
        self.assertTrue(rules["profit_claim_requires_positive_contribution_margin"])
        self.assertTrue(rules["profit_claim_requires_reconciled_delivery"])
        self.assertTrue(rules["profit_claim_requires_repeatability"])
        self.assertFalse(rules["live_trading_authorized"])

    def test_guard_fails_closed_when_profitability_contract_is_incomplete(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for rel in (
                "governance/SYSTEM_CONSTITUTION.md",
                "governance/authority_matrix.json",
                "governance/five_council_policy.json",
                "governance/incident_learning_policy.json",
                "governance/legal_evidence_policy.json",
                "governance/constitutional_amendment_policy.json",
                "governance/verticals.json",
                "governance/lane_access_policy.json",
                "governance/lane_runtime_contracts.json",
                "governance/profitability_lane_contracts.json",
                "agents/registry.json",
            ):
                src = ROOT / rel
                dst = root / rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
            target = root / "governance/profitability_lane_contracts.json"
            data = json.loads(target.read_text(encoding="utf-8"))
            del data["lanes"]["digital_products"]["delivery"]
            target.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaises(guard.ConstitutionalGuardError):
                guard.validate_runtime_root(root)


if __name__ == "__main__":
    unittest.main()
