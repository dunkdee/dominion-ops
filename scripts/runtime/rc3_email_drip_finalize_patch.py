#!/usr/bin/env python3
from pathlib import Path

SOURCE = Path('services/email_drip/email_drip.py')
TESTS = Path('tests/test_email_drip_governance.py')
source = SOURCE.read_text(encoding='utf-8')


def replace_once(old: str, new: str, label: str) -> None:
    global source
    count = source.count(old)
    if count != 1:
        raise SystemExit(f'{label}: expected exactly one match, found {count}')
    source = source.replace(old, new, 1)


replace_once(
    'import hashlib\nimport html as html_lib',
    'import hashlib\nimport html as html_lib\nimport ssl',
    'ssl import',
)
replace_once(
    'DRIP_CHECK_INTERVAL = int(os.getenv("DRIP_CHECK_INTERVAL", "3600"))  # seconds\nDRIP_SEND_MODE = os.getenv("DRIP_SEND_MODE", "hold").strip().lower()\nif DRIP_SEND_MODE not in {"hold", "live"}:\n    raise RuntimeError("DRIP_SEND_MODE must be hold or live")',
    'DRIP_CHECK_INTERVAL = int(os.getenv("DRIP_CHECK_INTERVAL", "3600"))  # seconds\nif DRIP_CHECK_INTERVAL <= 0:\n    raise RuntimeError("DRIP_CHECK_INTERVAL must be positive")\nCONFIGURED_DRIP_SEND_MODE = os.getenv("DRIP_SEND_MODE", "hold").strip().lower()\nif CONFIGURED_DRIP_SEND_MODE not in {"hold", "live"}:\n    raise RuntimeError("DRIP_SEND_MODE must be hold or live")\nDRIP_LIVE_AUTHORIZED_AT = os.getenv("DRIP_LIVE_AUTHORIZED_AT", "").strip()\nDRIP_LIVE_AUTH_MAX_AGE_SECONDS = int(os.getenv("DRIP_LIVE_AUTH_MAX_AGE_SECONDS", "900"))\nif DRIP_LIVE_AUTH_MAX_AGE_SECONDS <= 0:\n    raise RuntimeError("DRIP_LIVE_AUTH_MAX_AGE_SECONDS must be positive")\n\ndef _live_start_authorized(now=None):\n    if CONFIGURED_DRIP_SEND_MODE != "live":\n        return False\n    if not DRIP_LIVE_AUTHORIZED_AT:\n        return False\n    current = now or datetime.now(timezone.utc)\n    try:\n        authorized = datetime.fromisoformat(DRIP_LIVE_AUTHORIZED_AT.replace("Z", "+00:00"))\n    except ValueError:\n        return False\n    if authorized.tzinfo is None:\n        return False\n    age = (current - authorized).total_seconds()\n    return 0 <= age <= DRIP_LIVE_AUTH_MAX_AGE_SECONDS\n\nDRIP_SEND_MODE = "live" if _live_start_authorized() else "hold"',
    'live startup authorization',
)
replace_once(
    'def _load_leads() -> dict:\n    if LEADS_FILE.exists():\n        with open(LEADS_FILE, "r", encoding="utf-8") as f:\n            return json.load(f)\n    return {"leads": [], "stats": {"total_captured": 0, "emails_sent": 0}}',
    'def _load_leads() -> dict:\n    if not LEADS_FILE.exists():\n        raise FileNotFoundError(f"Lead store missing: {LEADS_FILE}")\n    with open(LEADS_FILE, "r", encoding="utf-8") as f:\n        return json.load(f)',
    'lead store fail closed',
)
replace_once(
    '    tmp = LEADS_FILE.parent / f".{LEADS_FILE.name}.{os.getpid()}.{threading.get_ident()}.tmp"\n    try:\n        with tmp.open("w", encoding="utf-8") as handle:\n            json.dump(data, handle, indent=2, default=str)\n            handle.flush()\n            os.fsync(handle.fileno())\n        os.chmod(tmp, mode)',
    '    tmp = LEADS_FILE.parent / f".{LEADS_FILE.name}.{os.getpid()}.{threading.get_ident()}.tmp"\n    try:\n        fd_tmp = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)\n        with os.fdopen(fd_tmp, "w", encoding="utf-8") as handle:\n            json.dump(data, handle, indent=2, default=str)\n            handle.flush()\n            os.fsync(handle.fileno())\n        os.chmod(tmp, mode)',
    'restrictive temp file creation',
)
replace_once(
    '        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20) as srv:\n            srv.starttls()',
    '        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20) as srv:\n            srv.starttls(context=ssl.create_default_context())',
    'smtp certificate verification',
)
replace_once(
    '@app.post("/api/run-drip")\ndef run_drip_manual():\n    sent = _run_drip_cycle()\n    return {"status": "ok", "emails_sent_this_cycle": sent}',
    '@app.post("/api/run-drip")\ndef run_drip_manual():\n    raise HTTPException(status_code=403, detail="manual_drip_disabled")',
    'manual trigger disabled',
)
replace_once(
    'def _plan_due_message(lead: dict, now: datetime) -> dict:\n    """Return one scheduler-faithful candidate or a non-send status; never mutate state."""\n    raw_email = str(lead.get("email", ""))',
    'def _plan_due_message(lead: dict, now: datetime) -> dict:\n    """Return one scheduler-faithful candidate or a non-send status; never mutate state."""\n    if not isinstance(lead, dict):\n        return {"status": "invalid_lead_record", "lead_ref": "missing"}\n    raw_email = str(lead.get("email", ""))',
    'non-mapping lead fail closed',
)
replace_once(
    '    sent_raw = lead.get("emails_sent", [])\n    if not isinstance(sent_raw, list):\n        return {"status": "invalid_emails_sent", "lead_ref": _lead_ref(email)}\n    already_sent = {str(value) for value in sent_raw}',
    '    if "emails_sent" not in lead:\n        return {"status": "invalid_emails_sent", "lead_ref": _lead_ref(email)}\n    sent_raw = lead.get("emails_sent")\n    if not isinstance(sent_raw, list):\n        return {"status": "invalid_emails_sent", "lead_ref": _lead_ref(email)}\n    if lead.get("pending_send"):\n        return {"status": "send_reconciliation_required", "lead_ref": _lead_ref(email)}\n    already_sent = {str(value) for value in sent_raw}',
    'send history and pending reconciliation',
)
old_loop = '''    for step in DRIP_SCHEDULE:
        if step["key"] in already_sent or days_since < step["day"]:
            continue
        content = emails.get(step["key"])
        if not content:
            continue
        unsubscribe_url = _unsubscribe_url(email)
        return {
            "status": "candidate",
            "email": email,
            "lead_ref": _lead_ref(email),
            "name": lead.get("name") or "Friend",
            "book": book,
            "step": step["key"],
            "subject": content["subject"],
            "body": content["body"],
            "unsubscribe_url": unsubscribe_url,
        }
    return {"status": "no_due_email", "book": book, "lead_ref": _lead_ref(email)}'''
