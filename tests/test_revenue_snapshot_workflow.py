import unittest
from pathlib import Path


WORKFLOW = Path('.github/workflows/cron-status.yml')


class RevenueSnapshotWorkflowTests(unittest.TestCase):
    def test_revenue_snapshot_fails_closed_and_emits_receipt(self):
        text = WORKFLOW.read_text(encoding='utf-8')
        self.assertIn('N8N_AGENT_GATEWAY_URL is not configured', text)
        self.assertIn('N8N_AGENT_GATEWAY_URL is malformed', text)
        self.assertIn('N8N_TOOL_SECRET is not configured', text)
        self.assertIn('REVENUE_SNAPSHOT_RECEIPT=PASS', text)
        self.assertNotIn('skipping snapshot', text)
        self.assertNotIn('Gateway unreachable — skipping', text)


if __name__ == '__main__':
    unittest.main()
