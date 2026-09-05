from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from buddy_core.core import message_delivery


class FakeSMTP:
    instances = []
    data_code = 250
    data_response = b"2.0.0 queued as TEST123"
    fail_stage = None

    def __init__(self, host, port, timeout):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.mail_from = None
        self.rcpt_to = None
        self.data_bytes = None
        self.__class__.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def ehlo_or_helo_if_needed(self):
        if self.fail_stage == "connect":
            raise OSError("connect failed")

    def starttls(self, context=None):
        if self.fail_stage == "tls":
            raise OSError("tls failed")
        return 220, b"ready"

    def ehlo(self):
        return 250, b"ok"

    def login(self, username, password):
        if self.fail_stage == "login":
            raise OSError("login failed")
        self.username = username
        self.password = password
        return 235, b"ok"

    def mail(self, sender):
        self.mail_from = sender
        return 250, b"ok"

    def rcpt(self, recipient):
        self.rcpt_to = recipient
        return 250, b"ok"

    def data(self, raw):
        self.data_bytes = raw
        if self.fail_stage == "data":
            raise TimeoutError("ambiguous after DATA")
        return self.data_code, self.data_response


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    FakeSMTP.instances.clear()
    FakeSMTP.data_code = 250
    FakeSMTP.data_response = b"2.0.0 queued as TEST123"
    FakeSMTP.fail_stage = None
    monkeypatch.setenv("BUDDY_EXTERNAL_MESSAGE_MODE", "live")
    monkeypatch.setenv("SMTP_HOST", "mail.privateemail.com")
    monkeypatch.setenv("SMTP_PORT", "587")
    monkeypatch.setenv("SMTP_EMAIL", "sender@dominionhealing.org")
    monkeypatch.setenv("SMTP_PASSWORD", "super-secret-password")
    monkeypatch.setenv("BUDDY_MESSAGE_FROM_EMAIL", "sender@dominionhealing.org")
    monkeypatch.setenv("BUDDY_MESSAGE_FROM_NAME", "Dominion Healing")


def _payload(destination="recipient@example.com", body="Approved body", subject="Approved subject"):
    digest = hashlib.sha256(f"{subject}\n{body}".encode()).hexdigest()
    return {
        "capability": "external.message",
        "instruction": f"Send this email to {destination}",
        "destination": destination,
        "content": {
            "subject": subject,
            "body_text": body,
            "content_sha256": digest,
        },
    }


def test_freeze_binds_explicit_destination_and_exact_staged_artifact(tmp_path):
    staged = tmp_path / "staged"
    staged.mkdir()
    artifact = staged / "message.md"
    raw = "Subject: Exact approved subject\n\nExact approved body.\n"
    artifact.write_text(raw, encoding="utf-8")
    output = {
        "artifact": str(artifact),
        "sha256": hashlib.sha256(raw.encode()).hexdigest(),
        "preview": "MUST NOT BE USED WHEN VERIFIED ARTIFACT EXISTS",
    }
    frozen = message_delivery.freeze_authorized_email_step(
        {"capability": "external.message", "instruction": "Email recipient@example.com now"},
        [output],
        staged,
    )
    assert frozen["destination"] == "recipient@example.com"
    assert frozen["content"]["subject"] == "Exact approved subject"
    assert frozen["content"]["body_text"] == "Exact approved body."
    assert "MUST NOT BE USED" not in frozen["content"]["body_text"]


def test_freeze_rejects_missing_or_multiple_destinations(tmp_path):
    with pytest.raises(ValueError):
        message_delivery.freeze_authorized_email_step(
            {"capability": "external.message", "instruction": "Send this email"},
            ["body"],
            tmp_path,
        )
    with pytest.raises(ValueError):
        message_delivery.freeze_authorized_email_step(
            {"capability": "external.message", "instruction": "Send a@example.com and b@example.com"},
            ["body"],
            tmp_path,
        )


