from __future__ import annotations

import os
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from fastapi import HTTPException

APP_NAME = "Dominion Video Studio"
DATA_DIR = Path(os.getenv("VIDEO_STUDIO_DATA_DIR", "/data")).resolve()
DB_PATH = DATA_DIR / "video_studio.db"
ASSET_DIR = DATA_DIR / "assets"
EXPORT_DIR = DATA_DIR / "exports"
WORKER_TOKEN = os.getenv("VIDEO_STUDIO_WORKER_TOKEN", "")
MAX_UPLOAD_BYTES = int(os.getenv("VIDEO_STUDIO_MAX_UPLOAD_BYTES", str(100 * 1024 * 1024)))

ALLOWED_ASSET_KINDS = {"portrait", "voice", "source_video"}
ALLOWED_EXTENSIONS = {
    "portrait": {".jpg", ".jpeg", ".png", ".webp"},
    "voice": {".wav", ".mp3", ".m4a", ".aac", ".ogg"},
    "source_video": {".mp4", ".mov", ".mkv", ".webm"},
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


@contextmanager
def db() -> Iterator[sqlite3.Connection]:
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        yield connection
        connection.commit()
    finally:
        connection.close()


def init_storage() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    ASSET_DIR.mkdir(parents=True, exist_ok=True)
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    with db() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS consents (
                id TEXT PRIMARY KEY,
                subject_name TEXT NOT NULL,
                likeness_confirmed INTEGER NOT NULL,
                voice_confirmed INTEGER NOT NULL,
                rights_confirmed INTEGER NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS projects (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                script TEXT NOT NULL,
                output_format TEXT NOT NULL,
                consent_id TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(consent_id) REFERENCES consents(id)
            );
            CREATE TABLE IF NOT EXISTS assets (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                kind TEXT NOT NULL,
                original_name TEXT NOT NULL,
                stored_path TEXT NOT NULL,
                media_type TEXT,
                size_bytes INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                engine TEXT NOT NULL,
                status TEXT NOT NULL,
                progress INTEGER NOT NULL DEFAULT 0,
                error TEXT,
                output_path TEXT,
                claimed_by TEXT,
                claim_token_hash TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS approvals (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                job_id TEXT NOT NULL,
                decision TEXT NOT NULL,
                note TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE,
                FOREIGN KEY(job_id) REFERENCES jobs(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_assets_project_kind ON assets(project_id, kind);
            CREATE INDEX IF NOT EXISTS idx_jobs_status_created ON jobs(status, created_at);
            """
        )
        job_columns = {row["name"] for row in connection.execute("PRAGMA table_info(jobs)").fetchall()}
        if "claim_token_hash" not in job_columns:
            connection.execute("ALTER TABLE jobs ADD COLUMN claim_token_hash TEXT")


def get_project(connection: sqlite3.Connection, project_id: str) -> sqlite3.Row:
    row = connection.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return row


def validate_consent(connection: sqlite3.Connection, consent_id: str) -> sqlite3.Row:
    row = connection.execute("SELECT * FROM consents WHERE id = ?", (consent_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Consent record not found")
    if not (row["likeness_confirmed"] and row["voice_confirmed"] and row["rights_confirmed"]):
        raise HTTPException(status_code=409, detail="All consent confirmations are required")
    return row


def latest_asset(connection: sqlite3.Connection, project_id: str, kind: str) -> sqlite3.Row | None:
    return connection.execute(
        "SELECT * FROM assets WHERE project_id = ? AND kind = ? ORDER BY created_at DESC LIMIT 1",
        (project_id, kind),
    ).fetchone()


def update_job(job_id: str, *, status: str, progress: int, error: str | None = None, output_path: str | None = None) -> None:
    with db() as connection:
        connection.execute(
            "UPDATE jobs SET status = ?, progress = ?, error = ?, output_path = ?, updated_at = ? WHERE id = ?",
            (status, progress, error, output_path, utc_now(), job_id),
        )


def require_worker_token(token: str | None) -> None:
    if not WORKER_TOKEN:
        raise HTTPException(status_code=503, detail="External worker mode is not configured")
    if token != WORKER_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid worker token")
