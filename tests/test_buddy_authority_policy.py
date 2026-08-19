import copy
import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from validate_buddy_authority_policy import (  # noqa: E402
    OBSERVER_FORBIDDEN_PATTERNS,
    PolicyError,
    _missing_founder_gate,
    _pattern_hits,
    _unpinned_actions,
    autonomy_workflow_errors,
    validate,
    workflow_triggers,
)


POLICY_PATH = ROOT / "governance" / "buddy" / "buddy_authority_policy.json"


class BuddyAuthorityPolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))

    def test_canonical_policy_passes(self):
        validate(copy.deepcopy(self.policy))

    def test_buddy_is_primary_founder_directed_personal_ai(self):
        identity = self.policy["identity"]
        self.assertEqual(identity["role"], "PRIMARY_PERSONAL_AI")
        self.assertEqual(identity["authority_model"], "FOUNDER_DIRECTED")
        self.assertEqual(identity["principal"], "Dewayne Singleton")

    def test_direct_and_standing_founder_authorization_are_supported(self):
        sources = set(self.policy["authorization"]["accepted_sources"])
        self.assertEqual(sources, {"DIRECT_FOUNDER_INSTRUCTION", "ACTIVE_STANDING_FOUNDER_POLICY"})

    def test_unbounded_repair_attempts_fail(self):
        candidate = copy.deepcopy(self.policy)
        candidate["self_repair"]["max_attempts"] = 99
        with self.assertRaises(PolicyError):
            validate(candidate)

    def test_repair_scope_cannot_silently_expand(self):
        candidate = copy.deepcopy(self.policy)
        candidate["self_repair"]["allowed_services"].append("dominion-n8n.service")
        with self.assertRaises(PolicyError):
            validate(candidate)

    def test_external_action_mode_cannot_become_self_authorized(self):
        candidate = copy.deepcopy(self.policy)
        candidate["external_actions"]["mode"] = "SELF_AUTHORIZED"
        with self.assertRaises(PolicyError):
            validate(candidate)

    def test_vm_only_source_cannot_claim_verified_conformance(self):
        candidate = copy.deepcopy(self.policy)
        candidate["live_conformance"]["status"] = "VERIFIED"
        with self.assertRaises(PolicyError):
            validate(candidate)

    def test_legal_identity_impersonation_cannot_be_enabled(self):
        candidate = copy.deepcopy(self.policy)
        candidate["representation"]["may_claim_founder_legal_identity"] = True
        with self.assertRaises(PolicyError):
            validate(candidate)

    def test_autonomy_policy_has_four_canonical_lanes(self):
        lanes = self.policy["autonomy_control"]["lanes"]
        self.assertEqual(set(lanes), {
            "ci_validation",
            "runtime_observation",
            "buddy_bounded_self_repair",
            "founder_approved_apply",
        })

    def test_bounded_healer_scope_matches_buddy_policy(self):
        bounded = set(self.policy["autonomy_control"]["lanes"]
                      ["buddy_bounded_self_repair"]["allowed_services"])
        canonical = set(self.policy["self_repair"]["allowed_services"])
        self.assertEqual(bounded, canonical)

    def test_repository_workflows_match_autonomy_policy(self):
        observer = self.policy["autonomy_control"]["lanes"]["runtime_observation"]["workflow"]
        if not (ROOT / observer).is_file():
            self.skipTest("workflow tree not present in local policy-only fixture")
        self.assertEqual(autonomy_workflow_errors(ROOT, self.policy), [])

    def test_trigger_parser_handles_quoted_on_key(self):
        text = 'name: test\n"on":\n  push:\n  workflow_dispatch:\njobs:\n  x:\n    runs-on: ubuntu-latest\n'
        self.assertEqual(workflow_triggers(text), {"push", "workflow_dispatch"})

    def test_founder_gate_without_exact_sha_is_rejected(self):
        block = """  apply:
    if: >-
      github.event_name == 'workflow_dispatch' &&
      inputs.confirm == 'APPLY TEST' &&
      github.ref == 'refs/heads/main'
"""
        self.assertIn("inputs.commit_sha == github.sha",
                      _missing_founder_gate(block, "APPLY TEST"))

    def test_observer_restart_command_is_forbidden(self):
        hits = _pattern_hits("sudo systemctl restart example.service",
                             OBSERVER_FORBIDDEN_PATTERNS)
        self.assertIn("systemd mutation", hits)

    def test_automatic_action_reference_must_be_commit_pinned(self):
        # \\n was a defect: backslash is not whitespace so [^\s#]+ consumed it.
        # Actual newline terminates the capture correctly.
        self.assertEqual(
            _unpinned_actions("    uses: appleboy/ssh-action@v1.2.0\n"),
            ["appleboy/ssh-action@v1.2.0"],
        )
        self.assertEqual(
            _unpinned_actions(
                "    uses: appleboy/ssh-action@"
                "7eaf76671a0d7eec5d98ee897acda4f968735a17 # v1.2.0\n"
            ),
            [],
        )


