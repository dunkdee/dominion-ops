#!/usr/bin/env python3
from pathlib import Path

source_path = Path('services/email_drip/email_drip.py')
tests_path = Path('tests/test_email_drip_governance.py')
source = source_path.read_text(encoding='utf-8')
tests = tests_path.read_text(encoding='utf-8')


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f'{label}: expected exactly one match, found {count}')
    return text.replace(old, new, 1)


source = replace_once(
    source,
    'DRIP_LIVE_AUTHORIZED_AT = os.getenv("DRIP_LIVE_AUTHORIZED_AT", "").strip()\nDRIP_LIVE_AUTH_MAX_AGE_SECONDS = int(os.getenv("DRIP_LIVE_AUTH_MAX_AGE_SECONDS", "900"))',
    'DRIP_LIVE_AUTHORIZED_AT = os.getenv("DRIP_LIVE_AUTHORIZED_AT", "").strip()\nDRIP_LIVE_PREFLIGHT_OK = os.getenv("DRIP_LIVE_PREFLIGHT_OK", "").strip().lower() == "true"\nDRIP_LIVE_AUTH_MAX_AGE_SECONDS = int(os.getenv("DRIP_LIVE_AUTH_MAX_AGE_SECONDS", "900"))',
    'live preflight config',
)
source = replace_once(
    source,
    'def _live_start_authorized(now=None):\n    if CONFIGURED_DRIP_SEND_MODE != "live":\n        return False\n    if not DRIP_LIVE_AUTHORIZED_AT:',
    'def _live_start_authorized(now=None):\n    if CONFIGURED_DRIP_SEND_MODE != "live":\n        return False\n    if not DRIP_LIVE_PREFLIGHT_OK:\n        return False\n    if not DRIP_LIVE_AUTHORIZED_AT:',
    'live preflight gate',
)
source = replace_once(
    source,
    '        log.info("SMTP sent lead_ref=%s subject=%s", lead_ref, subject)',
    '        log.info("SMTP sent lead_ref=%s", lead_ref)',
    'smtp pii log',
)
source = replace_once(
    source,
    '            with SUPPRESSION_FILE.open("r", encoding="utf-8") as handle:\n                data = json.load(handle)\n            emails = data.get("emails", [])',
    '            with SUPPRESSION_FILE.open("r", encoding="utf-8") as handle:\n                data = json.load(handle)\n            if not isinstance(data, dict):\n                return "error"\n            emails = data.get("emails", [])',
    'suppression root validation',
)
source = replace_once(
    source,
    '    name = (payload.name or "Friend").strip() or "Friend"\n    source_value = (payload.source or "").strip()\n    book = _resolve_book(source_value)',
    '    name = (payload.name or "Friend").strip() or "Friend"\n    source_value = (payload.source or "").strip()\n    if len(name) > 120 or len(source_value) > 128:\n        raise HTTPException(status_code=400, detail="capture_field_too_long")\n    book = _resolve_book(source_value)',
    'capture field bounds',
)
source = replace_once(
    source,
    '            for lead in data["leads"]:\n                if _normalize_email(str(lead.get("email", ""))) == email:',
    '            for lead in data["leads"]:\n                if not isinstance(lead, dict):\n                    continue\n                if _normalize_email(str(lead.get("email", ""))) == email:',
    'duplicate lookup corrupt row guard',
)
old_status = '''@app.get("/api/drip-status")
def drip_status():
    data = _load_leads()
    total = len(data["leads"])
    by_book = {}
    fully_dripped = 0
    for lead in data["leads"]:
        b = lead.get("book", "unknown")
        by_book[b] = by_book.get(b, 0) + 1
        sent_steps = lead.get("emails_sent", [])
        if isinstance(sent_steps, list) and len(sent_steps) >= 5:
            fully_dripped += 1

    return {
        "total_leads": total,
        "leads_by_book": by_book,
        "total_emails_sent": data["stats"].get("emails_sent", 0),
        "fully_completed_sequences": fully_dripped,
        "sendgrid_configured": False,
        "smtp_configured": bool(GMAIL_ADDRESS and GMAIL_PASSWORD),
        "transport": "smtp",
        "from_email": FROM_EMAIL,
        "drip_check_interval_seconds": DRIP_CHECK_INTERVAL,
    }
'''
new_status = '''@app.get("/api/drip-status")
def drip_status():
    data = _load_leads()
    if not isinstance(data, dict) or not isinstance(data.get("leads"), list):
        raise HTTPException(status_code=503, detail="lead_store_unavailable")
    stats = data.get("stats") if isinstance(data.get("stats"), dict) else {}
    total = len(data["leads"])
    by_book = {}
    fully_dripped = 0
    schedule_keys = [step["key"] for step in DRIP_SCHEDULE]
    for lead in data["leads"]:
        if not isinstance(lead, dict):
            by_book["invalid_record"] = by_book.get("invalid_record", 0) + 1
            continue
        b = str(lead.get("book", "unknown") or "unknown")
        by_book[b] = by_book.get(b, 0) + 1
        sent_steps = lead.get("emails_sent")
        if isinstance(sent_steps, list) and sent_steps == schedule_keys:
            fully_dripped += 1

    return {
        "total_leads": total,
        "leads_by_book": by_book,
        "total_emails_sent": stats.get("emails_sent", 0),
        "fully_completed_sequences": fully_dripped,
        "sendgrid_configured": False,
        "smtp_configured": bool(GMAIL_ADDRESS and GMAIL_PASSWORD),
        "transport": "smtp",
        "from_email": FROM_EMAIL,
        "drip_check_interval_seconds": DRIP_CHECK_INTERVAL,
    }
'''
source = replace_once(source, old_status, new_status, 'drip status validation')
source = replace_once(
    source,
    '        "live_start_authorized": DRIP_SEND_MODE == "live",\n    }',
    '        "live_start_authorized": DRIP_SEND_MODE == "live",\n        "live_preflight_ok": DRIP_LIVE_PREFLIGHT_OK,\n    }',
    'health preflight flag',
)
source = replace_once(
    source,
    '                lead["pending_send"] = {"step": plan["step"], "attempted_at": now.isoformat()}\n                _save_leads(data)',
    '                if not GMAIL_ADDRESS or not GMAIL_PASSWORD:\n                    log.error("SMTP blocked before submission lead_ref=%s", plan["lead_ref"])\n                    continue\n\n                lead["pending_send"] = {"step": plan["step"], "attempted_at": now.isoformat()}\n                _save_leads(data)',
    'transport precheck before pending',
)
source = source.replace('FastAPI service that captures leads and runs a 5-email drip sequence\nfor each of the three KDP books.', 'FastAPI service that captures leads and runs governed 5-email drip sequences\nfor approved Dominion products.')
source = source.replace('app = FastAPI(title="KDP Email Drip Engine", version="1.0.0")', 'app = FastAPI(title="Dominion Email Drip Engine", version="1.0.0")')

