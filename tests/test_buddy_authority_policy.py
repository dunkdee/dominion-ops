import copy
import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from validate_buddy_authority_policy import PolicyError, validate  # noqa: E402


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


if __name__ == "__main__":
    unittest.main()
