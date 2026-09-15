import json
from pathlib import Path


def test_commercial_closure_receipt_schema_is_fail_closed():
    schema = json.loads(Path("governance/commercial_closure_receipt_schema_v1.json").read_text(encoding="utf-8"))
    assert schema["allowed_status"] == ["VERIFIED_PASS", "BLOCKED", "RETIRED"]
    assert schema["rules"] == {
        "verified_pass_requires_evidence": True,
        "verified_pass_requires_zero_open_dependencies": True,
        "blocked_requires_recovery_path": True,
        "retired_requires_dependency_check": True,
    }
    assert "evidence_reference" in schema["required_fields"]
    assert "rollback_or_recovery" in schema["required_fields"]
    assert "open_dependencies" in schema["required_fields"]
