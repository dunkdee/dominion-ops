from pathlib import Path
import textwrap


def replace_once(path: str, old: str, new: str) -> None:
    p = Path(path)
    src = p.read_text(encoding="utf-8")
    count = src.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected exactly one match, found {count}: {old[:120]!r}")
    p.write_text(src.replace(old, new, 1), encoding="utf-8")


# A. AuthorizationLedger: make os.replace durability fail-closed by fsyncing parent dir.
replace_once(
    "buddy_core/core/authorization.py",
    '''            os.replace(tmp, path)\n            try:\n                path.chmod(0o600)\n            except OSError:\n                pass\n''',
    '''            os.replace(tmp, path)\n            if os.name == "posix":\n                dir_fd = None\n                try:\n                    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)\n                    dir_fd = os.open(str(path.parent), flags)\n                    os.fsync(dir_fd)\n                except (OSError, NotImplementedError) as exc:\n                    raise AuthorizationError("authorization_state_directory_fsync_failed") from exc\n                finally:\n                    if dir_fd is not None:\n                        try:\n                            os.close(dir_fd)\n                        except OSError:\n                            pass\n            try:\n                path.chmod(0o600)\n            except OSError:\n                pass\n''',
)

# B. Held plans contain authorization-bound content/destinations: enforce exact 0700 on POSIX.
replace_once(
    "buddy_core/core/operator.py",
    "import re\nimport tempfile\n",
    "import re\nimport stat\nimport tempfile\n",
)
replace_once(
    "buddy_core/core/operator.py",
    '''        self.held_dir.mkdir(parents=True, exist_ok=True)\n        try:\n            self.held_dir.chmod(0o700)\n        except OSError:\n            pass\n''',
    '''        self.held_dir.mkdir(parents=True, exist_ok=True)\n        if os.name == "posix":\n            try:\n                self.held_dir.chmod(0o700)\n                actual_mode = stat.S_IMODE(self.held_dir.stat().st_mode)\n            except (OSError, NotImplementedError) as exc:\n                raise AuthorizationError("held_plan_directory_permissions_unavailable") from exc\n            if actual_mode != 0o700:\n                raise AuthorizationError(\n                    f"held_plan_directory_not_private:{oct(actual_mode)}"\n                )\n''',
)

# C. If ledger request succeeds but held-plan persistence fails, preserve safe approval refs.
replace_once(
    "buddy_core/core/operator.py",
    '''                try:\n                    request = self._ledger.request(\n''',
    '''                request = None\n                try:\n                    request = self._ledger.request(\n''',
)
replace_once(
    "buddy_core/core/operator.py",
    '''                except (AuthorizationError, OSError, TypeError, ValueError) as exc:\n                    receipts.append({\n                        "step": index,\n                        "capability": frozen_step["capability"],\n                        "status": "BLOCKED",\n                        "attempts": 0,\n                        "errors": [{"attempt": 0, "error": "AuthorizationStorageUnavailable",\n                                    "detail": str(exc)[:200]}],\n                        "result": None,\n                        "evidence": [],\n                    })\n                    break\n''',
    '''                except (AuthorizationError, OSError, TypeError, ValueError) as exc:\n                    blocked = {\n                        "step": index,\n                        "capability": frozen_step["capability"],\n                        "status": "BLOCKED",\n                        "attempts": 0,\n                        "errors": [{"attempt": 0, "error": "AuthorizationStorageUnavailable",\n                                    "detail": str(exc)[:200]}],\n                        "result": None,\n                        "evidence": [],\n                    }\n                    if isinstance(request, dict):\n                        approval_id = request.get("approval_id")\n                        payload_hash = request.get("payload_hash")\n                        if approval_id:\n                            blocked["approval_id"] = approval_id\n                        if payload_hash:\n                            blocked["payload_hash"] = payload_hash\n                    receipts.append(blocked)\n                    break\n''',
)

# Regression coverage for all three independent-review blockers.
Path("tests/test_pr235_final_authority_closure.py").write_text(textwrap.dedent(r'''\
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
'''), encoding="utf-8")

for helper in (
    ".github/scripts/pr235_authority_closure_patch.py",
    ".github/workflows/pr235-authority-final-closure.yml",
):
    helper_path = Path(helper)
    if helper_path.exists():
        helper_path.unlink()

print("PR235_FINAL_AUTHORITY_CLOSURE=APPLIED")
