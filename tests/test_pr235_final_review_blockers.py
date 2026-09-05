"""Final independent-review blocker regressions for PR #235."""
from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class FinalReviewBlockerTests(unittest.TestCase):
    def test_bridge_bearer_authorization_is_real_token_validation(self):
        source = (ROOT / "buddy_core" / "buddy_bridge_api.py").read_text(encoding="utf-8")
        self.assertIn('expected = f"Bearer {BUDDY_WEB_TOKEN}"', source)
        self.assertIn("hmac.compare_digest(auth, expected)", source)
        self.assertNotIn('Authorization: ******', source)

    def test_rollback_gates_clean_and_patch_on_successful_switch(self):
        source = (ROOT / "scripts" / "deploy_foundation_vm_remote.sh").read_text(encoding="utf-8")
        restore = source.split("restore_local_state()", 1)[1].split("quarantine_local_state()", 1)[0]
        self.assertIn('restore_output="$(git switch --detach --quiet "$PREVIOUS_SHA" 2>&1)"', restore)
        self.assertIn('if [ "$rc" -eq 0 ]; then', restore)
        self.assertIn('if [ "$rc" -eq 0 ] && [ -s "$LOCAL_STATE_BACKUP/index.patch" ]', restore)

    def test_external_delivery_uses_tamper_evident_audit(self):
        source = (ROOT / "buddy_core" / "core" / "operator.py").read_text(encoding="utf-8")
        external = source.split("def _execute_external", 1)[1].split("def _no_delivery_backend", 1)[0]
        self.assertIn("governed_audit_log(", external)
        self.assertIn("delivery_evidence_sha256", external)
        self.assertNotIn('audit("external_action_executed"', external)

    def test_external_delivery_requires_receipt_provenance_and_time(self):
        source = (ROOT / "buddy_core" / "core" / "operator.py").read_text(encoding="utf-8")
        self.assertIn("platform_receipt_id", source)
        self.assertIn("provenance_keys", source)
        self.assertIn("time_keys", source)

    def test_saraqael_self_check_entrypoint_runs_in_standalone_layout(self):
        """The migration runbook tells operators to run the chain self-check.

        On the standalone VM layout there is no importable `buddy_core`
        package, so if `core.operator` imports `watchmen.saraqael` at module
        scope the cycle through phi_memory raises ImportError, falls through to
        the buddy_core.* branch, and kills the entrypoint with
        ModuleNotFoundError. Importing saraqael first must keep working.
        """
        import os
        import subprocess
        import sys
        import tempfile

        core_dir = ROOT / "buddy_core"
        for statement in ("from watchmen.saraqael import log",
                          "import sentinel",
                          "import core; from watchmen.saraqael import log"):
            with tempfile.TemporaryDirectory() as tmp:
                result = subprocess.run(
                    [sys.executable, "-c", statement],
                    cwd=str(core_dir), capture_output=True, text=True,
                    env={**os.environ,
                         "DOMINION_WATCHMEN_STATE_DIR": tmp + "/w"},
                )
                self.assertEqual(result.returncode, 0,
                                 f"{statement!r} failed: {result.stderr[-400:]}")

    def test_governed_audit_log_is_resolved_at_call_time(self):
        source = (ROOT / "buddy_core" / "core" / "operator.py").read_text(encoding="utf-8")
        self.assertIn("def governed_audit_log(", source)
        # A module-scope import of saraqael would reintroduce the cycle.
        self.assertNotIn("\nfrom watchmen.saraqael import", source)
        self.assertNotIn("\nfrom buddy_core.watchmen.saraqael import", source)


if __name__ == "__main__":
    unittest.main()