new_loop = '''    schedule_keys = [step["key"] for step in DRIP_SCHEDULE]
    if any(key not in schedule_keys for key in already_sent):
        return {"status": "invalid_send_history", "book": book, "lead_ref": _lead_ref(email)}
    expected_prefix = schedule_keys[:len(sent_raw)]
    if sent_raw != expected_prefix:
        return {"status": "invalid_send_history", "book": book, "lead_ref": _lead_ref(email)}

    next_index = len(sent_raw)
    if next_index >= len(DRIP_SCHEDULE):
        return {"status": "no_due_email", "book": book, "lead_ref": _lead_ref(email)}
    step = DRIP_SCHEDULE[next_index]
    if days_since < step["day"]:
        return {"status": "no_due_email", "book": book, "lead_ref": _lead_ref(email)}

    if next_index > 0:
        last_raw = str(lead.get("last_sent_at", "")).strip()
        if not last_raw:
            return {"status": "invalid_send_history", "book": book, "lead_ref": _lead_ref(email)}
        try:
            last_sent = datetime.fromisoformat(last_raw.replace("Z", "+00:00"))
        except ValueError:
            return {"status": "invalid_send_history", "book": book, "lead_ref": _lead_ref(email)}
        if last_sent.tzinfo is None:
            return {"status": "invalid_send_history", "book": book, "lead_ref": _lead_ref(email)}
        required_gap_days = step["day"] - DRIP_SCHEDULE[next_index - 1]["day"]
        if (now - last_sent) < timedelta(days=required_gap_days):
            return {"status": "spacing_hold", "book": book, "lead_ref": _lead_ref(email)}

    content = emails.get(step["key"])
    if not content:
        return {"status": "no_email_content", "book": book, "lead_ref": _lead_ref(email)}
    unsubscribe_url = _unsubscribe_url(email)
    return {
        "status": "candidate",
        "email": email,
        "lead_ref": _lead_ref(email),
        "name": lead.get("name") or "Friend",
        "book": book,
        "step": step["key"],
        "subject": content["subject"],
        "body": content["body"],
        "unsubscribe_url": unsubscribe_url,
    }'''
