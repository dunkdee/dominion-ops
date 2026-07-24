"""Application-level append-only, hash-chained evidence ledger.

The ledger detects alteration, deletion, reordering, and broken linkage. It does
not claim filesystem immutability; production deployment must add storage-level
retention and access controls.
"""

from __future__ import annotations

import fcntl
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .canonical import canonical_json, sha256_json

GENESIS_HASH = "0" * 64


class LedgerError(RuntimeError):
    """Raised when ledger integrity or append requirements fail."""


class AppendOnlyLedger:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.lock_path = self.path.with_suffix(self.path.suffix + ".lock")

    def _acquire_lock(self, exclusive: bool) -> int:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(self.lock_path, os.O_CREAT | os.O_RDWR, 0o600)
        fcntl.flock(descriptor, fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)
        return descriptor

    @staticmethod
    def _release_lock(descriptor: int) -> None:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)

    def _read_records(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        records: list[dict[str, Any]] = []
        with self.path.open("r", encoding="utf-8") as handle:
            for line_number, raw in enumerate(handle, start=1):
                line = raw.strip()
                if not line:
                    raise LedgerError(f"blank ledger line at {line_number}")
                try:
                    value = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise LedgerError(f"invalid JSON at line {line_number}: {exc}") from exc
                if not isinstance(value, dict):
                    raise LedgerError(f"ledger line {line_number} must be an object")
                records.append(value)
        return records

    @staticmethod
    def _hashable_record(record: dict[str, Any]) -> dict[str, Any]:
        return {key: value for key, value in record.items() if key != "record_hash"}

    def _verify_unlocked(self) -> dict[str, Any]:
        records = self._read_records()
        previous_hash = GENESIS_HASH
        for expected_sequence, record in enumerate(records, start=1):
            required = {
                "sequence",
                "timestamp",
                "event_type",
                "actor",
                "payload",
                "previous_hash",
                "record_hash",
            }
            missing = sorted(required - set(record))
            if missing:
                raise LedgerError(
                    f"ledger record {expected_sequence} missing fields: {', '.join(missing)}"
                )
            if record["sequence"] != expected_sequence:
                raise LedgerError(
                    f"ledger sequence mismatch: expected {expected_sequence}, got {record['sequence']}"
                )
            if record["previous_hash"] != previous_hash:
                raise LedgerError(f"ledger chain mismatch at sequence {expected_sequence}")
            calculated = sha256_json(self._hashable_record(record))
            if record["record_hash"] != calculated:
                raise LedgerError(f"ledger record hash mismatch at sequence {expected_sequence}")
            previous_hash = record["record_hash"]
        return {
            "valid": True,
            "record_count": len(records),
            "head_hash": previous_hash,
        }

    def verify(self) -> dict[str, Any]:
        lock = self._acquire_lock(exclusive=False)
        try:
            return self._verify_unlocked()
        finally:
            self._release_lock(lock)

    @staticmethod
    def _write_all(descriptor: int, content: bytes) -> None:
        offset = 0
        while offset < len(content):
            written = os.write(descriptor, content[offset:])
            if written <= 0:
                raise LedgerError("ledger append did not make progress")
            offset += written

    def append(
        self,
        *,
        event_type: str,
        actor: str,
        payload: dict[str, Any],
        timestamp: str | None = None,
    ) -> dict[str, Any]:
        if not event_type or not actor:
            raise LedgerError("event_type and actor are required")
        if not isinstance(payload, dict):
            raise LedgerError("payload must be an object")

        lock = self._acquire_lock(exclusive=True)
        try:
            verification = self._verify_unlocked()
            sequence = verification["record_count"] + 1
            record: dict[str, Any] = {
                "sequence": sequence,
                "timestamp": timestamp or datetime.now(timezone.utc).isoformat(),
                "event_type": event_type,
                "actor": actor,
                "payload": payload,
                "previous_hash": verification["head_hash"],
            }
            record["record_hash"] = sha256_json(record)
            encoded = (canonical_json(record) + "\n").encode("utf-8")

            descriptor = os.open(
                self.path,
                os.O_APPEND | os.O_CREAT | os.O_WRONLY,
                0o600,
            )
            try:
                self._write_all(descriptor, encoded)
                os.fsync(descriptor)
            finally:
                os.close(descriptor)

            self._verify_unlocked()
            return record
        finally:
            self._release_lock(lock)

    def records(self) -> Iterable[dict[str, Any]]:
        lock = self._acquire_lock(exclusive=False)
        try:
            self._verify_unlocked()
            return tuple(self._read_records())
        finally:
            self._release_lock(lock)
