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

    def test_owner_authorized_runtime_trigger_is_fail_closed_and_not_push_driven(self):
        text = WORKFLOW.read_text(encoding='utf-8')

        # The rejected PR #327 proved that a push-triggered production-secret
        # workflow is unacceptable while main is unprotected. Issue-comment
        # execution may reach the runner only for the canonical revenue issue
        # and repository owner; the first step then binds authorization to the
        # current main SHA before any SSH secret is referenced.
        self.assertIn('issue_comment:', text)
        self.assertIn('types: [created]', text)
        self.assertNotIn('\n  push:', text)
        self.assertIn("github.event.issue.number == 305", text)
        self.assertIn("github.event.comment.user.login == github.repository_owner", text)
        self.assertIn("github.event.comment.author_association == 'OWNER'", text)
        self.assertNotIn(
            "github.event.comment.body == format('RUN_REVENUE_SNAPSHOT:{0}', github.sha)",
            text,
        )

        # Exact-SHA authorization is performed as the first executable step so
        # a mismatch is observable and fail-closed before the later secret steps.
        self.assertIn('Prove owner-authorized execution boundary', text)
        self.assertIn('$GITHUB_API_URL/repos/$GITHUB_REPOSITORY/commits/main', text)
        self.assertIn('expected="RUN_REVENUE_SNAPSHOT:$main_sha"', text)
        self.assertIn('test "$COMMENT_BODY" = "$expected"', text)
        self.assertIn('REVENUE_SNAPSHOT_AUTHORIZATION=PASS', text)

        auth_index = text.index('Prove owner-authorized execution boundary')
        secret_index = text.index('Require Foundation VM connection material')
        self.assertLess(auth_index, secret_index)


if __name__ == '__main__':
    unittest.main()
