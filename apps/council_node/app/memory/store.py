"""Memory layers A-D with a hard secret boundary.

The work order requires that no credential or token may enter semantic
memory. That is enforced here at write time, not at read time: a write
carrying a secret shape is *rejected*, and the caller gets an exception.

Rejecting is deliberate. Silently scrubbing would let a caller believe it
stored something it did not, and storing-then-filtering would mean the secret
briefly existed in the store. Neither is acceptable for Layer C, which is
long-lived and semantically searchable.

Layer A (constitutional) is not writable through this API at all.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path

from ..models.router import scan_for_secrets


class MemoryRejected(RuntimeError):
    """A memory write was refused. Carries the reason, never the payload."""


class Sensitivity(str, Enum):
    PUBLIC = "public"
    INTERNAL = "internal"
    SENSITIVE = "sensitive"


class RetentionClass(str, Enum):
    WORKING = "working"        # Layer D, expires
    OPERATIONAL = "operational"  # Layer B
    SEMANTIC = "semantic"     # Layer C, long-lived


DEFAULT_TTL_SECONDS = {
    RetentionClass.WORKING: 3600,
    RetentionClass.OPERATIONAL: 0,
    RetentionClass.SEMANTIC: 0,
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class MemoryItem:
    content: str
    source: str
    agent_id: str
    retention: RetentionClass = RetentionClass.WORKING
    sensitivity: Sensitivity = Sensitivity.INTERNAL
    confidence: float = 0.5
    lane_id: str = ""
    item_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: str = field(default_factory=lambda: _now().isoformat())
    expires_at: str | None = None
    embedding: list[float] | None = None

    def to_dict(self) -> dict:
        return {
            "item_id": self.item_id, "content": self.content, "source": self.source,
            "agent_id": self.agent_id, "lane_id": self.lane_id,
            "retention": self.retention.value, "sensitivity": self.sensitivity.value,
            "confidence": self.confidence, "created_at": self.created_at,
            "expires_at": self.expires_at,
        }


SCHEMA = """
CREATE TABLE IF NOT EXISTS memory_items (
    item_id     TEXT PRIMARY KEY,
    content     TEXT NOT NULL,
    source      TEXT NOT NULL,
    agent_id    TEXT NOT NULL,
    lane_id     TEXT NOT NULL DEFAULT '',
    retention   TEXT NOT NULL,
    sensitivity TEXT NOT NULL,
    confidence  REAL NOT NULL,
    created_at  TEXT NOT NULL,
    expires_at  TEXT,
    embedding   TEXT
);
CREATE INDEX IF NOT EXISTS idx_memory_lane ON memory_items(lane_id);
CREATE INDEX IF NOT EXISTS idx_memory_expiry ON memory_items(expires_at);
"""


class MemoryStore:
    """SQLite-backed store.

    SQLite matches every other deployed Dominion service, so a single-node
    Council Node needs no new database dependency. The interface is kept
    narrow (write/search/expire) so the PostgreSQL + pgvector backend the
    work order specifies can replace it without touching callers.
    """

    def __init__(self, db_path: Path | str) -> None:
        self.db_path = Path(db_path).expanduser()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    # ── writes ──────────────────────────────────────────────────────────

    def write(self, item: MemoryItem) -> MemoryItem:
        """Store an item, refusing anything that carries a secret shape."""
        found = scan_for_secrets(item.content)
        if found:
            raise MemoryRejected(
                f"memory write refused: content matched {len(found)} secret pattern(s); "
                "credentials must never enter memory"
            )
        if item.retention is RetentionClass.SEMANTIC and item.sensitivity is Sensitivity.SENSITIVE:
            raise MemoryRejected(
                "sensitive content may not be written to long-lived semantic memory"
            )

        if item.expires_at is None:
            ttl = DEFAULT_TTL_SECONDS.get(item.retention, 0)
            if ttl:
                item.expires_at = (_now() + timedelta(seconds=ttl)).isoformat()

        self._conn.execute(
            """INSERT INTO memory_items
               (item_id, content, source, agent_id, lane_id, retention, sensitivity,
                confidence, created_at, expires_at, embedding)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (
                item.item_id, item.content, item.source, item.agent_id, item.lane_id,
                item.retention.value, item.sensitivity.value, item.confidence,
                item.created_at, item.expires_at,
                json.dumps(item.embedding) if item.embedding else None,
            ),
        )
        self._conn.commit()
        return item

    # ── reads ───────────────────────────────────────────────────────────

    def get(self, item_id: str) -> MemoryItem | None:
        row = self._conn.execute(
            "SELECT * FROM memory_items WHERE item_id = ?", (item_id,)
        ).fetchone()
        return self._row_to_item(row) if row else None

    def search(self, query: str, *, lane_id: str = "", limit: int = 10) -> list[MemoryItem]:
        """Keyword search over unexpired items.

        Deliberately lexical. A real embedding search belongs in pgvector; a
        fake similarity score here would be worse than an honest LIKE.
        """
        self.expire()
        sql = "SELECT * FROM memory_items WHERE content LIKE ?"
        params: list = [f"%{query}%"]
        if lane_id:
            sql += " AND lane_id = ?"
            params.append(lane_id)
        sql += " ORDER BY confidence DESC, created_at DESC LIMIT ?"
        params.append(limit)
        return [self._row_to_item(r) for r in self._conn.execute(sql, params).fetchall()]

    def expire(self) -> int:
        """Delete expired working memory. Returns how many were removed."""
        cur = self._conn.execute(
            "DELETE FROM memory_items WHERE expires_at IS NOT NULL AND expires_at < ?",
            (_now().isoformat(),),
        )
        self._conn.commit()
        return cur.rowcount

    def count(self) -> int:
        return int(self._conn.execute("SELECT COUNT(*) FROM memory_items").fetchone()[0])

    @staticmethod
    def _row_to_item(row: sqlite3.Row) -> MemoryItem:
        return MemoryItem(
            item_id=row["item_id"], content=row["content"], source=row["source"],
            agent_id=row["agent_id"], lane_id=row["lane_id"],
            retention=RetentionClass(row["retention"]),
            sensitivity=Sensitivity(row["sensitivity"]),
            confidence=row["confidence"], created_at=row["created_at"],
            expires_at=row["expires_at"],
            embedding=json.loads(row["embedding"]) if row["embedding"] else None,
        )
