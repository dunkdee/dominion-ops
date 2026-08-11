#!/usr/bin/env python3
"""Tests for the repo-native Founder Oversight and Evidence Control layer."""

from __future__ import annotations

import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "validate_founder_oversight.py"


def load_validator():
    spec = importlib.util.spec_from_file_location("validate_founder_oversight", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


class FounderOversightTests(unittest.TestCase):
    def setUp(self):
        self.validator = load_validator()

    def test_contract_passes_with_safe_lane_states(self):
        result = self.validator.validate(ROOT)
        self.assertEqual(result, {"lanes": 5, "protected_holds": 8, "schemas": 2})

    def test_protected_hold_drift_fails_closed(self):
        temp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, temp)
        shutil.copytree(ROOT / "governance", temp / "governance")
        shutil.copytree(ROOT / "runtime", temp / "runtime")
        contract_path = temp / "governance" / "founder_oversight_contract.json"
        contract = json.loads(contract_path.read_text(encoding="utf-8"))
        contract["protected_holds"]["tiktok"] = "DRAFT_ONLY"
        contract_path.write_text(json.dumps(contract), encoding="utf-8")
        with self.assertRaises(self.validator.OversightValidationError):
            self.validator.validate(temp)

    def test_example_cannot_claim_runtime_execution(self):
        temp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, temp)
        shutil.copytree(ROOT / "governance", temp / "governance")
        shutil.copytree(ROOT / "runtime", temp / "runtime")
        mission_path = temp / "runtime" / "examples" / "founder_oversight_mission.example.json"
        mission = json.loads(mission_path.read_text(encoding="utf-8"))
        mission["status"] = "VERIFIED_CLOSED"
        mission_path.write_text(json.dumps(mission), encoding="utf-8")
        with self.assertRaises(self.validator.OversightValidationError):
            self.validator.validate(temp)


if __name__ == "__main__":
    unittest.main()
