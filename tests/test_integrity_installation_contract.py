import json
from pathlib import Path


def test_integrity_installation_contract_requires_runtime_receipts_and_anti_drift():
    contract = json.loads(Path('governance/integrity_installation_contract.json').read_text(encoding='utf-8'))
    rules = contract['rules']
    assert rules['repository_merge_is_not_runtime_proof'] is True
    assert rules['runtime_receipt_required_for_runtime_done'] is True
    assert rules['silent_skip_is_failure'] is True
    assert rules['parallel_authority_forbidden'] is True
    assert rules['rollback_required_for_consequential_change'] is True

    receipts = set(contract['required_receipts'])
    assert 'DEERFLOW_CAPABILITY_PROOF=PASS' in receipts
    assert 'DEERFLOW_RUNTIME_HEALTH=PASS' in receipts
    assert 'REVENUE_SNAPSHOT_RECEIPT=PASS' in receipts
    assert 'voltedge_real_order_receipt' in receipts
    assert 'source_to_order_attribution_receipt' in receipts
    assert 'adaptive_learning_receipt' in receipts
