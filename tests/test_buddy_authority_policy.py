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
    _on_has_exact_path,
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

    def test_push_path_must_match_the_workflow_exactly(self):
        text = """on:
  push:
    paths:
      - '.github/workflows/example.yml'
"""
        self.assertTrue(
            _on_has_exact_path(text, ".github/workflows/example.yml")
        )
        self.assertFalse(
            _on_has_exact_path(text, ".github/workflows/other.yml")
        )

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
        self.assertEqual(
            _unpinned_actions("    uses: appleboy/ssh-action@v1.2.0\\n"),
            ["appleboy/ssh-action@v1.2.0"],
        )
        self.assertEqual(
            _unpinned_actions(
                "    uses: appleboy/ssh-action@"
                "7eaf76671a0d7eec5d98ee897acda4f968735a17 # v1.2.0\\n"
            ),
            [],
        )


if __name__ == "__main__":
    unittest.main()
