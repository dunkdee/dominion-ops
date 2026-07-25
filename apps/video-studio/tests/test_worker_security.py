from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app

TOKEN = "test-worker-token"


def create_external_job(client: TestClient, suffix: str) -> tuple[str, str, str]:
    consent = client.post(
        "/api/consents",
        json={
            "subject_name": f"Authorized Subject {suffix}",
            "likeness_confirmed": True,
            "voice_confirmed": True,
            "rights_confirmed": True,
        },
    )
    assert consent.status_code == 201
    project = client.post(
        "/api/projects",
        json={
            "title": f"Worker Security {suffix}",
            "script": "Controlled worker lease test.",
            "output_format": "vertical",
            "consent_id": consent.json()["id"],
        },
    )
    assert project.status_code == 201
    project_id = project.json()["id"]

    portrait = client.post(
        f"/api/projects/{project_id}/assets",
        data={"kind": "portrait"},
        files={"file": (f"portrait-{suffix}.png", b"portrait-bytes", "image/png")},
    )
    voice = client.post(
        f"/api/projects/{project_id}/assets",
        data={"kind": "voice"},
        files={"file": (f"voice-{suffix}.wav", b"voice-bytes", "audio/wav")},
    )
    assert portrait.status_code == 201
    assert voice.status_code == 201

    queued = client.post(
        f"/api/projects/{project_id}/jobs",
        json={"engine": "external_clone"},
    )
    assert queued.status_code == 202
    return project_id, queued.json()["id"], portrait.json()["id"]


def claim(client: TestClient, worker_id: str) -> dict:
    response = client.post(
        "/api/workers/claim",
        json={"worker_id": worker_id},
        headers={"X-Worker-Token": TOKEN, "X-Worker-ID": worker_id},
    )
    assert response.status_code == 200
    assert response.json()["job"] is not None
    return response.json()


def lease_headers(worker_id: str, lease: str) -> dict[str, str]:
    return {
        "X-Worker-Token": TOKEN,
        "X-Worker-ID": worker_id,
        "X-Worker-Lease": lease,
    }


def test_claim_requires_matching_authenticated_identity() -> None:
    with TestClient(app) as client:
        create_external_job(client, "identity")

        no_token = client.post(
            "/api/workers/claim",
            json={"worker_id": "worker-a"},
            headers={"X-Worker-ID": "worker-a"},
        )
        assert no_token.status_code == 401

        mismatch = client.post(
            "/api/workers/claim",
            json={"worker_id": "worker-b"},
            headers={"X-Worker-Token": TOKEN, "X-Worker-ID": "worker-a"},
        )
        assert mismatch.status_code == 409


def test_job_lease_limits_asset_access_and_expires() -> None:
    with TestClient(app) as client:
        _, job_id, portrait_id = create_external_job(client, "lease")
        claimed = claim(client, "worker-lease")
        assert claimed["job"]["id"] == job_id
        assert "claim_token_hash" not in claimed["job"]
        lease = claimed["lease_token"]
        asset_url = next(asset["download_url"] for asset in claimed["assets"] if asset["id"] == portrait_id)

        missing_lease = client.get(
            asset_url,
            headers={"X-Worker-Token": TOKEN, "X-Worker-ID": "worker-lease"},
        )
        assert missing_lease.status_code == 401

        wrong_worker = client.get(asset_url, headers=lease_headers("worker-other", lease))
        assert wrong_worker.status_code == 403

        authorized = client.get(asset_url, headers=lease_headers("worker-lease", lease))
        assert authorized.status_code == 200
        assert authorized.content == b"portrait-bytes"

        invalid_media = client.post(
            f"/api/workers/jobs/{job_id}/output",
            headers=lease_headers("worker-lease", lease),
            files={"file": ("output.mp4", b"not-an-mp4", "video/mp4")},
        )
        assert invalid_media.status_code == 422

        failed = client.post(
            f"/api/workers/jobs/{job_id}/complete",
            headers=lease_headers("worker-lease", lease),
            json={"status": "failed", "error": "controlled test failure"},
        )
        assert failed.status_code == 200

        expired = client.get(asset_url, headers=lease_headers("worker-lease", lease))
        assert expired.status_code == 403

        public_job = client.get(f"/api/jobs/{job_id}")
        assert public_job.status_code == 200
        assert "claim_token_hash" not in public_job.json()


def test_lease_cannot_cross_job_boundary() -> None:
    with TestClient(app) as client:
        create_external_job(client, "first")
        _, second_job_id, second_portrait_id = create_external_job(client, "second")

        first_claim = claim(client, "worker-first")
        second_claim = claim(client, "worker-second")
        assert second_claim["job"]["id"] == second_job_id
        second_asset_url = next(
            asset["download_url"]
            for asset in second_claim["assets"]
            if asset["id"] == second_portrait_id
        )

        crossed = client.get(
            second_asset_url,
            headers=lease_headers("worker-first", first_claim["lease_token"]),
        )
        assert crossed.status_code == 403

        authorized = client.get(
            second_asset_url,
            headers=lease_headers("worker-second", second_claim["lease_token"]),
        )
        assert authorized.status_code == 200
