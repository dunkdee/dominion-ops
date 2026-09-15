from pathlib import Path


def test_canonical_artifact_index_names_existing_files():
    text = Path("governance/README-commercial-closure.txt").read_text(encoding="utf-8")
    for path in (
        "governance/commercial_closure_gate_v1.json",
        "governance/commercial_closure_receipt_schema_v1.json",
        "governance/commercial_closure_current_state.json",
        "docs/COMMERCIAL_CLOSURE_EXECUTION.md",
        "docs/COMMERCIAL_CLOSURE_STATUS.md",
    ):
        assert path in text
        assert Path(path).exists()
