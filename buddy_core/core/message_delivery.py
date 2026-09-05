"""Governed external-message delivery through the existing PrivateEmail SMTP lane.

This module has no authority of its own.  It accepts only the exact payload that
Buddy already froze, authenticated, granted, and redeemed.  The transport is
disabled unless BUDDY_EXTERNAL_MESSAGE_MODE=live and SMTP credentials are
present.

A successful receipt means the configured SMTP server accepted the complete
message with a 250 DATA response.  It does not claim inbox placement, reading,
or recipient action.
"""
from __future__ import annotations

import hashlib
import os
import re
import smtplib
import ssl
from datetime import datetime, timezone
from email.message import EmailMessage
from email.utils import format_datetime, make_msgid
from pathlib import Path
from typing import Any


_MAX_SUBJECT = 240
_MAX_BODY_BYTES = 256_000
_EMAIL_RE = re.compile(
    r"(?<![A-Za-z0-9.!#$%&'*+/=?^_`{|}~-])"
    r"([A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]{1,64}@"
    r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
    r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+)"
    r"(?![A-Za-z0-9-])"
)


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def normalize_email(value: Any) -> str:
    email = str(value or "").strip().lower()
    if not email or len(email) > 254 or email.count("@") != 1 or any(ch.isspace() for ch in email):
        return ""
    if not _EMAIL_RE.fullmatch(email):
        return ""
    local, domain = email.rsplit("@", 1)
    if local.startswith(".") or local.endswith(".") or ".." in local:
        return ""
    if any(len(label) > 63 or label.startswith("-") or label.endswith("-") for label in domain.split(".")):
        return ""
    return email


def _instruction_destination(instruction: str) -> str:
    matches = {normalize_email(m.group(1)) for m in _EMAIL_RE.finditer(instruction or "")}
    matches.discard("")
    if len(matches) != 1:
        return ""
    return next(iter(matches))


def _artifact_text(content: Any, staged_root: Path) -> str:
    """Resolve a staged artifact only when its path and digest are both valid."""
    if isinstance(content, str):
        return content
    if not isinstance(content, dict):
        return ""

    path_value = content.get("artifact")
    digest = str(content.get("sha256") or "").strip().lower()
    if path_value and re.fullmatch(r"[0-9a-f]{64}", digest):
        try:
            root = staged_root.expanduser().resolve(strict=True)
            path = Path(str(path_value)).expanduser().resolve(strict=True)
        except (OSError, RuntimeError):
            return ""
        if not path.is_file() or not path.is_relative_to(root):
            return ""
        try:
            raw = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            return ""
        if _sha256_text(raw) != digest:
            return ""
        return raw

    # Structured callers can supply an already-frozen body directly.
    for key in ("body_text", "body", "text", "preview"):
        value = content.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return ""


def _subject_and_body(raw: str) -> tuple[str, str]:
    text = (raw or "").replace("\r\n", "\n").strip()
    if not text:
        return "", ""
    lines = text.split("\n")
    first = lines[0].strip()
    match = re.match(r"^(?:subject\s*:\s*)(.+)$", first, flags=re.I)
    if match:
        subject = match.group(1).strip()
        body = "\n".join(lines[1:]).lstrip()
    else:
        # The default is created before Founder authorization, then included in
        # the frozen payload hash; it is not invented by the executor later.
        subject = "Message from Dominion Healing"
        body = text
    subject = re.sub(r"[\r\n]+", " ", subject).strip()[:_MAX_SUBJECT]
    return subject, body


def freeze_authorized_email_step(step: dict, outputs: list[Any], staged_root: Path) -> dict:
    """Canonicalize destination/content *before* the authorization request.

    The returned destination, subject, and body become part of the existing
    payload_fingerprint() input.  No recipient or message content is resolved
    after Founder approval.
    """
    frozen = dict(step)
    destination = normalize_email(frozen.get("destination"))
    if not destination:
        destination = _instruction_destination(str(frozen.get("instruction") or ""))
    if not destination:
        raise ValueError("external.message requires exactly one explicit email destination")

    supplied = frozen.get("content")
    if supplied is None:
        candidates = [value for value in outputs if value is not None]
        supplied = candidates[-1] if candidates else None
    raw = _artifact_text(supplied, staged_root)
    subject, body = _subject_and_body(raw)
    if not subject or not body:
        raise ValueError("external.message requires non-empty staged message content")
    if len(body.encode("utf-8")) > _MAX_BODY_BYTES:
        raise ValueError("external.message body exceeds bounded size")

    frozen["destination"] = destination
    frozen["content"] = {
        "subject": subject,
        "body_text": body,
        "content_sha256": _sha256_text(subject + "\n" + body),
    }
    return frozen


def _safe_provider_name(host: str) -> str:
    host = (host or "").strip().lower()
    if host == "mail.privateemail.com" or host.endswith(".privateemail.com"):
        return "privateemail_smtp"
    return "configured_smtp"