class ActionUsesRegexRegressionTests(unittest.TestCase):
    """Regression suite for ACTION_USES_RE double-escape + list-marker defect.

    Recognition tests come first.  SHA acceptance is proved only after
    recognition is independently established — otherwise a regex that
    matches nothing would produce [] and falsely pass the acceptance test.
    """

    # --- Positive recognition (must return non-empty) ---

    def test_mapping_form_uses_is_recognized(self):
        """8-space mapping-form uses: must be matched and reported."""
        # Broken regex returns [] — this test catches non-recognition.
        result = _unpinned_actions("        uses: actions/checkout@v3\n")
        self.assertEqual(result, ["actions/checkout@v3"])

    def test_list_item_uses_is_recognized(self):
        """6-space list-item - uses: must be matched and reported."""
        result = _unpinned_actions("      - uses: actions/checkout@v3\n")
        self.assertEqual(result, ["actions/checkout@v3"])

    def test_multiple_uses_lines_all_scanned(self):
        """Every uses: line in a multi-step block must be evaluated."""
        sha = "da39a3ee5e6b4b0d3255bfef95601890afd80709"
        text = (
            "    steps:\n"
            "      - uses: actions/checkout@v4\n"
            f"        uses: actions/setup-python@{sha}\n"
            "      - uses: docker/build-push-action@v5\n"
        )
        result = _unpinned_actions(text)
        self.assertIn("actions/checkout@v4", result)
        self.assertIn("docker/build-push-action@v5", result)
        self.assertNotIn(f"actions/setup-python@{sha}", result)
        self.assertEqual(len(result), 2)

    # --- Detection ---

    def test_unpinned_version_tag_is_detected(self):
        """Semver tag reference must appear in the unpinned list."""
        result = _unpinned_actions("      - uses: appleboy/ssh-action@v1.2.0\n")
        self.assertEqual(result, ["appleboy/ssh-action@v1.2.0"])

    # --- SHA acceptance (valid only after recognition is proven above) ---

    def test_40_char_sha_accepted_mapping_form(self):
        """Pinned 40-char SHA in mapping form must not be reported."""
        sha = "7eaf76671a0d7eec5d98ee897acda4f968735a17"
        result = _unpinned_actions(f"        uses: appleboy/ssh-action@{sha}\n")
        self.assertEqual(result, [])

    def test_40_char_sha_accepted_list_item_form(self):
        """Pinned 40-char SHA in list-item form must not be reported."""
        sha = "7eaf76671a0d7eec5d98ee897acda4f968735a17"
        result = _unpinned_actions(f"      - uses: appleboy/ssh-action@{sha}\n")
        self.assertEqual(result, [])

    # --- Comments / whitespace ---

    def test_trailing_comment_on_pinned_sha_does_not_break_acceptance(self):
        """# version comment after a SHA must not prevent pinning acceptance."""
        sha = "7eaf76671a0d7eec5d98ee897acda4f968735a17"
        result = _unpinned_actions(
            f"        uses: appleboy/ssh-action@{sha} # v1.2.0\n"
        )
        self.assertEqual(result, [])

    def test_trailing_whitespace_after_unpinned_tag_does_not_suppress_detection(self):
        """Spaces after an unpinned version tag must not prevent detection."""
        result = _unpinned_actions("      - uses: actions/checkout@v3   \n")
        self.assertIn("actions/checkout@v3", result)

    # --- Local actions ---

    def test_local_action_without_at_sign_is_not_flagged(self):
        """Local ./path actions have no @ and must not appear in results."""
        result = _unpinned_actions("      - uses: ./.github/actions/my-action\n")
        self.assertEqual(result, [])

    # --- Boundary ---

    def test_39_char_hex_is_treated_as_unpinned(self):
        """A 39-character hex string is not a valid commit SHA and must be flagged."""
        short = "a" * 39
        result = _unpinned_actions(f"      - uses: actions/checkout@{short}\n")
        self.assertEqual(len(result), 1)


if __name__ == "__main__":
    unittest.main()
