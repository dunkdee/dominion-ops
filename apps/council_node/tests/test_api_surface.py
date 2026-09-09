"""HTTP surface (Gate 2, Gate 8).

Exercises the app the way a caller does. The assertions that matter are the
refusals: Founder endpoints must reject an unauthenticated mutation, and no
response may carry the Founder token.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

TOKEN = "api-surface-founder-token"


@pytest.fixture
def client(governance_dir: Path, tmp_path: Path, monkeypatch):
    monkeypatch.setenv("COUNCIL_GOVERNANCE_DIR", str(governance_dir))
    monkeypatch.setenv("COUNCIL_RECEIPT_DIR", str(tmp_path / "receipts"))
    monkeypatch.setenv("COUNCIL_FOUNDER_TOKEN", TOKEN)
    monkeypatch.setenv("COUNCIL_EXTERNAL_MODELS_ENABLED", "false")

    from apps.council_node.app import config, deps

    config.reset_settings_for_tests()
    deps.services.cache_clear()

    from apps.council_node.app.main import app

    with TestClient(app) as c:
        yield c

    config.reset_settings_for_tests()
    deps.services.cache_clear()


def test_health_is_public_and_cheap(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_ready_reports_governance_loaded(client):
    body = client.get("/ready").json()
    assert body["ready"] is True
    assert body["policy_revision"]


def test_status_never_carries_the_founder_token(client):
    r = client.get("/api/status")
    assert r.status_code == 200
    assert TOKEN not in r.text
    assert r.json()["settings"]["founder_gate_configured"] is True


def test_founder_mutation_requires_the_token(client):
    r = client.post("/api/founder/hold", json={"lane_id": "traffic", "reason": "pause"})
    assert r.status_code == 403


def test_founder_mutation_succeeds_with_the_token(client):
    r = client.post(
        "/api/founder/hold",
        json={"lane_id": "traffic", "reason": "pause"},
        headers={"X-Founder-Token": TOKEN},
    )
    assert r.status_code == 200
    assert r.json()["held"] is True

    lane = client.get("/api/lanes/traffic").json()
    assert lane["founder_hold"] is True


def test_wrong_token_is_rejected(client):
    r = client.post(
        "/api/founder/hold",
        json={"lane_id": "traffic", "reason": "pause"},
        headers={"X-Founder-Token": "not-the-token"},
    )
    assert r.status_code == 403


def test_governance_evaluate_is_read_only_and_denies_unknown_agent(client):
    r = client.post("/api/governance/evaluate", json={
        "agent_id": "nobody", "lane_id": "traffic",
        "capability_id": "read.public", "action_id": "read.public",
    })
    assert r.status_code == 200
    # An unregistered agent has no granted capabilities, so this must not allow.
    assert r.json()["verdict"] != "ALLOW"


def test_unknown_lane_and_receipt_are_404(client):
    assert client.get("/api/lanes/does-not-exist").status_code == 404
    assert client.get("/api/receipts/does-not-exist").status_code == 404


def test_interactive_docs_are_not_exposed(client):
    """A governed control plane should not ship a live API console."""
    assert client.get("/docs").status_code == 404
    assert client.get("/redoc").status_code == 404
