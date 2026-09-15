from pathlib import Path


DOC = Path("docs/COMMERCIAL_CLOSURE_EXECUTION.md")


def test_commercial_closure_binds_to_existing_canonical_work():
    text = DOC.read_text(encoding="utf-8")
    for issue in ("#81", "#101", "#305"):
        assert issue in text
    assert "replacement orchestrator" in text
    assert "Self-report never counts as completion" in text
    assert "COMMERCIAL READY" in text
