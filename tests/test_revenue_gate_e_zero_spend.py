from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / '.github/workflows/revenue-gate-e-zero-spend-proof.yml'
SCRIPT = ROOT / 'scripts/revenue_runtime/prove_gate_e_zero_spend.sh'


class GateEZeroSpendProofTests(unittest.TestCase):
    def test_workflow_is_owner_bound_and_exact_main_scoped(self):
        text = WORKFLOW.read_text(encoding='utf-8')
        self.assertIn("github.event.issue.number == 305", text)
        self.assertIn("github.event.comment.user.login == github.repository_owner", text)
        self.assertIn("github.event.comment.author_association == 'OWNER'", text)
        self.assertIn("RUN_GATE_E_ZERO_SPEND:$main_sha:PROVE GATE E", text)
        self.assertIn('environment: foundation-vm-production', text)
        self.assertIn('HostKeyAlias=foundation-vm', text)
        self.assertIn('StrictHostKeyChecking=yes', text)
        self.assertIn('issues: write', text)

    def test_proof_forbids_spend_and_external_redirect_follow(self):
        text = SCRIPT.read_text(encoding='utf-8')
        self.assertIn("'treatment_pct': 0", text)
        self.assertIn("'auto_promote': False", text)
        self.assertIn('purchase_events=0', text)
        self.assertIn('refund_events=0', text)
        self.assertIn('external_redirect_followed=false', text)
        self.assertIn('/pause', text)
        self.assertNotIn('curl -L', text)
        self.assertNotIn('--location', text)

    def test_proof_requires_signed_campaign_identity_and_zero_revenue(self):
        text = SCRIPT.read_text(encoding='utf-8')
        self.assertIn("q.get('utm_source') == ['dominion_revenue']", text)
        self.assertIn("q.get('utm_medium') == ['experiment']", text)
        self.assertIn("q.get('utm_campaign') == [exp_id]", text)
        self.assertIn("q.get('utm_content') == ['control']", text)
        self.assertIn("int(metrics[variant].get('revenue_cents',0)) == 0", text)
        self.assertIn("int(metrics[variant].get('refund_cents',0)) == 0", text)


if __name__ == '__main__':
    unittest.main()
