from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
DEPLOY = (ROOT / "scripts/deploy_command_center.sh").read_text(encoding="utf-8")


class CommandCenterPublicAcceptanceContractTests(unittest.TestCase):
    def test_public_acceptance_uses_current_radah_memshalah_markers(self):
        self.assertIn("RADAH MEMSHALAH", DEPLOY)
        self.assertIn("AGENTS NETWORK / GOVERNED OPERATORS", DEPLOY)
        self.assertNotIn("grep -Fq 'All Dominion lanes'", DEPLOY)

    def test_public_route_is_bounded_and_diagnostic(self):
        self.assertIn("probe_public_health()", DEPLOY)
        self.assertIn("seq 1 12", DEPLOY)
        self.assertIn("COMMAND_CENTER_PUBLIC_ROUTE=PASS", DEPLOY)
        self.assertIn("Public Command Center health probe failed after bounded retries", DEPLOY)
        self.assertIn("Public Command Center status probe failed after bounded retries", DEPLOY)

    def test_public_truth_and_receipt_remain_release_gates(self):
        self.assertIn("COMMAND_CENTER_PUBLIC_TRUTH=PASS", DEPLOY)
        self.assertIn("dominion-command-center-build-receipt-v1", DEPLOY)
        self.assertIn("COMMAND_CENTER_BUILD_RECEIPT=PASS", DEPLOY)


if __name__ == "__main__":
    unittest.main()
