from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVER_PATH = ROOT / "apps" / "mcp-cli-server" / "server.py"
REGISTRY_PATH = ROOT / "governance" / "mcp_connector_registry.json"
INSTALLER_PATH = ROOT / "scripts" / "install_mcp_cli_server.sh"
BRIDGE_V3_PATH = ROOT / "scripts" / "command_center_state_bridge_v3.py"

spec = importlib.util.spec_from_file_location("dominion_mcp_cli", SERVER_PATH)
assert spec and spec.loader
mcp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mcp)


class DominionMcpCliTests(unittest.TestCase):
    def test_registry_is_fail_closed_and_launch_connectors_are_read_only(self):
        registry = mcp.load_registry(REGISTRY_PATH)
        self.assertEqual(registry["schema"], "dominion-mcp-connector-registry-v1")
        self.assertEqual(registry["default_mode"], "deny")
        self.assertFalse(registry["external_mutation_enabled"])
        self.assertGreaterEqual(len(registry["connectors"]), 8)
        self.assertTrue(all(item["effect"] == "read_only" for item in registry["connectors"].values()))
        self.assertTrue(all(item["adapter"] in {"http_get", "exec", "file_read"} for item in registry["connectors"].values()))

    def test_modern_discovery_and_tools_are_deterministic(self):
        discover = mcp.handle_rpc({"jsonrpc": "2.0", "id": 1, "method": "server/discover", "params": {"_meta": {"io.modelcontextprotocol/protocolVersion": "2026-07-28"}}})
        self.assertEqual(discover["result"]["supportedVersions"][0], "2026-07-28")
        self.assertIn("tools", discover["result"]["capabilities"])
        self.assertEqual(discover["result"]["_meta"]["io.modelcontextprotocol/serverInfo"]["name"], "dominion-mcp-cli")

        listed = mcp.handle_rpc({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {"_meta": {"io.modelcontextprotocol/protocolVersion": "2026-07-28"}}})
        names = [tool["name"] for tool in listed["result"]["tools"]]
        self.assertEqual(names, ["dominion_connectors_list", "dominion_connector_invoke"])
        self.assertEqual(listed["result"]["cacheScope"], "private")

    def test_legacy_initialize_remains_compatible_without_becoming_primary(self):
        initialized = mcp.handle_rpc({"jsonrpc": "2.0", "id": 3, "method": "initialize", "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "test", "version": "1"}}})
        self.assertEqual(initialized["result"]["protocolVersion"], "2025-06-18")
        self.assertIn("Prefer MCP 2026-07-28", initialized["result"]["instructions"])

    def test_arbitrary_connector_and_unknown_params_fail_closed(self):
        with self.assertRaises(mcp.ConnectorError):
            mcp.invoke_connector("does_not_exist", {})
        registry = mcp.load_registry(REGISTRY_PATH)
        with self.assertRaises(mcp.ConnectorError):
            mcp.invoke_connector("command_center_status", {"url": "https://example.com"}, registry)

    def test_file_adapter_is_root_bounded_and_receipted_without_body(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            allowed = root / "allowed"
            allowed.mkdir()
            (allowed / "note.txt").write_text("safe payload", encoding="utf-8")
            mcp.STATE_DIR = root / "state"
            registry = {
                "schema": "dominion-mcp-connector-registry-v1",
                "default_mode": "deny",
                "external_mutation_enabled": False,
                "connectors": {
                    "test_file": {
                        "adapter": "file_read",
                        "effect": "read_only",
                        "root": str(allowed),
                        "path": "note.txt",
                        "max_bytes": 1024,
                        "allowed_params": {"path": {"max_length": 80, "pattern": r"^[A-Za-z0-9._/-]+$"}},
                    }
                },
            }
            result = mcp.invoke_connector("test_file", {}, registry)
            self.assertEqual(result["result"]["text"], "safe payload")
            receipts = list((mcp.STATE_DIR / "receipts").glob("*.json"))
            self.assertEqual(len(receipts), 1)
            receipt_text = receipts[0].read_text(encoding="utf-8")
            self.assertNotIn("safe payload", receipt_text)
            self.assertIn("arguments_sha256", receipt_text)
            with self.assertRaises(mcp.ConnectorError):
                mcp.invoke_connector("test_file", {"path": "../escape.txt"}, registry)

    def test_exec_adapter_never_uses_a_shell_and_http_target_is_registry_fixed(self):
        text = SERVER_PATH.read_text(encoding="utf-8")
        self.assertIn("subprocess.run(argv, shell=False", text)
        self.assertNotIn("shell=True", text)
        self.assertIn('target = str(spec.get("target") or "")', text)
        self.assertNotIn('supplied_params.get("url")', text)
        self.assertIn("NoRedirect", text)

    def test_install_and_canonical_bridge_make_mcp_a_release_gate(self):
        installer = INSTALLER_PATH.read_text(encoding="utf-8")
        self.assertIn("127.0.0.1 --port 8390", installer)
        self.assertIn("server/discover", installer)
        self.assertIn("MCP_STDIO_DISCOVERY=PASS", installer)
        self.assertIn("external_mutation_enabled", installer)
        bridge = BRIDGE_V3_PATH.read_text(encoding="utf-8")
        self.assertIn('systems["mcp_cli"]', bridge)
        self.assertIn("http://127.0.0.1:8390/health", bridge)


if __name__ == "__main__":
    unittest.main()
