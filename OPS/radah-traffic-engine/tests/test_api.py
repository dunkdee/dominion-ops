
import importlib
import os
import tempfile
import time

os.environ["ENVIRONMENT"] = "test"
os.environ["API_KEY"] = "test-key"
os.environ["AUDIT_HMAC_KEY"] = "test-audit-key"
os.environ["RADAH_SHARED_SECRET"] = "test-radah-key"
os.environ["REQUIRE_RADAH_SIGNATURE"] = "false"
os.environ["DB_PATH"] = tempfile.mktemp(suffix=".db")

from fastapi.testclient import TestClient

from app.db import init_db
from app.main import app


def radah(corr: str, action: str, target: str):
    now = int(time.time())
    return {
        "correlation_id": corr,
        "action": action,
        "target": target,
        "decision": "ALLOW",
        "reason": "integration test authority",
        "authority_version": "test-v1",
        "issued_at": now,
        "expires_at": now + 120,
    }


def test_governed_create_event_metrics_and_replay():
    init_db()

    with TestClient(app) as client:
        body = {
            "radah": radah(
                "corr-api-create-001",
                "CREATE_OPPORTUNITY",
                "opportunity:healthcare-accessibility",
            ),
            "opportunity": {
                "name": "Healthcare Accessibility",
                "slug": "healthcare-accessibility",
                "demand": 8.5,
                "buyer_intent": 9.2,
                "urgency": 9.5,
                "competition": 5.5,
                "scalability": 9.0,
                "defensibility": 8.5,
                "execution_ease": 7.5,
                "payout": 400.0,
                "conversion_rate": 0.025,
            },
        }

        r = client.post(
            "/v1/opportunities",
            json=body,
            headers={"X-API-Key": "test-key"},
        )
        assert r.status_code == 200, r.text
        assert r.json()["expected_rpv"] == 10.0

        # Same consumed RADAH correlation ID must not be reusable.
        r2 = client.post(
            "/v1/opportunities",
            json=body,
            headers={"X-API-Key": "test-key"},
        )
        assert r2.status_code == 409

        visit = {
            "opportunity_slug": "healthcare-accessibility",
            "event_type": "visit",
            "source": "organic",
            "medium": "search",
            "revenue": 0,
        }
        headers = {
            "X-API-Key": "test-key",
            "Idempotency-Key": "visit-00000001",
        }
        e1 = client.post("/v1/events", json=visit, headers=headers)
        e2 = client.post("/v1/events", json=visit, headers=headers)
        assert e1.status_code == 200
        assert e2.status_code == 200
        assert e2.json()["idempotent_replay"] is True

        sale = {
            "opportunity_slug": "healthcare-accessibility",
            "event_type": "sale",
            "source": "organic",
            "medium": "search",
            "revenue": 400,
        }
        s = client.post(
            "/v1/events",
            json=sale,
            headers={
                "X-API-Key": "test-key",
                "Idempotency-Key": "sale-00000001",
            },
        )
        assert s.status_code == 200

        m = client.get("/v1/metrics/healthcare-accessibility")
        assert m.status_code == 200
        data = m.json()
        assert data["visits"] == 1
        assert data["revenue"] == 400.0
        assert data["actual_rpv"] == 400.0
        assert data["execution_authorized"] is False

        a = client.get(
            "/v1/audit/verify",
            headers={"X-API-Key": "test-key"},
        )
        assert a.status_code == 200
        assert a.json()["valid"] is True
