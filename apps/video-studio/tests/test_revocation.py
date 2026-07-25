from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.state import ASSET_DIR, EXPORT_DIR, db, utc_now

TOKEN = "test-worker-token"
WORKER_ID = "revocation-worker"


def worker_headers(lease: str | None = None) -> dict[str, str]:
    headers = {"X-Worker-Token": TOKEN, "X-Worker-ID": WORKER_ID}
    if lease:
        headers["X-Worker-Lease"] = lease
    return headers


def create_project_with_assets(client: TestClient) -> tuple[str, str, str]:
    consent = client.post(
        "/api/consents",
        json={
            "subject_name": "Revocation Subject",
            "likeness_confirmed": True,
            "voice_confirmed": True,
            "rights_confirmed": True,
        },
    )
    assert consent.status_code == 201
    project = client.post(
        "/api/projects",
        json={
            "title": "Revocation Test",
            "script": "This project will be revoked.",
            "output_format": "vertical",
            "consent_id": consent.json()["id"],
        },
    )
    assert project.status_code == 201
    project_id = project.json()["id"]
    portrait = client.post(
        f"/api/projects/{project_id}/assets",
        data={"kind": "portrait"},
        files={"file": ("portrait.png", b"portrait-media", "image/png")},
    )
    voice = client.post(
        f"/api/projects/{project_id}/assets",
        data={"kind": "voice"},
        files={"file": ("voice.wav", b"voice-media", "audio/wav")},
    )
    assert portrait.status_code == 201
    assert voice.status_code == 201
    return project_id, portrait.json()["id"], voice.json()["id"]


def test_revocation_deletes_media_cancels_jobs_and_expires_lease() -> None:
    with TestClient(app) as client:
        project_id, portrait_id, _ = create_project_with_assets(client)
        queued = client.post(
            f"/api/projects/{project_id}/jobs",
            json={"engine": "external_clone"},
        )
        assert queued.status_code == 202
        claimed = client.post(
            "/api/workers/claim",
            json={"worker_id": WORKER_ID},
            headers=worker_headers(),
        )
        assert claimed.status_code == 200
        lease = claimed.json()["lease_token"]
        asset_url = next(
            asset["download_url"]
            for asset in claimed.json()["assets"]
            if asset["id"] == portrait_id
        )
        assert client.get(asset_url, headers=worker_headers(lease)).status_code == 200

        output_path = EXPORT_DIR / "completed-before-revocation.mp4"
        output_path.write_bytes(b"private-generated-output")
        completed_job_id = "job_completed_for_revocation"
        now = utc_now()
        with db() as connection:
            connection.execute(
                """
                INSERT INTO jobs (
                    id, project_id, engine, status, progress, error, output_path,
                    claimed_by, claim_token_hash, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    completed_job_id,
                    project_id,
                    "proof_render",
                    "completed",
                    100,
                    None,
                    str(output_path),
                    None,
                    None,
                    now,
                    now,
                ),
            )

        mismatch = client.post(
            f"/api/projects/{project_id}/revoke",
            json={"confirm_project_id": "wrong-project", "reason": "Subject revoked consent."},
        )
        assert mismatch.status_code == 422

        revoked = client.post(
            f"/api/projects/{project_id}/revoke",
            json={"confirm_project_id": project_id, "reason": "Subject revoked consent."},
        )
        assert revoked.status_code == 200
        result = revoked.json()
        assert result["status"] == "revoked"
        assert result["deleted_asset_count"] == 2
        assert result["deleted_output_count"] == 1
        assert result["already_revoked"] is False

        assert not (ASSET_DIR / project_id).exists()
        assert not output_path.exists()
        assert client.get(asset_url, headers=worker_headers(lease)).status_code == 403

        project = client.get(f"/api/projects/{project_id}")
        assert project.status_code == 200
        body = project.json()
        assert body["status"] == "revoked"
        assert body["assets"] == []
        assert body["revocation"]["reason"] == "Subject revoked consent."
        assert all(job["status"] == "canceled" for job in body["jobs"])

        requeue = client.post(
            f"/api/projects/{project_id}/jobs",
            json={"engine": "proof_render"},
        )
        assert requeue.status_code == 409
        reupload = client.post(
            f"/api/projects/{project_id}/assets",
            data={"kind": "portrait"},
            files={"file": ("replacement.png", b"replacement", "image/png")},
        )
        assert reupload.status_code == 409
        approval = client.post(
            f"/api/projects/{project_id}/approval",
            json={"decision": "approved", "note": "must remain blocked"},
        )
        assert approval.status_code == 409

        repeated = client.post(
            f"/api/projects/{project_id}/revoke",
            json={"confirm_project_id": project_id, "reason": "Repeated request."},
        )
        assert repeated.status_code == 200
        assert repeated.json()["already_revoked"] is True
        assert repeated.json()["id"] == result["id"]

        with db() as connection:
            stored_jobs = connection.execute(
                "SELECT status, output_path, claim_token_hash FROM jobs WHERE project_id = ?",
                (project_id,),
            ).fetchall()
            audit_count = connection.execute(
                "SELECT COUNT(*) AS total FROM project_revocations WHERE project_id = ?",
                (project_id,),
            ).fetchone()["total"]
        assert audit_count == 1
        assert all(row["status"] == "canceled" for row in stored_jobs)
        assert all(row["output_path"] is None for row in stored_jobs)
        assert all(row["claim_token_hash"] is None for row in stored_jobs)
