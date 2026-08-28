from __future__ import annotations

import importlib.util
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BRIDGE_PATH = ROOT / "scripts/command_center_state_bridge_v2.py"
BRIDGE_V3_PATH = ROOT / "scripts/command_center_state_bridge_v3.py"
DOCKERFILE = ROOT / "apps/command-center/Dockerfile"
COMPOSE = ROOT / "docker-compose.command-center.yml"
APP = ROOT / "apps/command-center/app.py"
INTELLIGENCE = ROOT / "apps/command-center/intelligence.py"
ENV_EXAMPLE = ROOT / "config/command-center.env.example"
INDEX = ROOT / "apps/command-center/index.html"
REVENUE = ROOT / "apps/command-center/revenue.py"
DEPLOY = ROOT / "scripts/deploy_command_center.sh"
INSTALL = ROOT / "scripts/install_command_center_state_bridge.sh"
MCP_INSTALL = ROOT / "scripts/install_mcp_cli_server.sh"

spec = importlib.util.spec_from_file_location("command_center_state_bridge_v2", BRIDGE_PATH)
assert spec and spec.loader
bridge = importlib.util.module_from_spec(spec); spec.loader.exec_module(bridge)


class CommandCenterLiveTruthTests(unittest.TestCase):
    def test_lane_policy_is_exactly_11_open_scheduler_eligible(self):
        lanes, holds = bridge.lane_state(ROOT)
        self.assertTrue(lanes["connected"]); self.assertEqual(lanes["registered"], 11); self.assertEqual(lanes["open"], 11); self.assertTrue(lanes["all_open"])
        self.assertTrue(all(x["internal_work_open"] and x["scheduler_eligible"] for x in lanes["items"])); self.assertGreaterEqual(len(holds), 5)

    def test_revenue_snapshot_reads_real_ledger_shape_without_fabrication(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "revenue.db"; db = sqlite3.connect(db_path)
            db.executescript("""
            CREATE TABLE experiments (id TEXT PRIMARY KEY,name TEXT NOT NULL,product_id TEXT NOT NULL,target_url TEXT NOT NULL,status TEXT NOT NULL,winner TEXT,activated_at TEXT,decided_at TEXT,created_at TEXT NOT NULL);
            CREATE TABLE events (id TEXT PRIMARY KEY,experiment_id TEXT NOT NULL,visitor_id TEXT NOT NULL,variant TEXT NOT NULL,event_type TEXT NOT NULL,revenue_cents INTEGER NOT NULL DEFAULT 0);
            INSERT INTO experiments VALUES ('e1','Speaker Offer','p1','https://www.voltedgegoods.com/product-page/test','active',NULL,'2026-08-26T00:00:00+00:00',NULL,'2026-08-26T00:00:00+00:00');
            INSERT INTO events VALUES ('i1','e1','v1','control','impression',0),('c1','e1','v1','control','click',0),('p1','e1','v1','control','purchase',2999);
            """); db.commit(); db.close()
            state = bridge.revenue_state(db_path)
            self.assertTrue(state["connected"]); self.assertEqual(state["active_experiment_count"], 1)
            self.assertEqual(state["totals"], {"visitors": 1, "clicks": 1, "purchases": 1, "revenue_cents": 2999}); self.assertEqual(state["constraint"], "STATISTICAL_EVIDENCE")

    def test_missing_revenue_ledger_is_unavailable_not_zero(self):
        state = bridge.revenue_state(Path("/definitely/not/a/revenue.db"))
        self.assertFalse(state["connected"]); self.assertEqual(state["constraint"], "REVENUE_RUNTIME_UNAVAILABLE"); self.assertIsNone(state["totals"]["visitors"]); self.assertIsNone(state["totals"]["revenue_cents"])

    def test_receipt_index_scans_all_governed_receipt_trees_without_bodies(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for rel in ("autopilot/receipts/a.json", "revenue-runtime/receipts/r.json", "command-center/receipts/c.json", "mcp-cli/receipts/m.json"):
                path = root / rel; path.parent.mkdir(parents=True, exist_ok=True); path.write_text('{"secret":"must-not-be-indexed"}', encoding="utf-8")
            receipts = bridge.receipt_index(root, limit=10)
            self.assertEqual(len(receipts), 4); self.assertTrue(all(set(item) == {"source", "name", "observed_at"} for item in receipts)); self.assertNotIn("secret", json.dumps(receipts))

    def test_docker_image_packages_every_app_import(self):
        text = DOCKERFILE.read_text(encoding="utf-8")
        self.assertIn("COPY app.py intelligence.py revenue.py runtime_state.py index.html ./", text); self.assertIn("import app, intelligence, revenue, runtime_state", text)

    def test_compose_mounts_canonical_runtime_snapshot(self):
        text = COMPOSE.read_text(encoding="utf-8")
        self.assertIn("COMMAND_CENTER_RUNTIME_DIR", text); self.assertIn("/runtime:ro", text); self.assertIn("RUNTIME_STATE_PATH: /runtime/runtime-state.json", text); self.assertNotIn("CHECKOUT_ART_OF_TRUE_HEALING", text)

    def test_intelligence_fallback_is_authenticated_buddy_operator_and_private_loopback(self):
        compose = COMPOSE.read_text(encoding="utf-8")
        intelligence = INTELLIGENCE.read_text(encoding="utf-8")
        env_example = ENV_EXAMPLE.read_text(encoding="utf-8")
        self.assertIn("network_mode: host", compose)
        self.assertIn('["uvicorn", "app:app", "--host", "127.0.0.1", "--port", "8091"]', compose)
        self.assertNotIn("ports:\n", compose)
        self.assertIn("BUDDY_FALLBACK_URL: http://127.0.0.1:5070", compose)
        self.assertIn("BUDDY_FALLBACK_TOKEN_FILE: /run/secrets/buddy_web_token", compose)
        self.assertIn("buddy_web_token", compose)
        self.assertNotIn("BUDDY_WEB_TOKEN:", compose)
        self.assertNotIn("CONDUCTOR_URL:", compose)
        self.assertIn("def call_buddy_operator", intelligence)
        self.assertIn('f"{cfg.buddy_fallback_url}/buddy/api/chat"', intelligence)
        self.assertIn('headers = {"Authorization": f"Bearer {token}"}', intelligence)
        self.assertIn('"source": "buddy_operator"', intelligence)
        self.assertNotIn('for endpoint in ("/chat", "/api/chat")', intelligence)
        self.assertNotIn('"/invoke"', intelligence)
        self.assertNotIn('"/execute-next"', intelligence)
        self.assertIn("NEMOTRON_BASE_URL=\n", env_example)
        self.assertIn("Recovery hold", env_example)
        self.assertIn("BUDDY_FALLBACK_URL=http://127.0.0.1:5070", env_example)
        self.assertIn("Conductor remains the execution/orchestration service", env_example)

    def test_api_has_no_hardcoded_sprint_revenue_or_traffic(self):
        text = APP.read_text(encoding="utf-8")
        self.assertIn("canonical_runtime_state", text); self.assertIn('metrics.get("revenue_usd")', text); self.assertIn('metrics.get("visitors")', text)
        self.assertNotIn('"revenue": 0', text); self.assertNotIn('"traffic": 0', text)

    def test_vault_prefix_route_and_same_origin_api_survive(self):
        app = APP.read_text(encoding="utf-8"); index = INDEX.read_text(encoding="utf-8")
        self.assertIn("x-forwarded-prefix", app); self.assertIn("const API_BASE=", app); self.assertIn("fetch(API_BASE+'/api/status'", app); self.assertIn("fetch('/api/status'", index)

    def test_revenue_module_uses_live_runtime_not_legacy_offer_catalog(self):
        text = REVENUE.read_text(encoding="utf-8")
        self.assertIn('"vertical": "voltedge-commerce"', text); self.assertIn("canonical_runtime_state", text); self.assertNotIn("Credit Dispute Toolkit", text); self.assertNotIn("AI Automation Blueprint", text)

    def test_mcp_is_part_of_canonical_bridge_and_not_a_sidecar_truth_source(self):
        v3 = BRIDGE_V3_PATH.read_text(encoding="utf-8")
        self.assertIn('systems["mcp_cli"]', v3)
        self.assertIn("http://127.0.0.1:8390/health", v3)
        install = INSTALL.read_text(encoding="utf-8")
        self.assertIn("command_center_state_bridge_v3.py", install)
        self.assertIn("s['systems']['mcp_cli']['ok'] is True", install)

    def test_deploy_requires_full_live_acceptance_routing_mcp_intelligence_and_build_receipt(self):
        text = DEPLOY.read_text(encoding="utf-8")
        for marker in (
            "install_mcp_cli_server.sh",
            "COMMAND_CENTER_MCP_PREBOOT=PASS",
            "COMMAND_CENTER_PREBOOT_TRUTH=PASS",
            "COMMAND_CENTER_BUDDY_FALLBACK_PREBOOT=PASS",
            "BUDDY_WEB_TOKEN",
            "COMMAND_CENTER_BUDDY_TOKEN_FILE",
            "INTELLIGENCE_ACCEPTANCE_PROBE",
            "COMMAND_CENTER_INTELLIGENCE=PASS",
            "source in {'buddy_operator','nemotron'}",
            "command-center-fallback",
            "intelligence_source",
            "active_experiment_count",
            "dominion-command-center-state.service",
            "COMMAND_CENTER_PUBLIC_TRUTH=PASS",
            "converge_command_center_vault_route.sh",
            "dominion-command-center-build-receipt-v1",
            "COMMAND_CENTER_BUILD_RECEIPT=PASS",
            "mcp_cli=online",
        ):
            self.assertIn(marker, text)
        self.assertNotIn("echo $BUDDY_TOKEN", text)
        install = INSTALL.read_text(encoding="utf-8"); self.assertIn("OnUnitActiveSec=60s", install); self.assertIn("command_center_state_bridge_v3.py", install)
        mcp_install = MCP_INSTALL.read_text(encoding="utf-8"); self.assertIn("2026-07-28", mcp_install); self.assertIn("loopback", mcp_install.lower())

    def test_public_acceptance_uses_current_ui_and_bounded_retries(self):
        text = DEPLOY.read_text(encoding="utf-8")
        self.assertIn("probe_public_health()", text)
        self.assertIn("COMMAND_CENTER_PUBLIC_ROUTE=PASS", text)
        self.assertIn("RADAH MEMSHALAH", text)
        self.assertIn("AGENTS NETWORK / GOVERNED OPERATORS", text)
        self.assertIn("Public Command Center health probe failed after bounded retries", text)
        self.assertIn("Public Command Center status probe failed after bounded retries", text)
        self.assertNotIn("grep -Fq 'All Dominion lanes'", text)


if __name__ == "__main__": unittest.main()
