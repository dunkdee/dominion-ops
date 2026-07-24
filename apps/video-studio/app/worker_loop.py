from __future__ import annotations

import threading

from .render import render_proof_job
from .state import db, utc_now

STOP = threading.Event()
THREAD: threading.Thread | None = None


def loop() -> None:
    while not STOP.is_set():
        job_id: str | None = None
        with db() as connection:
            connection.execute("BEGIN IMMEDIATE")
            job = connection.execute(
                "SELECT id FROM jobs WHERE status = 'queued' AND engine = 'proof_render' ORDER BY created_at LIMIT 1"
            ).fetchone()
            if job:
                job_id = job["id"]
                connection.execute("UPDATE jobs SET status = 'starting', updated_at = ? WHERE id = ?", (utc_now(), job_id))
        if job_id:
            render_proof_job(job_id)
        else:
            STOP.wait(1.0)


def start() -> None:
    global THREAD
    if THREAD is None or not THREAD.is_alive():
        STOP.clear()
        THREAD = threading.Thread(target=loop, name="proof-render-worker", daemon=True)
        THREAD.start()


def stop() -> None:
    STOP.set()
    if THREAD and THREAD.is_alive():
        THREAD.join(timeout=3)