# Keep live test fixtures faithful to the strengthened startup authorization contract.
tests = replace_once(
    tests,
    '        if mode == "live":\n            monkeypatch.setenv("DRIP_LIVE_AUTHORIZED_AT", datetime.now(timezone.utc).isoformat())\n        else:\n            monkeypatch.delenv("DRIP_LIVE_AUTHORIZED_AT", raising=False)',
    '        if mode == "live":\n            monkeypatch.setenv("DRIP_LIVE_AUTHORIZED_AT", datetime.now(timezone.utc).isoformat())\n            monkeypatch.setenv("DRIP_LIVE_PREFLIGHT_OK", "true")\n        else:\n            monkeypatch.delenv("DRIP_LIVE_AUTHORIZED_AT", raising=False)\n            monkeypatch.delenv("DRIP_LIVE_PREFLIGHT_OK", raising=False)',
    'live fixture preflight flag',
)

append = r'''


def test_non_object_suppression_document_fails_closed(tmp_path, monkeypatch):
    module, _, suppression = load_module(tmp_path, monkeypatch)
    suppression.write_text('[]', encoding='utf-8')
    assert module._suppression_state('customer@example.invalid') == 'error'


def test_capture_skips_non_object_legacy_rows(tmp_path, monkeypatch):
    module, leads_path, _ = load_module(tmp_path, monkeypatch)
    leads_path.write_text(json.dumps({'leads':[None, 'legacy-row'], 'stats':{'total_captured':0,'emails_sent':0}}), encoding='utf-8')
    result = module.capture_email(module.EmailCapture(email='new@example.invalid', name='New', source='sovereign_mind'))
    assert result['status'] == 'ok'
    saved = json.loads(leads_path.read_text(encoding='utf-8'))
    assert any(isinstance(row, dict) and row.get('email') == 'new@example.invalid' for row in saved['leads'])


def test_capture_fields_are_bounded(tmp_path, monkeypatch):
    module, _, _ = load_module(tmp_path, monkeypatch)
    with pytest.raises(module.HTTPException) as exc:
        module.capture_email(module.EmailCapture(email='new@example.invalid', name='N' * 121, source='sovereign_mind'))
    assert exc.value.status_code == 400
    with pytest.raises(module.HTTPException) as exc:
        module.capture_email(module.EmailCapture(email='new2@example.invalid', name='New', source='s' * 129))
    assert exc.value.status_code == 400


def test_status_counts_only_exact_completed_histories_and_tolerates_bad_rows(tmp_path, monkeypatch):
    module, leads_path, _ = load_module(tmp_path, monkeypatch)
    keys = [step['key'] for step in module.DRIP_SCHEDULE]
    good = due_lead(datetime.now(timezone.utc))
    good['emails_sent'] = keys.copy()
    bad = {**good, 'email':'bad@example.invalid', 'emails_sent':['welcome'] * len(keys)}
    leads_path.write_text(json.dumps({'leads':[None, good, bad], 'stats':{'emails_sent':5}}), encoding='utf-8')
    status = module.drip_status()
    assert status['fully_completed_sequences'] == 1
    assert status['leads_by_book']['invalid_record'] == 1


def test_missing_smtp_credentials_do_not_create_pending_send(tmp_path, monkeypatch):
    module, leads_path, _ = load_module(tmp_path, monkeypatch, mode='live')
    now = datetime.now(timezone.utc)
    data = {'leads':[due_lead(now)], 'stats':{'total_captured':1,'emails_sent':0}}
    leads_path.write_text(json.dumps(data), encoding='utf-8')
    module.GMAIL_PASSWORD = ''
    called = []
    monkeypatch.setattr(module, '_send_email', lambda *a, **k: called.append(True) or False)
    assert module._run_drip_cycle() == 0
    saved = json.loads(leads_path.read_text(encoding='utf-8'))
    assert 'pending_send' not in saved['leads'][0]
    assert called == []


def test_live_mode_requires_preflight_flag_even_with_fresh_authorization(tmp_path, monkeypatch):
    monkeypatch.setenv('DRIP_SEND_MODE', 'live')
    monkeypatch.setenv('DRIP_LIVE_AUTHORIZED_AT', datetime.now(timezone.utc).isoformat())
    monkeypatch.delenv('DRIP_LIVE_PREFLIGHT_OK', raising=False)
    module, _, _ = load_module(tmp_path, monkeypatch, mode=None)
    assert module.CONFIGURED_DRIP_SEND_MODE == 'live'
    assert module.DRIP_SEND_MODE == 'hold'
    assert module.DRIP_LIVE_PREFLIGHT_OK is False


def test_smtp_success_log_format_does_not_include_subject_literal():
    text = SOURCE.read_text(encoding='utf-8')
    assert 'SMTP sent lead_ref=%s subject=%s' not in text
'''
if 'def test_non_object_suppression_document_fails_closed' not in tests:
    tests += append

source_path.write_text(source, encoding='utf-8', newline='\n')
tests_path.write_text(tests, encoding='utf-8', newline='\n')
