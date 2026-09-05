from pathlib import Path
import textwrap

path = Path('buddy_core/watchmen/saraqael.py')
src = path.read_text(encoding='utf-8')


def replace_once(old: str, new: str) -> None:
    global src
    count = src.count(old)
    if count != 1:
        raise SystemExit(f'expected one match, found {count}: {old[:120]!r}')
    src = src.replace(old, new, 1)


replace_once(
    'import tempfile\nfrom datetime import datetime, timezone\n',
    '''import tempfile
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
''',
)

replace_once(
    '''def state_dir() -> Path:
    """The machine-local audit state directory (not created by this call)."""
    override = os.environ.get(ENV_STATE_DIR, "").strip()
    return Path(override).expanduser() if override else DEFAULT_STATE_DIR
''',
    '''def state_dir() -> Path:
    """Resolve machine-local audit state and reject any path inside this checkout."""
    override = os.environ.get(ENV_STATE_DIR, "").strip()
    candidate = (Path(override).expanduser() if override else DEFAULT_STATE_DIR).resolve(strict=False)
    repo_root = _BASE_DIR.parent.resolve(strict=False)
    if candidate == repo_root or repo_root in candidate.parents:
        raise WatchmenStateError(
            f"audit state directory must be outside the repository checkout: {candidate}"
        )
    return candidate
''',
)

marker = 'def legacy_repo_artifacts() -> list:\n'
insert = '''@contextmanager
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


'''
replace_once(marker, insert + marker)

replace_once(
    '''    if path.exists():
        _assert_private_file(path, label="audit signing key file")
        try:
            raw = path.read_bytes()
        except OSError as exc:
            raise WatchmenStateError(
                f"audit signing key file is unreadable: {exc}") from exc
        return _validate_key(raw, str(path))
    return _generate_key(path)
''',
    '''    if path.exists():
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
''',
)

old_txn = '''    key = _resolve_key()
    _ensure_state_dir()

    if audit_file().exists() or chain_file().exists():
        existing = verify_chain()
        if existing.get("valid") is not True:
            raise WatchmenStateError(
                f"existing audit history is untrusted: {existing.get('message', 'unknown failure')}")

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

    _append_entry(audit_file(), json.dumps(entry, ensure_ascii=True) + "\\n")

    chain["last_hash"] = entry_hash
    chain["count"] = entry["seq"]
    _save_chain(chain)
'''
new_txn = '''    with _exclusive_audit_lock():
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

        _append_entry(audit_file(), json.dumps(entry, ensure_ascii=True) + "\\n")

        chain["last_hash"] = entry_hash
        chain["count"] = entry["seq"]
        _save_chain(chain)
'''
replace_once(old_txn, new_txn)

replace_once(
    '''def tail(n: int = 20) -> list:
    """Return the last N entries, raising if the underlying history is corrupt."""
    return _read_entries()[-n:]
''',
    '''def tail(n: int = 20) -> list:
    """Return the last N entries only after the entire chain verifies."""
    status = verify_chain()
    if status.get("valid") is not True:
        raise WatchmenStateError(
            f"audit history is untrusted: {status.get('message', 'unknown verification failure')}"
        )
    return _read_entries()[-n:]
''',
)

path.write_text(src, encoding='utf-8')

test_path = Path('tests/test_watchmen_review_closure.py')
test_path.write_text(textwrap.dedent(r'''\
"""Final regressions for independent Saraqael review findings on PR #235."""
from __future__ import annotations

import json
import multiprocessing
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "buddy_core"))

from watchmen import saraqael  # noqa: E402


def _log_worker(state_dir: str, event: str, start, out) -> None:
    os.environ[saraqael.ENV_STATE_DIR] = state_dir
    try:
        start.wait()
        row = saraqael.log("review-test", event, "ok")
        out.put((True, row.get("seq")))
    except Exception as exc:
        out.put((False, f"{type(exc).__name__}:{exc}"))


class SaraqaelReviewClosureTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old = os.environ.get(saraqael.ENV_STATE_DIR)
        os.environ[saraqael.ENV_STATE_DIR] = self.tmp.name

    def tearDown(self):
        if self.old is None:
            os.environ.pop(saraqael.ENV_STATE_DIR, None)
        else:
            os.environ[saraqael.ENV_STATE_DIR] = self.old
        self.tmp.cleanup()

    def test_state_dir_rejects_checkout_path(self):
        repo_root = Path(saraqael.__file__).resolve().parents[2]
        os.environ[saraqael.ENV_STATE_DIR] = str(repo_root / ".watchmen-should-never-live-here")
        with self.assertRaises(saraqael.WatchmenStateError):
            saraqael.state_dir()

    def test_missing_key_with_existing_history_requires_recovery(self):
        state = saraqael.state_dir()
        state.mkdir(parents=True, exist_ok=True)
        if os.name == "posix":
            state.chmod(0o700)
        audit = state / "watchmen_audit.log"
        audit.write_text("{}\n", encoding="utf-8")
        if os.name == "posix":
            audit.chmod(0o600)
        with self.assertRaisesRegex(saraqael.WatchmenStateError, "explicit recovery"):
            saraqael._resolve_key()
        self.assertFalse((state / "watchmen_hmac.key").exists())

    def test_tail_rejects_valid_json_tampering(self):
        saraqael.log("review-test", "before", "ok")
        path = saraqael.audit_file()
        row = json.loads(path.read_text(encoding="utf-8").strip())
        row["status"] = "forged"
        path.write_text(json.dumps(row) + "\n", encoding="utf-8")
        if os.name == "posix":
            path.chmod(0o600)
        with self.assertRaises(saraqael.WatchmenStateError):
            saraqael.tail(1)

    @unittest.skipUnless(os.name == "posix", "fork-based concurrency regression")
    def test_concurrent_log_writers_keep_one_valid_linear_chain(self):
        ctx = multiprocessing.get_context("fork")
        start = ctx.Event()
        out = ctx.Queue()
        workers = [ctx.Process(target=_log_worker, args=(self.tmp.name, f"event-{i}", start, out)) for i in range(8)]
        for worker in workers:
            worker.start()
        start.set()
        for worker in workers:
            worker.join(15)
            self.assertEqual(worker.exitcode, 0)
        results = [out.get(timeout=3) for _ in workers]
        self.assertTrue(all(ok for ok, _ in results), results)
        status = saraqael.verify_chain()
        self.assertTrue(status["valid"], status)
        self.assertEqual(status["entries_checked"], len(workers))
        seqs = sorted(value for ok, value in results if ok)
        self.assertEqual(seqs, list(range(1, len(workers) + 1)))

    def test_lock_file_is_private_on_posix(self):
        saraqael.log("review-test", "mode", "ok")
        lock = saraqael.state_dir() / "watchmen_audit.lock"
        self.assertTrue(lock.exists())
        if os.name == "posix":
            self.assertEqual(stat.S_IMODE(lock.stat().st_mode), 0o600)


if __name__ == "__main__":
    unittest.main()
'''), encoding='utf-8')

for helper in (
    '.github/workflows/pr235-saraqael-final-fix.yml',
    '.github/scripts/pr235_saraqael_patch.py',
):
    p = Path(helper)
    if p.exists():
        p.unlink()

print('PR235_SARAQAEL_FINAL_REVIEW_CLOSURE=APPLIED')
