from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from scripts.validate_public_api_candidate_registry import RegistryValidationError, validate_registry


ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = ROOT / "governance" / "public_api_candidate_registry.json"


class PublicApiCandidateRegistryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))

    def test_canonical_registry_passes(self) -> None:
        result = validate_registry(self.registry)
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["candidate_count"], 15)
        self.assertGreaterEqual(result["high_priority_count"], 1)

    def test_defaults_to_quarantine(self) -> None:
        broken = copy.deepcopy(self.registry)
        broken["default_candidate_state"] = "APPROVED_FOR_RUNTIME"
        with self.assertRaisesRegex(RegistryValidationError, "registry_must_default_to_quarantine"):
            validate_registry(broken)

    def test_automatic_activation_is_forbidden(self) -> None:
        broken = copy.deepcopy(self.registry)
        broken["automatic_activation_enabled"] = True
        with self.assertRaisesRegex(RegistryValidationError, "automatic_activation_must_be_disabled"):
            validate_registry(broken)

    def test_external_mutation_is_forbidden(self) -> None:
        broken = copy.deepcopy(self.registry)
        broken["external_mutation_enabled"] = True
        with self.assertRaisesRegex(RegistryValidationError, "external_mutation_must_be_disabled"):
            validate_registry(broken)

    def test_runtime_promotion_target_is_fixed(self) -> None:
        broken = copy.deepcopy(self.registry)
        broken["runtime_registry"] = "somewhere/else.json"
        with self.assertRaisesRegex(RegistryValidationError, "runtime_registry_target_invalid"):
            validate_registry(broken)

    def test_candidate_cannot_contain_runtime_target(self) -> None:
        broken = copy.deepcopy(self.registry)
        broken["candidates"]["zenserp"]["target"] = "https://example.invalid/runtime"
        with self.assertRaisesRegex(RegistryValidationError, "candidate_contains_runtime_or_secret_fields"):
            validate_registry(broken)

    def test_candidate_cannot_contain_secret_field(self) -> None:
        broken = copy.deepcopy(self.registry)
        broken["candidates"]["zenserp"]["api_key"] = "not-a-real-secret"
        with self.assertRaisesRegex(RegistryValidationError, "candidate_contains_runtime_or_secret_fields"):
            validate_registry(broken)

    def test_candidate_effect_ceiling_must_be_read_only(self) -> None:
        broken = copy.deepcopy(self.registry)
        broken["candidates"]["mediastack"]["effect_ceiling"] = "write"
        with self.assertRaisesRegex(RegistryValidationError, "candidate_effect_not_read_only"):
            validate_registry(broken)

    def test_quarantined_candidate_cannot_claim_runtime_verification(self) -> None:
        broken = copy.deepcopy(self.registry)
        broken["candidates"]["screenshotlayer"]["runtime_verified"] = True
        with self.assertRaisesRegex(RegistryValidationError, "quarantined_candidate_cannot_be_runtime_verified"):
            validate_registry(broken)

    def test_discovery_url_must_use_https(self) -> None:
        broken = copy.deepcopy(self.registry)
        broken["candidates"]["fixer"]["discovery_url"] = "http://example.invalid"
        with self.assertRaisesRegex(RegistryValidationError, "candidate_discovery_url_invalid"):
            validate_registry(broken)


if __name__ == "__main__":
    unittest.main()