replace_once(old_loop, new_loop, 'sequential spacing planner')
replace_once(
    '                safe_name = html_lib.escape(str(plan["name"]), quote=True)\n                body = plan["body"].replace("{{name}}", safe_name)\n                safe_url = html_lib.escape(plan["unsubscribe_url"], quote=True)\n                disclaimer = BOOK_DISCLAIMERS.get(plan["book"], "")\n                body += \'<hr style="margin-top:28px;border:0;border-top:1px solid #ddd;">\'\n                if disclaimer:\n                    body += f\'<p style="font-size:12px;color:#777">{html_lib.escape(disclaimer)}</p>\'\n                body += \'<p style="font-size:12px;color:#777">You received this because you signed up at Dominion Healing. \' + f\'<a href="{safe_url}">Unsubscribe</a></p>\'\n\n                if _send_email(plan["email"], plan["name"], plan["subject"], body):\n                    lead.setdefault("emails_sent", []).append(plan["step"])\n                    lead["last_sent_at"] = now.isoformat()\n                    data["stats"]["emails_sent"] += 1\n                    sent_count += 1\n                    changed = True',
    '                safe_name = html_lib.escape(str(plan["name"]), quote=True)\n                body = plan["body"].replace("{{name}}", safe_name)\n                subject = str(plan["subject"]).replace("{{name}}", str(plan["name"]))\n                safe_url = html_lib.escape(plan["unsubscribe_url"], quote=True)\n                disclaimer = BOOK_DISCLAIMERS.get(plan["book"], "")\n                footer = \'<hr style="margin-top:28px;border:0;border-top:1px solid #ddd;">\'\n                if disclaimer:\n                    footer += f\'<p style="font-size:12px;color:#777">{html_lib.escape(disclaimer)}</p>\'\n                footer += \'<p style="font-size:12px;color:#777">You received this because you signed up at Dominion Healing. \' + f\'<a href="{safe_url}">Unsubscribe</a></p>\'\n                if "</body>" not in body:\n                    log.error("Email template missing closing body; send blocked lead_ref=%s", plan["lead_ref"])\n                    continue\n                body = body.replace("</body>", footer + "</body>", 1)\n\n                lead["pending_send"] = {"step": plan["step"], "attempted_at": now.isoformat()}\n                _save_leads(data)\n                if _send_email(plan["email"], plan["name"], subject, body):\n                    lead.setdefault("emails_sent", []).append(plan["step"])\n                    lead["last_sent_at"] = now.isoformat()\n                    lead.pop("pending_send", None)\n                    data["stats"]["emails_sent"] += 1\n                    _save_leads(data)\n                    sent_count += 1\n                else:\n                    log.error("Send outcome requires reconciliation lead_ref=%s step=%s", plan["lead_ref"], plan["step"])',
    'durable pending send and footer placement',
)
replace_once('    changed = False\n    try:', '    try:', 'remove changed flag')
replace_once(
    '\n            if changed:\n                _save_leads(data)\n    except (RuntimeError, json.JSONDecodeError, OSError, Timeout, TypeError, ValueError) as exc:',
    '\n    except (RuntimeError, json.JSONDecodeError, OSError, Timeout, TypeError, ValueError, FileNotFoundError) as exc:',
    'per-send persistence cleanup',
)
replace_once(
    '@app.on_event("startup")\ndef start_drip_scheduler():\n    # Ensure leads file exists\n    if not LEADS_FILE.exists():\n        _save_leads({"leads": [], "stats": {"total_captured": 0, "emails_sent": 0}})\n    thread = threading.Thread(target=_drip_loop, daemon=True)',
    '@app.on_event("startup")\ndef start_drip_scheduler():\n    if not LEADS_FILE.exists():\n        raise RuntimeError("Lead store missing; explicit initialization required")\n    thread = threading.Thread(target=_drip_loop, daemon=True)',
    'startup store fail closed',
)
replace_once(
    '        "send_mode": DRIP_SEND_MODE,',
    '        "send_mode": DRIP_SEND_MODE,\n        "configured_send_mode": CONFIGURED_DRIP_SEND_MODE,\n        "live_start_authorized": DRIP_SEND_MODE == "live",',
    'health activation evidence',
)
SOURCE.write_text(source, encoding='utf-8', newline='\n')

