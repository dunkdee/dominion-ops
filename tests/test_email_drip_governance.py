from __future__ import annotations

import importlib.util
import json
import smtplib
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

SOURCE = Path(__file__).parents[1] / "services" / "email_drip" / "email_drip.py"


def load_module(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, mode: str = "hold"):
    secret = tmp_path / "webhook_secret.key"
    secret.write_text("synthetic-test-secret", encoding="utf-8")
    leads = tmp_path / "leads.json"
    leads.write_text(json.dumps({"leads": [], "stats": {"total_captured": 0, "emails_sent": 0}}), encoding="utf-8")
    suppression = tmp_path / "suppression.json"
    suppression.write_text(json.dumps({"emails": []}), encoding="utf-8")
    monkeypatch.setenv("DRIP_WEBHOOK_SECRET_PATH", str(secret))
    monkeypatch.setenv("DRIP_LEADS_FILE", str(leads))
    monkeypatch.setenv("DRIP_SUPPRESSION_FILE", str(suppression))
    monkeypatch.setenv("DRIP_SEND_MODE", mode)
    monkeypatch.setenv("SMTP_EMAIL", "sender@example.invalid")
    monkeypatch.setenv("SMTP_PASSWORD", "synthetic-password")
    name = f"email_drip_test_{id(tmp_path)}_{mode}"
    spec = importlib.util.spec_from_file_location(name, SOURCE)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    module.log.disabled = True
    return module, leads, suppression


def due_lead(now: datetime, *, source: str = "sovereign_mind", book: str = "sovereign_mind") -> dict:
    return {
        "email": "customer@example.invalid",
        "name": "Customer",
        "source": source,
        "book": book,
        "captured_at": (now - timedelta(days=7)).isoformat(),
        "emails_sent": ["welcome", "value", "social_proof"],
        "last_sent_at": None,
        "unsubscribe_url": "",
    }


def test_default_mode_is_hold(tmp_path, monkeypatch):
    module, _, _ = load_module(tmp_path, monkeypatch)
    assert module.DRIP_SEND_MODE == "hold"


def test_preflight_is_scheduler_faithful_redacted_and_free_audit_safe(tmp_path, monkeypatch):
    module, _, _ = load_module(tmp_path, monkeypatch)
    now = datetime.now(timezone.utc)
    data = {"leads": [due_lead(now), {**due_lead(now), "email": ""}, {**due_lead(now), "source": "free-audit"}], "stats": {}}
    report = module._build_preflight_report(data=data, now=now)
    assert report["candidate_count"] == 1
    assert report["candidates"] == [{"book": "sovereign_mind", "step": "soft_sell", "subject": module.EMAILS_SOVEREIGN_MIND["soft_sell"]["subject"]}]
    assert report["status_counts"]["ghost_or_invalid"] == 1
    assert report["status_counts"]["no_email_content"] == 1
    assert report["free_audit_candidate_count"] == 0
    assert "customer@example.invalid" not in json.dumps(report)
    assert report["transport_invoked"] is False
    assert report["state_mutated"] is False


def test_hold_cycle_never_calls_transport_or_advances_state(tmp_path, monkeypatch):
    module, leads_path, _ = load_module(tmp_path, monkeypatch, mode="hold")
    now = datetime.now(timezone.utc)
    data = {"leads": [due_lead(now)], "stats": {"total_captured": 1, "emails_sent": 0}}
    leads_path.write_text(json.dumps(data), encoding="utf-8")
    calls = []
    monkeypatch.setattr(module, "_send_email", lambda *a, **k: calls.append(True) or True)
    assert module._run_drip_cycle() == 0
    assert calls == []
    assert json.loads(leads_path.read_text(encoding="utf-8")) == data


def test_failed_transport_does_not_advance_state(tmp_path, monkeypatch):
    module, leads_path, _ = load_module(tmp_path, monkeypatch, mode="live")
    now = datetime.now(timezone.utc)
    data = {"leads": [due_lead(now)], "stats": {"total_captured": 1, "emails_sent": 0}}
    leads_path.write_text(json.dumps(data), encoding="utf-8")
    monkeypatch.setattr(module, "_send_email", lambda *a, **k: False)
    assert module._run_drip_cycle() == 0
    assert json.loads(leads_path.read_text(encoding="utf-8")) == data


def test_success_advances_once_and_does_not_duplicate(tmp_path, monkeypatch):
    module, leads_path, _ = load_module(tmp_path, monkeypatch, mode="live")
    now = datetime.now(timezone.utc)
    data = {"leads": [due_lead(now)], "stats": {"total_captured": 1, "emails_sent": 0}}
    leads_path.write_text(json.dumps(data), encoding="utf-8")
    monkeypatch.setattr(module, "_send_email", lambda *a, **k: True)
    assert module._run_drip_cycle() == 1
    after = json.loads(leads_path.read_text(encoding="utf-8"))
    assert after["leads"][0]["emails_sent"].count("soft_sell") == 1
    assert after["stats"]["emails_sent"] == 1
    assert module._run_drip_cycle() == 0
    again = json.loads(leads_path.read_text(encoding="utf-8"))
    assert again["leads"][0]["emails_sent"].count("soft_sell") == 1
    assert again["stats"]["emails_sent"] == 1


def test_suppression_schema_failure_is_fail_closed(tmp_path, monkeypatch):
    module, _, suppression = load_module(tmp_path, monkeypatch)
    suppression.write_text('{"emails":"not-a-list"}', encoding="utf-8")
    report = module._build_preflight_report(data={"leads": [due_lead(datetime.now(timezone.utc))], "stats": {}})
    assert report["candidate_count"] == 0
    assert report["status_counts"]["suppression_error"] == 1


