"""Durable receipt storage.

Receipts are immutable once written. The writer refuses to overwrite an
existing file, so a replayed or forged finalization cannot quietly replace
history. Writes are atomic (temp file + rename) so a crash mid-write leaves
either the old file or the new one, never a truncated receipt.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from .schema import Receipt, ReceiptError

DIR_MODE = 0o700
FILE_MODE = 0o600


class ReceiptWriter:
    def __init__(self, root: Path | str) -> None:
        self.root = Path(root).expanduser()
        self.root.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(self.root, DIR_MODE)
        except OSError:
            # A mounted volume may refuse chmod; the write itself still applies
            # a 0600 mode, so this is not fatal.
            pass

    def path_for(self, receipt_id: str) -> Path:
        return self.root / f"{receipt_id}.json"

    def write(self, receipt: Receipt) -> Path:
        if not receipt.content_hash:
            raise ReceiptError("refusing to persist a receipt that was never finalized")
        if not receipt.sanitized:
            raise ReceiptError("refusing to persist an unsanitized receipt")

        target = self.path_for(receipt.receipt_id)
        if target.exists():
            raise ReceiptError(f"receipt {receipt.receipt_id} already exists and is immutable")

        payload = json.dumps(receipt.to_dict(), sort_keys=True, indent=2)
        fd, tmp = tempfile.mkstemp(dir=str(self.root), prefix=".receipt-", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(tmp, FILE_MODE)
            os.replace(tmp, target)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise
        return target

    def read(self, receipt_id: str) -> Receipt:
        target = self.path_for(receipt_id)
        if not target.exists():
            raise ReceiptError(f"receipt {receipt_id} not found")
        return Receipt.from_dict(json.loads(target.read_text(encoding="utf-8")))

    def list_ids(self) -> list[str]:
        return sorted(p.stem for p in self.root.glob("*.json"))
