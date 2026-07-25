from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import subprocess
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, File, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse

from .models import WorkerClaim, WorkerComplete
from .state import (
    ASSET_DIR,
    EXPORT_DIR,
    MAX_UPLOAD_BYTES,
    db,
    get_project,
    require_worker_token,
    utc_now,
)

router = APIRouter(prefix="/api/workers")


def _worker_identity(token: str | None, worker_id: str | None) -> str:
    require_worker_token(token)
    identity = (worker_id or "").strip()
    if not identity or len(identity) > 120:
        raise HTTPException(status_code=422, detail="A valid worker identity is required")
    return identity


def _lease_hash(lease: str) -> str:
    return hashlib.sha256(lease.encode("utf-8")).hexdigest()


def _require_claimed_job(job: object, worker_id: str, lease: str | None) -> None:
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if job["engine"] != "external_clone":
        raise HTTPException(status_code=409, detail="Job is not assigned to an external worker")
    if job["status"] != "claimed" or job["claimed_by"] != worker_id:
        raise HTTPException(status_code=403, detail="Worker does not hold this job")
    stored_hash = job["claim_token_hash"] or ""
    supplied_hash = _lease_hash(lease or "")
    if not stored_hash or not hmac.compare_digest(stored_hash, supplied_hash):
        raise HTTPException(status_code=401, detail="Invalid or expired worker lease")


def _validate_mp4(path: Path) -> None:
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=codec_name,width,height",
                "-of",
                "json",
                str(path),
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        payload = json.loads(result.stdout or "{}")
        streams = payload.get("streams", [])
        stream = streams[0] if streams else {}
        if result.returncode != 0 or stream.get("codec_name") != "h264":
            raise ValueError("missing H.264 video stream")
        if int(stream.get("width", 0)) < 1 or int(stream.get("height", 0)) < 1:
            raise ValueError("invalid video dimensions")
    except (OSError, ValueError, json.JSONDecodeError, subprocess.TimeoutExpired) as exc:
        raise HTTPException(status_code=422, detail=f"Worker output failed MP4 validation: {exc}") from exc


@router.post("/claim")
def claim_external_job(
    payload: WorkerClaim,
    x_worker_token: Annotated[str | None, Header()] = None,
    x_worker_id: Annotated[str | None, Header()] = None,
) -> dict:
    worker_id = _worker_identity(x_worker_token, x_worker_id)
    if payload.worker_id != worker_id:
        raise HTTPException(status_code=409, detail="Worker identity header and claim body must match")
    lease = secrets.token_urlsafe(32)
    with db() as connection:
        connection.execute("BEGIN IMMEDIATE")
        job = connection.execute(
            "SELECT * FROM jobs WHERE status = 'queued' AND engine = 'external_clone' ORDER BY created_at LIMIT 1"
        ).fetchone()
        if job is None:
            return {"job": None}
        connection.execute(
            """
            UPDATE jobs
            SET status = 'claimed', claimed_by = ?, claim_token_hash = ?, progress = 1, updated_at = ?
            WHERE id = ?
            """,
            (worker_id, _lease_hash(lease), utc_now(), job["id"]),
        )
        claimed_job = connection.execute("SELECT * FROM jobs WHERE id = ?", (job["id"],)).fetchone()
        project = get_project(connection, job["project_id"])
        assets = connection.execute("SELECT * FROM assets WHERE project_id = ?", (job["project_id"],)).fetchall()
    safe_job = dict(claimed_job)
    safe_job.pop("claim_token_hash", None)
    safe_assets = [
        {
            "id": row["id"],
            "kind": row["kind"],
            "original_name": row["original_name"],
            "media_type": row["media_type"],
            "size_bytes": row["size_bytes"],
            "download_url": f"/api/workers/jobs/{job['id']}/assets/{row['id']}",
        }
        for row in assets
    ]
    return {"job": safe_job, "project": dict(project), "assets": safe_assets, "lease_token": lease}


