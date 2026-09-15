from pathlib import Path


def test_status_document_is_fail_closed():
    text = Path("docs/COMMERCIAL_CLOSURE_STATUS.md").read_text(encoding="utf-8")
    assert "NOT COMMERCIAL READY" in text
    assert "#81" in text and "#101" in text and "#305" in text
