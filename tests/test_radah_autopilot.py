from __future__ import annotations

import importlib.util
import json
import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "autopilot" / "lane_supervisor.py"
spec = importlib.util.spec_from_file_location("lane_supervisor", MODULE_PATH)
assert spec and spec.loader
lane_supervisor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lane_supervisor)


class FakeOperator:
    def __init__(self):
        self.capabilities = {
            "brain.reason": {
                "auth_required": False,
                "classification": "internal",
            },
            "artifact.stage": {
                "auth_required": False,
                "classification": "internal",
            },
            "external.publish": {
                "auth_required": True,
                "classification": "privileged_write",
            },
            "unsafe.write": {
                "auth_required": False,
                "classification": "internal",
            },
        }


class RadahAutopilotTests(unittest.TestCase):
    def setUp(self):
        self.policy = lane_supervisor.load_json(ROOT / "governance" / "radah_memshalah_autopilot_policy.json")
        self.verticals = lane_supervisor.load_json(ROOT / "governance" / "verticals.json")

    def test_policy_covers_every_registered_lane_exactly_once(self):
        lanes = lane_supervisor.validate_policy(self.policy, self.verticals)
        registry_ids = {row["id"] for row in self.verticals["verticals"]}
        self.assertEqual({lane.lane_id for lane in lanes}, registry_ids)
        self.assertEqual(len(self.policy["primary_wave"]), 2)
        self.assertEqual(len(set(self.policy["primary_wave"])), 2)

    def test_all_lanes_have_real_internal_objectives(self):
        lanes = lane_supervisor.validate_policy(self.policy, self.verticals)
        for lane in lanes:
            self.assertGreater(len(lane.objective.strip()), 80, lane.lane_id)
        self.assertTrue(self.policy["all_lanes_must_progress"])
        self.assertFalse(self.policy["rules"]["external_actions_automatic"])
        self.assertTrue(self.policy["rules"]["no_live_trading"])

    def test_unseen_primary_lane_is_selected_before_standard_lane(self):
        lanes = lane_supervisor.validate_policy(self.policy, self.verticals)
        selected = lane_supervisor.select_lane(
            lanes,
            {"schema": "radah-autopilot-state-v1", "lanes": {}, "cycles": 0},
            datetime.now(timezone.utc),
        )
        self.assertIn(selected.lane_id, self.policy["primary_wave"])

    def test_recent_attempt_prevents_blocked_lane_starvation(self):
        lanes = lane_supervisor.validate_policy(self.policy, self.verticals)
        now = datetime.now(timezone.utc)
        first = lane_supervisor.select_lane(
            lanes,
            {"schema": "radah-autopilot-state-v1", "lanes": {}, "cycles": 0},
            now,
        )
        state = {
            "schema": "radah-autopilot-state-v1",
            "cycles": 1,
            "lanes": {first.lane_id: {"last_attempt_at": now.isoformat(), "last_status": "BLOCKED"}},
        }
        second = lane_supervisor.select_lane(lanes, state, now)
        self.assertNotEqual(first.lane_id, second.lane_id)

    def test_plan_accepts_only_allowlisted_internal_or_held_external_capabilities(self):
        op = FakeOperator()
        lane_supervisor.validate_plan(
            {"steps": [
                {"capability": "brain.reason", "instruction": "analyze"},
                {"capability": "artifact.stage", "instruction": "stage"},
                {"capability": "external.publish", "instruction": "publish"},
            ]},
            op,
            self.policy,
        )

        with self.assertRaises(lane_supervisor.AutopilotError):
            lane_supervisor.validate_plan(
                {"steps": [{"capability": "unsafe.write", "instruction": "mutate"}]},
                op,
                self.policy,
            )

    def test_external_capability_must_be_founder_held(self):
        op = FakeOperator()
        op.capabilities["external.publish"] = {
            "auth_required": False,
            "classification": "internal",
        }
        with self.assertRaises(lane_supervisor.AutopilotError):
            lane_supervisor.validate_plan(
                {"steps": [{"capability": "external.publish", "instruction": "publish"}]},
                op,
                self.policy,
            )

    def test_execute_fails_closed_without_runtime_activation(self):
        old = os.environ.pop("RADAH_AUTOPILOT_ENABLED", None)
        try:
            with tempfile.TemporaryDirectory() as tmp:
                with self.assertRaises(lane_supervisor.AutopilotError):
                    lane_supervisor.run_cycle(execute=True, state_dir=Path(tmp))
        finally:
            if old is not None:
                os.environ["RADAH_AUTOPILOT_ENABLED"] = old

    def test_plan_only_is_side_effect_free(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            receipt = lane_supervisor.run_cycle(execute=False, state_dir=root)
            self.assertEqual(receipt["status"], "PLANNED")
            self.assertFalse(receipt["external_actions_authorized"])
            self.assertFalse((root / "state.json").exists())
            self.assertFalse((root / "receipts").exists())


if __name__ == "__main__":
    unittest.main()
