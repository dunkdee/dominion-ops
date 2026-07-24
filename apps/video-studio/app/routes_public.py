from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from .models import ApprovalCreate, ConsentCreate, JobCreate, ProjectCreate
from .state import (
    ALLOWED_ASSET_KINDS,
    ALLOWED_EXTENSIONS,
    ASSET_DIR,
    EXPORT_DIR,
    MAX_UPLOAD_BYTES,
    db,
    get_project,
    latest_asset,
    new_id,
    utc_now,
    validate_consent,
)

router = APIRouter(prefix="/api")


@router.post("/consents", status_code=201)
def create_consent(payload: ConsentCreate) -> dict:
    if not (payload.likeness_confirmed and payload.voice_confirmed and payload.rights_confirmed):
        raise HTTPException(status_code=422, detail="All consent confirmations must be true")
    consent_id = new_id("consent")
    with db() as connection:
        connection.execute(
            "INSERT INTO consents VALUES (?, ?, ?, ?, ?, ?)",
            (
                consent_id,
                payload.subject_name.strip(),
                int(payload.likeness_confirmed),
                int(payload.voice_confirmed),
                int(payload.rights_confirmed),
                utc_now(),
            ),
        )
    return {"id": consent_id, "status": "confirmed"}


@router.post("/projects", status_code=201)
def create_project(payload: ProjectCreate) -> dict:
    project_id = new_id("project")
    now = utc_now()
    with db() as connection:
        validate_consent(connection, payload.consent_id)
        connection.execute(
            "INSERT INTO projects VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                project_id,
                payload.title.strip(),
                payload.script.strip(),
                payload.output_format,
                payload.consent_id,
                "draft",
                now,
                now,
            ),
        )
    return {"id": project_id, "status": "draft"}


@router.get("/projects")
def list_projects() -> list[dict]:
    with db() as connection:
        rows = connection.execute("SELECT * FROM projects ORDER BY created_at DESC").fetchall()
    return [dict(row) for row in rows]


@router.get("/projects/{project_id}")
def read_project(project_id: str) -> dict:
    with db() as connection:
        project = get_project(connection, project_id)
        assets = connection.execute(
            "SELECT id, kind, original_name, media_type, size_bytes, created_at FROM assets WHERE project_id = ? ORDER BY created_at",
            (project_id,),
        ).fetchall()
        jobs = connection.execute(
            "SELECT id, engine, status, progress, error, created_at, updated_at FROM jobs WHERE project_id = ? ORDER BY created_at DESC",
            (project_id,),
        ).fetchall()
    result = dict(project)
    result["assets"] = [dict(row) for row in assets]
    result["jobs"] = [dict(row) for row in jobs]
    return result


@router.post("/projects/{project_id}/assets", status_code=201)
def upload_asset(project_id: str, kind: str = Form(...), file: UploadFile = File(...)) -> dict:
    if kind not in ALLOWED_ASSET_KINDS:
        raise HTTPException(status_code=422, detail="Unsupported asset kind")
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS[kind]:
        raise HTTPException(status_code=422, detail=f"Unsupported file type for {kind}")
    with db() as connection:
        get_project(connection, project_id)

    asset_id = new_id("asset")
    project_dir = ASSET_DIR / project_id
    project_dir.mkdir(parents=True, exist_ok=True)
    stored_path = project_dir / f"{asset_id}{suffix}"
    total = 0
    try:
        with stored_path.open("wb") as destination:
            while chunk := file.file.read(1024 * 1024):
                total += len(chunk)
                if total > MAX_UPLOAD_BYTES:
                    raise HTTPException(status_code=413, detail="Upload exceeds configured limit")
                destination.write(chunk)
    except Exception:
        stored_path.unlink(missing_ok=True)
        raise
    finally:
        file.file.close()

    with db() as connection:
        connection.execute(
            "INSERT INTO assets VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                asset_id,
                project_id,
                kind,
                Path(file.filename or stored_path.name).name,
                str(stored_path),
                file.content_type,
                total,
                utc_now(),
            ),
        )
        connection.execute("UPDATE projects SET status = ?, updated_at = ? WHERE id = ?", ("assets_ready", utc_now(), project_id))
    return {"id": asset_id, "kind": kind, "size_bytes": total}


@router.post("/projects/{project_id}/jobs", status_code=202)
def queue_job(project_id: str, payload: JobCreate) -> dict:
    job_id = new_id("job")
    now = utc_now()
    with db() as connection:
        project = get_project(connection, project_id)
        validate_consent(connection, project["consent_id"])
        if latest_asset(connection, project_id, "portrait") is None:
            raise HTTPException(status_code=409, detail="Upload a portrait before generating")
        if latest_asset(connection, project_id, "voice") is None:
            raise HTTPException(status_code=409, detail="Upload a voice recording before generating")
        connection.execute(
            "INSERT INTO jobs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (job_id, project_id, payload.engine, "queued", 0, None, None, None, now, now),
        )
        connection.execute("UPDATE projects SET status = ?, updated_at = ? WHERE id = ?", ("queued", now, project_id))
    return {"id": job_id, "status": "queued", "engine": payload.engine}


@router.get("/jobs/{job_id}")
def read_job(job_id: str) -> dict:
    with db() as connection:
        job = connection.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    result = dict(job)
    result["download_url"] = f"/api/jobs/{job_id}/download" if job["status"] == "completed" else None
    return result


@router.get("/jobs/{job_id}/download")
def download_job(job_id: str) -> FileResponse:
    with db() as connection:
        job = connection.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if job["status"] != "completed" or not job["output_path"]:
        raise HTTPException(status_code=409, detail="Output is not ready")
    path = Path(job["output_path"]).resolve()
    if not path.exists() or EXPORT_DIR not in path.parents:
        raise HTTPException(status_code=404, detail="Output file is missing")
    return FileResponse(path, media_type="video/mp4", filename=f"{job_id}.mp4")


@router.post("/projects/{project_id}/approval", status_code=201)
def record_approval(project_id: str, payload: ApprovalCreate) -> dict:
    approval_id = new_id("approval")
    with db() as connection:
        get_project(connection, project_id)
        job = connection.execute(
            "SELECT * FROM jobs WHERE project_id = ? AND status = 'completed' ORDER BY created_at DESC LIMIT 1",
            (project_id,),
        ).fetchone()
        if job is None:
            raise HTTPException(status_code=409, detail="A completed output is required before review")
        connection.execute(
            "INSERT INTO approvals VALUES (?, ?, ?, ?, ?, ?)",
            (approval_id, project_id, job["id"], payload.decision, payload.note, utc_now()),
        )
        connection.execute("UPDATE projects SET status = ?, updated_at = ? WHERE id = ?", (payload.decision, utc_now(), project_id))
    return {"id": approval_id, "project_id": project_id, "job_id": job["id"], "decision": payload.decision}
