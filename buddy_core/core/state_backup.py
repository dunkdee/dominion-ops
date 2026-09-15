"""Fail-closed backup, integrity verification, and isolated restore for Buddy state."""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import zipfile
from datetime import datetime, timezone
from pathlib import Path

try:
    from .learning_engine import default_state_dir, state_lock
except ImportError:  # pragma: no cover - VM runtime can import core directly.
    from core.learning_engine import default_state_dir, state_lock

FORMAT = "dominion-buddy-state-backup-v1"
STATE_FILES = ("lessons.jsonl", "missions.jsonl", "audit.jsonl")
MANIFEST_NAME = "manifest.json"


class StateIntegrityError(RuntimeError):
    """Buddy state failed a parse, hash, archive, or restore integrity check."""


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _verify_records(data: bytes, name: str) -> int:
    if not data:
        return 0
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise StateIntegrityError(f"{name}: invalid UTF-8") from exc
    count = 0
    for line_no, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            raise StateIntegrityError(f"{name}:{line_no}: blank JSONL record")
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise StateIntegrityError(f"{name}:{line_no}: invalid JSON") from exc
        if not isinstance(record, dict):
            raise StateIntegrityError(f"{name}:{line_no}: record must be an object")
        supplied = record.get("record_hash")
        if not isinstance(supplied, str) or len(supplied) != 64:
            raise StateIntegrityError(f"{name}:{line_no}: missing or invalid record_hash")
        payload = dict(record)
        payload.pop("record_hash", None)
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        expected = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        if not hmac.compare_digest(supplied, expected):
            raise StateIntegrityError(f"{name}:{line_no}: record_hash mismatch")
        count += 1
    return count


def verify_state_dir(state_dir: Path | str) -> dict:
    source = Path(state_dir)
    files = {}
    total_records = 0
    with state_lock(source):
        for name in STATE_FILES:
            path = source / name
            if not path.exists():
                files[name] = {"present": False, "size": 0, "sha256": None, "records": 0}
                continue
            if not path.is_file():
                raise StateIntegrityError(f"{name}: expected regular file")
            data = path.read_bytes()
            records = _verify_records(data, name)
            files[name] = {
                "present": True,
                "size": len(data),
                "sha256": _sha256(data),
                "records": records,
            }
            total_records += records
    return {"files": files, "total_records": total_records}


def create_backup(destination: Path | str, *, source_dir: Path | str | None = None) -> dict:
    source = Path(source_dir) if source_dir is not None else default_state_dir()
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    payloads: dict[str, bytes] = {}
    file_meta = {}
    total_records = 0

    with state_lock(source):
        for name in STATE_FILES:
            path = source / name
            if not path.exists():
                file_meta[name] = {"present": False, "size": 0, "sha256": None, "records": 0}
                continue
            if not path.is_file():
                raise StateIntegrityError(f"{name}: expected regular file")
            data = path.read_bytes()
            records = _verify_records(data, name)
            payloads[name] = data
            file_meta[name] = {
                "present": True,
                "size": len(data),
                "sha256": _sha256(data),
                "records": records,
            }
            total_records += records

    manifest = {
        "format": FORMAT,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "scope": "buddy-state-only",
        "files": file_meta,
        "total_records": total_records,
    }
    tmp = destination.with_name(destination.name + ".tmp")
    try:
        with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(MANIFEST_NAME, json.dumps(manifest, indent=2, sort_keys=True) + "\n")
            for name, data in payloads.items():
                archive.writestr(name, data)
        with tmp.open("rb") as handle:
            os.fsync(handle.fileno())
        os.replace(tmp, destination)
        try:
            destination.chmod(0o600)
        except OSError:
            pass
    finally:
        if tmp.exists():
            tmp.unlink()

    verified = verify_backup(destination)
    return {
        "archive": str(destination),
        "archive_sha256": _sha256(destination.read_bytes()),
        "total_records": verified["total_records"],
        "files": verified["files"],
    }


def _read_verified_archive(archive_path: Path | str) -> tuple[dict, dict[str, bytes]]:
    archive_path = Path(archive_path)
    try:
        with zipfile.ZipFile(archive_path, "r") as archive:
            names = archive.namelist()
            if len(names) != len(set(names)):
                raise StateIntegrityError("archive contains duplicate member names")
            allowed = {MANIFEST_NAME, *STATE_FILES}
            unexpected = sorted(set(names) - allowed)
            if unexpected:
                raise StateIntegrityError(f"archive contains unexpected members: {unexpected}")
            if MANIFEST_NAME not in names:
                raise StateIntegrityError("archive manifest missing")
            try:
                manifest = json.loads(archive.read(MANIFEST_NAME).decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise StateIntegrityError("archive manifest invalid") from exc
            if manifest.get("format") != FORMAT or manifest.get("scope") != "buddy-state-only":
                raise StateIntegrityError("archive manifest format/scope mismatch")
            meta = manifest.get("files")
            if not isinstance(meta, dict) or set(meta) != set(STATE_FILES):
                raise StateIntegrityError("archive manifest file set mismatch")

            payloads = {}
            total_records = 0
            for name in STATE_FILES:
                entry = meta[name]
                if not isinstance(entry, dict):
                    raise StateIntegrityError(f"{name}: invalid manifest entry")
                present = entry.get("present") is True
                if not present:
                    if name in names:
                        raise StateIntegrityError(f"{name}: archive/member presence mismatch")
                    if entry.get("records") != 0 or entry.get("size") != 0 or entry.get("sha256") is not None:
                        raise StateIntegrityError(f"{name}: invalid absent-file metadata")
                    continue
                if name not in names:
                    raise StateIntegrityError(f"{name}: archive member missing")
                data = archive.read(name)
                if len(data) != entry.get("size"):
                    raise StateIntegrityError(f"{name}: size mismatch")
                if not hmac.compare_digest(_sha256(data), str(entry.get("sha256", ""))):
                    raise StateIntegrityError(f"{name}: file hash mismatch")
                records = _verify_records(data, name)
                if records != entry.get("records"):
                    raise StateIntegrityError(f"{name}: record count mismatch")
                payloads[name] = data
                total_records += records
            if total_records != manifest.get("total_records"):
                raise StateIntegrityError("manifest total record count mismatch")
            return manifest, payloads
    except zipfile.BadZipFile as exc:
        raise StateIntegrityError("invalid backup archive") from exc


def verify_backup(archive_path: Path | str) -> dict:
    manifest, _ = _read_verified_archive(archive_path)
    return {
        "format": manifest["format"],
        "total_records": manifest["total_records"],
        "files": manifest["files"],
    }


def restore_backup_isolated(archive_path: Path | str, target_dir: Path | str) -> dict:
    target = Path(target_dir)
    if target.resolve() == default_state_dir().resolve():
        raise StateIntegrityError("refusing to restore over live Buddy state")
    manifest, payloads = _read_verified_archive(archive_path)
    if target.exists() and any(target.iterdir()):
        raise StateIntegrityError("isolated restore target must be empty")
    target.mkdir(parents=True, exist_ok=True)

    for name, data in payloads.items():
        path = target / name
        with path.open("xb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
    restored = verify_state_dir(target)
    if restored["total_records"] != manifest["total_records"]:
        raise StateIntegrityError("restored record count mismatch")
    for name in STATE_FILES:
        if manifest["files"][name] != restored["files"][name]:
            raise StateIntegrityError(f"{name}: restored metadata mismatch")
    return {
        "target": str(target),
        "total_records": restored["total_records"],
        "files": restored["files"],
    }
