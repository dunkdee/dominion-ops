import os
import tempfile
import time

os.environ["ENVIRONMENT"] = "test"
os.environ["API_KEY"] = "test-key"
os.environ["AUDIT_HMAC_KEY"] = "test-audit-key"
os.environ["RADAH_SHARED_SECRET"] = "test-radah-key"
os.environ["REQUIRE_RADAH_SIGNATURE"] = "false"
os.environ["ENABLE_PUBLIC_LEAD_CAPTURE"] = "false"
os.environ["DB_PATH"] = tempfile.mktemp(suffix=".db")

from fastapi.testclient import TestClient

from app.db import init_db, tx
from app.main import app


def radah(corr: str, action: str, target: str):
    now = int(time.time())
    return {
        "correlation_id": corr,
        "action": action,
        "target": target,
        "decision": "ALLOW",
        "reason": "verified test authority",
        "authority_version": "test-v1",
        "issued_at": now,
        "expires_at": now + 120,
    }


def seed_lead():
    init_db()
    now = int(time.time())
    lead_id = "lead-handoff-001"
    with tx(write=True) as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO childcare_leads(
                id,idempotency_key,business_name,contact_name,work_email,state,county,
                employee_count,estimated_annual_childcare_budget,company_website,
                consent_recorded,status,created_at,expires_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                lead_id,"idem-lead-handoff-001","Example Co","Jane Owner",
                "jane@example.test","TX","Dallas",25,36000,"https://example.test",
                1,"PENDING_RADAH_HANDOFF",now,now+86400,
            ),
        )
    return lead_id


def test_provider_descriptor_is_privacy_safe():
    with TestClient(app) as client:
        r = client.get("/v1/tools/employer-childcare/providers")
        assert r.status_code == 200
        p = r.json()["providers"][0]
        assert p["id"] == "tootris"
        assert p["published_reward_usd"] == 250
        assert p["transmits_saved_lead_data"] is False


def test_governed_handoff_redirect_and_confirmed_conversion():
    lead_id = seed_lead()
    with TestClient(app, follow_redirects=False) as client:
        body = {
            "radah": radah(
                "corr-handoff-create-001",
                "AUTHORIZE_CHILDCARE_HANDOFF",
                f"childcare-lead:{lead_id}",
            ),
            "provider": "tootris",
            "ttl_minutes": 60,
        }
        r = client.post(
            f"/v1/tools/employer-childcare/leads/{lead_id}/handoff",
            json=body,
            headers={"X-API-Key": "test-key"},
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["authorized"] is True
        assert data["provider"]["transmits_saved_lead_data"] is False

        path = data["handoff_url"].replace("http://testserver", "")
        click = client.get(path)
        assert click.status_code == 302
        assert click.headers["location"] == "https://go.tootris.com/refer"

        conversion = {
            "radah": radah(
                "corr-handoff-convert-001",
                "CONFIRM_CHILDCARE_CONVERSION",
                f"childcare-handoff:{data['handoff_id']}",
            ),
            "provider_receipt_id": "provider-confirmation-001",
            "confirmed_reward_usd": 250,
        }
        c = client.post(
            f"/v1/tools/employer-childcare/handoffs/{data['handoff_id']}/conversion",
            json=conversion,
            headers={"X-API-Key": "test-key"},
        )
        assert c.status_code == 200, c.text
        assert c.json()["confirmed_reward_usd"] == 250

        m = client.get("/v1/metrics/employer-childcare-net-cost")
        assert m.status_code == 200
        assert m.json()["revenue"] == 250.0
