from __future__ import annotations
import hashlib
import hmac
import json
import time
import uuid

from .config import settings
from .db import tx


def _canon(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def append_audit(
    *,
    correlation_id: str,
    actor: str,
    action: str,
    target: str,
    result: str,
    before: dict | None = None,
    after: dict | None = None,
) -> str:
    before = before or {}
    after = after or {}
    ts = int(time.time())
    audit_id = str(uuid.uuid4())

    with tx(write=True) as conn:
        last = conn.execute(
            "SELECT entry_hash FROM audit_log ORDER BY seq DESC LIMIT 1"
        ).fetchone()
        prev_hash = last["entry_hash"] if last else "GENESIS"

        material = {
            "audit_id": audit_id,
            "correlation_id": correlation_id,
            "actor": actor,
            "action": action,
            "target": target,
            "result": result,
            "before": before,
            "after": after,
            "timestamp": ts,
            "prev_hash": prev_hash,
        }
        entry_hash = hmac.new(
            settings.audit_hmac_key.encode(),
            _canon(material).encode(),
            hashlib.sha256,
        ).hexdigest()

        conn.execute("""
            INSERT INTO audit_log(
                audit_id, correlation_id, actor, action, target, result,
                before_json, after_json, timestamp, prev_hash, entry_hash
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?)
        """, (
            audit_id, correlation_id, actor, action, target, result,
            _canon(before), _canon(after), ts, prev_hash, entry_hash
        ))
    return audit_id


def verify_audit_chain() -> dict:
    with tx() as conn:
        rows = conn.execute("SELECT * FROM audit_log ORDER BY seq ASC").fetchall()

    prev = "GENESIS"
    checked = 0
    for row in rows:
        if row["prev_hash"] != prev:
            return {"valid": False, "checked": checked, "error": "prev_hash mismatch"}
        material = {
            "audit_id": row["audit_id"],
            "correlation_id": row["correlation_id"],
            "actor": row["actor"],
            "action": row["action"],
            "target": row["target"],
            "result": row["result"],
            "before": json.loads(row["before_json"]),
            "after": json.loads(row["after_json"]),
            "timestamp": row["timestamp"],
            "prev_hash": row["prev_hash"],
        }
        expected = hmac.new(
            settings.audit_hmac_key.encode(),
            _canon(material).encode(),
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(expected, row["entry_hash"]):
            return {"valid": False, "checked": checked, "error": "entry_hash mismatch"}
        prev = row["entry_hash"]
        checked += 1

    return {"valid": True, "checked": checked, "head": prev}
