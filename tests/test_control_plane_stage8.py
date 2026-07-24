from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from control_plane.canonical import sha256_json
from control_plane.final_release import evaluate_final_release

ROOT = Path(__file__).resolve().parents[1]
RECORDS = ROOT / "runtime" / "records" / "stage8" / "similarweb_target_approval"


def load(path: Path | str) -> dict:
    target = path if isinstance(path, Path) else ROOT / path
    return json.loads(target.read_text(encoding="utf-8"))


def load_reviews() -> list[dict]:
    return [load(path) for path in sorted((RECORDS / "reviews").glob("*.json"))]


def rehash(record: dict, field: str) -> None:
    record[field] = sha256_json({key: value for key, value in record.items() if key != field})


class Stage8FinalReleaseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.request = load(RECORDS / "release_request.json")
        self.human = load("governance/approvals/similarweb_target_manifest_approval.json")
        self.reviews = load_reviews()
        self.policy = load("governance/final_release_policy.json")
        self.council = load("governance/five_council_policy.json")
        self.gates = load("governance/runtime_activation_gates.json")

    def evaluate(self, reviews: list[dict] | None = None) -> dict:
        return evaluate_final_release(
            release_request=self.request,
            human_authorization=self.human,
            council_reviews=self.reviews if reviews is None else reviews,
            final_release_policy=self.policy,
            council_policy=self.council,
            activation_gates=self.gates,
        )

    def test_five_council_is_last_affirmative_gate(self) -> None:
        self.assertEqual(
            self.policy["release_sequence"],
            [
                "technical_readiness_verified",
                "human_scope_authorization_recorded",
                "five_council_independent_final_review",
                "release_within_approved_scope",
            ],
        )
        self.assertEqual(self.policy["final_affirmative_gate"], "five_council")
        self.assertFalse(self.policy["human_authority"]["post_council_affirmative_click_required"])
        self.assertTrue(self.policy["human_authority"]["may_revoke_or_emergency_stop_at_any_time"])

    def test_target_manifest_final_decision_is_reproducible(self) -> None:
        result = self.evaluate()
        stored = load(RECORDS / "final_decision.json")
        self.assertEqual(result, stored)
        self.assertEqual(result["decision"], "FINAL_RELEASE_APPROVED")
        self.assertEqual(len(result["approvals"]), 5)
        self.assertFalse(result["trial_activation_authorized"])
        self.assertFalse(result["external_execution_authorized"])

    def test_missing_council_review_holds_release(self) -> None:
        result = self.evaluate(self.reviews[:-1])
        self.assertEqual(result["decision"], "HOLD")
        self.assertIn("missing_council_reviews", result["errors"])
        self.assertIn("unanimous_council_approval_not_met", result["errors"])

    def test_veto_blocks_release(self) -> None:
        reviews = copy.deepcopy(self.reviews)
        security = next(item for item in reviews if item["council_id"] == "security_risk")
        security["decision"] = "VETO"
        rehash(security, "review_hash")
        result = self.evaluate(reviews)
        self.assertEqual(result["decision"], "VETO")
        self.assertIn("security_risk", result["vetoes"])
        self.assertFalse(result["external_execution_authorized"])

    def test_council_review_before_human_authorization_holds(self) -> None:
        reviews = copy.deepcopy(self.reviews)
        reviews[0]["review_sequence"] = 1
        rehash(reviews[0], "review_hash")
        result = self.evaluate(reviews)
        self.assertEqual(result["decision"], "HOLD")
        self.assertTrue(any(item.startswith("review_not_after_human_authorization:") for item in result["errors"]))

    def test_target_manifest_is_approved_but_trial_is_not_started(self) -> None:
        plan = load("runtime/plans/similarweb_7_day_capture.json")
        self.assertTrue(plan["human_target_review_completed"])
        self.assertEqual(plan["activation_status"], "NOT_STARTED")
        self.assertTrue(self.gates["similarweb_target_manifest_approved"])
        self.assertFalse(self.gates["similarweb_trial_activation_enabled"])
        self.assertIn("trial_activation_without_new_final_five_council_release", self.gates["blocked_capabilities"])

    def test_kdp_inventory_records_two_live_paperbacks_without_revenue_claim(self) -> None:
        inventory = load("revenue/kdp/title_inventory.json")
        self.assertEqual(inventory["inventory_status"], "VISUALLY_VERIFIED_PARTIAL")
        self.assertEqual(inventory["coverage_status"], "PARTIAL_ACCOUNT_VIEW")
        self.assertEqual([item["title"] for item in inventory["titles"]], [
            "Shadow Hearts",
            "Rising Above the Storms: A Road to Mental Wellness",
        ])
        self.assertTrue(all(item["listing_status"] == "LIVE" for item in inventory["titles"]))
        self.assertTrue(all(item["price"] == "14.99" for item in inventory["titles"]))
        self.assertFalse(inventory["revenue_verified"])
        self.assertTrue(all(item["rights_status"] == "UNVERIFIED" for item in inventory["titles"]))

    def test_runtime_remains_shadow_only(self) -> None:
        self.assertEqual(self.gates["stage"], 8)
        self.assertEqual(self.gates["mode"], "shadow_only")
        self.assertFalse(self.gates["external_execution_enabled"])
        self.assertEqual(self.gates["final_release_gate"], "FIVE_COUNCIL_UNANIMOUS_AFTER_HUMAN_SCOPE_AUTHORIZATION")


if __name__ == "__main__":
    unittest.main()