def test_smtp_failure_has_no_provider_or_outbox_fallback(tmp_path, monkeypatch):
    module, _, _ = load_module(tmp_path, monkeypatch, mode="live")
    monkeypatch.setenv("HOME", str(tmp_path))

    class FailingSMTP:
        def __init__(self, *args, **kwargs):
            raise OSError("synthetic smtp failure")

    monkeypatch.setattr(smtplib, "SMTP", FailingSMTP)
    assert module._send_email("customer@example.invalid", "Customer", "subject", "<p>body</p>") is False
    assert not (tmp_path / "email_outbox").exists()


def test_source_contains_no_legacy_transport_or_high_risk_claim_markers():
    text = SOURCE.read_text(encoding="utf-8")
    forbidden = ["SENDGRID_API_KEY", "sendgrid.SendGridAPIClient", "trying SendGrid", "email_outbox", "Johns Hopkins", "42% more likely", "dopamine and serotonin", "antidepressants", "$23,000", "14% more likely", "78% of Americans", "mailto:{FROM_EMAIL}?subject=Unsubscribe"]
    assert [item for item in forbidden if item in text] == []


def test_missing_suppression_store_is_fail_closed(tmp_path, monkeypatch):
    module, _, suppression = load_module(tmp_path, monkeypatch)
    suppression.unlink()
    report = module._build_preflight_report(
        data={"leads": [due_lead(datetime.now(timezone.utc))], "stats": {}}
    )
    assert report["candidate_count"] == 0
    assert report["status_counts"]["suppression_error"] == 1


def test_unknown_stored_book_is_fail_closed(tmp_path, monkeypatch):
    module, _, _ = load_module(tmp_path, monkeypatch)
    now = datetime.now(timezone.utc)
    lead = due_lead(now, source="website", book="unapproved_sequence")
    report = module._build_preflight_report(data={"leads": [lead], "stats": {}}, now=now)
    assert report["candidate_count"] == 0
    assert report["status_counts"]["invalid_book"] == 1


def test_capture_ignores_supplied_unsubscribe_url_and_logs_no_raw_source(tmp_path, monkeypatch):
    module, leads_path, _ = load_module(tmp_path, monkeypatch)
    payload = module.EmailCapture(
        email="customer@example.invalid",
        name="Customer",
        source="sovereign_mind private-note-should-not-be-logged",
        unsubscribe_url="https://attacker.invalid/unsubscribe",
    )
    result = module.capture_email(payload)
    assert result["status"] == "ok"
    lead = json.loads(leads_path.read_text(encoding="utf-8"))["leads"][0]
    assert lead["unsubscribe_url"].startswith(module.UNSUBSCRIBE_BASE_URL + "?")
    assert "attacker.invalid" not in lead["unsubscribe_url"]


def test_scheduler_escapes_customer_name_before_transport(tmp_path, monkeypatch):
    module, leads_path, _ = load_module(tmp_path, monkeypatch, mode="live")
    now = datetime.now(timezone.utc)
    lead = due_lead(now)
    lead["name"] = '<img src=x onerror="alert(1)">'
    data = {"leads": [lead], "stats": {"total_captured": 1, "emails_sent": 0}}
    leads_path.write_text(json.dumps(data), encoding="utf-8")
    captured = {}

    def transport(_email, _name, _subject, body):
        captured["body"] = body
        return False

    monkeypatch.setattr(module, "_send_email", transport)
    assert module._run_drip_cycle() == 0
    assert "<img src=x" not in captured["body"]
    assert "&lt;img src=x" in captured["body"]
    assert "attacker.invalid" not in captured["body"]


def test_service_defaults_to_loopback_binding():
    text = SOURCE.read_text(encoding="utf-8")
    assert 'host=os.getenv("DRIP_HOST", "127.0.0.1")' in text
    assert 'host="0.0.0.0"' not in text


@pytest.mark.parametrize(
    "bad_email",
    ["not-an-email", "bad@", "bad @example.com", "bad@example", "a..b@example.com", "a@-example.com"],
)
def test_capture_rejects_malformed_email(tmp_path, monkeypatch, bad_email):
    module, _, _ = load_module(tmp_path, monkeypatch)
    with pytest.raises(module.HTTPException) as exc:
        module.capture_email(module.EmailCapture(email=bad_email, source="sovereign_mind"))
    assert exc.value.status_code == 400
    assert exc.value.detail == "invalid_email"


def test_malformed_emails_sent_fails_closed_per_lead_without_blocking_valid_candidate(tmp_path, monkeypatch):
    module, _, _ = load_module(tmp_path, monkeypatch)
    now = datetime.now(timezone.utc)
    malformed = due_lead(now)
    malformed["emails_sent"] = None
    valid = due_lead(now)
    valid["email"] = "second@example.invalid"
    report = module._build_preflight_report(data={"leads": [malformed, valid], "stats": {}}, now=now)
    assert report["status_counts"]["invalid_emails_sent"] == 1
    assert report["candidate_count"] == 1
    assert report["candidates"][0]["step"] == "soft_sell"


def test_scheduler_and_capture_share_email_validation(tmp_path, monkeypatch):
    module, _, _ = load_module(tmp_path, monkeypatch)
    now = datetime.now(timezone.utc)
    invalid = due_lead(now)
    invalid["email"] = "bad@"
    report = module._build_preflight_report(data={"leads": [invalid], "stats": {}}, now=now)
    assert report["candidate_count"] == 0
    assert report["status_counts"]["ghost_or_invalid"] == 1
