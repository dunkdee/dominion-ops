import hashlib
import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

from buddy_core.core.state_backup import (
    STATE_FILES,
    StateIntegrityError,
    create_backup,
    restore_backup_isolated,
    verify_backup,
    verify_state_dir,
)

ROOT = Path(__file__).resolve().parents[1]


def _child_env(state_dir: Path) -> dict:
    env = os.environ.copy()
    path_parts = [str(ROOT), str(ROOT / "buddy_core")]
    if env.get("PYTHONPATH"):
        path_parts.append(env["PYTHONPATH"])
    env["PYTHONPATH"] = os.pathsep.join(path_parts)
    env["BUDDY_STATE_DIR"] = str(state_dir)
    return env


def _write_missions_in_processes(state_dir: Path, workers: int = 6, each: int = 25) -> None:
    code = (
        "from buddy_core.core.learning_engine import record_mission\n"
        "import sys\n"
        "worker=sys.argv[1]\n"
        f"for i in range({each}):\n"
        "    record_mission({'worker': worker, 'index': i, 'token': 'must-redact'})\n"
    )
    processes = [
        subprocess.Popen(
            [sys.executable, "-c", code, str(worker)],
            cwd=ROOT,
            env=_child_env(state_dir),
        )
        for worker in range(workers)
    ]
    failures = [process.wait(timeout=30) for process in processes]
    assert failures == [0] * workers


def _expected_hash(record: dict) -> str:
    payload = dict(record)
    payload.pop("record_hash", None)
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def test_cross_process_writes_are_complete_hashed_and_redacted(tmp_path):
    state = tmp_path / "state"
    workers = 6
    each = 25
    _write_missions_in_processes(state, workers=workers, each=each)

    lines = (state / "missions.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == workers * each
    seen = set()
    for line in lines:
        row = json.loads(line)
        assert row["record_hash"] == _expected_hash(row)
        assert row["token"] == "[REDACTED]"
        seen.add((row["worker"], row["index"]))
    assert len(seen) == workers * each

    report = verify_state_dir(state)
    assert report["total_records"] == workers * each
    assert report["files"]["missions.jsonl"]["records"] == workers * each


def test_backup_is_state_only_and_round_trips_into_isolated_target(tmp_path):
    state = tmp_path / "state"
    _write_missions_in_processes(state, workers=3, each=10)
    (state / "credentials.env").write_text("SUPER_SECRET=do-not-copy\n", encoding="utf-8")
    archive = tmp_path / "buddy-state.zip"

    created = create_backup(archive, source_dir=state)
    verified = verify_backup(archive)
    assert created["total_records"] == 30
    assert verified["total_records"] == 30

    with zipfile.ZipFile(archive, "r") as handle:
        members = set(handle.namelist())
    assert "credentials.env" not in members
    assert members <= {"manifest.json", *STATE_FILES}

    target = tmp_path / "isolated-restore"
    restored = restore_backup_isolated(archive, target)
    assert restored["total_records"] == 30
    assert verify_state_dir(target) == {
        "files": verified["files"],
        "total_records": verified["total_records"],
    }


def test_backup_fails_closed_on_record_hash_mismatch(tmp_path):
    state = tmp_path / "state"
    state.mkdir()
    bad = {
        "type": "mission",
        "objective": "tampered",
        "record_hash": "0" * 64,
    }
    (state / "missions.jsonl").write_text(json.dumps(bad) + "\n", encoding="utf-8")

    with pytest.raises(StateIntegrityError, match="record_hash mismatch"):
        create_backup(tmp_path / "bad.zip", source_dir=state)


def test_backup_fails_closed_on_malformed_jsonl(tmp_path):
    state = tmp_path / "state"
    state.mkdir()
    (state / "audit.jsonl").write_text("not-json\n", encoding="utf-8")

    with pytest.raises(StateIntegrityError, match="invalid JSON"):
        create_backup(tmp_path / "bad-json.zip", source_dir=state)


def test_restore_rejects_nonempty_target(tmp_path):
    state = tmp_path / "state"
    _write_missions_in_processes(state, workers=1, each=2)
    archive = tmp_path / "buddy-state.zip"
    create_backup(archive, source_dir=state)

    target = tmp_path / "restore-target"
    target.mkdir()
    (target / "existing.txt").write_text("preserve me", encoding="utf-8")
    with pytest.raises(StateIntegrityError, match="must be empty"):
        restore_backup_isolated(archive, target)
    assert (target / "existing.txt").read_text(encoding="utf-8") == "preserve me"


def test_restore_refuses_live_default_state(tmp_path):
    source = tmp_path / "source"
    _write_missions_in_processes(source, workers=1, each=1)
    archive = tmp_path / "buddy-state.zip"
    create_backup(archive, source_dir=source)

    from buddy_core.core.state_backup import default_state_dir

    with pytest.raises(StateIntegrityError, match="refusing to restore over live Buddy state"):
        restore_backup_isolated(archive, default_state_dir())
