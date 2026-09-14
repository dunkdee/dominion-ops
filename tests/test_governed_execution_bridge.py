import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "autopilot" / "governed_execution_bridge.py"
AUTOPILOT_DIR = str(ROOT / "scripts" / "autopilot")


def load_bridge():
    import sys
    if AUTOPILOT_DIR not in sys.path:
        sys.path.insert(0, AUTOPILOT_DIR)
    spec = importlib.util.spec_from_file_location("governed_execution_bridge", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


bridge = load_bridge()


class FakeLedger:
    def __init__(self, records):
        self.records = records

    def load(self, approval_id):
        return self.records.get(approval_id)


class FakeOperator:
    def __init__(self, held_dir, records, result=None):
        self.held_dir = Path(held_dir)
        self._ledger = FakeLedger(records)
        self.executed = []
        self.result = result or {
            "status": "COMPLETE",
            "mission_id": "mission-1",
            "receipts": [{"step": 1, "status": "VERIFIED"}],
            "held": None,
        }

    def execute(self, plan, session_id="default"):
        self.executed.append((plan, session_id))
        return dict(self.result)


def write_hold(root, approval_id="approval_123456abcdef", payload_hash="a" * 64):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    payload = {
        "approval_id": approval_id,
        "payload_hash": payload_hash,
        "step_index": 1,
        "session_id": "autopilot:commerce",
        "plan": {
            "mission_id": "mission-1",
            "objective": "bounded mission",
            "steps": [{"capability": "external.message", "instruction": "send exact message"}],
        },
    }
    (root / f"{approval_id}.json").write_text(json.dumps(payload), encoding="utf-8")
    return payload


class GovernedExecutionBridgeTests(unittest.TestCase):
    def test_source_has_no_authority_grant_path(self):
        text = MODULE_PATH.read_text(encoding="utf-8")
        self.assertNotIn(".grant(", text)
        self.assertNotIn("grant_and_resume", text)
        self.assertIn("authority_granted_by_bridge", text)
        self.assertIn("GRANTED", text)

    def test_plan_only_is_inert(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = bridge.run_bridge_cycle(execute=False, state_dir=Path(tmp))
            self.assertEqual(result["status"], "PLANNED")
            self.assertFalse(result["authority_granted_by_bridge"])
            self.assertFalse((Path(tmp) / "bridge-receipts").exists())

    def test_granted_exact_hold_resumes_without_granting(self):
        with tempfile.TemporaryDirectory() as tmp:
            held = Path(tmp) / "held"
            payload = write_hold(held)
            authority = {
                "status": "GRANTED",
                "payload_hash": payload["payload_hash"],
                "authorization_sequence": 7,
            }
            operator = FakeOperator(held, {payload["approval_id"]: authority})
            with mock.patch.object(bridge.base, "enabled_by_environment", return_value=True), \
                 mock.patch.object(bridge.base, "resolve_buddy_operator", return_value=operator), \
                 mock.patch.object(bridge.base, "run_cycle") as run_cycle:
                result = bridge.run_bridge_cycle(execute=True, state_dir=Path(tmp) / "state")

            self.assertEqual(result["action"], "RESUME_GRANTED_HOLD")
            self.assertEqual(result["status"], "COMPLETE")
            self.assertFalse(result["authority_granted_by_bridge"])
            self.assertEqual(len(operator.executed), 1)
            resumed_plan = operator.executed[0][0]
            self.assertEqual(
                resumed_plan["steps"][0]["authorization_id"],
                payload["approval_id"],
            )
            run_cycle.assert_not_called()

    def test_pending_hold_does_not_resume_and_normal_cycle_runs(self):
        with tempfile.TemporaryDirectory() as tmp:
            held = Path(tmp) / "held"
            payload = write_hold(held)
            authority = {"status": "PENDING", "payload_hash": payload["payload_hash"]}
            operator = FakeOperator(held, {payload["approval_id"]: authority})
            bounded = {"status": "COMPLETE", "mission_id": "mission-2", "receipts": []}
            with mock.patch.object(bridge.base, "enabled_by_environment", return_value=True), \
                 mock.patch.object(bridge.base, "resolve_buddy_operator", return_value=operator), \
                 mock.patch.object(bridge.base, "run_cycle", return_value=bounded) as run_cycle:
                result = bridge.run_bridge_cycle(execute=True, state_dir=Path(tmp) / "state")

            self.assertEqual(result["action"], "RUN_BOUNDED_LANE_CYCLE")
            self.assertFalse(operator.executed)
            run_cycle.assert_called_once()

    def test_payload_mismatch_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            held = Path(tmp) / "held"
            payload = write_hold(held)
            authority = {"status": "GRANTED", "payload_hash": "b" * 64}
            operator = FakeOperator(held, {payload["approval_id"]: authority})
            with self.assertRaises(bridge.BridgeError):
                bridge._candidate(operator)


if __name__ == "__main__":
    unittest.main()
