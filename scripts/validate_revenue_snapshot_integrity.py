from pathlib import Path

workflow = Path('.github/workflows/cron-status.yml').read_text(encoding='utf-8')
policy = Path('governance/revenue_snapshot_integrity_policy.json').read_text(encoding='utf-8')

required = [
    'set -euo pipefail',
    'N8N_AGENT_GATEWAY_URL is not configured',
    'N8N_AGENT_GATEWAY_URL is malformed',
    'N8N_TOOL_SECRET is not configured',
    'REVENUE_SNAPSHOT_RECEIPT=PASS',
]

missing = [item for item in required if item not in workflow]
if missing:
    raise SystemExit(f'REVENUE_SNAPSHOT_INTEGRITY=FAIL missing={missing}')

for forbidden in ('skipping snapshot', 'Gateway unreachable — skipping'):
    if forbidden in workflow:
        raise SystemExit(f'REVENUE_SNAPSHOT_INTEGRITY=FAIL silent_skip={forbidden!r}')

if '"no_success_without_measurement": true' not in policy:
    raise SystemExit('REVENUE_SNAPSHOT_INTEGRITY=FAIL policy')

print('REVENUE_SNAPSHOT_INTEGRITY=PASS')
