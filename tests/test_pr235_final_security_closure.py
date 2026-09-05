from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from buddy_core.core import authorization as auth
from buddy_core.core.operator import BuddyOperator
from buddy_core.watchmen import saraqael


@pytest.fixture
def authority_env(monkeypatch, tmp_path):
    monkeypatch.setenv("DOMINION_AUTHORIZATION_HMAC_KEY", "A" * 32)
    monkeypatch.setenv("DOMINION_WATCHMEN_HMAC_KEY", "W" * 32)
    monkeypatch.setenv("DOMINION_WATCHMEN_STATE_DIR", str(tmp_path / "watchmen"))
    return tmp_path


def test_public_checksum_cannot_forge_founder_authority(authority_env):
    ledger = auth.AuthorizationLedger(authority_env / "buddy")
    req = ledger.request(
        mission_id="m1", step=1, capability="external.publish",
        instruction="publish approved", content="exact", destination="dest",
    )
    path = ledger._path(req["approval_id"])
    forged = json.loads(path.read_text(encoding="utf-8"))
    forged["status"] = auth.GRANTED
    forged["approver"] = "attacker"
    forged["authorization_sequence"] = 999
    # Recompute the legacy public checksum exactly as an attacker could.
    forged["approval_hash"] = auth.sha256_json(
        {k: v for k, v in forged.items() if k != "approval_hash"}
    )
    path.write_text(auth.canonical_json(forged) + "\n", encoding="utf-8")
    result = ledger.verify_and_consume(
        req["approval_id"], capability="external.publish",
        instruction="publish approved", content="exact", destination="dest",
    )
    assert result == {"ok": False, "error": "authorization_record_tampered"}


def test_weak_authorization_hmac_key_fails_closed(monkeypatch, tmp_path):
    monkeypatch.setenv("DOMINION_AUTHORIZATION_HMAC_KEY", "short")
    with pytest.raises(auth.AuthorizationError, match="weaker than 256 bits"):
        auth.AuthorizationLedger(tmp_path / "buddy")


def test_external_executor_cannot_receive_regenerated_unbound_context(authority_env):
    op = BuddyOperator(state_dir=authority_env / "buddy")
    captured = {}

    def executor(step, context):
        captured["step"] = step
        captured["context"] = context
        return {
            "delivered": True,
            "result": {"ok": True},
            "evidence": [{
                "publication_id": "post-1",
                "platform": "test-platform",
                "observed_at": datetime.now(timezone.utc).isoformat(),
            }],
        }

    op._external_executors["external:publish"] = executor
    step = {
        "capability": "external.publish",
        "instruction": "publish exact",
        "content": "AUTHORIZED CONTENT",
        "destination": "authorized-destination",
    }
    cap = op.capabilities["external.publish"]
    context = {"outputs": ["REGENERATED ATTACK CONTENT"], "secret": "must-not-cross"}
    receipt = op._execute_external(
        1, step, cap, context,
        {"approval_id": "approval_aaaaaaaaaaaa", "authorization_sequence": 1,
         "payload_hash": "p" * 64, "approver": "founder"},
    )
    assert receipt["status"] == "VERIFIED"
    assert captured["context"] == {
        "capability": "external.publish",
        "instruction": "publish exact",
        "content": "AUTHORIZED CONTENT",
        "destination": "authorized-destination",
    }
    assert "REGENERATED ATTACK CONTENT" not in json.dumps(captured["context"])
    assert "secret" not in captured["context"]


def test_receipt_contracts_cover_every_external_capability():
    common = {"source": "provider", "observed_at": "2026-09-05T00:00:00Z"}
    assert BuddyOperator._validate_delivery_evidence(
        "external.submit", [{**common, "receipt_id": "generic"}]
    ) == (False, None)
    assert BuddyOperator._validate_delivery_evidence(
        "external.submit", [{**common, "submission_id": "sub-1"}]
    ) == (True, "sub-1")

    assert BuddyOperator._validate_delivery_evidence(
        "external.browser", [{**common, "receipt_id": "generic"}]
    ) == (False, None)
    assert BuddyOperator._validate_delivery_evidence(
        "external.browser", [{**common, "browser_action_id": "act-1", "action": "submit_form"}]
    ) == (True, "act-1")

    assert BuddyOperator._validate_delivery_evidence(
        "external.credential_or_network", [{**common, "receipt_id": "generic"}]
    ) == (False, None)
    strong = {
        **common,
        "network_change_id": "chg-1",
        "before_state": {"port": "closed"},
        "after_state": {"port": "closed"},
        "verification": {"ok": True},
        "rollback_receipt_id": "rb-1",
    }
    assert BuddyOperator._validate_delivery_evidence(
        "external.credential_or_network", [strong]
    ) == (True, "chg-1")


def test_non_json_delivery_evidence_returns_truthful_receipt(authority_env):
    op = BuddyOperator(state_dir=authority_env / "buddy")

    class NotJson:
        pass

    def executor(step, context):
        return {
            "delivered": True,
            "result": {"ok": True},
            "evidence": [{
                "publication_id": "post-2",
                "platform": "test-platform",
                "observed_at": "2026-09-05T00:00:00Z",
                "opaque": NotJson(),
            }],
        }

    op._external_executors["external:publish"] = executor
    receipt = op._execute_external(
        1,
        {"capability": "external.publish", "instruction": "x", "content": "y", "destination": "z"},
        op.capabilities["external.publish"], {},
        {"approval_id": "approval_bbbbbbbbbbbb", "authorization_sequence": 2,
         "payload_hash": "q" * 64, "approver": "founder"},
    )
    assert receipt["status"] == "DELIVERED_UNVERIFIED"
    assert receipt["errors"][0]["error"] == "EvidenceSerializationError"
    json.dumps(receipt)


def test_copied_buddy_layout_does_not_treat_home_as_checkout(tmp_path):
    fake = tmp_path / "home" / "buddy_core" / "watchmen" / "saraqael.py"
    fake.parent.mkdir(parents=True)
    fake.write_text("# copied runtime\n", encoding="utf-8")
    assert saraqael._detect_checkout_root(fake) is None


def test_explicit_watchmen_key_inside_source_is_rejected(monkeypatch):
    inside = Path(saraqael.__file__).resolve().parent / "forbidden-test.key"
    monkeypatch.delenv(saraqael.ENV_HMAC_KEY, raising=False)
    monkeypatch.setenv(saraqael.ENV_HMAC_FILE, str(inside))
    with pytest.raises(saraqael.WatchmenStateError, match="outside Buddy source"):
        saraqael._resolve_key()


def test_browser_chat_exposes_explicit_exact_id_approval_control():
    from buddy_core import buddy_web

    html = buddy_web.CHAT_HTML
    assert "renderHeldApproval" in html
    assert "approveHeld" in html
    assert "authorization_id: approvalId" in html
    assert "APPROVE & RESUME" in html
    assert "approve: true" in html
