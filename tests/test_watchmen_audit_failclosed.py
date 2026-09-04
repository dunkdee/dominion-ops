"""Regression tests for E0-001B Sentinel/Watchmen fail-closed audit behavior."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "buddy_core"))

import sentinel  # noqa: E402
from watchmen import saraqael  # noqa: E402


class FakeState:
    def __init__(self):
        self.restarts = 0
        self.fixes = 0
        self.data = {"cycles": 0, "last_result": None}

    def record_restart(self, _name):
        self.restarts += 1

    def record_fix(self):
        self.fixes += 1

    def can_alert(self, _key):
        return False

    def mark_alerted(self, _key):
        pass


class SentinelAuditBoundaryTests(unittest.TestCase):
    def test_audit_log_success_returns_governed_receipt(self):
        receipt = {"seq": 1, "hash": "abc"}
        with mock.patch("watchmen.saraqael.log", return_value=receipt):
            self.assertEqual(
                sentinel.audit_log("sentinel", "example", "ok", {"x": 1}),
                receipt,
            )

    def test_audit_unavailable_raises_and_never_writes_unsigned_fallback(self):
        legacy = Path.home() / "buddy_core" / "logs" / "sentinel_audit.log"
        existed = legacy.exists()
        before = legacy.read_bytes() if existed else None
        with mock.patch("watchmen.saraqael.log", side_effect=RuntimeError("audit down")):
            with self.assertRaises(sentinel.AuditUnavailable):
                sentinel.audit_log("sentinel", "blocked", "ok")
        if existed:
            self.assertEqual(legacy.read_bytes(), before)
        else:
            self.assertFalse(legacy.exists())

    def test_docker_mutation_does_not_run_when_audit_intent_is_unavailable(self):
        state = FakeState()
        with mock.patch.object(sentinel, "DOCKER_CONTAINERS", ["candidate"]), \
             mock.patch.object(sentinel, "check_docker_status", return_value="stopped"), \
             mock.patch.object(
                 sentinel, "_audit_intent",
                 side_effect=sentinel.AuditUnavailable("no governed audit"),
             ), \
             mock.patch.object(sentinel.subprocess, "run") as run:
            issues, fixed = sentinel.check_docker(state)
        run.assert_not_called()
        self.assertEqual(fixed, [])
        self.assertEqual(state.restarts, 0)
        self.assertEqual(state.fixes, 0)
        self.assertTrue(any("audit" in issue.lower() for issue in issues))

    def test_post_mutation_receipt_failure_is_not_reported_as_complete(self):
        state = FakeState()
        statuses = iter(["stopped", "running"])
        with mock.patch.object(sentinel, "DOCKER_CONTAINERS", ["candidate"]), \
             mock.patch.object(sentinel, "check_docker_status", side_effect=lambda _n: next(statuses)), \
             mock.patch.object(sentinel, "_audit_intent", return_value={"seq": 1}), \
             mock.patch.object(
                 sentinel, "audit_log",
                 side_effect=sentinel.AuditUnavailable("receipt failed"),
             ), \
             mock.patch.object(sentinel.subprocess, "run") as run, \
             mock.patch.object(sentinel.time, "sleep"):
            issues, fixed = sentinel.check_docker(state)
        run.assert_called_once()
        self.assertEqual(fixed, [])
        self.assertEqual(state.restarts, 0)
        self.assertEqual(state.fixes, 0)
        self.assertTrue(any("NOT ACCEPTED AS COMPLETE" in issue for issue in issues))

    def test_legacy_sentinel_fallback_is_git_ignored(self):
        ignored = ROOT / "buddy_core" / "logs" / "sentinel_audit.log"
        result = __import__("subprocess").run(
            ["git", "check-ignore", "-q", str(ignored)], cwd=str(ROOT)
        )
        self.assertEqual(result.returncode, 0)


class SaraqaelStrictReadTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.old_state = os.environ.get(saraqael.ENV_STATE_DIR)
        self.old_key = os.environ.get(saraqael.ENV_HMAC_KEY)
        self.old_key_file = os.environ.get(saraqael.ENV_HMAC_FILE)
        os.environ[saraqael.ENV_STATE_DIR] = str(Path(self.tmp.name) / "state")
        os.environ.pop(saraqael.ENV_HMAC_KEY, None)
        os.environ.pop(saraqael.ENV_HMAC_FILE, None)
        self.addCleanup(self._restore_env)

    def _restore_env(self):
        for name, value in (
            (saraqael.ENV_STATE_DIR, self.old_state),
            (saraqael.ENV_HMAC_KEY, self.old_key),
            (saraqael.ENV_HMAC_FILE, self.old_key_file),
        ):
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value

    def test_tail_surfaces_malformed_history_instead_of_skipping_it(self):
        saraqael.log("test", "valid", "ok")
        with open(saraqael.audit_file(), "a", encoding="utf-8") as handle:
            handle.write("{ malformed\n")
        with self.assertRaises(saraqael.WatchmenStateError):
            saraqael.tail()

    def test_report_marks_malformed_history_untrusted(self):
        saraqael.log("test", "valid", "ok")
        with open(saraqael.audit_file(), "a", encoding="utf-8") as handle:
            handle.write("{ malformed\n")
        report = saraqael.report()
        self.assertFalse(report["chain_valid"])
        self.assertTrue(report["corruption_visible"])

    @unittest.skipUnless(os.name == "posix", "POSIX permission enforcement")
    def test_state_dir_permission_failure_is_fail_closed(self):
        with mock.patch.object(saraqael.os, "chmod", side_effect=OSError("denied")):
            with self.assertRaises(saraqael.WatchmenStateError):
                saraqael._ensure_state_dir()

    @unittest.skipUnless(os.name == "posix", "POSIX permission enforcement")
    def test_insecure_explicit_key_file_is_rejected(self):
        key_path = Path(self.tmp.name) / "explicit.key"
        key_path.write_text("secret-material\n", encoding="utf-8")
        key_path.chmod(0o644)
        os.environ[saraqael.ENV_HMAC_FILE] = str(key_path)
        with self.assertRaises(saraqael.WatchmenStateError):
            saraqael._resolve_key()

    def test_report_valid_chain_remains_valid(self):
        saraqael.log("test", "one", "ok")
        saraqael.log("test", "two", "ok")
        report = saraqael.report()
        self.assertTrue(report["chain_valid"], report["chain_msg"])
        self.assertFalse(report["corruption_visible"])
        self.assertEqual(report["total"], 2)


if __name__ == "__main__":
    unittest.main()
