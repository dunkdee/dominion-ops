import json
from pathlib import Path

workflow = Path('.github/workflows/cron-status.yml').read_text(encoding='utf-8')
policy = json.loads(Path('governance/revenue_snapshot_integrity_policy.json').read_text(encoding='utf-8'))

required = [
    'set -euo pipefail',
    'VM_HOST is not configured',
    'VM_USER is not configured',
    'VM_SSH_KEY is not configured',
    'sudo docker exec dominion-db psql',
    'FROM orders',
    'amount_cents IS NOT NULL AND amount_cents > 0',
    'orders table — dominion-db',
    'orders.amount_cents',
    'REVENUE_SNAPSHOT_PROVENANCE=PASS',
    'REVENUE_SNAPSHOT_RECEIPT=PASS',
    '17 */3 * * *',
]

missing = [item for item in required if item not in workflow]
if missing:
    raise SystemExit(f'REVENUE_SNAPSHOT_INTEGRITY=FAIL missing={missing}')

for forbidden in (
    'skipping snapshot',
    'Gateway unreachable — skipping',
    'N8N_AGENT_GATEWAY_URL',
    'N8N_TOOL_SECRET',
    'roi_snapshot',
    '*/30 * * * *',
):
    if forbidden in workflow:
        raise SystemExit(f'REVENUE_SNAPSHOT_INTEGRITY=FAIL forbidden={forbidden!r}')

requirements = policy.get('requirements', {})
expected = {
    'canonical_purchase_source': 'dominion-db.orders',
    'canonical_revenue_source': 'orders.amount_cents',
    'foundation_vm_connection_required': True,
    'database_query_failure_is_blocking': True,
    'success_provenance_receipt': 'REVENUE_SNAPSHOT_PROVENANCE=PASS',
    'success_measurement_receipt': 'REVENUE_SNAPSHOT_RECEIPT=PASS',
    'scheduled_cadence_hours': 3,
}
for key, value in expected.items():
    if requirements.get(key) != value:
        raise SystemExit(
            f'REVENUE_SNAPSHOT_INTEGRITY=FAIL policy_requirement={key!r} '
            f'expected={value!r} actual={requirements.get(key)!r}'
        )

anti_drift = policy.get('anti_drift', {})
for key in ('no_parallel_analytics_authority', 'no_silent_skip', 'no_success_without_measurement'):
    if anti_drift.get(key) is not True:
        raise SystemExit(f'REVENUE_SNAPSHOT_INTEGRITY=FAIL policy_anti_drift={key!r}')

print('REVENUE_SNAPSHOT_INTEGRITY=PASS')
