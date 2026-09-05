"""
Founder authorization ledger — the key to the external boundary.
================================================================

BUDDY_CONSTITUTION.md requires Founder authorization when an action crosses a
materially consequential boundary, and allows a *reviewed standing
authorization* to pre-authorize a class of actions with explicit scope,
limits, destinations, budgets, expiry, and evidence requirements.

The operator already enforces the gate: any capability marked
``auth_required`` (or classified ``privileged_write``/``destructive``) is HELD
before dispatch. What was missing is the other half — a way to actually issue
that authorization. The hold minted a throwaway UUID, persisted nothing, and
nothing on the system could ever redeem it. A gate with no key is not
governance; it is a dead end, and it silently stalls every lane Radah
Memshalah prepares work for.

This module supplies the key, using the same discipline
``control_plane/final_release.py`` already proves for releases:

* **Bound to the payload.** An authorization carries ``payload_hash`` — the
  canonical hash of the exact capability, instruction and content held. It
  authorizes *that action*, never a blank cheque. Change so much as a
  character of what gets published and the authorization no longer matches.
* **Authenticated.** ``approval_hash`` is an HMAC-SHA256 over the whole
  record using a machine-local secret outside writable Buddy state. A process
  that can edit ledger JSON cannot manufacture Founder authority.
* **Single-use.** Consumption is recorded; a spent authorization can never be
  replayed.
* **Monotonic.** Each grant takes the next ``authorization_sequence``, so an
  older authorization cannot be resurrected out of order.
* **Expiring.** An unused grant goes stale rather than lingering forever.
* **Fail closed.** Every verification failure denies. There is no path where
  ambiguity results in execution.

Nothing here executes anything. It decides whether an execution is authorized
and leaves the receipt proving why.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import stat
import tempfile
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

try:
    import fcntl
except ImportError:  # pragma: no cover - Windows
    fcntl = None

try:
    import msvcrt
except ImportError:  # pragma: no cover - POSIX
    msvcrt = None

SCHEMA = "dominion-founder-authorization-v1"
AUTH_HMAC_ENV = "DOMINION_AUTHORIZATION_HMAC_KEY"
AUTH_HMAC_FILE_ENV = "DOMINION_AUTHORIZATION_HMAC_KEY_FILE"
AUTH_DEFAULT_KEY_FILE = Path.home() / ".dominion" / "authorization" / "ledger_hmac.key"

# An unused grant expires rather than lingering as a standing blank cheque.
DEFAULT_TTL_SECONDS = 24 * 3600

PENDING = "PENDING"
GRANTED = "GRANTED"
CONSUMED = "CONSUMED"
DENIED = "DENIED"
EXPIRED = "EXPIRED"


class AuthorizationError(Exception):
    """Raised only for programmer error. Policy denials are returned, not raised."""


def canonical_json(value: Any) -> str:
    """Deterministic JSON, matching control_plane.canonical."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _record_mac_material(record: dict) -> bytes:
    return canonical_json({k: v for k, v in record.items() if k != "approval_hash"}).encode("utf-8")


def _path_within(path: Path, parent: Path) -> bool:
    path = path.resolve(strict=False)
    parent = parent.resolve(strict=False)
    return path == parent or parent in path.parents


def _detect_checkout_root(start: Path | None = None) -> Path | None:
    current = (start or Path(__file__)).resolve(strict=False)
    if current.is_file():
        current = current.parent
    for candidate in (current, *current.parents):
        if (candidate / ".git").exists():
            return candidate.resolve(strict=False)
        if (candidate / ".github").is_dir() and (candidate / "buddy_core").is_dir():
            return candidate.resolve(strict=False)
    return None


def _validate_auth_key(raw: bytes, origin: str) -> bytes:
    key = raw.strip()
    if len(key) < 32:
        raise AuthorizationError(f"authorization signing key from {origin} is weaker than 256 bits")
    return key


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).isoformat()


