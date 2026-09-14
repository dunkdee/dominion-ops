from pathlib import Path


WORKFLOW = Path('.github/workflows/cron-status.yml')


def test_revenue_snapshot_fails_closed_and_emits_receipt():
    text = WORKFLOW.read_text(encoding='utf-8')

    assert 'N8N_AGENT_GATEWAY_URL is not configured' in text
    assert 'N8N_AGENT_GATEWAY_URL is malformed' in text
    assert 'N8N_TOOL_SECRET is not configured' in text
    assert 'REVENUE_SNAPSHOT_RECEIPT=PASS' in text
    assert 'skipping snapshot' not in text
    assert 'Gateway unreachable — skipping' not in text
