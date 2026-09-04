"""
watchmen/saraqael.py — SARAQAEL (Audit Watchman)
=================================================
The first and foundational Watchman. Append-only, tamper-evident audit log
with cryptographic chain signatures. All other Watchmen report here.

Architecture:
  - Each entry is HMAC-SHA256 signed over its content plus the hash of the
    previous entry (chained). Altering, reordering, or removing any entry
    breaks the chain and is detected by verify_chain().
  - Machine-readable JSONL — one JSON object per line.
  - Exposes: log(), verify_chain(), tail(), report()

Security properties and their limits:
  - "Tamper-evident", not "tamper-proof". An attacker who can write the audit
    log can also delete it, and one who additionally holds the signing key can
    forge a self-consistent chain. What the chain guarantees is that
    modification without the key is *detectable*, not that it is prevented.
  - The signing key is machine-local and never lives in this repository.
    Anyone holding the key can sign entries, so the key file is the trust
    boundary — it is created 0600 inside a 0700 state directory.

Runtime state lives OUTSIDE the git checkout. Location resolution:
  1. $DOMINION_WATCHMEN_STATE_DIR
  2. ~/.dominion/watchmen            (default)

Signing key resolution (fail-closed — no predictable fallback exists):
  1. $DOMINION_WATCHMEN_HMAC_KEY        (used in memory only, never written)
  2. $DOMINION_WATCHMEN_HMAC_KEY_FILE   (must exist and be readable)
  3. <state dir>/watchmen_hmac.key      (generated with os/secrets randomness
                                         on first use, then reused)

Governance: phi = 1.618 | DominionBrain validation required for chain reset.
"""

import os
import sys
import json
import hmac
import secrets
import hashlib
import tempfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from phi_memory import get_store as _get_mem

_memory = _get_mem()
_AGENT  = "saraqael"

# ── Config ────────────────────────────────────────────────────

ENV_STATE_DIR = "DOMINION_WATCHMEN_STATE_DIR"
ENV_HMAC_KEY  = "DOMINION_WATCHMEN_HMAC_KEY"
ENV_HMAC_FILE = "DOMINION_WATCHMEN_HMAC_KEY_FILE"

DEFAULT_STATE_DIR = Path.home() / ".dominion" / "watchmen"

DIR_MODE  = 0o700
FILE_MODE = 0o600

# Legacy repo-local runtime artifacts from before audit state was moved out of
# the checkout. They are NON-AUTHORITATIVE: they were signed with a key that
# was published in this repository's source, so nothing about their contents
# can be trusted. They are never read, never imported, and never counted.
_BASE_DIR = Path(__file__).resolve().parent.parent
LEGACY_ARTIFACTS = (
    _BASE_DIR / "watchmen_audit.log",
    _BASE_DIR / "watchmen_chain.json",
)


class WatchmenStateError(RuntimeError):
    """Audit state could not be resolved, read, or trusted. Always fail closed."""


# ── Paths ─────────────────────────────────────────────────────

def state_dir() -> Path:
    """The machine-local audit state directory (not created by this call)."""
    override = os.environ.get(ENV_STATE_DIR, "").strip()
    return Path(override).expanduser() if override else DEFAULT_STATE_DIR


def audit_file() -> Path:
    return state_dir() / "watchmen_audit.log"


def chain_file() -> Path:
    return state_dir() / "watchmen_chain.json"


def key_file() -> Path:
    return state_dir() / "watchmen_hmac.key"


def _ensure_state_dir() -> Path:
    """Create the state directory on demand with owner-only permissions."""
    d = state_dir()
    try:
        d.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise WatchmenStateError(f"cannot create audit state directory: {exc}") from exc
    _chmod(d, DIR_MODE)
    return d


def _chmod(path: Path, mode: int) -> None:
    """Best-effort permission tightening; a no-op where the OS lacks support."""
    try:
        os.chmod(path, mode)
    except (OSError, NotImplementedError):
        pass


