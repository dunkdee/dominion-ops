#!/usr/bin/env python3
from pathlib import Path

path = Path('tests/test_email_drip_governance.py')
text = path.read_text(encoding='utf-8')


def replace_once(old: str, new: str, label: str) -> None:
    global text
    count = text.count(old)
    if count != 1:
        raise SystemExit(f'{label}: expected exactly one match, found {count}')
    text = text.replace(old, new, 1)


replace_once(
    'def load_module(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, mode: str = "hold"):',
    'def load_module(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, mode: str | None = "hold"):',
    'optional mode fixture',
)
replace_once(
    '    monkeypatch.setenv("DRIP_SUPPRESSION_FILE", str(suppression))\n    monkeypatch.setenv("DRIP_SEND_MODE", mode)\n    monkeypatch.setenv("SMTP_EMAIL", "sender@example.invalid")',
    '    monkeypatch.setenv("DRIP_SUPPRESSION_FILE", str(suppression))\n    if mode is not None:\n        monkeypatch.setenv("DRIP_SEND_MODE", mode)\n        if mode == "live":\n            monkeypatch.setenv("DRIP_LIVE_AUTHORIZED_AT", datetime.now(timezone.utc).isoformat())\n        else:\n            monkeypatch.delenv("DRIP_LIVE_AUTHORIZED_AT", raising=False)\n    monkeypatch.setenv("SMTP_EMAIL", "sender@example.invalid")',
    'live authorization fixture',
)
replace_once(
    '        "emails_sent": ["welcome", "value", "social_proof"],\n        "last_sent_at": None,',
    '        "emails_sent": ["welcome", "value", "social_proof"],\n        "last_sent_at": (now - timedelta(days=2)).isoformat(),',
    'due fixture send history',
)
replace_once(
    '    monkeypatch.setattr(module, "_send_email", lambda *a, **k: False)\n    assert module._run_drip_cycle() == 0\n    assert json.loads(leads_path.read_text(encoding="utf-8")) == data',
    '    monkeypatch.setattr(module, "_send_email", lambda *a, **k: False)\n    assert module._run_drip_cycle() == 0\n    saved = json.loads(leads_path.read_text(encoding="utf-8"))\n    assert saved["leads"][0]["emails_sent"] == data["leads"][0]["emails_sent"]\n    assert saved["leads"][0]["pending_send"]["step"] == "soft_sell"\n    assert saved["stats"]["emails_sent"] == 0',
    'failed transport reconciliation semantics',
)

# Final appended footer test uses the shared due_lead fixture, whose next step is soft_sell.
text = text.replace("assert saved['pending_send']['step'] == 'welcome'", "assert saved['pending_send']['step'] == 'soft_sell'")

path.write_text(text, encoding='utf-8', newline='\n')
