"""Minimal Linux file-lock shim used by Dominion Email Drip.

Implements the small subset of the third-party ``filelock`` API that the
service uses, without adding a production package dependency. Foundation VM is
Linux-only, so ``fcntl.flock`` is the canonical primitive here.
"""

from __future__ import annotations

import fcntl
import os
import time
from pathlib import Path


class Timeout(Exception):
    """Raised when a lock cannot be acquired within the configured timeout."""


class FileLock:
    def __init__(self, lock_file: str, timeout: float = 5) -> None:
        self.lock_file = Path(lock_file)
        self.timeout = float(timeout)
        self._fd: int | None = None

    def acquire(self) -> "FileLock":
        if self._fd is not None:
            return self

        fd = os.open(self.lock_file, os.O_RDWR | os.O_CREAT, 0o600)
        deadline = time.monotonic() + max(self.timeout, 0.0)
        try:
            while True:
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    self._fd = fd
                    return self
                except BlockingIOError as exc:
                    if time.monotonic() >= deadline:
                        raise Timeout(f"timed out acquiring {self.lock_file}") from exc
                    time.sleep(0.05)
        except Exception:
            os.close(fd)
            raise

    def release(self) -> None:
        fd = self._fd
        if fd is None:
            return
        self._fd = None
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)

    def __enter__(self) -> "FileLock":
        return self.acquire()

    def __exit__(self, exc_type, exc, tb) -> bool:
        self.release()
        return False
