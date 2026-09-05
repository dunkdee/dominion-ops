\
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
