from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AGENT = ROOT / "scripts/system_integrity_agent.py"
CONTRACT = ROOT / "governance/system_integrity_agent.json"
SERVICE = ROOT / "deploy/systemd/dominion-system-integrity.service"
TIMER = ROOT / "deploy/systemd/dominion-system-integrity.timer"
INSTALL = ROOT / "scripts/install_system_integrity_agent.sh"
BRIDGE = ROOT / "scripts/command_center_state_bridge_v3.py"

spec = importlib.util.spec_from_file_location("system_integrity_agent", AGENT)
assert spec and spec.loader
agent = importlib.util.module_from_spec(spec)
spec.loader.exec_module(agent)


class SystemIntegrityAgentTests(unittest.TestCase):
    def test_contract_is_single_responsibility_and_non_mutating(self):
        contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
        self.assertEqual(contract["schema"], "dominion-system-integrity-agent-v1")
        self.assertEqual(contract["cadence_seconds"], 89)
        self.assertEqual(contract["authority"]["mode"], "OBSERVE_VERIFY_REQUEST_RECOVERY")
        self.assertTrue(contract["authority"]["founder_final_authority"])
        for key, value in contract["authority"].items():
            if key.startswith("may_"):
                self.assertFalse(value, key)
        self.assertIn("reliability", contract["single_responsibility"].lower())
        self.assertIn("never perform business work", contract["single_responsibility"].lower())

    def test_agent_rejects_authority_expansion(self):
        contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "contract.json"
            contract["authority"]["may_deploy"] = True
            path.write_text(json.dumps(contract), encoding="utf-8")
            with self.assertRaises(ValueError):
                agent.load_contract(path)

    def test_agent_source_has_no_direct_repair_or_external_execution(self):
        text = AGENT.read_text(encoding="utf-8")
        for forbidden in (
            "systemctl restart",
            "docker restart",
            "docker start",
            "git push",
            "git commit",
            "gcloud compute firewall-rules",
            "subprocess.run(cmd, shell=True",
        ):
            self.assertNotIn(forbidden, text)
        self.assertIn("REQUEST_BOUNDED_RECOVERY", text)
        self.assertIn("fix-buddy-brains.yml", CONTRACT.read_text(encoding="utf-8"))

    def test_systemd_is_oneshot_read_only_except_own_state(self):
        service = SERVICE.read_text(encoding="utf-8")
        timer = TIMER.read_text(encoding="utf-8")
        self.assertIn("Type=oneshot", service)
        self.assertIn("ProtectSystem=strict", service)
        self.assertIn("ProtectHome=read-only", service)
        self.assertIn("ReadWritePaths=/home/malachisingleton8/.dominion/system-integrity", service)
        self.assertIn("OnUnitActiveSec=89s", timer)
        self.assertIn("Persistent=true", timer)

    def test_installer_requires_first_passing_deep_probe(self):
        text = INSTALL.read_text(encoding="utf-8")
        self.assertIn("SYSTEM_INTEGRITY_FIRST_CYCLE=PASS", text)
        self.assertIn("deep_probe_executed", text)
        self.assertIn("dominion-system-integrity.timer", text)
        self.assertIn("cadence=89s", text)

    def test_command_center_truth_surfaces_fresh_integrity_state(self):
        text = BRIDGE.read_text(encoding="utf-8")
        self.assertIn('systems["system_integrity"]', text)
        self.assertIn("age <= 240", text)
        self.assertIn('"status": "STALE"', text)


if __name__ == "__main__":
    unittest.main()
