from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "validate_commercial_release_ledger.py"
LEDGER = ROOT / "governance" / "commercial_release_1_0" / "closure_ledger.json"

spec = importlib.util.spec_from_file_location("closure_validator", SCRIPT)
assert spec and spec.loader
validator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validator)


def load_ledger():
    return json.loads(LEDGER.read_text(encoding="utf-8"))


def test_seed_ledger_is_structurally_valid_but_not_release_certified():
    ledger = load_ledger()
    now = validator.parse_dt("2026-09-15T06:30:00+00:00")
    errors, _ = validator.validate_ledger(ledger, now=now, require_release_certified=False)
    assert errors == []

    errors, _ = validator.validate_ledger(ledger, now=now, require_release_certified=True)
    assert errors
    assert any("not commercially/operationally certified" in error for error in errors)


def test_expired_runtime_evidence_downgrades_effective_state_to_stale():
    ledger = load_ledger()
    now = validator.parse_dt("2026-09-16T01:15:02+00:00")
    _, effective = validator.validate_ledger(ledger, now=now, require_release_certified=False)
    deerflow = next(
        component
        for component in effective["components"]
        if component["component_id"] == "runtime.deerflow-nemotron"
    )
    assert deerflow["runtime_state"] == "STALE"
    assert deerflow["release_stage"] == "STALE"


def test_closed_shortcut_is_rejected():
    ledger = load_ledger()
    ledger = copy.deepcopy(ledger)
    ledger["components"][0]["release_stage"] = "CLOSED"
    now = validator.parse_dt("2026-09-15T06:30:00+00:00")
    errors, _ = validator.validate_ledger(ledger, now=now, require_release_certified=False)
    assert any("CLOSED is forbidden" in error for error in errors)


def test_certified_component_requires_no_blocker_and_fresh_runtime_evidence():
    ledger = load_ledger()
    ledger = copy.deepcopy(ledger)
    component = ledger["components"][0]
    component.update(
        {
            "engineering_state": "CERTIFIED",
            "deployment_state": "CERTIFIED",
            "runtime_state": "CERTIFIED",
            "customer_state": "NOT_APPLICABLE",
            "commercial_state": "CERTIFIED",
            "security_state": "CERTIFIED",
            "recovery_state": "CERTIFIED",
            "release_stage": "COMMERCIAL_OPERATIONAL_CERTIFIED",
            "deployed_sha_or_digest": "sha256:example",
            "current_blocker": "still broken",
            "rollback_reference": "rollback://example",
        }
    )
    now = validator.parse_dt("2026-09-15T06:30:00+00:00")
    errors, _ = validator.validate_ledger(ledger, now=now, require_release_certified=False)
    assert any("certified component cannot have current_blocker" in error for error in errors)


def test_duplicate_receipt_ids_are_rejected_globally():
    ledger = load_ledger()
    ledger = copy.deepcopy(ledger)
    receipt = copy.deepcopy(ledger["components"][0]["evidence_receipts"][0])
    ledger["components"][1]["evidence_receipts"].append(receipt)
    now = validator.parse_dt("2026-09-15T06:30:00+00:00")
    errors, _ = validator.validate_ledger(ledger, now=now, require_release_certified=False)
    assert any("duplicate global receipt_id" in error for error in errors)
