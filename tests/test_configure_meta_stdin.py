"""Non-interactive Meta credential provisioning.

The Founder is not always at the VM terminal, so the governed workflow can
supply the credential payload on stdin from GitHub Secrets. The payload must
never reach argv, a file, or any log line, and a malformed payload must fail
without echoing what it contained.

configure_meta imports CredentialVault inside main(), so this module -- and
therefore its payload handling -- is importable and testable without the
cryptography extension.
"""

from __future__ import annotations

import io
import json
import unittest

from apps.dominion_publisher import configure_meta
from apps.dominion_publisher.configure_meta import PayloadError, read_stdin_payload

APP_ID = "1234567890123456"
APP_SECRET = "not-a-real-secret-only-used-in-tests"


class PayloadParsingTests(unittest.TestCase):
    def parse(self, raw):
        return read_stdin_payload(io.StringIO(raw))

    def test_minimal_payload_fills_the_documented_defaults(self):
        parsed = self.parse(json.dumps({"app_id": APP_ID, "app_secret": APP_SECRET}))
        self.assertEqual(parsed["app_id"], APP_ID)
        self.assertEqual(parsed["app_secret"], APP_SECRET)
        self.assertEqual(parsed["redirect_uri"], configure_meta.DEFAULT_REDIRECT_URI)
        self.assertEqual(parsed["graph_version"], configure_meta.DEFAULT_GRAPH_VERSION)

    def test_defaults_can_be_overridden(self):
        parsed = self.parse(json.dumps({
            "app_id": APP_ID, "app_secret": APP_SECRET,
            "redirect_uri": "https://example.invalid/cb", "graph_version": "v26.0",
        }))
        self.assertEqual(parsed["redirect_uri"], "https://example.invalid/cb")
        self.assertEqual(parsed["graph_version"], "v26.0")

    def test_surrounding_whitespace_is_stripped(self):
        parsed = self.parse(json.dumps({
            "app_id": f"  {APP_ID}  ", "app_secret": f"\t{APP_SECRET}\n",
        }))
        self.assertEqual(parsed["app_id"], APP_ID)
        self.assertEqual(parsed["app_secret"], APP_SECRET)

    # ── failure paths ────────────────────────────────────────────────────

    def test_empty_stdin_is_rejected(self):
        for raw in ("", "   \n"):
            with self.subTest(raw=repr(raw)):
                with self.assertRaises(PayloadError):
                    self.parse(raw)

    def test_non_json_is_rejected(self):
        with self.assertRaises(PayloadError):
            self.parse("app_id=123&app_secret=abc")

    def test_non_object_json_is_rejected(self):
        for raw in ('["a"]', '"string"', "42"):
            with self.subTest(raw=raw):
                with self.assertRaises(PayloadError):
                    self.parse(raw)

    def test_missing_fields_are_named(self):
        with self.assertRaises(PayloadError) as ctx:
            self.parse(json.dumps({"app_id": APP_ID}))
        self.assertIn("app_secret", str(ctx.exception))

        with self.assertRaises(PayloadError) as ctx:
            self.parse(json.dumps({"app_secret": APP_SECRET}))
        self.assertIn("app_id", str(ctx.exception))

    def test_blank_values_are_treated_as_missing(self):
        with self.assertRaises(PayloadError):
            self.parse(json.dumps({"app_id": APP_ID, "app_secret": "   "}))

    def test_error_never_quotes_the_secret(self):
        """A malformed payload must not leak its contents through the message."""
        with self.assertRaises(PayloadError) as ctx:
            self.parse(json.dumps({"app_id": "", "app_secret": APP_SECRET}))
        self.assertNotIn(APP_SECRET, str(ctx.exception))

        with self.assertRaises(PayloadError) as ctx:
            self.parse(f'{{"app_secret": "{APP_SECRET}", ')  # truncated JSON
        self.assertNotIn(APP_SECRET, str(ctx.exception))


class TransportSafetyTests(unittest.TestCase):
    """The secret must travel on stdin, never on the command line."""

    def test_module_reads_the_payload_from_stdin(self):
        src = (configure_meta.__file__ or "")
        self.assertTrue(src.endswith("configure_meta.py"))
        with open(src, encoding="utf-8") as handle:
            body = handle.read()
        self.assertIn("read_stdin_payload(sys.stdin)", body)

    def test_secret_is_not_accepted_as_an_argument(self):
        with open(configure_meta.__file__, encoding="utf-8") as handle:
            body = handle.read()
        # Only the mode flag is read from argv; no credential is parsed from it.
        self.assertIn('"--stdin" in args', body)
        for forbidden in ("--app-secret", "--app_secret", "--secret"):
            self.assertNotIn(forbidden, body)

    def test_interactive_path_still_masks_the_secret(self):
        with open(configure_meta.__file__, encoding="utf-8") as handle:
            body = handle.read()
        self.assertIn("getpass.getpass", body)

    def test_success_line_reveals_only_the_last_four_of_the_app_id(self):
        with open(configure_meta.__file__, encoding="utf-8") as handle:
            body = handle.read()
        self.assertIn("app_id_suffix", body)
        self.assertIn("app_id[-4:]", body)
        self.assertNotIn('{payload["app_secret"]}', body)


class WorkflowWiringTests(unittest.TestCase):
    """The governed workflow must pipe, not pass, and must gate on the Founder."""

    @classmethod
    def setUpClass(cls):
        from pathlib import Path
        root = Path(__file__).resolve().parents[1]
        cls.wf = (root / ".github" / "workflows" / "governed-meta-binding.yml").read_text(encoding="utf-8")
        cls.ctl = (root / "scripts" / "dominion_publisher" / "meta_control.sh").read_text(encoding="utf-8")

    def test_configure_is_founder_gated(self):
        self.assertIn("configure requires the Founder actor", self.wf)
        self.assertIn("configure requires the Founder triggering actor", self.wf)

    def test_missing_secrets_fail_before_touching_the_vm(self):
        self.assertIn("META_APP_ID secret is missing", self.wf)
        self.assertIn("META_APP_SECRET secret is missing", self.wf)

    def test_payload_is_piped_into_ssh_rather_than_passed_as_an_argument(self):
        self.assertIn("| ssh -i", self.wf)
        self.assertIn("configure-stdin", self.wf)
        # The secret must never be interpolated into a remote command string.
        self.assertNotIn("META_APP_SECRET='$META_APP_SECRET'", self.wf)
        self.assertNotIn('app_secret=$META_APP_SECRET', self.wf)

    def test_control_script_forwards_stdin_to_the_configure_module(self):
        self.assertIn("configure-stdin)", self.ctl)
        self.assertIn("configure_meta --stdin", self.ctl)


if __name__ == "__main__":
    unittest.main()