def legacy_repo_artifacts() -> list:
    """Legacy in-repo runtime files that still exist, reported but NEVER trusted.

    Returned purely so operators can see what to delete. No continuity is
    claimed between these files and the authoritative machine-local chain.
    """
    return [str(p) for p in LEGACY_ARTIFACTS if p.exists()]


# ── Signing key ───────────────────────────────────────────────

def _validate_key(raw: bytes, origin: str) -> bytes:
    key = raw.strip()
    if not key:
        raise WatchmenStateError(f"audit signing key from {origin} is empty or blank")
    return key


def _generate_key(path: Path) -> bytes:
    """Create a new random signing key atomically, 0600, without ever logging it."""
    key = secrets.token_hex(32).encode("ascii")
    fd = None
    try:
        # O_EXCL so a concurrent generator cannot be clobbered; if we lose the
        # race we fall back to reading the winner's key.
        fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, FILE_MODE)
        with os.fdopen(fd, "wb") as f:
            fd = None
            f.write(key + b"\n")
            f.flush()
            os.fsync(f.fileno())
    except FileExistsError:
        return _validate_key(path.read_bytes(), str(path))
    except OSError as exc:
        if fd is not None:
            os.close(fd)
        raise WatchmenStateError(f"cannot create audit signing key: {exc}") from exc
    _chmod(path, FILE_MODE)
    return key


def _resolve_key() -> bytes:
    """Resolve the HMAC signing key. Never returns a default or derived value."""
    env_key = os.environ.get(ENV_HMAC_KEY)
    if env_key is not None:
        return _validate_key(env_key.encode("utf-8"), f"${ENV_HMAC_KEY}")

    env_file = os.environ.get(ENV_HMAC_FILE)
    if env_file is not None:
        path = Path(env_file.strip()).expanduser()
        if not env_file.strip():
            raise WatchmenStateError(f"${ENV_HMAC_FILE} is set but empty")
        try:
            raw = path.read_bytes()
        except OSError as exc:
            raise WatchmenStateError(
                f"audit signing key file is missing or unreadable: {exc}") from exc
        return _validate_key(raw, str(path))

    _ensure_state_dir()
    path = key_file()
    if path.exists():
        try:
            raw = path.read_bytes()
        except OSError as exc:
            raise WatchmenStateError(
                f"audit signing key file is unreadable: {exc}") from exc
        return _validate_key(raw, str(path))
    return _generate_key(path)


# ── Atomic state writes ───────────────────────────────────────

def _atomic_write(path: Path, data: bytes) -> None:
    """Replace `path` atomically so a crash can never leave a half-written chain."""
    directory = path.parent
    fd, tmp = tempfile.mkstemp(dir=str(directory), prefix=path.name + ".", suffix=".tmp")
    try:
        if hasattr(os, "fchmod"):
            try:
                os.fchmod(fd, FILE_MODE)
            except (OSError, NotImplementedError):
                pass
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    _chmod(path, FILE_MODE)


# ── Chain helpers ─────────────────────────────────────────────

_GENESIS = {"last_hash": "GENESIS", "count": 0}


def _load_chain() -> dict:
    """Load chain state, failing closed rather than inventing a fresh genesis.

    A corrupt or unreadable chain file is a tamper signal. Silently resetting
    to GENESIS there would let an attacker erase history and have the next
    entry look like a legitimate first entry.
    """
    path = chain_file()
    if not path.exists():
        if audit_file().exists():
            raise WatchmenStateError(
                "chain state is missing while an audit log exists; "
                "refusing to fabricate chain continuity")
        return dict(_GENESIS)
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise WatchmenStateError(f"chain state unreadable: {exc}") from exc
    try:
        state = json.loads(raw)
    except (ValueError, TypeError) as exc:
        raise WatchmenStateError(f"chain state is corrupt: {exc}") from exc
    if (not isinstance(state, dict)
            or not isinstance(state.get("last_hash"), str)
            or not isinstance(state.get("count"), int)
            or state["count"] < 0):
        raise WatchmenStateError("chain state is malformed")
    return state


