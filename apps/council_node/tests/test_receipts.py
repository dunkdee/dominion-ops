"""Receipt integrity (Gate 6).

A receipt is the only thing standing between "we did it" and proof. These
tests attack that: tamper with a sealed receipt, claim DONE without evidence,
try to overwrite history, and confirm each is caught.
"""

from __future__ import annotations

import json

import pytest

from apps.council_node.app.receipts.schema import Receipt, ReceiptError, ReceiptStatus
from apps.council_node.app.receipts.verifier import verify_receipt


def _receipt(**kw) -> Receipt:
    base = dict(
        task_id="t-1", lane_id="publisher", agent_id="worker-01",
        action="publish", expected_result="published",
    )
    base.update(kw)
    return Receipt(**base)


def test_finalize_seals_and_hashes():
    r = _receipt()
    r.add_evidence("github_run", "run-123", "green")
    r.finalize(ReceiptStatus.DONE, "published", policy_revision="pol", code_revision="sha")
    assert r.content_hash
    assert r.sanitized is True
    assert verify_receipt(r).valid


def test_tampering_breaks_the_hash():
    r = _receipt()
    r.add_evidence("github_run", "run-123")
    r.finalize(ReceiptStatus.DONE, "published")
    assert verify_receipt(r).hash_valid

    r.observed_result = "something else entirely"
    result = verify_receipt(r)
    assert not result.hash_valid
    assert not result.valid
    assert any("hash does not match" in reason for reason in result.reasons)


def test_done_without_evidence_is_not_a_valid_claim():
    r = _receipt()
    r.finalize(ReceiptStatus.DONE, "published")
    result = verify_receipt(r)
    assert result.hash_valid          # the bytes are intact
    assert not result.claim_supported  # but the claim is not supported
    assert not result.valid
    assert any("no evidence" in reason for reason in result.reasons)


def test_done_with_mismatched_observation_is_invalid():
    r = _receipt(expected_result="health=200")
    r.add_evidence("probe", "curl", "ran")
    r.finalize(ReceiptStatus.DONE, "health=503")
    result = verify_receipt(r)
    assert not result.claim_supported
    assert any("does not match" in reason for reason in result.reasons)


def test_in_progress_receipt_proves_nothing():
    r = _receipt()
    result = verify_receipt(r)
    assert not result.valid
    assert any("never finalized" in reason for reason in result.reasons)


def test_double_finalize_is_refused():
    r = _receipt()
    r.finalize(ReceiptStatus.DONE, "published")
    with pytest.raises(ReceiptError, match="already finalized"):
        r.finalize(ReceiptStatus.BLOCKED, "changed my mind")


def test_evidence_cannot_be_added_after_sealing():
    r = _receipt()
    r.finalize(ReceiptStatus.DONE, "published")
    with pytest.raises(ReceiptError, match="finalized"):
        r.add_evidence("late", "evidence")


def test_writer_refuses_unfinalized_receipts(receipts):
    with pytest.raises(ReceiptError, match="never finalized"):
        receipts.write(_receipt())


def test_written_receipts_are_immutable(receipts):
    r = _receipt()
    r.add_evidence("probe", "ok")
    r.finalize(ReceiptStatus.DONE, "published")
    receipts.write(r)
    with pytest.raises(ReceiptError, match="immutable"):
        receipts.write(r)


def test_round_trip_preserves_hash(receipts):
    r = _receipt()
    r.add_evidence("probe", "ok", "detail")
    r.finalize(ReceiptStatus.DONE, "published", policy_revision="pol")
    path = receipts.write(r)

    loaded = receipts.read(r.receipt_id)
    assert loaded.content_hash == r.content_hash
    assert verify_receipt(loaded).valid
    # And the stored file is the sanitized dict, not a pickle of internals.
    assert json.loads(path.read_text())["receipt_id"] == r.receipt_id


def test_secrets_are_stripped_at_finalization():
    secret = "sk-live-abcdefghijklmnopqrstuvwxyz123456"
    r = _receipt(expected_result=f"used {secret}")
    r.add_evidence("call", f"auth={secret}", f"key {secret}")
    r.finalize(ReceiptStatus.DONE, f"sent {secret}", secret_values=(secret,))

    blob = json.dumps(r.to_dict())
    assert secret not in blob
    assert "[REDACTED]" in blob
