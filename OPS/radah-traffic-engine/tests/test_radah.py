import os, time, tempfile
os.environ["ENVIRONMENT"] = "test"
os.environ["API_KEY"] = "test-key"
os.environ["AUDIT_HMAC_KEY"] = "test-audit-key"
os.environ["RADAH_SHARED_SECRET"] = "test-radah-key"
os.environ["REQUIRE_RADAH_SIGNATURE"] = "false"
os.environ["DB_PATH"] = tempfile.mktemp(suffix=".db")

from fastapi import HTTPException
from app.db import init_db
from app.models import RadahEnvelope
from app.radah import enforce_radah


def env(decision="ALLOW"):
    now = int(time.time())
    return RadahEnvelope(
        correlation_id="corr-test-12345",
        action="CREATE_OPPORTUNITY",
        target="opportunity:test-lane",
        decision=decision,
        reason="test",
        authority_version="test-v1",
        issued_at=now,
        expires_at=now + 60,
    )


def test_hold_fails_closed():
    init_db()
    try:
        enforce_radah(
            env("HOLD"),
            expected_action="CREATE_OPPORTUNITY",
            expected_target="opportunity:test-lane",
            signature=None,
            signature_timestamp=None,
        )
        assert False
    except HTTPException as e:
        assert e.status_code == 423