extra_tests = r'''


def test_manual_run_endpoint_is_disabled(tmp_path, monkeypatch):
    module, _, _ = load_module(tmp_path, monkeypatch)
    with pytest.raises(module.HTTPException) as exc:
        module.run_drip_manual()
    assert exc.value.status_code == 403


def test_missing_lead_store_fails_closed(tmp_path, monkeypatch):
    module, leads_path, _ = load_module(tmp_path, monkeypatch)
    leads_path.unlink()
    with pytest.raises(FileNotFoundError):
        module._load_leads()


def test_non_mapping_lead_is_invalid(tmp_path, monkeypatch):
    module, _, _ = load_module(tmp_path, monkeypatch)
    plan = module._plan_due_message(None, datetime.now(timezone.utc))
    assert plan['status'] == 'invalid_lead_record'


def test_missing_send_history_is_not_assumed_empty(tmp_path, monkeypatch):
    module, _, _ = load_module(tmp_path, monkeypatch)
    now = datetime.now(timezone.utc)
    lead = due_lead(now)
    lead.pop('emails_sent')
    assert module._plan_due_message(lead, now)['status'] == 'invalid_emails_sent'


def test_pending_send_blocks_retry(tmp_path, monkeypatch):
    module, _, _ = load_module(tmp_path, monkeypatch)
    now = datetime.now(timezone.utc)
    lead = due_lead(now)
    lead['pending_send'] = {'step': 'welcome', 'attempted_at': now.isoformat()}
    assert module._plan_due_message(lead, now)['status'] == 'send_reconciliation_required'


def test_overdue_sequence_preserves_spacing(tmp_path, monkeypatch):
    module, _, _ = load_module(tmp_path, monkeypatch)
    now = datetime.now(timezone.utc)
    lead = due_lead(now - timedelta(days=20))
    lead['emails_sent'] = ['welcome']
    lead['last_sent_at'] = now.isoformat()
    plan = module._plan_due_message(lead, now)
    assert plan['status'] == 'spacing_hold'


def test_footer_inserted_inside_html_and_failed_transport_leaves_pending(tmp_path, monkeypatch):
    module, leads_path, _ = load_module(tmp_path, monkeypatch, mode='hold')
    module.DRIP_SEND_MODE = 'live'
    now = datetime.now(timezone.utc)
    lead = due_lead(now)
    leads_path.write_text(json.dumps({'leads':[lead], 'stats':{'total_captured':1,'emails_sent':0}}), encoding='utf-8')
    captured = {}
    def transport(_email, _name, _subject, body):
        captured['body'] = body
        return False
    monkeypatch.setattr(module, '_send_email', transport)
    assert module._run_drip_cycle() == 0
    assert captured['body'].index('Unsubscribe') < captured['body'].index('</body>')
    saved = json.loads(leads_path.read_text(encoding='utf-8'))['leads'][0]
    assert saved['pending_send']['step'] == 'welcome'
    assert saved['emails_sent'] == []


def test_live_mode_requires_fresh_start_authorization(tmp_path, monkeypatch):
    monkeypatch.setenv('DRIP_SEND_MODE', 'live')
    monkeypatch.delenv('DRIP_LIVE_AUTHORIZED_AT', raising=False)
    module, _, _ = load_module(tmp_path, monkeypatch, mode=None)
    assert module.CONFIGURED_DRIP_SEND_MODE == 'live'
    assert module.DRIP_SEND_MODE == 'hold'


def test_nonpositive_interval_rejected(tmp_path, monkeypatch):
    monkeypatch.setenv('DRIP_CHECK_INTERVAL', '0')
    with pytest.raises(RuntimeError):
        load_module(tmp_path, monkeypatch)


def test_default_send_mode_is_hold_when_unset(tmp_path, monkeypatch):
    monkeypatch.delenv('DRIP_SEND_MODE', raising=False)
    module, _, _ = load_module(tmp_path, monkeypatch, mode=None)
    assert module.CONFIGURED_DRIP_SEND_MODE == 'hold'
    assert module.DRIP_SEND_MODE == 'hold'
'''

tests = TESTS.read_text(encoding='utf-8')
if 'test_manual_run_endpoint_is_disabled' not in tests:
    TESTS.write_text(tests + extra_tests, encoding='utf-8', newline='\n')
