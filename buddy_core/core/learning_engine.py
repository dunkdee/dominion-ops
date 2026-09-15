"""Evidence-backed learning for Buddy.

Learning may improve knowledge, routing suggestions, playbooks, and strategy.
It never changes Founder authority, credentials, privileged policy, or production
code automatically.
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

_STATE = Path(os.getenv("BUDDY_STATE_DIR", str(Path.home() / ".dominion" / "buddy")))
LESSONS = _STATE / "lessons.jsonl"
MISSIONS = _STATE / "missions.jsonl"
AUDIT = _STATE / "audit.jsonl"
_lock = threading.RLock()
_LOCK_NAME = ".state.lock"


def _ensure(state_dir: Path | None = None):
    (state_dir or _STATE).mkdir(parents=True, exist_ok=True)


@contextmanager
def state_lock(state_dir: Path | str | None = None):
    """Serialize Buddy state access across threads and processes on one machine."""
    directory = Path(state_dir) if state_dir is not None else _STATE
    _ensure(directory)
    lock_path = directory / _LOCK_NAME
    with _lock:
        with lock_path.open("a+b") as handle:
            if os.name == "nt":
                import msvcrt

                handle.seek(0, os.SEEK_END)
                if handle.tell() == 0:
                    handle.write(b"\0")
                    handle.flush()
                    os.fsync(handle.fileno())
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
                try:
                    yield
                finally:
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
                try:
                    yield
                finally:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def default_state_dir() -> Path:
    return _STATE


def _safe(value):
    """Recursively redact common secret-bearing fields from persisted evidence."""
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            lk = str(k).lower()
            secretish = ("password", "secret", "token", "api_key", "apikey", "cookie", "hmac_key")
            if (any(x in lk for x in secretish) or lk == "approval_hash" or
                    (lk == "authorization" and not isinstance(v, dict))):
                out[k] = "[REDACTED]"
            else:
                out[k] = _safe(v)
        return out
    if isinstance(value, list):
        return [_safe(v) for v in value]
    if isinstance(value, str) and len(value) > 20000:
        return value[:20000] + "...[TRUNCATED]"
    return value


def _append(path: Path, record: dict):
    _ensure()
    clean = _safe(record)
    raw = json.dumps(clean, ensure_ascii=False, sort_keys=True)
    clean["record_hash"] = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    line = json.dumps(clean, ensure_ascii=False) + "\n"
    with state_lock():
        with path.open("a", encoding="utf-8") as handle:
            handle.write(line)
            handle.flush()
            os.fsync(handle.fileno())
    return clean


def record_lesson(topic: str, lesson: str, *, evidence=None, confidence: float = 0.5,
                  lesson_class: str = "AGENT_INFERENCE", verified: bool = False) -> dict:
    allowed = {"FOUNDER_CONFIRMED_PREFERENCE", "OBSERVED_OUTCOME", "AGENT_INFERENCE", "WEB_RESEARCH"}
    if lesson_class not in allowed:
        raise ValueError("unsupported lesson class")
    if lesson_class == "FOUNDER_CONFIRMED_PREFERENCE" and not verified:
        raise ValueError("founder preference requires explicit verification")
    record = {
        "type": "lesson",
        "topic": topic.strip()[:500],
        "lesson": lesson.strip()[:12000],
        "lesson_class": lesson_class,
        "confidence": max(0.0, min(float(confidence), 1.0)),
        "verified": bool(verified),
        "evidence": evidence or [],
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "authority_effect": "NONE",
    }
    return _append(LESSONS, record)


def record_mission(record: dict) -> dict:
    payload = dict(record)
    payload.setdefault("type", "mission")
    payload.setdefault("timestamp", datetime.now(timezone.utc).isoformat())
    return _append(MISSIONS, payload)


def audit(event: str, data: dict) -> dict:
    return _append(AUDIT, {
        "type": "audit",
        "event": event,
        "data": data,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })


def recent_lessons(topic: str | None = None, limit: int = 20) -> list[dict]:
    if not LESSONS.exists():
        return []
    rows = []
    needle = (topic or "").lower().strip()
    try:
        with state_lock():
            lines = LESSONS.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    for line in reversed(lines):
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if needle and needle not in (str(row.get("topic", "")) + " " + str(row.get("lesson", ""))).lower():
            continue
        rows.append(row)
        if len(rows) >= max(1, min(limit, 100)):
            break
    return rows