def test_smtp_250_acceptance_returns_capability_receipt():
    outcome = message_delivery.deliver_authorized_email(_payload(), smtp_factory=FakeSMTP)
    assert outcome["delivered"] is True
    assert outcome["result"]["status"] == "SMTP_ACCEPTED"
    evidence = outcome["evidence"][0]
    assert evidence["provider"] == "privateemail_smtp"
    assert evidence["smtp_response_code"] == 250
    assert evidence["delivery_status"] == "accepted"
    assert evidence["message_id"] == outcome["result"]["message_id"]
    sent = FakeSMTP.instances[-1]
    assert sent.rcpt_to == "recipient@example.com"
    assert b"Approved body" in sent.data_bytes
    assert b"Approved subject" in sent.data_bytes


def test_only_authorized_destination_and_content_are_sent():
    payload = _payload(destination="approved@example.com", body="ONLY APPROVED BODY", subject="ONLY APPROVED SUBJECT")
    payload["ambient_unapproved"] = {
        "destination": "attacker@example.com",
        "body": "UNAPPROVED BODY",
    }
    outcome = message_delivery.deliver_authorized_email(payload, smtp_factory=FakeSMTP)
    assert outcome["delivered"] is True
    sent = FakeSMTP.instances[-1]
    assert sent.rcpt_to == "approved@example.com"
    assert b"ONLY APPROVED BODY" in sent.data_bytes
    assert b"UNAPPROVED BODY" not in sent.data_bytes
    assert b"attacker@example.com" not in sent.data_bytes


def test_integrity_mismatch_blocks_before_transport():
    payload = _payload()
    payload["content"]["body_text"] = "tampered after authorization"
    outcome = message_delivery.deliver_authorized_email(payload, smtp_factory=FakeSMTP)
    assert outcome["delivered"] is False
    assert "integrity" in outcome["detail"]
    assert FakeSMTP.instances == []


def test_hold_mode_and_missing_credentials_block_before_transport(monkeypatch):
    monkeypatch.setenv("BUDDY_EXTERNAL_MESSAGE_MODE", "hold")
    assert message_delivery.deliver_authorized_email(_payload(), smtp_factory=FakeSMTP)["delivered"] is False
    assert FakeSMTP.instances == []
    monkeypatch.setenv("BUDDY_EXTERNAL_MESSAGE_MODE", "live")
    monkeypatch.delenv("SMTP_PASSWORD")
    monkeypatch.delenv("EMAIL_PASSWORD", raising=False)
    assert message_delivery.deliver_authorized_email(_payload(), smtp_factory=FakeSMTP)["delivered"] is False
    assert FakeSMTP.instances == []


def test_invalid_destination_blocks_before_transport():
    payload = _payload()
    payload["destination"] = "not-an-email"
    outcome = message_delivery.deliver_authorized_email(payload, smtp_factory=FakeSMTP)
    assert outcome["delivered"] is False
    assert FakeSMTP.instances == []


def test_pre_data_failure_is_blocked_and_secret_never_leaks():
    FakeSMTP.fail_stage = "login"
    outcome = message_delivery.deliver_authorized_email(_payload(), smtp_factory=FakeSMTP)
    assert outcome["delivered"] is False
    assert "super-secret-password" not in repr(outcome)


def test_post_data_transport_failure_is_ambiguous_and_not_retryable():
    FakeSMTP.fail_stage = "data"
    outcome = message_delivery.deliver_authorized_email(_payload(), smtp_factory=FakeSMTP)
    assert outcome["delivered"] is True
    assert outcome["evidence"] == []
    assert outcome["result"]["status"] == "DELIVERY_STATE_AMBIGUOUS"
    assert outcome["result"]["do_not_retry_without_reconciliation"] is True
    assert len(FakeSMTP.instances) == 1


def test_server_rejection_is_not_claimed_as_delivery():
    FakeSMTP.data_code = 554
    FakeSMTP.data_response = b"rejected"
    outcome = message_delivery.deliver_authorized_email(_payload(), smtp_factory=FakeSMTP)
    assert outcome["delivered"] is False
    assert "554" in outcome["detail"]
