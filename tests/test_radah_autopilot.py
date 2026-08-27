from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "autopilot" / "lane_supervisor.py"
INSTALLER_PATH = ROOT / "scripts" / "autopilot" / "install_autopilot.sh"
ACTIVATION_WORKFLOW_PATH = ROOT / ".github" / "workflows" / "activate-radah-memshalah-autopilot.yml"
COMPLETED_CLOSURE_WORKFLOW_PATH = ROOT / ".github" / "workflows" / "authorized-entire-production-closure-20260826.yml"
spec = importlib.util.spec_from_file_location("lane_supervisor", MODULE_PATH)
assert spec and spec.loader
lane_supervisor = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = lane_supervisor
spec.loader.exec_module(lane_supervisor)


class FakeOperator:
    def __init__(self):
        self.capabilities = {
            "brain.reason": {"auth_required": False, "classification": "internal"},
            "artifact.stage": {"auth_required": False, "classification": "internal"},
            "external.publish": {"auth_required": True, "classification": "privileged_write"},
            "unsafe.write": {"auth_required": False, "classification": "internal"},
        }


class RadahAutopilotTests(unittest.TestCase):
    def setUp(self):
        self.policy = lane_supervisor.load_json(ROOT / "governance" / "radah_memshalah_autopilot_policy.json")
        self.verticals = lane_supervisor.load_json(ROOT / "governance" / "verticals.json")

    def test_completed_one_time_production_trigger_is_absent(self):
        self.assertFalse(COMPLETED_CLOSURE_WORKFLOW_PATH.exists())

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
            ]}, op, self.policy,
        )
        with self.assertRaises(lane_supervisor.AutopilotError):
            lane_supervisor.validate_plan(
                {"steps": [{"capability": "unsafe.write", "instruction": "mutate"}]}, op, self.policy
            )

    def test_external_capability_must_be_founder_held(self):
        op = FakeOperator()
        op.capabilities["external.publish"] = {"auth_required": False, "classification": "internal"}
        with self.assertRaises(lane_supervisor.AutopilotError):
            lane_supervisor.validate_plan(
                {"steps": [{"capability": "external.publish", "instruction": "publish"}]}, op, self.policy
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
            self.assertTrue(lane_supervisor.bounded_cycle_ok(receipt))
            self.assertFalse(receipt["external_actions_authorized"])
            self.assertFalse((root / "state.json").exists())
            self.assertFalse((root / "receipts").exists())

    def test_governed_blocked_cycle_is_healthy_scheduler_progress(self):
        receipt = {
            "schema": "radah-autopilot-receipt-v1", "lane": "analytics_services",
            "status": "BLOCKED", "mission_id": "mission_test", "external_actions_authorized": False,
            "receipts": [{"capability": "revenue.prepare", "status": "BLOCKED", "hold_code": "CURRENT_AUTHORITY_UNAVAILABLE"}],
        }
        self.assertTrue(lane_supervisor.bounded_cycle_ok(receipt))

    def test_supervisor_failure_cannot_masquerade_as_healthy_blocker(self):
        receipt = {
            "schema": "radah-autopilot-receipt-v1", "lane": "analytics_services",
            "status": "BLOCKED", "mission_id": None, "external_actions_authorized": False,
            "receipts": [], "supervisor_error": {"type": "ImportError", "detail": "missing runtime"},
        }
        self.assertFalse(lane_supervisor.bounded_cycle_ok(receipt))

    def test_blocked_receipt_updates_rotation_state(self):
        lanes = lane_supervisor.validate_policy(self.policy, self.verticals)
        lane = lanes[0]
        now = datetime.now(timezone.utc)
        with tempfile.TemporaryDirectory() as tmp:
            state_dir = Path(tmp)
            state = {"schema": "radah-autopilot-state-v1", "lanes": {}, "cycles": 0}
            receipt = {
                "schema": "radah-autopilot-receipt-v1", "lane": lane.lane_id, "status": "BLOCKED",
                "mission_id": "mission_blocked", "external_actions_authorized": False,
                "receipts": [{"capability": "revenue.prepare", "status": "BLOCKED"}],
            }
            lane_supervisor.persist_cycle(state_dir=state_dir, state=state, lane=lane, receipt=receipt, now=now)
            saved = lane_supervisor.load_state(state_dir / "state.json")
            self.assertEqual(saved["cycles"], 1)
            self.assertEqual(saved["lanes"][lane.lane_id]["last_status"], "BLOCKED")
            self.assertEqual(saved["lanes"][lane.lane_id]["last_attempt_at"], now.isoformat())
            self.assertEqual(saved["lanes"][lane.lane_id]["last_progress_at"], now.isoformat())

    def test_installer_reuses_proven_buddy_python_runtime(self):
        installer = INSTALLER_PATH.read_text(encoding="utf-8")
        self.assertIn("systemctl show dominion-buddy-web.service -p ExecStart --value", installer)
        self.assertIn("BUDDY_RUNTIME_IMPORT=PASS", installer)
        self.assertIn("ExecStart=$buddy_python", installer)
        self.assertNotIn("ExecStart=/usr/bin/python3", installer)
        self.assertIn("ConditionPathExists=$buddy_python", installer)

    def test_activation_bundle_contains_every_layered_runtime_dependency(self):
        workflow = ACTIVATION_WORKFLOW_PATH.read_text(encoding="utf-8")
        required = (
            "scripts/autopilot/revenue_workplane_supervisor.py",
            "scripts/autopilot/multilane_supervisor.py",
            "scripts/autopilot/control_plane_guard.py",
            "governance/SYSTEM_CONSTITUTION.md",
            "governance/authority_matrix.json",
            "governance/five_council_policy.json",
            "governance/incident_learning_policy.json",
            "governance/legal_evidence_policy.json",
            "governance/constitutional_amendment_policy.json",
            "governance/revenue_workplane.json",
            "governance/lane_access_policy.json",
            "governance/lane_runtime_contracts.json",
            "governance/profitability_lane_contracts.json",
            "agents/registry.json",
        )
        for path in required:
            self.assertIn(path, workflow, path)

    def test_installer_preserves_known_layered_execstart_dependencies_atomically(self):
        installer = INSTALLER_PATH.read_text(encoding="utf-8")
        self.assertIn('systemctl cat "$service_name"', installer)
        self.assertIn('systemctl show "$service_name" -p ExecStart --value', installer)
        self.assertIn("AUTOPILOT_EFFECTIVE_OVERLAY=DETECTED", installer)
        self.assertIn("overlay_mode=\"multilane\"", installer)
        self.assertIn("overlay_mode=\"revenue\"", installer)
        self.assertIn("unknown_effective_execstart", installer)
        self.assertIn("effective_execstart_unresolved", installer)
        self.assertIn("scripts/autopilot/revenue_workplane_supervisor.py", installer)
        self.assertIn("scripts/autopilot/multilane_supervisor.py", installer)
        self.assertIn("scripts/autopilot/control_plane_guard.py", installer)
        self.assertIn("governance/SYSTEM_CONSTITUTION.md", installer)
        self.assertIn("governance/lane_runtime_contracts.json", installer)
        self.assertIn("governance/profitability_lane_contracts.json", installer)
        self.assertIn("agents/registry.json", installer)
        self.assertIn("AUTOPILOT_LAYERED_OVERLAY=PRESERVED", installer)
        self.assertIn("expected_entrypoint=", installer)
        self.assertIn('grep -Fq "$expected_entrypoint"', installer)
        self.assertIn("AUTOPILOT_EFFECTIVE_ENTRYPOINT=PASS", installer)
        self.assertIn("AUTOPILOT_LAYERED_MIGRATION=PASS", installer)

    def test_installer_latest_receipt_selection_is_pipefail_safe(self):
        installer = INSTALLER_PATH.read_text(encoding="utf-8")
        self.assertIn("sort -nr | sed -n '1p' | cut", installer)
        self.assertNotIn("sort -nr | head -1 | cut", installer)

    def test_installer_validates_multilane_overlay_as_multilane_not_single_lane(self):
        installer = INSTALLER_PATH.read_text(encoding="utf-8")
        self.assertIn("validate_latest_multilane_sweep", installer)
        self.assertIn("AUTOPILOT_LAYERED_MULTILANE_SMOKE=PASS", installer)
        self.assertIn("constitutional.get('human_final_authority') == 'human_overseer'", installer)
        self.assertIn("cycles_before + selected_count", installer)

    def test_installer_proves_governed_blocker_rotation_before_timer(self):
        installer = INSTALLER_PATH.read_text(encoding="utf-8")
        self.assertIn("AUTOPILOT_FIRST_CYCLE=PASS", installer)
        self.assertIn("AUTOPILOT_BLOCKED_ROTATION=PASS", installer)
        self.assertIn("if [ \"$first_status\" = \"BLOCKED\" ]", installer)
        self.assertIn("assert not p.get('supervisor_error')", installer)
        self.assertIn("assert p.get('mission_id')", installer)
        self.assertIn("assert not not_lane or lane != not_lane", installer)
        self.assertIn("AUTOPILOT_TIMER=PASS cadence=30m", installer)


if __name__ == "__main__":
    unittest.main()
