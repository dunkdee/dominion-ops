from fastapi.testclient import TestClient

from app.main import app


def test_consent_project_and_missing_assets_gate() -> None:
    with TestClient(app) as client:
        health = client.get("/health")
        assert health.status_code == 200
        assert health.json()["status"] == "ok"

        consent = client.post(
            "/api/consents",
            json={
                "subject_name": "Authorized Subject",
                "likeness_confirmed": True,
                "voice_confirmed": True,
                "rights_confirmed": True,
            },
        )
        assert consent.status_code == 201

        project = client.post(
            "/api/projects",
            json={
                "title": "Test",
                "script": "This is a controlled test.",
                "output_format": "vertical",
                "consent_id": consent.json()["id"],
            },
        )
        assert project.status_code == 201

        queued = client.post(
            f"/api/projects/{project.json()['id']}/jobs",
            json={"engine": "proof_render"},
        )
        assert queued.status_code == 409
        assert "portrait" in queued.json()["detail"].lower()


def test_incomplete_consent_is_rejected() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/api/consents",
            json={
                "subject_name": "Unauthorized Subject",
                "likeness_confirmed": True,
                "voice_confirmed": False,
                "rights_confirmed": True,
            },
        )
        assert response.status_code == 422
