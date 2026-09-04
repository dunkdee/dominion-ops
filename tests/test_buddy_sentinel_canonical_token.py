"""Sentinel must keep BUDDY_WEB_TOKEN in exactly one file, never mirror it.

Every other required key is still synced across all three legacy dotenv
files for backward compatibility. The token is different: it is a live
production credential, and mirroring it into three files is exactly how the
duplicate-assignment bug this branch fixes got there. Sentinel must instead
enforce a single canonical file and actively strip the key from the rest.
"""

from __future__ import annotations

import importlib
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "buddy_core"))


class _FakeState:
    def __init__(self):
        self.fixes = 0

    def record_fix(self):
        self.fixes += 1


def load_sentinel(home: Path):
    """Import sentinel.py fresh with ENV_FILES/CANONICAL_TOKEN_FILE pointed at a temp home."""
    for name in ("sentinel",):
        sys.modules.pop(name, None)
    with mock.patch.object(Path, "home", return_value=home):
        module = importlib.import_module("sentinel")
        importlib.reload(module)
    return module


class SentinelCanonicalTokenTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.home = Path(self._tmp.name)
        (self.home / "buddy_core").mkdir()
        (self.home / "conductor").mkdir()
        self.addCleanup(self._tmp.cleanup)
        self.sentinel = load_sentinel(self.home)
        # check_env_keys only syncs into files that already exist.
        (self.home / "conductor" / ".env").touch()
        (self.home / ".env").touch()
        # Every other required key just needs to exist somewhere so the loop
        # for non-token keys doesn't report MISSING noise in these tests.
        for key in self.sentinel.REQUIRED_ENV_KEYS:
            if key != self.sentinel.TOKEN_KEY:
                self.write("buddy_core/.env", f"{key}=placeholder\n", append=True)

    def write(self, rel: str, body: str, append: bool = False):
        path = self.home / rel
        mode = "a" if append and path.exists() else "w"
        with open(path, mode, encoding="utf-8") as f:
            f.write(body)
        return path

    def test_token_scattered_across_three_files_consolidates_to_one(self):
        self.write("buddy_core/.env", "BUDDY_WEB_TOKEN=canonical-value\n", append=True)
        self.write("conductor/.env", "BUDDY_WEB_TOKEN=stale-value\n")
        self.write(".env", "BUDDY_WEB_TOKEN=another-stale-value\n")

        issues, fixed = self.sentinel.check_env_keys(_FakeState())

        canonical = (self.home / "buddy_core" / ".env").read_text()
        conductor = (self.home / "conductor" / ".env").read_text()
        home_env = (self.home / ".env").read_text()

        self.assertIn("BUDDY_WEB_TOKEN=canonical-value", canonical)
        self.assertNotIn("BUDDY_WEB_TOKEN=", conductor)
        self.assertNotIn("BUDDY_WEB_TOKEN=", home_env)
        self.assertTrue(any("NON-CANONICAL" in i for i in issues))

    def test_already_consolidated_state_is_a_no_op(self):
        self.write("buddy_core/.env", "BUDDY_WEB_TOKEN=only-value\n", append=True)

        issues, fixed = self.sentinel.check_env_keys(_FakeState())
        token_fixes = [f for f in fixed if "BUDDY_WEB_TOKEN" in f]
        self.assertEqual(token_fixes, [])
        self.assertEqual((self.home / "buddy_core" / ".env").read_text().count("BUDDY_WEB_TOKEN="), 1)

    def test_duplicate_assignment_in_canonical_file_is_collapsed_not_mirrored(self):
        self.write(
            "buddy_core/.env",
            "BUDDY_WEB_TOKEN=\nOTHER=1\nBUDDY_WEB_TOKEN=real-value\n",
            append=True,
        )

        self.sentinel.check_env_keys(_FakeState())

        canonical = (self.home / "buddy_core" / ".env").read_text()
        self.assertEqual(canonical.count("BUDDY_WEB_TOKEN="), 1)
        self.assertIn("BUDDY_WEB_TOKEN=real-value", canonical)

    def test_value_found_only_in_a_legacy_file_is_migrated_into_canonical(self):
        # No token in buddy_core/.env yet, only in a legacy file.
        self.write("conductor/.env", "BUDDY_WEB_TOKEN=legacy-only-value\n")

        self.sentinel.check_env_keys(_FakeState())

        canonical = (self.home / "buddy_core" / ".env").read_text()
        conductor = (self.home / "conductor" / ".env").read_text()
        self.assertIn("BUDDY_WEB_TOKEN=legacy-only-value", canonical)
        self.assertNotIn("BUDDY_WEB_TOKEN=", conductor)

    def test_other_required_keys_are_still_mirrored_everywhere(self):
        # Sanity check: the single-source rule is specific to the token, not
        # a regression for every other required key's backward-compat sync.
        self.write("buddy_core/.env", "BUDDY_WEB_TOKEN=x\n", append=True)
        self.sentinel.check_env_keys(_FakeState())
        for key in self.sentinel.REQUIRED_ENV_KEYS:
            if key == self.sentinel.TOKEN_KEY:
                continue
            for rel in ("buddy_core/.env", "conductor/.env", ".env"):
                self.assertIn(key, (self.home / rel).read_text())


if __name__ == "__main__":
    unittest.main()