@router.get("/jobs/{job_id}/assets/{asset_id}")
def download_worker_asset(
    job_id: str,
    asset_id: str,
    x_worker_token: Annotated[str | None, Header()] = None,
    x_worker_id: Annotated[str | None, Header()] = None,
    x_worker_lease: Annotated[str | None, Header()] = None,
) -> FileResponse:
    worker_id = _worker_identity(x_worker_token, x_worker_id)
    with db() as connection:
        job = connection.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        _require_claimed_job(job, worker_id, x_worker_lease)
        asset = connection.execute(
            "SELECT * FROM assets WHERE id = ? AND project_id = ?",
            (asset_id, job["project_id"]),
        ).fetchone()
    if asset is None:
        raise HTTPException(status_code=404, detail="Asset not found for claimed job")
    path = Path(asset["stored_path"]).resolve()
    if not path.exists() or ASSET_DIR not in path.parents:
        raise HTTPException(status_code=404, detail="Asset file is missing")
    return FileResponse(path, media_type=asset["media_type"], filename=asset["original_name"])


@router.post("/jobs/{job_id}/output", status_code=201)
def upload_worker_output(
    job_id: str,
    file: UploadFile = File(...),
    x_worker_token: Annotated[str | None, Header()] = None,
    x_worker_id: Annotated[str | None, Header()] = None,
    x_worker_lease: Annotated[str | None, Header()] = None,
) -> dict:
    worker_id = _worker_identity(x_worker_token, x_worker_id)
    if Path(file.filename or "").suffix.lower() != ".mp4":
        raise HTTPException(status_code=422, detail="Worker output must be an MP4")
    with db() as connection:
        job = connection.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        _require_claimed_job(job, worker_id, x_worker_lease)

    output_path = EXPORT_DIR / f"{job_id}.mp4"
    total = 0
    try:
        with output_path.open("wb") as destination:
            while chunk := file.file.read(1024 * 1024):
                total += len(chunk)
                if total > MAX_UPLOAD_BYTES * 5:
                    raise HTTPException(status_code=413, detail="Worker output exceeds configured limit")
                destination.write(chunk)
        if total == 0:
            raise HTTPException(status_code=422, detail="Worker output is empty")
        _validate_mp4(output_path)
    except Exception:
        output_path.unlink(missing_ok=True)
        raise
    finally:
        file.file.close()

    with db() as connection:
        connection.execute(
            """
            UPDATE jobs
            SET status = 'completed', progress = 100, output_path = ?, error = NULL,
                claim_token_hash = NULL, updated_at = ?
            WHERE id = ?
            """,
            (str(output_path), utc_now(), job_id),
        )
        connection.execute(
            "UPDATE projects SET status = ?, updated_at = ? WHERE id = ?",
            ("review_ready", utc_now(), job["project_id"]),
        )
    return {"id": job_id, "status": "completed", "size_bytes": total}


@router.post("/jobs/{job_id}/complete")
def complete_external_job(
    job_id: str,
    payload: WorkerComplete,
    x_worker_token: Annotated[str | None, Header()] = None,
    x_worker_id: Annotated[str | None, Header()] = None,
    x_worker_lease: Annotated[str | None, Header()] = None,
) -> dict:
    worker_id = _worker_identity(x_worker_token, x_worker_id)
    with db() as connection:
        job = connection.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        _require_claimed_job(job, worker_id, x_worker_lease)
        output_path = payload.output_path
        if payload.status == "completed":
            if not output_path:
                raise HTTPException(status_code=422, detail="Completed jobs require an output path")
            resolved = Path(output_path).resolve()
            expected = (EXPORT_DIR / f"{job_id}.mp4").resolve()
            if resolved != expected or not resolved.exists():
                raise HTTPException(status_code=422, detail="Output path must be this job's existing export file")
            _validate_mp4(resolved)
        connection.execute(
            """
            UPDATE jobs
            SET status = ?, progress = 100, error = ?, output_path = ?,
                claim_token_hash = NULL, updated_at = ?
            WHERE id = ?
            """,
            (payload.status, payload.error, output_path, utc_now(), job_id),
        )
        connection.execute(
            "UPDATE projects SET status = ?, updated_at = ? WHERE id = ?",
            ("review_ready" if payload.status == "completed" else "failed", utc_now(), job["project_id"]),
        )
    return {"id": job_id, "status": payload.status}
