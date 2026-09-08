from __future__ import annotations

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEAM_STATE = ROOT / "brain/agent-team-current-state.md"
RENDERER = ROOT / "scripts/render_dominion_brain.py"
BRIDGE = ROOT / "scripts/command_center_state_bridge_v3.py"
REVENUE = ROOT / "apps/revenue_runtime/service.py"
PUBLISHER = ROOT / "apps/dominion_publisher/service.py"
STOREFRONT_RECEIPT = ROOT / "evidence/production-closure/2026-09-08-voltedge-best-sellers-correction.json"


class FiveModuleProductionClosureTests(unittest.TestCase):
    def test_brain_carries_current_five_module_closure(self):
        text = TEAM_STATE.read_text(encoding="utf-8")
        for heading in (
            "### 1. Publisher + Meta",
            "### 2. Obsidian / Dominion Brain",
            "### 3. Command Center",
            "### 4. VoltEdge / Wix storefront",
            "### 5. Traffic + revenue loop",
        ):
            self.assertIn(heading, text)
        self.assertIn("Never mark Meta complete from code existence alone", text)
        self.assertIn("orders_count=0", text)
        self.assertIn("existing governance hold remains effective", text)

        renderer = RENDERER.read_text(encoding="utf-8")
        self.assertIn('TEAM_STATE = REPO / "brain" / "agent-team-current-state.md"', renderer)
        self.assertIn('"04-Agents/TEAM_CURRENT_STATE.md", TEAM_STATE', renderer)

    def test_publisher_and_command_center_preserve_runtime_truth(self):
        publisher = PUBLISHER.read_text(encoding="utf-8")
        self.assertIn('@app.post("/oauth/meta/bind")', publisher)
        self.assertIn('x_human_approval != "APPROVED"', publisher)
        self.assertIn('@app.post("/jobs/publish")', publisher)
        self.assertIn('"provider_post_id": receipt.provider_post_id', publisher)

        bridge = BRIDGE.read_text(encoding="utf-8")
        for phase in (
            "AWAITING_META_APP_CONFIGURATION",
            "AWAITING_META_ACCOUNT_BINDING",
            "BOUND_AWAITING_CONTROLLED_CANARY",
            "PUBLISHING_PROVEN",
        ):
            self.assertIn(phase, bridge)
        self.assertIn('systems["publisher_controlled_publish"]', bridge)

    def test_revenue_loop_requires_attribution_and_purchase_evidence(self):
        revenue = REVENUE.read_text(encoding="utf-8")
        for marker in (
            '"utm_source": "dominion_revenue"',
            '"utm_campaign": exp_id',
            '"add_to_cart", "checkout", "purchase", "refund"',
            'Automatic promotion requires purchase evidence',
            '"automatic_paid_spend": False',
        ):
            self.assertIn(marker, revenue)

    def test_storefront_receipt_does_not_fabricate_best_sellers(self):
        receipt = json.loads(STOREFRONT_RECEIPT.read_text(encoding="utf-8"))
        self.assertEqual(receipt["truth"], "VERIFIED")
        self.assertEqual(receipt["evidence"]["orders_count"], 0)
        self.assertFalse(receipt["evidence"]["current_visible"])
        self.assertEqual(receipt["evidence"]["current_revision"], "3")
        self.assertFalse(receipt["secrets_present"])


if __name__ == "__main__":
    unittest.main()
