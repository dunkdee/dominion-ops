import json
from pathlib import Path

contract = json.loads(Path('governance/integrity_installation_contract.json').read_text(encoding='utf-8'))
required_rules = {
    'repository_merge_is_not_runtime_proof': True,
    'runtime_receipt_required_for_runtime_done': True,
    'silent_skip_is_failure': True,
    'parallel_authority_forbidden': True,
    'rollback_required_for_consequential_change': True,
    'completed_work_reopens_only_on_regression_evidence': True,
}
for key, expected in required_rules.items():
    if contract.get('rules', {}).get(key) is not expected:
        raise SystemExit(f'INTEGRITY_INSTALLATION_CONTRACT=FAIL rule={key}')

receipts = set(contract.get('required_receipts', []))
for receipt in (
    'DEERFLOW_CAPABILITY_PROOF=PASS',
    'DEERFLOW_RUNTIME_HEALTH=PASS',
    'REVENUE_SNAPSHOT_RECEIPT=PASS',
    'voltedge_real_order_receipt',
    'source_to_order_attribution_receipt',
    'adaptive_learning_receipt',
):
    if receipt not in receipts:
        raise SystemExit(f'INTEGRITY_INSTALLATION_CONTRACT=FAIL receipt={receipt}')

print('INTEGRITY_INSTALLATION_CONTRACT=PASS')
