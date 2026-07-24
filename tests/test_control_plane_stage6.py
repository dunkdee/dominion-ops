from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from control_plane.trial_capture import ingest_trial_capture, summarize_trial_completeness, validate_trial_capture_plan

ROOT = Path(__file__).resolve().parents[1]


class Stage6Fixture(unittest.TestCase):
    def setUp(self) -> None:
        self.plan = json.loads((ROOT / "runtime/plans/similarweb_7_day_capture.json").read_text(encoding="utf-8"))
        self.policy = json.loads((ROOT / "governance/similarweb_trial_capture_policy.json").read_text(encoding="utf-8"))
        self.snapshot = json.loads((ROOT / "runtime/examples/stage6_similarweb_export_fixture.json").read_text(encoding="utf-8"))


class ReadinessTests(Stage6Fixture):
    def test_plan_requires_human_target_review_before_activation(self) -> None:
        result = validate_trial_capture_plan(self.plan, self.policy)
        self.assertEqual(result["status"], "READY_FOR_HUMAN_TARGET_REVIEW")
        self.assertEqual(result["target_count"], 15)
        self.assertFalse(result["automated_platform_scraping_authorized"])
        self.assertFalse(result["trial_started"])

    def test_human_reviewed_plan_can_be_ready_without_starting_trial(self) -> None:
        plan = copy.deepcopy(self.plan)
        plan["human_target_review_completed"] = True
        result = validate_trial_capture_plan(plan, self.policy)
        self.assertEqual(result["status"], "READY_TO_ACTIVATE_TRIAL")
        self.assertFalse(result["trial_started"])
        self.assertEqual(result["external_actions"], [])

    def test_automated_platform_scraping_is_rejected(self) -> None:
        plan = copy.deepcopy(self.plan)
        plan["acquisition_methods"] = ["AUTOMATED_PLATFORM_SCRAPE"]
        result = validate_trial_capture_plan(plan, self.policy)
        self.assertEqual(result["status"], "HOLD")
        self.assertIn("prohibited_acquisition_method:AUTOMATED_PLATFORM_SCRAPE", result["errors"])

    def test_duplicate_target_domain_is_rejected(self) -> None:
        plan = copy.deepcopy(self.plan)
        plan["targets"][1]["domain"] = plan["targets"][0]["domain"]
        result = validate_trial_capture_plan(plan, self.policy)
        self.assertEqual(result["status"], "HOLD")
        self.assertTrue(any(item.startswith("duplicate_target_domain:") for item in result["errors"]))

    def test_billing_control_is_human_owned(self) -> None:
        plan = copy.deepcopy(self.plan)
        plan["billing_control"]["owner"] = "coordinator"
        result = validate_trial_capture_plan(plan, self.policy)
        self.assertEqual(result["status"], "HOLD")
        self.assertIn("billing_owner_must_be_human_overseer", result["errors"])


class IngestionTests(Stage6Fixture):
    def test_repository_fixture_is_test_only(self) -> None:
        result = ingest_trial_capture(plan=self.plan, policy=self.policy, snapshot=self.snapshot)
        self.assertEqual(result["status"], "TEST_ONLY")
        self.assertFalse(result["revenue_verified"])
        self.assertFalse(result["automated_platform_scraping_used"])
        self.assertEqual(result["external_actions"], [])

    def test_permitted_actual_export_is_accepted_as_estimated_signal_only(self) -> None:
        plan = copy.deepcopy(self.plan)
        plan["human_target_review_completed"] = True
        snapshot = copy.deepcopy(self.snapshot)
        snapshot.pop("test_fixture")
        snapshot["evidence"] = ["local-export:file-hash", "provider:similarweb", "period:2026-06"]
        result = ingest_trial_capture(plan=plan, policy=self.policy, snapshot=snapshot)
        self.assertEqual(result["status"], "ACCEPTED_ESTIMATED_SIGNAL")
        self.assertFalse(result["revenue_verified"])
        self.assertFalse(result["external_distribution_authorized"])

    def test_duplicate_capture_is_rejected(self) -> None:
        plan = copy.deepcopy(self.plan)
        plan["human_target_review_completed"] = True
        snapshot = copy.deepcopy(self.snapshot)
        snapshot.pop("test_fixture")
        first = ingest_trial_capture(plan=plan, policy=self.policy, snapshot=snapshot)
        second = ingest_trial_capture(plan=plan, policy=self.policy, snapshot=snapshot, existing_records=[first])
        self.assertEqual(second["status"], "HOLD")
        self.assertIn("duplicate_capture_rejected", second["errors"])

    def test_completeness_report_identifies_uncaptured_targets(self) -> None:
        plan = copy.deepcopy(self.plan)
        plan["human_target_review_completed"] = True
        snapshot = copy.deepcopy(self.snapshot)
        snapshot.pop("test_fixture")
        record = ingest_trial_capture(plan=plan, policy=self.policy, snapshot=snapshot)
        result = summarize_trial_completeness(plan, self.policy, [record])
        self.assertEqual(result["status"], "INCOMPLETE")
        self.assertEqual(result["accepted_target_count"], 1)
        self.assertEqual(len(result["missing_domains"]), 14)
        self.assertFalse(result["external_execution_authorized"])


if __name__ == "__main__":
    unittest.main()
