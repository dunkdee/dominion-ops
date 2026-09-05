"""Regression tests for the final PR #235 authority/durability review closure."""
from __future__ import annotations

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

from core import authorization as authorization_mod  # noqa: E402
from core.authorization import AuthorizationError, AuthorizationLedger  # noqa: E402
from core.operator import BuddyOperator  # noqa: E402


class AuthorizationDurabilityTests(unittest.TestCase):
    @unittest.skipUnless(os.name == "posix", "parent-directory fsync is a POSIX durability boundary")
    def test_parent_directory_fsync_failure_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = AuthorizationLedger(Path(tmp))
            real_fsync = authorization_mod.os.fsync

            def guarded_fsync(fd):
                if stat.S_ISDIR(os.fstat(fd).st_mode):
                    raise OSError("simulated directory fsync failure")
                return real_fsync(fd)

            with mock.patch.object(authorization_mod.os, "fsync", side_effect=guarded_fsync):
                with self.assertRaisesRegex(AuthorizationError, "directory_fsync_failed"):
                    ledger.request(
                        mission_id="durability",
                        step=1,
                        capability="external.publish",
                        instruction="publish approved artifact",
                        content={"body": "approved"},
                        destination="https://example.invalid/approved",
                    )


class HeldPlanPrivacyTests(unittest.TestCase):
    @unittest.skipUnless(os.name == "posix", "exact POSIX mode regression")
    def test_held_plan_directory_is_exactly_0700(self):
        with tempfile.TemporaryDirectory() as tmp:
            operator = BuddyOperator(state_dir=Path(tmp))
            self.assertEqual(stat.S_IMODE(operator.held_dir.stat().st_mode), 0o700)

    @unittest.skipUnless(os.name == "posix", "POSIX chmod fail-closed regression")
    def test_held_plan_permission_failure_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            original = Path.chmod

            def fail_held(path, mode, *args, **kwargs):
                if path.name == "held":
                    raise OSError("simulated chmod failure")
                return original(path, mode, *args, **kwargs)

            with mock.patch.object(Path, "chmod", fail_held):
                with self.assertRaisesRegex(AuthorizationError, "held_plan_directory_permissions_unavailable"):
                    BuddyOperator(state_dir=Path(tmp))


class StrandedApprovalReferenceTests(unittest.TestCase):
    def test_persist_failure_returns_blocked_receipt_with_approval_references(self):
        with tempfile.TemporaryDirectory() as tmp:
            operator = BuddyOperator(state_dir=Path(tmp))
            operator._persist_held_plan = mock.Mock(side_effect=OSError("simulated held-plan persistence failure"))
            plan = {
                "mission_id": "persist-failure",
                "objective": "publish an approved artifact",
                "evidence_policy": "HYBRID",
                "steps": [{
                    "capability": "external.publish",
                    "instruction": "publish the approved artifact",
                    "content": {"body": "approved"},
                    "destination": "https://example.invalid/approved",
                }],
            }
            record = operator.execute(plan, session_id="final-review")
            self.assertEqual(record["status"], "BLOCKED")
            receipt = record["receipts"][-1]
            self.assertEqual(receipt["status"], "BLOCKED")
            self.assertTrue(receipt.get("approval_id"))
            self.assertTrue(receipt.get("payload_hash"))
            pending = operator._ledger.load(receipt["approval_id"])
            self.assertIsNotNone(pending)
            self.assertEqual(pending["payload_hash"], receipt["payload_hash"])


if __name__ == "__main__":
    unittest.main()
