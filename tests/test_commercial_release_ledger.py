from __future__ import annotations

import copy
import importlib.util
import json
from datetime import timedelta
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


def ledger_now(ledger):
    """Evaluate evolving ledger truth just after its own generation time."""
    return validator.parse_dt(ledger["generated_at"]) + timedelta(minutes=1)


def test_current_ledger_is_structurally_valid_but_not_release_certified():
    ledger = load_ledger()
    now = ledger_now(ledger)
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
    errors, _ = validator.validate_ledger(ledger, now=ledger_now(ledger), require_release_certified=False)
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
    errors, _ = validator.validate_ledger(ledger, now=ledger_now(ledger), require_release_certified=False)
    assert any("certified component cannot have current_blocker" in error for error in errors)


def test_duplicate_receipt_ids_are_rejected_globally():
    ledger = load_ledger()
    ledger = copy.deepcopy(ledger)
    receipt = copy.deepcopy(ledger["components"][0]["evidence_receipts"][0])
    ledger["components"][1]["evidence_receipts"].append(receipt)
    errors, _ = validator.validate_ledger(ledger, now=ledger_now(ledger), require_release_certified=False)
    assert any("duplicate global receipt_id" in error for error in errors)


def test_future_dated_evidence_is_rejected():
    ledger = load_ledger()
    ledger = copy.deepcopy(ledger)
    now = ledger_now(ledger)
    receipt = ledger["components"][0]["evidence_receipts"][0]
    receipt["verified_at"] = (now + timedelta(hours=1)).isoformat()
    errors, _ = validator.validate_ledger(ledger, now=now, require_release_certified=False)
    assert any("verified_at is in the future" in error for error in errors)


def synthetic_certification_claims(*, applicable):
    """Adversarial input only: these receipts are deliberately not real evidence."""
    components = []
    for lane in range(1, 13):
        component = {
            field: "CERTIFIED" if applicable else "NOT_APPLICABLE"
            for field in validator.STATE_FIELDS
        }
        component.update(
            component_id=f"release.lane{lane:02}.synthetic",
            lane_id=lane,
            owner="synthetic builder",
            purpose="negative control",
            location="offline test",
            release_stage="COMMERCIAL_OPERATIONAL_CERTIFIED",
            dependencies=[],
            deployed_sha_or_digest="a" * 40 if applicable else None,
            last_verified_at="2026-09-15T06:00:00+00:00",
            evidence_receipts=[
                {
                    "receipt_id": f"fabricated-{lane}",
                    "kind": "production_runtime_receipt",
                    "reference": "https://example.invalid/unverified-proof",
                    "verified_at": "2026-09-15T06:00:00+00:00",
                    "freshness": "EXPIRING" if applicable else "IMMUTABLE",
                    "expires_at": "2026-09-16T06:00:00+00:00" if applicable else None,
                }
            ],
            current_blocker=None,
            rollback_reference="unverified rollback claim",
        )
        components.append(component)
    return dict(
        release_id="DOMINION-COMMERCIAL-RELEASE-1.0",
        release_objective="synthetic negative control",
        generated_at="2026-09-15T06:00:00+00:00",
        default_runtime_evidence_ttl_hours=24,
        allowed_progression=validator.PROGRESSION,
        components=components,
    )


def test_blanket_not_applicable_cannot_certify_release():
    ledger = synthetic_certification_claims(applicable=False)
    errors, _ = validator.validate_ledger(
        ledger,
        now=validator.parse_dt("2026-09-15T06:30:00Z"),
        require_release_certified=True,
    )
    assert any("independent release certification evidence verification" in e for e in errors)


def test_plausible_but_unauthenticated_receipts_cannot_certify_release():
    ledger = synthetic_certification_claims(applicable=True)
    now = validator.parse_dt("2026-09-15T06:30:00Z")
    structural_errors, _ = validator.validate_ledger(
        ledger,
        now=now,
        require_release_certified=False,
    )
    assert structural_errors == []
    errors, _ = validator.validate_ledger(
        ledger,
        now=now,
        require_release_certified=True,
    )
    assert any("independent release certification evidence verification" in e for e in errors)


def test_final_certification_cli_returns_failure_for_fabricated_claims(tmp_path):
    import subprocess
    import sys

    path = tmp_path / "synthetic-ledger.json"
    path.write_text(json.dumps(synthetic_certification_claims(applicable=True)))
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--ledger",
            str(path),
            "--as-of",
            "2026-09-15T06:30:00Z",
            "--require-release-certified",
        ],
        text=True,
        capture_output=True,
    )
    assert result.returncode == 1
    assert "CLOSURE_LEDGER_VALIDATION=FAIL" in result.stdout
    assert "release_certified=true" not in result.stdout
