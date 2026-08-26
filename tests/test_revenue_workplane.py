from __future__ import annotations

import importlib.util
import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AUTOPILOT_DIR = ROOT / "scripts" / "autopilot"
if str(AUTOPILOT_DIR) not in sys.path:
    sys.path.insert(0, str(AUTOPILOT_DIR))

SPEC = importlib.util.spec_from_file_location(
    "revenue_workplane_supervisor",
    AUTOPILOT_DIR / "revenue_workplane_supervisor.py",
)
assert SPEC and SPEC.loader
workplane_supervisor = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(workplane_supervisor)


class RevenueWorkplaneTests(unittest.TestCase):
    def setUp(self):
        self.workplane = json.loads((ROOT / "governance" / "revenue_workplane.json").read_text(encoding="utf-8"))
        self.autopilot = json.loads((ROOT / "governance" / "radah_memshalah_autopilot_policy.json").read_text(encoding="utf-8"))

    def test_workplane_binds_live_canary_to_commerce(self):
        self.assertEqual(self.workplane["primary_lane"], "commerce_fulfillment")
        self.assertEqual(self.workplane["active_experiment"]["id"], "voltedge-speaker-offer-v1")
        self.assertEqual(
            self.workplane["active_experiment"]["route"],
            "https://dominionhealing.org/r/voltedge-speaker-offer-v1",
        )
        self.assertEqual(self.workplane["active_experiment"]["activation_evidence"]["workflow_run_id"], 32929081710)
        self.assertTrue(self.workplane["active_experiment"]["activation_evidence"]["public_route_verified"])
        self.assertEqual(self.workplane["active_experiment"]["synthetic_traffic_at_activation"], 0)

    def test_delegation_is_narrow_and_does_not_unlock_global_external_actions(self):
        delegated = self.autopilot["delegated_runtimes"]["dominion_revenue_runtime"]
        self.assertTrue(delegated["automatic_reversible_cro"])
        self.assertFalse(delegated["automatic_price_change"])
        self.assertFalse(delegated["automatic_paid_spend"])
        self.assertFalse(self.autopilot["rules"]["external_actions_automatic"])
        self.assertTrue(self.autopilot["rules"]["no_price_change"])
        self.assertEqual(delegated["primary_lane"], "commerce_fulfillment")
        self.assertIn("content_traffic", delegated["supporting_lanes"])

    def test_revenue_objectives_require_runtime_truth(self):
        objectives = self.autopilot["lane_objectives"]
        for lane in ("commerce_fulfillment", "content_traffic", "intelligence_orchestration", "infrastructure"):
            self.assertIn("REVENUE_WORKPLANE_SNAPSHOT", objectives[lane])
        self.assertIn("never invent metrics", objectives["commerce_fulfillment"].lower())
        self.assertIn("active experiment route", objectives["content_traffic"].lower())

    def test_snapshot_derives_traffic_constraint_from_real_ledger(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db_path = root / "revenue.db"
            with sqlite3.connect(db_path) as db:
                db.executescript(
                    """
                    CREATE TABLE experiments (
                        id TEXT PRIMARY KEY, status TEXT, winner TEXT, product_id TEXT,
                        target_url TEXT, success_event TEXT, treatment_pct INTEGER,
                        auto_promote INTEGER, activated_at TEXT, decided_at TEXT
                    );
                    CREATE TABLE events (
                        id TEXT PRIMARY KEY, experiment_id TEXT, visitor_id TEXT,
                        variant TEXT, event_type TEXT, revenue_cents INTEGER,
                        occurred_at TEXT, metadata_json TEXT
                    );
                    """
                )
                db.execute(
                    "INSERT INTO experiments VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (
                        "voltedge-speaker-offer-v1", "active", None, "p1",
                        "https://www.voltedgegoods.com/product-page/x", "purchase", 50,
                        1, "2026-08-26T04:08:36+00:00", None,
                    ),
                )
            workplane_path = root / "workplane.json"
            workplane_path.write_text(json.dumps({
                "runtime": {"database": str(db_path)},
                "active_experiment": {
                    "id": "voltedge-speaker-offer-v1",
                    "route": "https://dominionhealing.org/r/voltedge-speaker-offer-v1",
                },
            }), encoding="utf-8")

            original = workplane_supervisor.WORKPLANE_PATH
            try:
                workplane_supervisor.WORKPLANE_PATH = workplane_path
                snapshot = workplane_supervisor.load_revenue_snapshot()
            finally:
                workplane_supervisor.WORKPLANE_PATH = original

            self.assertTrue(snapshot["available"])
            self.assertEqual(snapshot["constraint"], "QUALIFIED_TRAFFIC")
            self.assertEqual(snapshot["totals"]["visitors"], 0)
            self.assertEqual(snapshot["totals"]["revenue_cents"], 0)
            self.assertFalse(snapshot["automatic_price_change"])
            self.assertFalse(snapshot["automatic_paid_spend"])

    def test_command_center_describes_real_work_plane_not_sales_claim(self):
        revenue = (ROOT / "obsidian" / "command-center" / "09-Revenue.md").read_text(encoding="utf-8")
        self.assertIn("Production Revenue Work Plane", revenue)
        self.assertIn("voltedge-speaker-offer-v1", revenue)
        self.assertIn("dominion-revenue-evaluator.timer", revenue)
        self.assertIn("zero synthetic traffic", revenue.lower())
        self.assertIn("not sales", revenue.lower())

    def test_installer_overrides_only_autopilot_execstart(self):
        installer = (ROOT / "scripts" / "autopilot" / "install_revenue_workplane.sh").read_text(encoding="utf-8")
        self.assertIn("revenue-workplane.conf", installer)
        self.assertIn("revenue_workplane_supervisor.py --execute", installer)
        self.assertIn("dominion-revenue-runtime.service", installer)
        self.assertIn("dominion-revenue-evaluator.timer", installer)
        self.assertNotIn("systemctl restart dominion-revenue-runtime.service", installer)
        self.assertNotIn("systemctl restart dominion-radah-autopilot.timer", installer)


if __name__ == "__main__":
    unittest.main()