def _save_chain(state: dict) -> None:
    _atomic_write(chain_file(), (json.dumps(state, indent=2) + "\n").encode("utf-8"))


def _entry_hash(entry: dict, prev_hash: str, key: bytes) -> str:
    """HMAC-SHA256 of the entry content + previous hash."""
    payload = json.dumps(entry, sort_keys=True, ensure_ascii=True) + prev_hash
    return hmac.new(key, payload.encode(), hashlib.sha256).hexdigest()


def _append_entry(path: Path, line: str) -> None:
    """Append one JSONL record, creating the log 0600 if it does not exist."""
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_APPEND, FILE_MODE)
    with os.fdopen(fd, "a", encoding="utf-8") as f:
        f.write(line)
        f.flush()
        os.fsync(f.fileno())
    _chmod(path, FILE_MODE)


# ── Core API ──────────────────────────────────────────────────

def log(
    source: str,
    event: str,
    status: str = "info",
    details: dict = None,
    threat_level: str = "none",
) -> dict:
    """
    Append a cryptographically chained entry to the audit log.

    Args:
        source:       Watchman or system that generated the event
                      (e.g. 'gabriel', 'uriel', 'system')
        event:        Short event descriptor (e.g. 'ssh_attempt', 'file_modified')
        status:       'info' | 'warning' | 'critical' | 'ok'
        details:      Arbitrary dict — kept under 1KB
        threat_level: 'none' | 'low' | 'medium' | 'high' | 'critical'

    Returns:
        The completed entry dict (includes hash and sequence number).

    Raises:
        WatchmenStateError: if the signing key or chain state cannot be
        trusted. Refusing to write is deliberate — an unsigned or
        discontinuous entry is worse than no entry.
    """
    key   = _resolve_key()
    _ensure_state_dir()
    chain = _load_chain()
    ts    = datetime.now(timezone.utc).isoformat()

    entry = {
        "seq":          chain["count"] + 1,
        "ts":           ts,
        "source":       source,
        "event":        event,
        "status":       status,
        "threat_level": threat_level,
        "details":      details or {},
        "prev_hash":    chain["last_hash"],
    }

    entry_hash = _entry_hash(entry, chain["last_hash"], key)
    entry["hash"] = entry_hash

    _append_entry(audit_file(), json.dumps(entry, ensure_ascii=True) + "\n")

    chain["last_hash"] = entry_hash
    chain["count"]     = entry["seq"]
    _save_chain(chain)

    # PhiMemory: store critical events
    if threat_level in ("high", "critical"):
        try:
            level_map = {"high": 0.8, "critical": 1.0}
            _memory.store(_AGENT,
                [level_map.get(threat_level, 0.5), 1.0, 0.0, 0.0],
                metadata={"ts": ts[:19], "source": source, "event": event,
                          "threat": threat_level, "seq": entry["seq"]})
        except Exception:
            pass

    return entry


def _broken(seq, message: str) -> dict:
    return {"valid": False, "entries_checked": seq, "first_break": seq, "message": message}


