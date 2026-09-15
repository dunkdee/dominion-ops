import unittest
from pathlib import Path


WORKFLOW = Path('.github/workflows/cron-status.yml')


class RevenueSnapshotWorkflowTests(unittest.TestCase):
    def test_revenue_snapshot_reads_canonical_dominion_db_and_emits_receipt(self):
        text = WORKFLOW.read_text(encoding='utf-8')

        # Cost control: Dominion's three-hour operating cadence replaces the
        # broken 30-minute hosted runner loop.
        self.assertIn('17 */3 * * *', text)
        self.assertNotIn('*/30 * * * *', text)

        # The snapshot reads the canonical purchase source directly on the
        # Foundation VM. It must not depend on the legacy n8n roi_snapshot stub.
        self.assertIn('VM_HOST', text)
        self.assertIn('VM_USER', text)
        self.assertIn('VM_SSH_KEY', text)
        self.assertIn('sudo docker exec dominion-db psql', text)
        self.assertIn('FROM orders', text)
        self.assertIn('amount_cents IS NOT NULL AND amount_cents > 0', text)
        self.assertNotIn('N8N_AGENT_GATEWAY_URL', text)
        self.assertNotIn('N8N_TOOL_SECRET', text)
        self.assertNotIn('roi_snapshot', text)

        # Provenance and integrity remain fail-closed and machine-verifiable.
        self.assertIn('orders table — dominion-db', text)
        self.assertIn('orders.amount_cents', text)
        self.assertIn('purchase_count must be a non-negative integer', text)
        self.assertIn('revenue_cents must be a non-negative integer', text)
        self.assertIn('REVENUE_SNAPSHOT_PROVENANCE=PASS', text)
        self.assertIn('REVENUE_SNAPSHOT_RECEIPT=PASS', text)
        self.assertNotIn('skipping snapshot', text)
        self.assertNotIn('Gateway unreachable — skipping', text)


if __name__ == '__main__':
    unittest.main()