def _parse(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def payload_fingerprint(capability: str, instruction: str, content: Any = None,
                        destination: str | None = None) -> str:
    """Hash the exact action being authorized.

    Destination is part of the identity on purpose: authorizing a post to one
    place must never authorize the same words somewhere else.
    """
    return sha256_json({
        "capability": capability,
        "instruction": instruction,
        "content": content,
        "destination": destination,
    })


class AuthorizationLedger:
    """Durable store of Founder authorization requests and grants."""

    def __init__(self, state_dir: Path | str):
        self.state_dir = Path(state_dir).expanduser().resolve(strict=False)
        self.root = self.state_dir / "authorizations"
        self.root.mkdir(parents=True, exist_ok=True)
        self.receipts_path = self.root / "receipts.jsonl"
        self.sequence_path = self.root / "sequence.json"
        self.lock_path = self.root / ".ledger.lock"
        self._hmac_key = self._resolve_signing_key()

    def _resolve_signing_key(self) -> bytes:
        direct = os.environ.get(AUTH_HMAC_ENV)
        if direct is not None:
            return _validate_auth_key(direct.encode("utf-8"), f"${AUTH_HMAC_ENV}")

        configured = os.environ.get(AUTH_HMAC_FILE_ENV)
        if configured is not None and not configured.strip():
            raise AuthorizationError(f"${AUTH_HMAC_FILE_ENV} is set but empty")
        path = (
            Path(configured.strip()).expanduser().resolve(strict=False)
            if configured is not None
            else AUTH_DEFAULT_KEY_FILE.expanduser().resolve(strict=False)
        )

        source_root = Path(__file__).resolve(strict=False).parents[1]
        checkout_root = _detect_checkout_root(Path(__file__))
        if _path_within(path, self.state_dir):
            raise AuthorizationError("authorization signing key must be outside writable Buddy state")
        if _path_within(path, source_root):
            raise AuthorizationError("authorization signing key must be outside Buddy source")
        if checkout_root is not None and _path_within(path, checkout_root):
            raise AuthorizationError("authorization signing key must be outside repository checkout")

        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            if os.name == "posix":
                os.chmod(path.parent, 0o700)
                if stat.S_IMODE(path.parent.stat().st_mode) != 0o700:
                    raise AuthorizationError("authorization signing key directory is not private")
        except AuthorizationError:
            raise
        except OSError as exc:
            raise AuthorizationError("authorization signing key directory unavailable") from exc

        def read_existing() -> bytes:
            try:
                if os.name == "posix" and stat.S_IMODE(path.stat().st_mode) & 0o077:
                    raise AuthorizationError("authorization signing key file is not private")
                return _validate_auth_key(path.read_bytes(), str(path))
            except AuthorizationError:
                raise
            except OSError as exc:
                raise AuthorizationError("authorization signing key file unreadable") from exc

        if path.exists():
            return read_existing()

        key = secrets.token_hex(32).encode("ascii")
        fd = None
        try:
            fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            if os.name == "posix" and hasattr(os, "fchmod"):
                os.fchmod(fd, 0o600)
            with os.fdopen(fd, "wb") as fh:
                fd = None
                fh.write(key + b"\n")
                fh.flush()
                os.fsync(fh.fileno())
            if os.name == "posix":
                dir_fd = os.open(str(path.parent), os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
                try:
                    os.fsync(dir_fd)
                finally:
                    os.close(dir_fd)
                os.chmod(path, 0o600)
                if stat.S_IMODE(path.stat().st_mode) != 0o600:
                    raise AuthorizationError("authorization signing key file is not private")
            return key
        except FileExistsError:
            return read_existing()
        except AuthorizationError:
            raise
        except OSError as exc:
            raise AuthorizationError("authorization signing key generation failed") from exc
        finally:
            if fd is not None:
                try:
                    os.close(fd)
                except OSError:
                    pass

    def _record_mac(self, record: dict) -> str:
        return hmac.new(self._hmac_key, _record_mac_material(record), hashlib.sha256).hexdigest()

    def _record_mac_valid(self, record: dict) -> bool:
        supplied = record.get("approval_hash")
        if not isinstance(supplied, str) or len(supplied) != 64:
            return False
        return hmac.compare_digest(supplied, self._record_mac(record))

    # ── storage ──────────────────────────────────────────────────────────

    @contextmanager
    def _exclusive_lock(self):
        """Serialize grant/deny/redeem across processes, failing closed."""
        try:
            fd = os.open(self.lock_path, os.O_CREAT | os.O_RDWR, 0o600)
        except OSError as exc:
            raise AuthorizationError("authorization_lock_unavailable") from exc
        try:
            try:
                os.chmod(self.lock_path, 0o600)
            except OSError:
                pass
            if fcntl is not None:
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX)
                except OSError as exc:
                    raise AuthorizationError("authorization_lock_unavailable") from exc
                try:
                    yield
                finally:
                    try:
                        fcntl.flock(fd, fcntl.LOCK_UN)
                    except OSError:
                        pass
                return
            if msvcrt is not None:  # pragma: no cover - Windows
                try:
                    if os.fstat(fd).st_size == 0:
                        os.write(fd, b"0")
                        os.fsync(fd)
                    os.lseek(fd, 0, os.SEEK_SET)
                    msvcrt.locking(fd, msvcrt.LK_LOCK, 1)
                except OSError as exc:
                    raise AuthorizationError("authorization_lock_unavailable") from exc
                try:
                    yield
                finally:
                    try:
                        os.lseek(fd, 0, os.SEEK_SET)
                        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
                    except OSError:
                        pass
                return
            raise AuthorizationError("authorization_lock_unsupported")
        finally:
            os.close(fd)

    def _atomic_write_text(self, path: Path, value: str) -> None:
        fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=path.name + ".", suffix=".tmp")
        try:
            if hasattr(os, "fchmod"):
                try:
                    os.fchmod(fd, 0o600)
                except OSError:
                    pass
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fd = None
                fh.write(value)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp, path)
            if os.name == "posix":
                dir_fd = None
                try:
                    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
                    dir_fd = os.open(str(path.parent), flags)
                    os.fsync(dir_fd)
                except (OSError, NotImplementedError) as exc:
                    raise AuthorizationError("authorization_state_directory_fsync_failed") from exc
                finally:
                    if dir_fd is not None:
                        try:
                            os.close(dir_fd)
                        except OSError:
                            pass
            try:
                path.chmod(0o600)
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

    def _path(self, approval_id: str) -> Path:
        # Guard against traversal via a crafted id.
        if not approval_id or "/" in approval_id or "\\" in approval_id or approval_id.startswith("."):
            raise AuthorizationError("invalid approval_id")
        return self.root / f"{approval_id}.json"

    def _write(self, record: dict) -> dict:
        path = self._path(record["approval_id"])
        self._atomic_write_text(path, canonical_json(record) + "\n")
        return record

    def load(self, approval_id: str) -> dict | None:
        path = self._path(approval_id)
        if not path.is_file():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def _next_sequence(self) -> int:
        # Derive monotonic authority from authenticated records, not a mutable cache.
        current = 0
        for path in self.root.glob("approval_*.json"):
            try:
                record = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if not self._record_mac_valid(record):
                continue
            try:
                current = max(current, int(record.get("authorization_sequence") or 0))
            except (TypeError, ValueError):
                continue
        nxt = current + 1
        self._atomic_write_text(
            self.sequence_path, canonical_json({"sequence": nxt}) + "\n"
        )
        return nxt

    def _receipt(self, event: str, record: dict, **extra) -> None:
        entry = {
            "schema": SCHEMA,
            "event": event,
            "approval_id": record.get("approval_id"),
            "mission_id": record.get("mission_id"),
            "capability": record.get("capability"),
            "destination": record.get("destination"),
            "payload_hash": record.get("payload_hash"),
            "status": record.get("status"),
            "observed_at": _iso(_now()),
            **extra,
        }
        try:
            with self.receipts_path.open("a", encoding="utf-8") as fh:
                fh.write(canonical_json(entry) + "\n")
        except OSError:
            pass

    # ── lifecycle ────────────────────────────────────────────────────────

    def request(self, *, mission_id: str, step: int, capability: str,
                instruction: str, content: Any = None, destination: str | None = None,
                policy_tags: list | None = None, ttl_seconds: int = DEFAULT_TTL_SECONDS) -> dict:
        """Record a held boundary as a pending authorization request."""
        approval_id = "approval_" + uuid.uuid4().hex[:12]
        now = _now()
        record = {
            "schema": SCHEMA,
            "approval_id": approval_id,
            "status": PENDING,
            "mission_id": mission_id,
            "step": step,
            "capability": capability,
            "instruction": instruction,
            "destination": destination,
            "policy_tags": list(policy_tags or []),
            "payload_hash": payload_fingerprint(capability, instruction, content, destination),
            "content_preview": _preview(content, instruction),
            "reason": "FOUNDER_AUTHORIZATION_REQUIRED",
            "requested_at": _iso(now),
            "expires_at": _iso(now + timedelta(seconds=ttl_seconds)),
            "authorization_sequence": None,
            "approver": None,
            "granted_at": None,
            "consumed_at": None,
        }
        record["approval_hash"] = self._record_mac(record)
        self._write(record)
        self._receipt("authorization_requested", record)
        return record

    def pending(self) -> list:
        """Every request still awaiting a decision, newest first."""
        out = []
        for path in self.root.glob("approval_*.json"):
            try:
                record = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if not self._record_mac_valid(record):
                continue
            if record.get("status") != PENDING:
                continue
            if self._is_expired(record):
                continue
            out.append(record)
        out.sort(key=lambda r: r.get("requested_at") or "", reverse=True)
        return out

    def _is_expired(self, record: dict) -> bool:
        expires = _parse(record.get("expires_at"))
        return bool(expires and _now() > expires)

    def grant(self, approval_id: str, *, approver: str = "founder") -> dict:
        with self._exclusive_lock():
            return self._grant_locked(approval_id, approver=approver)

    def _grant_locked(self, approval_id: str, *, approver: str = "founder") -> dict:
        """Founder authorizes this specific held action. Fails closed."""
        record = self.load(approval_id)
        if record is None:
            return {"ok": False, "error": "unknown_approval_id"}
        if not self._record_mac_valid(record):
            return {"ok": False, "error": "authorization_record_tampered"}
        if record.get("status") == CONSUMED:
            return {"ok": False, "error": "already_consumed"}
        if record.get("status") == DENIED:
            return {"ok": False, "error": "already_denied"}
        if record.get("status") == GRANTED:
            return {"ok": False, "error": "already_granted"}
        if record.get("status") != PENDING:
            return {"ok": False, "error": "not_pending"}
        if self._is_expired(record):
            record["status"] = EXPIRED
            record["approval_hash"] = self._record_mac(record)
            self._write(record)
            self._receipt("authorization_expired", record)
            return {"ok": False, "error": "expired"}

        record["status"] = GRANTED
        record["approver"] = approver
        record["granted_at"] = _iso(_now())
        record["authorization_sequence"] = self._next_sequence()
        record["approval_hash"] = self._record_mac(record)
        self._write(record)
        self._receipt("authorization_granted", record,
                      authorization_sequence=record["authorization_sequence"],
                      approver=approver)
        return {"ok": True, "authorization": record}

    def deny(self, approval_id: str, *, approver: str = "founder", reason: str = "") -> dict:
        with self._exclusive_lock():
            return self._deny_locked(approval_id, approver=approver, reason=reason)

    def _deny_locked(self, approval_id: str, *, approver: str = "founder", reason: str = "") -> dict:
        record = self.load(approval_id)
        if record is None:
            return {"ok": False, "error": "unknown_approval_id"}
        if not self._record_mac_valid(record):
            return {"ok": False, "error": "authorization_record_tampered"}
        if record.get("status") in {CONSUMED, DENIED}:
            return {"ok": False, "error": "already_" + record["status"].lower()}
        record["status"] = DENIED
        record["approver"] = approver
        record["denied_reason"] = reason
        record["denied_at"] = _iso(_now())
        record["approval_hash"] = self._record_mac(record)
        self._write(record)
        self._receipt("authorization_denied", record, approver=approver, reason=reason)
        return {"ok": True, "authorization": record}

    def verify_and_consume(self, approval_id: str, *, capability: str, instruction: str,
                           content: Any = None, destination: str | None = None) -> dict:
        with self._exclusive_lock():
            return self._verify_and_consume_locked(
                approval_id,
                capability=capability,
                instruction=instruction,
                content=content,
                destination=destination,
            )

    def _verify_and_consume_locked(self, approval_id: str, *, capability: str, instruction: str,
                                    content: Any = None, destination: str | None = None) -> dict:
        """Single-use redemption, immediately before execution.

        Every failure denies. The payload presented here must hash identically
        to the payload that was authorized, so an approval can never be
        redirected onto different content or a different destination.
        """
        record = self.load(approval_id)
        if record is None:
            return {"ok": False, "error": "unknown_approval_id"}
        if not self._record_mac_valid(record):
            self._receipt("authorization_rejected", record, error="record_tampered")
            return {"ok": False, "error": "authorization_record_tampered"}
        if record.get("status") == CONSUMED:
            self._receipt("authorization_rejected", record, error="replay")
            return {"ok": False, "error": "already_consumed"}
        if record.get("status") != GRANTED:
            return {"ok": False, "error": "not_granted"}
        if self._is_expired(record):
            record["status"] = EXPIRED
            record["approval_hash"] = self._record_mac(record)
            self._write(record)
            self._receipt("authorization_expired", record)
            return {"ok": False, "error": "expired"}

        presented = payload_fingerprint(capability, instruction, content, destination)
        if presented != record.get("payload_hash"):
            self._receipt("authorization_rejected", record, error="payload_mismatch",
                          presented_payload_hash=presented)
            return {"ok": False, "error": "payload_mismatch"}

        record["status"] = CONSUMED
        record["consumed_at"] = _iso(_now())
        record["approval_hash"] = self._record_mac(record)
        self._write(record)
        self._receipt("authorization_consumed", record)
        return {"ok": True, "authorization": record}


def _preview(content: Any, instruction: str, limit: int = 2000) -> str:
    """What the Founder actually reads before deciding. Never truncate to the
    point of hiding what is being published."""
    if content is None:
        return instruction[:limit]
    if isinstance(content, str):
        return content[:limit]
    return canonical_json(content)[:limit]
