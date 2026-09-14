import json
import unittest
from pathlib import Path


class IntegrityInstallationContractTests(unittest.TestCase):
    def test_requires_runtime_receipts_and_anti_drift(self):
        contract = json.loads(Path('governance/integrity_installation_contract.json').read_text(encoding='utf-8'))
        rules = contract['rules']
        self.assertTrue(rules['repository_merge_is_not_runtime_proof'])
        self.assertTrue(rules['runtime_receipt_required_for_runtime_done'])
        self.assertTrue(rules['silent_skip_is_failure'])
        self.assertTrue(rules['parallel_authority_forbidden'])
        self.assertTrue(rules['rollback_required_for_consequential_change'])

        receipts = set(contract['required_receipts'])
        self.assertIn('DEERFLOW_CAPABILITY_PROOF=PASS', receipts)
        self.assertIn('DEERFLOW_RUNTIME_HEALTH=PASS', receipts)
        self.assertIn('REVENUE_SNAPSHOT_RECEIPT=PASS', receipts)
        self.assertIn('voltedge_real_order_receipt', receipts)
        self.assertIn('source_to_order_attribution_receipt', receipts)
        self.assertIn('adaptive_learning_receipt', receipts)


if __name__ == '__main__':
    unittest.main()