def deliver_authorized_email(payload: dict, *, smtp_factory=None) -> dict:
    """Deliver one already-authorized email and return truthful transport state.

    No retry is performed.  Once DATA transmission begins, a transport
    exception is treated as potentially delivered so the caller can return
    DELIVERED_UNVERIFIED instead of blindly sending a duplicate.
    """
    if not isinstance(payload, dict) or payload.get("capability") != "external.message":
        return {"delivered": False, "detail": "invalid authorized message payload"}

    destination = normalize_email(payload.get("destination"))
    content = payload.get("content")
    if not destination or not isinstance(content, dict):
        return {"delivered": False, "detail": "authorized destination/content unavailable"}

    subject = str(content.get("subject") or "").strip()
    body = str(content.get("body_text") or "")
    expected_hash = str(content.get("content_sha256") or "").strip().lower()
    actual_hash = _sha256_text(subject + "\n" + body)
    if (
        not subject
        or not body
        or len(subject) > _MAX_SUBJECT
        or len(body.encode("utf-8")) > _MAX_BODY_BYTES
        or expected_hash != actual_hash
    ):
        return {"delivered": False, "detail": "authorized message content failed integrity validation"}

    if os.getenv("BUDDY_EXTERNAL_MESSAGE_MODE", "hold").strip().lower() != "live":
        return {"delivered": False, "detail": "external.message delivery mode is hold"}

    host = os.getenv("SMTP_HOST", "mail.privateemail.com").strip()
    try:
        port = int(os.getenv("SMTP_PORT", "587"))
    except ValueError:
        return {"delivered": False, "detail": "SMTP port configuration invalid"}
    username = os.getenv("SMTP_EMAIL", os.getenv("EMAIL_ADDRESS", "")).strip()
    password = os.getenv("SMTP_PASSWORD", os.getenv("EMAIL_PASSWORD", ""))
    from_email = normalize_email(os.getenv("BUDDY_MESSAGE_FROM_EMAIL", os.getenv("DRIP_FROM_EMAIL", username)))
    from_name = os.getenv("BUDDY_MESSAGE_FROM_NAME", os.getenv("DRIP_FROM_NAME", "Dominion Healing")).strip()
    if not host or not (1 <= port <= 65535) or not username or not password or not from_email:
        return {"delivered": False, "detail": "SMTP delivery configuration unavailable"}

    timeout = 20
    try:
        configured_timeout = int(os.getenv("BUDDY_MESSAGE_SMTP_TIMEOUT", "20"))
        if 1 <= configured_timeout <= 60:
            timeout = configured_timeout
    except ValueError:
        pass

    from_domain = from_email.rsplit("@", 1)[-1]
    message_id = make_msgid(domain=from_domain)
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = f"{from_name} <{from_email}>" if from_name else from_email
    msg["To"] = destination
    msg["Date"] = format_datetime(datetime.now(timezone.utc))
    msg["Message-ID"] = message_id
    msg.set_content(body)

    factory = smtp_factory or smtplib.SMTP
    data_started = False
    try:
        with factory(host, port, timeout=timeout) as smtp:
            smtp.ehlo_or_helo_if_needed()
            smtp.starttls(context=ssl.create_default_context())
            smtp.ehlo()
            smtp.login(username, password)

            code, _ = smtp.mail(from_email)
            if int(code) not in {250, 251}:
                return {"delivered": False, "detail": f"SMTP MAIL rejected ({int(code)})"}
            code, _ = smtp.rcpt(destination)
            if int(code) not in {250, 251}:
                return {"delivered": False, "detail": f"SMTP recipient rejected ({int(code)})"}

            data_started = True
            code, response = smtp.data(msg.as_bytes())
            code = int(code)
            if code != 250:
                return {"delivered": False, "detail": f"SMTP DATA rejected ({code})"}

        delivered_at = _utc()
        response_bytes = response if isinstance(response, bytes) else str(response).encode("utf-8", errors="replace")
        destination_ref = _sha256_text(destination)[:16]
        evidence = [{
            "type": "smtp_acceptance",
            "message_id": message_id,
            "provider": _safe_provider_name(host),
            "delivered_at": delivered_at,
            "delivery_status": "accepted",
            "smtp_response_code": 250,
            "smtp_response_sha256": hashlib.sha256(response_bytes).hexdigest(),
            "content_sha256": actual_hash,
            "destination_sha256": _sha256_text(destination),
            "receipt_basis": "SMTP DATA accepted; Message-ID was inside the accepted message",
        }]
        return {
            "delivered": True,
            "result": {
                "status": "SMTP_ACCEPTED",
                "message_id": message_id,
                "provider": _safe_provider_name(host),
                "delivered_at": delivered_at,
                "destination_ref": destination_ref,
                "content_sha256": actual_hash,
            },
            "evidence": evidence,
        }
    except Exception as exc:  # transport errors are deliberately classified by stage
        if data_started:
            return {
                "delivered": True,
                "result": {
                    "status": "DELIVERY_STATE_AMBIGUOUS",
                    "message_id": message_id,
                    "provider": _safe_provider_name(host),
                    "destination_ref": _sha256_text(destination)[:16],
                    "content_sha256": actual_hash,
                    "do_not_retry_without_reconciliation": True,
                },
                "evidence": [],
                "detail": f"SMTP state ambiguous after DATA began ({type(exc).__name__})",
            }
        return {
            "delivered": False,
            "detail": f"SMTP delivery failed before DATA ({type(exc).__name__})",
        }
