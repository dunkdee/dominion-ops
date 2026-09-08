from __future__ import annotations

import importlib.util
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
BRIDGE = ROOT / "scripts/command_center_state_bridge_v3.py"
INSTALL = ROOT / "scripts/install_command_center_state_bridge.sh"
COMMAND_DEPLOY = ROOT / ".github/workflows/deploy-dominion-command-center.yml"
PUBLISHER_DEPLOY = ROOT / ".github/workflows/deploy-dominion-publisher.yml"

spec = importlib.util.spec_from_file_location("command_center_state_bridge_v3", BRIDGE)
assert spec and spec.loader
bridge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)


class CommandCenterPublisherConvergenceTests(unittest.TestCase):
    def test_publisher_ledger_reads_queue_and_receipts_without_mutation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db_path = root / "publisher/dominion_publisher.db"
            db_path.parent.mkdir(parents=True)
            db = sqlite3.connect(db_path)
            db.executescript(
                """
                CREATE TABLE jobs (
                    idempotency_key TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE receipts (
                    receipt_id TEXT PRIMARY KEY,
                    idempotency_key TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                INSERT INTO jobs VALUES
                  ('a','{}','QUEUED','2026-09-07T00:00:00Z','2026-09-07T00:00:00Z'),
                  ('b','{}','PUBLISHED','2026-09-07T00:00:00Z','2026-09-07T00:00:00Z'),
                  ('c','{}','FAILED','2026-09-07T00:00:00Z','2026-09-07T00:00:00Z');
                INSERT INTO receipts VALUES
                  ('r1','a','{}','2026-09-07T00:01:00Z'),
                  ('r2','b','{}','2026-09-07T00:02:00Z');
                """
            )
            db.commit()
            db.close()

            state = bridge._publisher_ledger(root)
            self.assertTrue(state["connected"])
            self.assertEqual(state["jobs_total"], 3)
            self.assertEqual(state["queued"], 1)
            self.assertEqual(state["published"], 1)
            self.assertEqual(state["failed"], 1)
            self.assertEqual(state["blocked"], 0)
            self.assertEqual(state["receipts_total"], 2)
            self.assertEqual(state["latest_receipt_at"], "2026-09-07T00:02:00Z")

    def test_publisher_phase_is_truthful_and_canary_requires_published_receipt(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            health = {
                "ok": True,
                "status": 200,
                "service": "dominion-publisher",
                "operator_gate_configured": True,
                "meta_app_configured": True,
                "meta_token_configured": True,
                "meta_graph_version_configured": True,
                "meta_bound_counts": {"facebook": 1, "instagram": 1},
                "platforms": ["facebook", "instagram"],
            }
            ledger = {
                "connected": True,
                "jobs_total": 0,
                "queued": 0,
                "published": 0,
                "failed": 0,
                "blocked": 0,
                "receipts_total": 0,
                "latest_receipt_at": None,
            }
            with patch.object(bridge, "_publisher_health", return_value=health), patch.object(
                bridge, "_publisher_ledger", return_value=ledger
            ):
                state = bridge._publisher_state(root)
            self.assertEqual(state["phase"], "BOUND_AWAITING_CONTROLLED_CANARY")
            self.assertFalse(state["canary_proven"])

            ledger["published"] = 1
            ledger["receipts_total"] = 1
            with patch.object(bridge, "_publisher_health", return_value=health), patch.object(
                bridge, "_publisher_ledger", return_value=ledger
            ):
                state = bridge._publisher_state(root)
            self.assertEqual(state["phase"], "PUBLISHING_PROVEN")
            self.assertTrue(state["canary_proven"])

    def test_command_center_acceptance_requires_publisher_truth(self):
        install = INSTALL.read_text(encoding="utf-8")
        self.assertIn("s['systems']['dominion_publisher']['ok'] is True", install)
        self.assertIn("s['systems']['publisher_queue_ledger']['ok'] is True", install)
        self.assertIn("p['ledger']['connected'] is True", install)
        self.assertIn("publisher_phase=", install)

        workflow = COMMAND_DEPLOY.read_text(encoding="utf-8")
        self.assertIn("github.event_name == 'push'", workflow)
        self.assertIn("scripts/command_center_state_bridge_v3.py", workflow)
        self.assertIn("s['systems']['dominion_publisher']=='online'", workflow)
        self.assertIn("publisher_controlled_publish", workflow)
        self.assertIn("DOMINION_PUBLISHER_COMMAND_CENTER=PASS", workflow)

    def test_publisher_release_auto_converges_but_meta_binding_stays_separate(self):
        workflow = PUBLISHER_DEPLOY.read_text(encoding="utf-8")
        self.assertIn("github.event_name == 'push'", workflow)
        self.assertIn("apps/dominion_publisher/**", workflow)
        self.assertIn("scripts/dominion_publisher/**", workflow)
        self.assertIn("foundation-vm-production", workflow)
        self.assertIn("DOMINION_PUBLISHER_DEPLOY=PASS", workflow)
        self.assertNotIn("BIND META PAGE", workflow)
        self.assertNotIn("META_APP_SECRET", workflow)


if __name__ == "__main__":
    unittest.main()
