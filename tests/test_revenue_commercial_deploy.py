from __future__ import annotations

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "revenue-runtime-commercial-deploy.yml"
DEPLOY = ROOT / "scripts" / "revenue_runtime" / "deploy_commercial_release_v1.sh"


class RevenueCommercialDeployTests(unittest.TestCase):
    def setUp(self):
        self.workflow = WORKFLOW.read_text(encoding="utf-8")
        self.deploy = DEPLOY.read_text(encoding="utf-8")

    def test_workflow_is_owner_issue_and_exact_main_bound(self):
        self.assertIn("issue_comment:", self.workflow)
        self.assertNotIn("push:", self.workflow)
        self.assertNotIn("pull_request:", self.workflow)
        self.assertIn("github.event.issue.number == 305", self.workflow)
        self.assertIn("github.event.comment.user.login == github.repository_owner", self.workflow)
        self.assertIn("github.event.comment.author_association == 'OWNER'", self.workflow)
        self.assertIn("$GITHUB_API_URL/repos/$GITHUB_REPOSITORY/commits/main", self.workflow)
        self.assertIn('expected="DEPLOY_REVENUE_COMMERCIAL_RUNTIME:$main_sha"', self.workflow)
        self.assertIn('test "$COMMENT_BODY" = "$expected"', self.workflow)
        self.assertIn("ref: ${{ steps.authorize.outputs.main_sha }}", self.workflow)

    def test_secrets_are_referenced_only_after_authorization_step(self):
        authorize = self.workflow.index("Prove owner authorization bound to current main")
        first_secret = self.workflow.index("secrets.VM_HOST")
        self.assertLess(authorize, first_secret)

    def test_outer_rollback_is_armed_before_legacy_installer(self):
        trap_pos = self.deploy.index("trap rollback ERR INT TERM EXIT")
        installer_pos = self.deploy.index('bash "$asset_root/scripts/revenue_runtime/install_revenue_runtime.sh"')
        self.assertLess(trap_pos, installer_pos)
        self.assertIn("REVENUE_COMMERCIAL_ROLLBACK=COMPLETE", self.deploy)

    def test_commercial_mode_disables_auto_cro_before_installer(self):
        disable_pos = self.deploy.index("Environment=DOMINION_REVENUE_RUNTIME_ENABLED=0")
        installer_pos = self.deploy.index('bash "$asset_root/scripts/revenue_runtime/install_revenue_runtime.sh"')
        self.assertLess(disable_pos, installer_pos)
        self.assertIn("REVENUE_AUTO_CRO=DISABLED", self.deploy)
        self.assertIn("execution_enabled", self.deploy)
        self.assertIn("is False", self.deploy)

    def test_deployment_restarts_service_and_proves_exact_asset_parity(self):
        self.assertIn('sudo systemctl restart "$service_name"', self.deploy)
        self.assertIn('cmp -s "$src" "$runtime_root/apps/revenue_runtime/$name"', self.deploy)
        self.assertIn("REVENUE_RUNTIME_MANIFEST=PASS", self.deploy)
        self.assertIn("REVENUE_RUNTIME_SOURCE_SHA=PASS", self.deploy)

    def test_generic_public_event_ingestion_is_removed(self):
        self.assertIn("REVENUE_PUBLIC_EVENT_INGESTION=DISABLED", self.deploy)
        self.assertIn("@dominion_revenue_public path /r /r/*", self.deploy)
        self.assertIn("/revenue/events", self.deploy)

    def test_runtime_acceptance_covers_auth_router_timer_db_and_rollback(self):
        self.assertIn('unauth="$(curl', self.deploy)
        self.assertIn('[ "$unauth" = 401 ]', self.deploy)
        self.assertIn("REVENUE_CONTROL_NEGATIVE_AUTH=PASS", self.deploy)
        self.assertIn("REVENUE_PUBLIC_ROUTER=PASS", self.deploy)
        self.assertIn("REVENUE_EVALUATOR_TIMER=PASS", self.deploy)
        self.assertIn("PRAGMA integrity_check", self.deploy)
        self.assertIn("REVENUE_DB_INTEGRITY=PASS", self.deploy)
        self.assertIn("REVENUE_ROLLBACK_REFERENCE=PASS", self.deploy)
        self.assertNotIn('rm -rf "$rollback_root"', self.deploy)

    def test_final_receipt_is_explicit(self):
        self.assertIn("REVENUE_COMMERCIAL_RUNTIME_DEPLOY=PASS", self.deploy)


if __name__ == "__main__":
    unittest.main()
