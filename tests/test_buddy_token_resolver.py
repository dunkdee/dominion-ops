"""BUDDY_WEB_TOKEN resolution: one answer, conflicts surfaced, secrets kept."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "buddy_core"))

from core.token_resolver import (  # noqa: E402
    count_assignments,
    fingerprint,
    parse_env_file,
    resolve_buddy_web_token,
)


class TokenResolverTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.home = Path(self._tmp.name)
        (self.home / "buddy_core").mkdir()
        (self.home / "conductor").mkdir()
        self.addCleanup(self._tmp.cleanup)

    def write(self, rel: str, body: str) -> Path:
        path = self.home / rel
        path.write_text(body, encoding="utf-8")
        return path

    def test_empty_duplicate_line_no_longer_shadows_the_real_token(self):
        # The exact production failure: a blank assignment above the real one.
        # dotenv(override=False) kept the blank and Buddy answered 503.
        self.write("buddy_core/.env", "BUDDY_WEB_TOKEN=\nOTHER=1\nBUDDY_WEB_TOKEN=live-token-value\n")
        resolution = resolve_buddy_web_token(env={}, home=self.home)
        self.assertEqual(resolution.token, "live-token-value")
        self.assertTrue(resolution.configured)
        self.assertEqual(resolution.duplicate_sources, ["buddy_core/.env"])
        self.assertTrue(resolution.duplicated)

    def test_process_environment_outranks_every_dotenv_file(self):
        self.write("buddy_core/.env", "BUDDY_WEB_TOKEN=from-file\n")
        resolution = resolve_buddy_web_token(env={"BUDDY_WEB_TOKEN": "from-systemd"}, home=self.home)
        self.assertEqual(resolution.token, "from-systemd")
        self.assertEqual(resolution.source, "process-environment")

    def test_precedence_matches_the_historical_buddy_web_load_order(self):
        self.write("buddy_core/.env", "BUDDY_WEB_TOKEN=buddy-core\n")
        self.write("conductor/.env", "BUDDY_WEB_TOKEN=conductor\n")
        self.write(".env", "BUDDY_WEB_TOKEN=home\n")
        resolution = resolve_buddy_web_token(env={}, home=self.home)
        self.assertEqual(resolution.token, "buddy-core")
        self.assertEqual(resolution.source, "buddy_core/.env")

    def test_disagreeing_files_are_reported_not_silently_picked(self):
        self.write("buddy_core/.env", "BUDDY_WEB_TOKEN=alpha\n")
        self.write(".env", "BUDDY_WEB_TOKEN=beta\n")
        resolution = resolve_buddy_web_token(env={}, home=self.home)
        self.assertTrue(resolution.conflict)
        self.assertEqual(resolution.conflicting_sources, ["buddy_core/.env", "~/.env"])
        self.assertEqual(resolution.token, "alpha")

    def test_identical_values_across_files_are_not_a_conflict(self):
        self.write("buddy_core/.env", "BUDDY_WEB_TOKEN=same\n")
        self.write("conductor/.env", "BUDDY_WEB_TOKEN=same\n")
        self.write(".env", "BUDDY_WEB_TOKEN=same\n")
        resolution = resolve_buddy_web_token(env={}, home=self.home)
        self.assertFalse(resolution.conflict)
        self.assertFalse(resolution.duplicated)

    def test_blank_only_file_is_reported_as_empty_not_configured(self):
        self.write("buddy_core/.env", "BUDDY_WEB_TOKEN=\n")
        resolution = resolve_buddy_web_token(env={}, home=self.home)
        self.assertFalse(resolution.configured)
        self.assertEqual(resolution.empty_sources, ["buddy_core/.env"])

    def test_report_never_carries_secret_material(self):
        self.write("buddy_core/.env", "BUDDY_WEB_TOKEN=super-secret-value\n")
        self.write(".env", "BUDDY_WEB_TOKEN=other-secret-value\n")
        report = repr(resolve_buddy_web_token(env={}, home=self.home).report())
        self.assertNotIn("super-secret-value", report)
        self.assertNotIn("other-secret-value", report)

    def test_parser_handles_export_quotes_and_comments(self):
        path = self.write("buddy_core/.env", '# comment\nexport BUDDY_WEB_TOKEN="quoted-value"\n')
        self.assertEqual(parse_env_file(path)["BUDDY_WEB_TOKEN"], "quoted-value")
        self.assertEqual(count_assignments(path), 1)

    def test_missing_file_resolves_empty_instead_of_raising(self):
        self.assertEqual(parse_env_file(self.home / "nope" / ".env"), {})
        self.assertEqual(count_assignments(self.home / "nope" / ".env"), 0)

    def test_fingerprints_distinguish_values_without_revealing_them(self):
        self.assertNotEqual(fingerprint("a"), fingerprint("b"))
        self.assertEqual(fingerprint(""), "")
        self.assertEqual(len(fingerprint("a")), 12)


if __name__ == "__main__":
    unittest.main()
