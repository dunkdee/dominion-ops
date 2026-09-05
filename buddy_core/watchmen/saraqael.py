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
    modification without the key is detectable, not that it is prevented.
  - The signing key is machine-local and never lives in this repository.
    Anyone holding the key can sign entries, so the key file is the trust
    boundary. On POSIX systems the state directory is enforced 0700 and the
    key/audit/chain files are enforced 0600; inability to enforce those modes
    is a fail-closed security error rather than a silent best effort.

Runtime state lives OUTSIDE the git checkout. Location resolution:
  1. $DOMINION_WATCHMEN_STATE_DIR
  2. ~/.dominion/watchmen            (default)

Signing key resolution (fail-closed — no predictable fallback exists):
  1. $DOMINION_WATCHMEN_HMAC_KEY        (used in memory only, never written)
  2. $DOMINION_WATCHMEN_HMAC_KEY_FILE   (must exist, be readable, and private)
  3. <state dir>/watchmen_hmac.key      (generated with cryptographic
                                         randomness on first use, then reused)

Governance: phi = 1.618 | DominionBrain validation required for chain reset.
"""

import os
import sys
import json
import hmac
import stat
import secrets
import hashlib
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone

try:
    import fcntl
except ImportError:  # pragma: no cover - Windows path
    fcntl = None

try:
    import msvcrt
except ImportError:  # pragma: no cover - POSIX path
    msvcrt = None
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


# ── Permission enforcement ───────────────────────────────────

def _posix_modes_required() -> bool:
    return os.name == "posix"


def _current_mode(path: Path) -> int:
    try:
        return stat.S_IMODE(path.stat().st_mode)
    except OSError as exc:
        raise WatchmenStateError(f"cannot inspect permissions for {path}: {exc}") from exc


def _enforce_mode(path: Path, mode: int) -> bool:
    """Enforce an exact owner-only mode on POSIX; fail closed if it cannot be set.

    Non-POSIX platforms do not expose equivalent POSIX mode semantics, so this
    returns False there without claiming that 0600/0700 was enforced.
    """
    if not _posix_modes_required():
        return False
    try:
        os.chmod(path, mode)
    except (OSError, NotImplementedError) as exc:
        raise WatchmenStateError(
            f"cannot enforce permissions {oct(mode)} on {path}: {exc}") from exc
    actual = _current_mode(path)
    if actual != mode:
        raise WatchmenStateError(
            f"permissions on {path} are {oct(actual)}, expected {oct(mode)}")
    return True


def _assert_private_file(path: Path, *, label: str) -> bool:
    """Require that a security-sensitive existing file is not group/world accessible."""
    if not _posix_modes_required():
        return False
    actual = _current_mode(path)
    if actual & 0o077:
        raise WatchmenStateError(
            f"{label} is not private: {path} has mode {oct(actual)}")
    return True


# ── Paths ─────────────────────────────────────────────────────

def _path_within(path: Path, parent: Path) -> bool:
    path = path.resolve(strict=False)
    parent = parent.resolve(strict=False)
    return path == parent or parent in path.parents


def _detect_checkout_root(start: Path | None = None) -> Path | None:
    """Return a concrete checkout root; never infer HOME merely from layout."""
    current = (start or _BASE_DIR).resolve(strict=False)
    if current.is_file():
        current = current.parent
    for candidate in (current, *current.parents):
        if (candidate / ".git").exists():
            return candidate.resolve(strict=False)
        if (candidate / ".github").is_dir() and (candidate / "buddy_core").is_dir():
            return candidate.resolve(strict=False)
    return None


def _path_is_source_controlled(path: Path) -> bool:
    candidate = path.expanduser().resolve(strict=False)
    # Always protect the runtime Buddy source tree, even in a copied deployment
    # that intentionally has no .git metadata.
    if _path_within(candidate, _BASE_DIR):
        return True
    checkout = _detect_checkout_root(_BASE_DIR)
    return checkout is not None and _path_within(candidate, checkout)


def state_dir() -> Path:
    """Resolve machine-local audit state without aliasing $HOME to a checkout."""
    override = os.environ.get(ENV_STATE_DIR, "").strip()
    candidate = (Path(override).expanduser() if override else DEFAULT_STATE_DIR).resolve(strict=False)
    if _path_is_source_controlled(candidate):
        raise WatchmenStateError(
            f"audit state directory must be outside Buddy source/repository checkout: {candidate}"
        )
    return candidate


def audit_file() -> Path:
    return state_dir() / "watchmen_audit.log"


def chain_file() -> Path:
    return state_dir() / "watchmen_chain.json"


def key_file() -> Path:
    return state_dir() / "watchmen_hmac.key"


def _ensure_state_dir() -> Path:
    """Create the state directory on demand and enforce owner-only permissions."""
    d = state_dir()
    try:
        d.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise WatchmenStateError(f"cannot create audit state directory: {exc}") from exc
    _enforce_mode(d, DIR_MODE)
    return d


@contextmanager
def _exclusive_audit_lock():
    """Serialize verify -> append -> chain-state replacement across processes."""
    directory = _ensure_state_dir()
    lock_path = directory / "watchmen_audit.lock"
    try:
        fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR, FILE_MODE)
    except OSError as exc:
        raise WatchmenStateError(f"cannot open audit transaction lock: {exc}") from exc
    try:
        _enforce_mode(lock_path, FILE_MODE)
        if fcntl is not None:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX)
            except OSError as exc:
                raise WatchmenStateError(f"cannot acquire audit transaction lock: {exc}") from exc
            try:
                yield
            finally:
                try:
                    fcntl.flock(fd, fcntl.LOCK_UN)
                except OSError:
                    pass
            return

        if msvcrt is not None:  # pragma: no cover - Windows runner path
            try:
                if os.fstat(fd).st_size == 0:
                    os.write(fd, b"0")
                    os.fsync(fd)
                os.lseek(fd, 0, os.SEEK_SET)
                msvcrt.locking(fd, msvcrt.LK_LOCK, 1)
            except OSError as exc:
                raise WatchmenStateError(f"cannot acquire audit transaction lock: {exc}") from exc
            try:
                yield
            finally:
                try:
                    os.lseek(fd, 0, os.SEEK_SET)
                    msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
                except OSError:
                    pass
            return

        raise WatchmenStateError("cross-process audit transaction locking is unsupported")
    finally:
        os.close(fd)


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
    if len(key) < 32:
        raise WatchmenStateError(f"audit signing key from {origin} is weaker than 256 bits")
    return key


def _generate_key(path: Path) -> bytes:
    """Create a new random signing key atomically, 0600, without ever logging it."""
    key = secrets.token_hex(32).encode("ascii")
    fd = None
    try:
        # O_EXCL means a concurrent generator cannot be clobbered; if we lose
        # the race we read the winner only after verifying its privacy.
        fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, FILE_MODE)
        if _posix_modes_required() and hasattr(os, "fchmod"):
            try:
                os.fchmod(fd, FILE_MODE)
            except (OSError, NotImplementedError) as exc:
                raise WatchmenStateError(
                    f"cannot protect generated audit signing key: {exc}") from exc
        with os.fdopen(fd, "wb") as f:
            fd = None
            f.write(key + b"\n")
            f.flush()
            os.fsync(f.fileno())
    except FileExistsError:
        _assert_private_file(path, label="audit signing key file")
        try:
            return _validate_key(path.read_bytes(), str(path))
        except OSError as exc:
            raise WatchmenStateError(f"audit signing key file is unreadable: {exc}") from exc
    except BaseException:
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass
        raise
    _enforce_mode(path, FILE_MODE)
    return key


def _resolve_key() -> bytes:
    """Resolve the HMAC signing key. Never returns a default or derived value."""
    env_key = os.environ.get(ENV_HMAC_KEY)
    if env_key is not None:
        return _validate_key(env_key.encode("utf-8"), f"${ENV_HMAC_KEY}")

    env_file = os.environ.get(ENV_HMAC_FILE)
    if env_file is not None:
        if not env_file.strip():
            raise WatchmenStateError(f"${ENV_HMAC_FILE} is set but empty")
        path = Path(env_file.strip()).expanduser().resolve(strict=False)
        if _path_is_source_controlled(path):
            raise WatchmenStateError(
                f"explicit audit signing key file must be outside Buddy source/repository checkout: {path}"
            )
        try:
            _assert_private_file(path, label="explicit audit signing key file")
            raw = path.read_bytes()
        except WatchmenStateError:
            raise
        except OSError as exc:
            raise WatchmenStateError(
                f"audit signing key file is missing or unreadable: {exc}") from exc
        return _validate_key(raw, str(path))

    _ensure_state_dir()
    path = key_file()
    if path.exists():
        _assert_private_file(path, label="audit signing key file")
        try:
            raw = path.read_bytes()
        except OSError as exc:
            raise WatchmenStateError(
                f"audit signing key file is unreadable: {exc}") from exc
        return _validate_key(raw, str(path))
    if audit_file().exists() or chain_file().exists():
        raise WatchmenStateError(
            "audit signing key is missing while audit history exists; explicit recovery is required"
        )
    return _generate_key(path)


# ── Atomic state writes ───────────────────────────────────────

def _atomic_write(path: Path, data: bytes) -> None:
    """Replace ``path`` atomically so a crash cannot leave half-written state."""
    directory = path.parent
    fd, tmp = tempfile.mkstemp(dir=str(directory), prefix=path.name + ".", suffix=".tmp")
    try:
        if _posix_modes_required() and hasattr(os, "fchmod"):
            try:
                os.fchmod(fd, FILE_MODE)
            except (OSError, NotImplementedError) as exc:
                raise WatchmenStateError(
                    f"cannot protect temporary audit state file: {exc}") from exc
        with os.fdopen(fd, "wb") as f:
            fd = None
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
        if _posix_modes_required():
            dir_fd = None
            try:
                dir_fd = os.open(str(directory), os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
                os.fsync(dir_fd)
            except (OSError, NotImplementedError) as exc:
                raise WatchmenStateError(
                    f"cannot fsync audit state directory after replacement: {exc}"
                ) from exc
            finally:
                if dir_fd is not None:
                    try:
                        os.close(dir_fd)
                    except OSError:
                        pass
    except BaseException:
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    _enforce_mode(path, FILE_MODE)


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
    _assert_private_file(path, label="audit chain state")
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
    fd = None
    try:
        fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_APPEND, FILE_MODE)
        if _posix_modes_required() and hasattr(os, "fchmod"):
            try:
                os.fchmod(fd, FILE_MODE)
            except (OSError, NotImplementedError) as exc:
                raise WatchmenStateError(
                    f"cannot protect audit log before append: {exc}") from exc
        with os.fdopen(fd, "a", encoding="utf-8") as f:
            fd = None
            f.write(line)
            f.flush()
            os.fsync(f.fileno())
    except BaseException:
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass
        raise
    _enforce_mode(path, FILE_MODE)


# ── Core API ──────────────────────────────────────────────────

def log(
    source: str,
    event: str,
    status: str = "info",
    details: dict = None,
    threat_level: str = "none",
) -> dict:
    """Append a cryptographically chained entry to the audit log.

    Existing history is verified before appending. If the chain is corrupt,
    unreadable, improperly protected, or cannot be verified with the active
    key, the write is refused rather than extending untrusted history.
    """
    with _exclusive_audit_lock():
        key = _resolve_key()
        _ensure_state_dir()

        if audit_file().exists() or chain_file().exists():
            existing = verify_chain()
            if existing.get("valid") is not True:
                raise WatchmenStateError(
                    f"existing audit history is untrusted: {existing.get('message', 'unknown failure')}"
                )

        chain = _load_chain()
        ts = datetime.now(timezone.utc).isoformat()

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
        chain["count"] = entry["seq"]
        _save_chain(chain)

    # PhiMemory: store critical events. This is secondary memory, not authority.
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
    """Verify every hash, link, sequence number, state value, and permission boundary."""
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
        _assert_private_file(path, label="audit log")
        key = _resolve_key()
    except WatchmenStateError as exc:
        return _broken(0, f"Audit trust boundary unavailable: {exc}")

    try:
        chain = _load_chain()
    except WatchmenStateError as exc:
        return _broken(0, f"Chain state untrusted: {exc}")

    entries = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for lineno, line in enumerate(f, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    parsed = json.loads(line)
                except ValueError:
                    return _broken(lineno, f"Audit log line {lineno} is not valid JSON")
                if not isinstance(parsed, dict):
                    return _broken(lineno, f"Audit log line {lineno} is not an object")
                entries.append(parsed)
    except OSError as exc:
        return _broken(0, f"Audit log unreadable: {exc}")

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
        if not isinstance(stored_hash, str):
            return _broken(seq, f"Entry #{seq} has an invalid hash field")
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
    """Read audit entries strictly; malformed records are corruption, not noise."""
    path = audit_file()
    if not path.exists():
        return []
    _assert_private_file(path, label="audit log")
    entries = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for lineno, line in enumerate(f, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    parsed = json.loads(line)
                except ValueError as exc:
                    raise WatchmenStateError(
                        f"audit log line {lineno} is not valid JSON") from exc
                if not isinstance(parsed, dict):
                    raise WatchmenStateError(
                        f"audit log line {lineno} is not an object")
                entries.append(parsed)
    except WatchmenStateError:
        raise
    except OSError as exc:
        raise WatchmenStateError(f"audit log unreadable: {exc}") from exc
    return entries


def tail(n: int = 20) -> list:
    """Return the last N entries only after the entire chain verifies."""
    status = verify_chain()
    if status.get("valid") is not True:
        raise WatchmenStateError(
            f"audit history is untrusted: {status.get('message', 'unknown verification failure')}"
        )
    return _read_entries()[-n:]


def report() -> dict:
    """Generate a truthful summary; corruption can never be summarized as healthy."""
    try:
        entries = _read_entries()
    except WatchmenStateError as exc:
        return {
            "total": 0,
            "chain_valid": False,
            "chain_msg": f"Audit state untrusted: {exc}",
            "by_status": {},
            "by_source": {},
            "open_threats": [],
            "corruption_visible": True,
        }

    chain_status = verify_chain()
    if not entries:
        return {
            "total": 0,
            "chain_valid": chain_status["valid"],
            "chain_msg": chain_status["message"],
            "by_status": {},
            "by_source": {},
            "open_threats": [],
            "corruption_visible": not chain_status["valid"],
        }

    total = 0
    by_status: dict = {}
    by_source: dict = {}
    threats = []

    for index, e in enumerate(entries, start=1):
        required = ("status", "source", "seq", "ts", "event")
        missing = [field for field in required if field not in e]
        if missing:
            chain_status = _broken(index, f"Audit entry {index} missing fields: {', '.join(missing)}")
            break
        total += 1
        by_status[e["status"]] = by_status.get(e["status"], 0) + 1
        by_source[e["source"]] = by_source.get(e["source"], 0) + 1
        if e.get("threat_level") in ("high", "critical"):
            threats.append({
                "seq": e["seq"],
                "ts": e["ts"],
                "source": e["source"],
                "event": e["event"],
                "level": e["threat_level"],
            })

    return {
        "total": total,
        "chain_valid": chain_status["valid"],
        "chain_msg": chain_status["message"],
        "by_status": by_status,
        "by_source": by_source,
        "open_threats": [t for t in threats[-10:]],
        "corruption_visible": not chain_status["valid"],
    }


def run():
    """Saraqael self-check — verify chain integrity and log startup."""
    # Refuse to extend any pre-existing untrusted history.
    if audit_file().exists() or chain_file().exists():
        before = verify_chain()
        if before.get("valid") is not True:
            raise WatchmenStateError(f"cannot start Saraqael on untrusted history: {before['message']}")
    log("saraqael", "startup", "ok", {"watchman": "Saraqael", "role": "audit"})
    result = verify_chain()
    status = "ok" if result["valid"] else "critical"
    if result["valid"]:
        log("saraqael", "chain_verify", status, result, threat_level="none")
    print(f"[SARAQAEL] Chain: {result['message']}")
    return result


if __name__ == "__main__":
    run()
    r = report()
    print(f"[SARAQAEL] Report: {r['total']} entries | Chain valid: {r['chain_valid']}")
