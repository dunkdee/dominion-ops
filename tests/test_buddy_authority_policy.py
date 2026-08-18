import copy
import json
import shutil
import sys
import tempfile
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

    def test_runtime_loops_use_local_systemd_not_hosted_schedules(self):
        autonomy = self.policy["autonomy_control"]
        self.assertFalse(
            autonomy["github_hosted_schedule_policy"]
            ["automatic_schedules_allowed"]
        )
        self.assertEqual(
            autonomy["github_hosted_schedule_policy"]["runtime_scheduler"],
            "SYSTEMD_ON_FOUNDATION_VM",
        )
        observer = autonomy["lanes"]["runtime_observation"]
        healer = autonomy["lanes"]["buddy_bounded_self_repair"]
        self.assertEqual(observer["interval_seconds"], 900)
        self.assertEqual(healer["interval_seconds"], 600)
        self.assertEqual(observer["workflow_mode"], "MANUAL_FALLBACK_ONLY")
        self.assertEqual(healer["workflow_mode"], "MANUAL_FALLBACK_ONLY")

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

    def test_hosted_schedule_is_rejected_even_without_production_markers(self):
        candidate = copy.deepcopy(self.policy)
        autonomy = candidate["autonomy_control"]
        autonomy["manual_only_workflows"] = {}
        autonomy["guarded_jobs"] = {}

        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            workflows = root / ".github" / "workflows"
            workflows.mkdir(parents=True)

            observer = autonomy["lanes"]["runtime_observation"]
            healer = autonomy["lanes"]["buddy_bounded_self_repair"]

            (root / observer["workflow"]).write_text(
                """name: observer
on:
  workflow_dispatch:
jobs:
  observe:
    runs-on: ubuntu-24.04
    steps:
      - run: |
          echo RUNTIME_OBSERVER=
          echo CONTAINMENT_HOLD=
          echo allow-ops-dashboard
          echo allow-twilio-router
          echo 127.0.0.1:5070/buddy
""",
                encoding="utf-8",
            )
            (root / healer["workflow"]).write_text(
                """name: healer
on:
  workflow_dispatch:
jobs:
  bounded-repair:
    runs-on: ubuntu-24.04
    steps:
      - run: |
          MAX_ATTEMPTS=2
          COOLDOWN_SECONDS=300
          echo dominion-buddy-web.service
          echo dominion-proposal-queue.service
          echo dominion-sentinel.service
          flock -n 9
          sudo systemctl restart "$unit"
          echo BUDDY_SELF_HEAL=NO_ACTION_HEALTHY
          echo BUDDY_SELF_HEAL=RECOVERED
          echo BUDDY_SELF_HEAL=BLOCKED_CIRCUIT_OPEN
""",
                encoding="utf-8",
            )

            legacy = autonomy["legacy_buddy_exception"]["workflow"]
            (root / legacy).write_text(
                f"""name: legacy
on:
  push:
    paths:
      - '{legacy}'
  workflow_dispatch:
jobs:
  repair:
    runs-on: ubuntu-24.04
    steps:
      - run: echo dominion-buddy-web.service dominion-proposal-queue.service dominion-sentinel.service
""",
                encoding="utf-8",
            )

            for relative in (
                observer["script"],
                observer["service_unit"],
                observer["timer_unit"],
                healer["script"],
                healer["service_unit"],
                healer["timer_unit"],
                autonomy["local_runtime_install"]["script"],
            ):
                source = ROOT / relative
                target = root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)

            self.assertEqual(autonomy_workflow_errors(root, candidate), [])

            (workflows / "rogue-schedule.yml").write_text(
                """name: rogue
on:
  schedule:
    - cron: '*/5 * * * *'
jobs:
  read:
    runs-on: ubuntu-latest
    steps:
      - run: echo read-only
""",
                encoding="utf-8",
            )
            errors = autonomy_workflow_errors(root, candidate)
            self.assertTrue(any(
                "GitHub-hosted schedule prohibited" in error
                for error in errors
            ), errors)


if __name__ == "__main__":
    unittest.main()