def verify_chain() -> dict:
    """
    Walk the entire audit log and verify every hash, link, and sequence number.

    Returns a report dict with 'valid', 'entries_checked', 'first_break'.
    Every failure path reports valid=False with a truthful reason; no
    condition here is allowed to resolve to a silent pass.
    """
    path = audit_file()
    if not path.exists():
        try:
            chain = _load_chain()
        except WatchmenStateError as exc:
            return _broken(0, f"Chain state untrusted: {exc}")
        if chain["count"] != 0 or chain["last_hash"] != "GENESIS":
            return _broken(
                0, f"Audit log missing while chain state claims {chain['count']} entries")
        return {"valid": True, "entries_checked": 0, "first_break": None,
                "message": "Log empty"}

    try:
        key = _resolve_key()
    except WatchmenStateError as exc:
        return _broken(0, f"Signing key unavailable: {exc}")

    try:
        chain = _load_chain()
    except WatchmenStateError as exc:
        return _broken(0, f"Chain state untrusted: {exc}")

    entries = []
    with open(path, "r", encoding="utf-8") as f:
        for lineno, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                parsed = json.loads(line)
            except ValueError:
                # A line that no longer parses is corruption, not noise.
                # Skipping it would let an attacker mangle an entry into
                # invisibility and still be told the chain is intact.
                return _broken(lineno, f"Audit log line {lineno} is not valid JSON")
            if not isinstance(parsed, dict):
                return _broken(lineno, f"Audit log line {lineno} is not an object")
            entries.append(parsed)

    if not entries:
        if chain["count"] != 0:
            return _broken(
                0, f"Audit log has no entries while chain state claims {chain['count']}")
        return {"valid": True, "entries_checked": 0, "first_break": None,
                "message": "No entries"}

    prev_hash = "GENESIS"
    for index, e in enumerate(entries, start=1):
        seq = e.get("seq", index)
        if e.get("seq") != index:
            return _broken(index, f"Sequence break at position {index} (seq={e.get('seq')})")
        if e.get("prev_hash") != prev_hash:
            return _broken(seq, f"Broken link at entry #{seq}: prev_hash does not match")
        stored_hash = e.get("hash", "")
        e_copy = {k: v for k, v in e.items() if k != "hash"}
        expected = _entry_hash(e_copy, prev_hash, key)
        if not hmac.compare_digest(expected, stored_hash):
            return _broken(seq, f"Chain broken at entry #{seq} (ts={e.get('ts')})")
        prev_hash = stored_hash

    if chain["count"] != len(entries) or chain["last_hash"] != prev_hash:
        return _broken(
            len(entries),
            f"Chain state disagrees with audit log "
            f"(state count={chain['count']}, log entries={len(entries)})")

    return {
        "valid":           True,
        "entries_checked": len(entries),
        "first_break":     None,
        "message":         f"Chain intact across {len(entries)} entries",
    }


def _read_entries() -> list:
    path = audit_file()
    if not path.exists():
        return []
    entries = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except ValueError:
                continue
    return entries


def tail(n: int = 20) -> list:
    """Return the last N audit log entries."""
    return _read_entries()[-n:]


def report() -> dict:
    """Generate a summary report of the audit log."""
    entries = _read_entries()
    if not entries:
        return {"total": 0, "by_status": {}, "by_source": {}, "threats": []}

    total = 0
    by_status: dict = {}
    by_source: dict = {}
    threats   = []

    for e in entries:
        try:
            total += 1
            by_status[e["status"]]  = by_status.get(e["status"], 0) + 1
            by_source[e["source"]]  = by_source.get(e["source"], 0) + 1
            if e.get("threat_level") in ("high", "critical"):
                threats.append({
                    "seq":    e["seq"],
                    "ts":     e["ts"],
                    "source": e["source"],
                    "event":  e["event"],
                    "level":  e["threat_level"],
                })
        except KeyError:
            pass

    chain_status = verify_chain()

    return {
        "total":        total,
        "chain_valid":  chain_status["valid"],
        "chain_msg":    chain_status["message"],
        "by_status":    by_status,
        "by_source":    by_source,
        "open_threats": [t for t in threats[-10:]],
    }


def run():
    """Saraqael self-check — verify chain integrity and log startup."""
    log("saraqael", "startup", "ok", {"watchman": "Saraqael", "role": "audit"})
    result = verify_chain()
    status = "ok" if result["valid"] else "critical"
    log("saraqael", "chain_verify", status, result,
        threat_level="none" if result["valid"] else "critical")
    print(f"[SARAQAEL] Chain: {result['message']}")
    return result


if __name__ == "__main__":
    run()
    r = report()
    print(f"[SARAQAEL] Report: {r['total']} entries | Chain valid: {r['chain_valid']}")
