"""Receipt schema — the proof object behind every claim.

Governance rule 7: no production claim without a receipt. A receipt records
what was expected, what was observed, and the exact policy and code revisions
in force, so a claim can be re-checked later without trusting the claimer.

A receipt is finalized exactly once. Finalizing computes a content hash over
the canonical JSON; any later edit breaks verification. The hash deliberately
excludes the hash field itself so verification is reproducible.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class ReceiptError(RuntimeError):
    """A receipt could not be produced or was tampered with."""


class ReceiptStatus(str, Enum):
    DONE = "DONE"
    IN_PROGRESS = "IN_PROGRESS"
    BLOCKED = "BLOCKED"
    UNKNOWN = "UNKNOWN"
    HOLD = "HOLD"

    @classmethod
    def terminal(cls) -> frozenset["ReceiptStatus"]:
        return frozenset({cls.DONE, cls.BLOCKED, cls.HOLD})


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class Evidence:
    type: str
    reference: str
    detail: str = ""

    def to_dict(self) -> dict:
        return {"type": self.type, "reference": self.reference, "detail": self.detail}


@dataclass
class Receipt:
    task_id: str
    lane_id: str
    agent_id: str
    action: str
    expected_result: str
    receipt_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    started_at: str = field(default_factory=utc_now)
    completed_at: str | None = None
    status: ReceiptStatus = ReceiptStatus.IN_PROGRESS
    evidence: list[Evidence] = field(default_factory=list)
    observed_result: str = ""
    policy_revision: str = ""
    code_revision: str = ""
    sanitized: bool = False
    content_hash: str = ""

    # ── construction ────────────────────────────────────────────────────

    def add_evidence(self, type: str, reference: str, detail: str = "") -> None:
        if self.content_hash:
            raise ReceiptError("cannot add evidence to a finalized receipt")
        self.evidence.append(Evidence(type=type, reference=reference, detail=detail))

    def to_dict(self) -> dict:
        data = asdict(self)
        data["status"] = self.status.value
        data["evidence"] = [e.to_dict() for e in self.evidence]
        return data

    # ── hashing ─────────────────────────────────────────────────────────

    def _hashable(self) -> dict:
        data = self.to_dict()
        data.pop("content_hash", None)
        return data

    def compute_hash(self) -> str:
        canonical = json.dumps(self._hashable(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def finalize(
        self,
        status: ReceiptStatus,
        observed_result: str,
        *,
        policy_revision: str = "",
        code_revision: str = "",
        secret_values: tuple[str, ...] = (),
    ) -> "Receipt":
        """Seal the receipt. Sanitizes first, then hashes what was sealed."""
        if self.content_hash:
            raise ReceiptError(f"receipt {self.receipt_id} is already finalized")

        from ..logging import redact

        self.status = ReceiptStatus(status)
        self.observed_result = redact(str(observed_result), secret_values)
        self.expected_result = redact(self.expected_result, secret_values)
        self.evidence = [
            Evidence(
                type=e.type,
                reference=redact(e.reference, secret_values),
                detail=redact(e.detail, secret_values),
            )
            for e in self.evidence
        ]
        self.policy_revision = policy_revision
        self.code_revision = code_revision
        self.completed_at = utc_now()
        self.sanitized = True
        self.content_hash = self.compute_hash()
        return self

    @property
    def matched_expectation(self) -> bool:
        """DONE is only honest when observation matched expectation."""
        return bool(self.observed_result) and self.observed_result == self.expected_result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Receipt":
        evidence = [Evidence(**e) for e in data.get("evidence", [])]
        known = {f for f in cls.__dataclass_fields__}
        kwargs = {k: v for k, v in data.items() if k in known}
        kwargs["evidence"] = evidence
        kwargs["status"] = ReceiptStatus(data.get("status", "UNKNOWN"))
        return cls(**kwargs)
