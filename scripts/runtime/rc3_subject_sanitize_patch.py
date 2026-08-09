#!/usr/bin/env python3
from pathlib import Path

source_path = Path('services/email_drip/email_drip.py')
tests_path = Path('tests/test_email_drip_governance.py')
source = source_path.read_text(encoding='utf-8')
old = '                subject = str(plan["subject"]).replace("{{name}}", str(plan["name"]))'
new = '                safe_subject_name = " ".join(str(plan["name"]).replace("\\r", " ").replace("\\n", " ").split())\n                subject = str(plan["subject"]).replace("{{name}}", safe_subject_name)'
count = source.count(old)
if count != 1:
    raise SystemExit(f'subject anchor count={count}')
source_path.write_text(source.replace(old, new, 1), encoding='utf-8', newline='\n')

tests = tests_path.read_text(encoding='utf-8')
if 'def test_subject_name_cannot_inject_headers' not in tests:
    tests += r'''


def test_subject_name_cannot_inject_headers(tmp_path, monkeypatch):
    module, leads_path, _ = load_module(tmp_path, monkeypatch, mode='hold')
    module.DRIP_SEND_MODE = 'live'
    now = datetime.now(timezone.utc)
    lead = due_lead(now)
    lead['name'] = 'Dewayne\r\nBcc: attacker@example.invalid'
    module.BOOK_EMAILS['sovereign_mind']['soft_sell']['subject'] = 'A note for {{name}}'
    leads_path.write_text(json.dumps({'leads':[lead], 'stats':{'total_captured':1,'emails_sent':0}}), encoding='utf-8')
    captured = {}
    def transport(_email, _name, subject, _body):
        captured['subject'] = subject
        return False
    monkeypatch.setattr(module, '_send_email', transport)
    assert module._run_drip_cycle() == 0
    assert '\r' not in captured['subject']
    assert '\n' not in captured['subject']
    assert captured['subject'] == 'A note for Dewayne Bcc: attacker@example.invalid'
'''
    tests_path.write_text(tests, encoding='utf-8', newline='\n')
