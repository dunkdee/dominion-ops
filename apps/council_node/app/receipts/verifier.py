"""Receipt verification.

Verification is fail-closed: anything it cannot prove is reported as invalid
with a stated reason, never as a pass. It answers three separate questions,
and a caller can care about them independently:

  hash_valid      the stored content still hashes to the recorded value
  sanitized       the receipt claims to have passed redaction
  claim_supported a DONE status is backed by evidence and a matching
                  observation -- a DONE with no evidence is not a proof
"""

from __future__ import annotations

from dataclasses import dataclass

from .schema import Receipt, ReceiptStatus


@dataclass(frozen=True)
class VerificationResult:
    valid: bool
    hash_valid: bool
    sanitized: bool
    claim_supported: bool
    reasons: tuple[str, ...]


def verify_receipt(receipt: Receipt) -> VerificationResult:
    reasons: list[str] = []

    hash_valid = False
    if not receipt.content_hash:
        reasons.append("receipt was never finalized")
    else:
        hash_valid = receipt.compute_hash() == receipt.content_hash
        if not hash_valid:
            reasons.append("content hash does not match receipt body")

    sanitized = bool(receipt.sanitized)
    if not sanitized:
        reasons.append("receipt is not marked sanitized")

    claim_supported = True
    if receipt.status is ReceiptStatus.DONE:
        if not receipt.evidence:
            claim_supported = False
            reasons.append("DONE claimed with no evidence")
        if not receipt.matched_expectation:
            claim_supported = False
            reasons.append("observed result does not match expected result")
    if receipt.status is ReceiptStatus.IN_PROGRESS:
        claim_supported = False
        reasons.append("receipt is still IN_PROGRESS and proves nothing yet")

    return VerificationResult(
        valid=hash_valid and sanitized and claim_supported,
        hash_valid=hash_valid,
        sanitized=sanitized,
        claim_supported=claim_supported,
        reasons=tuple(reasons),
    )
