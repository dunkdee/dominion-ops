from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / '.github/workflows/revenue-gate-e-live-canary-prepare.yml'
SCRIPT = ROOT / 'scripts/revenue_runtime/prepare_gate_e_live_canary.sh'


class GateELiveCanaryTests(unittest.TestCase):
    def test_workflow_is_owner_bound_and_exact_main_scoped(self):
        text = WORKFLOW.read_text(encoding='utf-8')
        self.assertIn("github.event.issue.number == 305", text)
        self.assertIn("github.event.comment.user.login == github.repository_owner", text)
        self.assertIn("github.event.comment.author_association == 'OWNER'", text)
        self.assertIn("PREPARE_GATE_E_LIVE_CANARY:$main_sha:PREPARE GATE E", text)
        self.assertIn('environment: foundation-vm-production', text)
        self.assertIn('HostKeyAlias=foundation-vm', text)
        self.assertIn('StrictHostKeyChecking=yes', text)
        self.assertIn('issues: write', text)

    def test_live_canary_preserves_fail_closed_commercial_controls(self):
        text = SCRIPT.read_text(encoding='utf-8')
        self.assertIn("obj.get('execution_enabled') is False", text)
        self.assertIn("obj.get('automatic_price_changes') is False", text)
        self.assertIn("obj.get('automatic_paid_spend') is False", text)
        self.assertIn("'treatment_pct': 0", text)
        self.assertIn("'auto_promote': False", text)
        self.assertNotIn("obj.get('execution_enabled') is True", text)

    def test_live_canary_does_not_create_synthetic_click_or_payment(self):
        text = SCRIPT.read_text(encoding='utf-8')
        self.assertIn('synthetic_click=false', text)
        self.assertIn('automated_spend=false', text)
        self.assertIn('price_mutation=false', text)
        self.assertNotIn('curl -L', text)
        self.assertNotIn('--location', text)
        self.assertNotIn('/click?', text)
        self.assertNotIn('/revenue/events', text)
        self.assertNotIn('payment', text.lower().split('GATE_E_LIVE_CANARY_PREP=PASS')[0][-200:])

    def test_failure_path_pauses_but_success_leaves_canary_active(self):
        text = SCRIPT.read_text(encoding='utf-8')
        self.assertIn('if [ "$completed" -ne 1 ]', text)
        self.assertIn('/pause', text)
        self.assertIn("assert exp['status'] == 'active'", text)
        self.assertIn('completed=1', text)
        self.assertIn('GATE_E_LIVE_EXPERIMENT_ACTIVE=PASS', text)

    def test_public_route_uses_existing_revenue_runtime_origin(self):
        text = SCRIPT.read_text(encoding='utf-8')
        self.assertIn('public_origin="https://dominionhealing.org"', text)
        self.assertIn('public_route="$public_origin/r/$exp_id"', text)
        self.assertIn('GATE_E_LIVE_CANARY_PREP=PASS', text)


if __name__ == '__main__':
    unittest.main()
