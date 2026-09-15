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

        # A production-secret snapshot must never be push-triggered. Unrelated
        # issue comments (Council/deploy/etc.) must be rejected at job admission,
        # while a matching snapshot token still receives exact-main validation
        # in the first executable step.
        self.assertIn('issue_comment:', text)
        self.assertIn('types: [created]', text)
        self.assertNotIn('\n  push:', text)
        self.assertIn("github.event.issue.number == 305", text)
        self.assertIn("github.event.comment.user.login == github.repository_owner", text)
        self.assertIn("github.event.comment.author_association == 'OWNER'", text)
        self.assertIn("startsWith(github.event.comment.body, 'RUN_REVENUE_SNAPSHOT:')", text)
        self.assertNotIn("startsWith(github.event.comment.body, 'DEPLOY_REVENUE_COMMERCIAL_RUNTIME:')", text)

        # Exact-SHA authorization remains observable and fail-closed before
        # later secret-bearing SSH steps.
        self.assertIn('Prove owner-authorized execution boundary', text)
        self.assertIn('$GITHUB_API_URL/repos/$GITHUB_REPOSITORY/commits/main', text)
        self.assertIn('expected="RUN_REVENUE_SNAPSHOT:$main_sha"', text)
        self.assertIn('test "$COMMENT_BODY" = "$expected"', text)
        self.assertIn('REVENUE_SNAPSHOT_AUTHORIZATION=PASS', text)

        auth_index = text.index('Prove owner-authorized execution boundary')
        secret_index = text.index('Require Foundation VM connection material')
        self.assertLess(auth_index, secret_index)

    def test_foundation_vm_host_identity_is_pinned(self):
        text = WORKFLOW.read_text(encoding='utf-8')

        self.assertIn('secrets.VM_SSH_KNOWN_HOSTS', text)
        self.assertIn('VM_SSH_KNOWN_HOSTS is not configured', text)
        self.assertIn('FOUNDATION_VM_HOST_IDENTITY=PINNED alias=foundation-vm', text)
        self.assertIn('HostKeyAlias=foundation-vm', text)
        self.assertIn('StrictHostKeyChecking=yes', text)
        self.assertIn('foundation-vm host-key alias entry', text)
        self.assertNotIn('ssh-keyscan', text)


if __name__ == '__main__':
    unittest.main()
