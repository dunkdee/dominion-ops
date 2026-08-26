from __future__ import annotations
import hashlib
import json
import time
import uuid
from fastapi import HTTPException

from .db import tx
from .models import RadahEnvelope
from .security import verify_radah_signature


def _payload_hash(payload: dict) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


def enforce_radah(
    envelope: RadahEnvelope,
    *,
    expected_action: str,
    expected_target: str,
    signature: str | None,
    signature_timestamp: str | None,
) -> None:
    """
    Fail closed. A revenue score never authorizes execution.
    """
    now = int(time.time())

    if envelope.action != expected_action:
        raise HTTPException(status_code=403, detail="RADAH action mismatch")
    if envelope.target != expected_target:
        raise HTTPException(status_code=403, detail="RADAH target mismatch")
    if envelope.issued_at > now + 60:
        raise HTTPException(status_code=403, detail="RADAH decision issued in the future")
    if envelope.expires_at <= now:
        raise HTTPException(status_code=403, detail="RADAH authorization expired")
    if envelope.decision == "HOLD":
        raise HTTPException(status_code=423, detail=f"RADAH HOLD: {envelope.reason}")
    if envelope.decision == "DENY":
        raise HTTPException(status_code=403, detail=f"RADAH DENY: {envelope.reason}")
    if envelope.decision != "ALLOW":
        raise HTTPException(status_code=403, detail="RADAH authorization required")

    payload = envelope.model_dump()
    verify_radah_signature(payload, signature, signature_timestamp)

    ph = _payload_hash(payload)
    decision_id = str(uuid.uuid4())
    try:
        with tx(write=True) as conn:
            conn.execute("""
                INSERT INTO radah_decisions(
                    decision_id, correlation_id, action, target, decision, reason,
                    authority_version, expires_at, issued_at, payload_hash
                ) VALUES(?,?,?,?,?,?,?,?,?,?)
            """, (
                decision_id, envelope.correlation_id, envelope.action,
                envelope.target, envelope.decision, envelope.reason,
                envelope.authority_version, envelope.expires_at,
                envelope.issued_at, ph
            ))
    except Exception as exc:
        # Reuse/replay of a correlation ID is denied.
        raise HTTPException(status_code=409, detail="RADAH decision already consumed") from exc
