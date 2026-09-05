"""Regression coverage for PR #235 independent-review round two."""
from __future__ import annotations

import importlib.util
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "buddy_core"))

from core import operator as operator_mod  # noqa: E402
from core.authorization import AuthorizationError  # noqa: E402
from core.operator import BuddyOperator  # noqa: E402


def _load_validator():
    path = ROOT / "scripts" / "validate_elite_governance.py"
    spec = importlib.util.spec_from_file_location("elite_governance_round2", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class GovernanceFormattingResistanceTests(unittest.TestCase):
    def test_current_autopilot_passes_semantic_gate(self):
        validator = _load_validator()
        source = (ROOT / "scripts" / "autopilot" / "lane_supervisor.py").read_text(encoding="utf-8")
        ok, reason = validator.autopilot_productivity_semantics(source)
        self.assertTrue(ok, reason)

    def test_whitespace_and_single_quote_bypass_is_rejected(self):
        validator = _load_validator()
        unsafe = """
def productive_complete(receipt):
    return receipt.get('status') == 'COMPLETE'

def persist_cycle(receipt, lane_state, now):
    if bounded_cycle_ok ( receipt ) :
        lane_state [ 'last_progress_at' ] = now
        lane_state [ 'last_productive_at' ] = now
"""
        ok, reason = validator.autopilot_productivity_semantics(unsafe)
        self.assertFalse(ok)
        self.assertIn("without productive_complete", reason)

    def test_held_cannot_be_declared_productive_by_helper(self):
        validator = _load_validator()
        unsafe = """
def productive_complete(receipt):
    return receipt.get("status") in {"COMPLETE", "HELD"}

def persist_cycle(receipt, lane_state, now):
    if productive_complete(receipt):
        lane_state["last_progress_at"] = now
        lane_state["last_productive_at"] = now
"""
        ok, reason = validator.autopilot_productivity_semantics(unsafe)
        self.assertFalse(ok)
        self.assertIn("exclusively", reason)


class HeldPlanDurabilityTests(unittest.TestCase):
    @unittest.skipUnless(os.name == "posix", "parent-directory fsync is a POSIX durability boundary")
    def test_held_plan_parent_directory_fsync_failure_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            operator = BuddyOperator(state_dir=Path(tmp))
            real_fsync = operator_mod.os.fsync

            def guarded_fsync(fd):
                if stat.S_ISDIR(os.fstat(fd).st_mode):
                    raise OSError("simulated held-plan directory fsync failure")
                return real_fsync(fd)

            with mock.patch.object(operator_mod.os, "fsync", side_effect=guarded_fsync):
                with self.assertRaisesRegex(AuthorizationError, "held_plan_directory_fsync_failed"):
                    operator._persist_held_plan(
                        "approval_aaaaaaaaaaaa",
                        {"mission_id": "durability", "step": {"capability": "external.publish"}},
                    )


if __name__ == "__main__":
    unittest.main()
