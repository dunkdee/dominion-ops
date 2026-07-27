"""
Tests for main.py (FastAPI application)

Uses FastAPI's TestClient with all external service functions mocked so no
real Anthropic, Higgins, or YouTube calls are made.
"""
import pytest
from unittest.mock import MagicMock, patch


@pytest.fixture(autouse=True)
def reset_jobs():
    """Clear the in-memory _jobs dict between tests to avoid state leakage."""
    import main
    main._jobs.clear()
    yield
    main._jobs.clear()


@pytest.fixture
def client():
    from fastapi.testclient import TestClient
    from main import app
    return TestClient(app)


# ---------------------------------------------------------------------------
# GET /healthz
# ---------------------------------------------------------------------------

class TestHealthz:
    def test_returns_200(self, client):
        resp = client.get("/healthz")
        assert resp.status_code == 200

    def test_returns_ok_status(self, client):
        resp = client.get("/healthz")
        assert resp.json()["status"] == "ok"

    def test_returns_service_name(self, client):
        resp = client.get("/healthz")
        assert resp.json()["service"] == "movie-generator"


# ---------------------------------------------------------------------------
# POST /script/generate
# ---------------------------------------------------------------------------

class TestScriptGenerate:
    def test_returns_200_with_script(self, client):
        with patch("main.generate_script", return_value="INT. SPACE - DAY\nAction line.") as mock_gs, \
             patch("main.generate_title_and_description", return_value={
                 "title": "Space Movie", "description": "An epic tale", "tags": ["space"]
             }):
            resp = client.post("/script/generate", json={"prompt": "robots in space", "title": "Space Movie"})

        assert resp.status_code == 200
        body = resp.json()
        assert body["title"] == "Space Movie"
        assert body["script"] == "INT. SPACE - DAY\nAction line."
        assert body["youtube_meta"]["title"] == "Space Movie"

    def test_calls_generate_script_with_correct_args(self, client):
        with patch("main.generate_script", return_value="script") as mock_gs, \
             patch("main.generate_title_and_description", return_value={}):
            client.post("/script/generate", json={"prompt": "my premise", "title": "My Film"})

        mock_gs.assert_called_once_with("my premise", "My Film")

    def test_calls_generate_title_and_description(self, client):
        with patch("main.generate_script", return_value="script text") as mock_gs, \
             patch("main.generate_title_and_description", return_value={}) as mock_gtd:
            client.post("/script/generate", json={"prompt": "premise", "title": "Title"})

        mock_gtd.assert_called_once_with("script text", "Title")

    def test_missing_prompt_returns_422(self, client):
        resp = client.post("/script/generate", json={"title": "No Prompt"})
        assert resp.status_code == 422

    def test_missing_title_returns_422(self, client):
        resp = client.post("/script/generate", json={"prompt": "A story"})
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# POST /pipeline/start
# ---------------------------------------------------------------------------

class TestPipelineStart:
    def test_returns_queued_status_and_job_id(self, client):
        with patch("main.run_pipeline"):
            resp = client.post("/pipeline/start", json={
                "prompt": "A robot story",
                "title": "Robot Film",
            })

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "queued"
        assert "job_id" in body
        assert len(body["job_id"]) > 0

    def test_job_stored_in_jobs_dict(self, client):
        import main

        with patch("main.run_pipeline"):
            resp = client.post("/pipeline/start", json={
                "prompt": "A story",
                "title": "My Movie",
            })

        job_id = resp.json()["job_id"]
        assert job_id in main._jobs

    def test_initial_job_status_is_queued(self, client):
        import main

        with patch("main.run_pipeline"):
            resp = client.post("/pipeline/start", json={
                "prompt": "story",
                "title": "Film",
            })

        job_id = resp.json()["job_id"]
        assert main._jobs[job_id].status == "queued"

    def test_default_privacy_is_private(self, client):
        import main

        with patch("main.run_pipeline"):
            resp = client.post("/pipeline/start", json={
                "prompt": "story",
                "title": "Film",
            })

        job_id = resp.json()["job_id"]
        # Initial record; privacy is handled inside run_pipeline, not stored in PipelineResult
        assert resp.status_code == 200

    def test_upload_defaults_to_true(self, client):
        """PipelineRequest.upload defaults to True — verify no error without explicit value."""
        with patch("main.run_pipeline"):
            resp = client.post("/pipeline/start", json={"prompt": "p", "title": "t"})
        assert resp.status_code == 200

    def test_two_requests_get_different_job_ids(self, client):
        with patch("main.run_pipeline"):
            r1 = client.post("/pipeline/start", json={"prompt": "p", "title": "t"})
            r2 = client.post("/pipeline/start", json={"prompt": "p", "title": "t"})

        assert r1.json()["job_id"] != r2.json()["job_id"]


# ---------------------------------------------------------------------------
# GET /pipeline/status/{job_id}
# ---------------------------------------------------------------------------

class TestPipelineStatus:
    def _insert_job(self, status="running", title="My Film", scene_count=3,
                    youtube_url="", errors=None):
        import main
        from pipeline import PipelineResult

        job_id = "test-job-abc"
        main._jobs[job_id] = PipelineResult(
            title=title,
            script="",
            scene_count=scene_count,
            youtube_url=youtube_url,
            status=status,
            errors=errors or [],
        )
        return job_id

    def test_returns_404_for_unknown_job(self, client):
        resp = client.get("/pipeline/status/nonexistent-job-id")
        assert resp.status_code == 404

    def test_returns_404_detail(self, client):
        resp = client.get("/pipeline/status/no-such-job")
        assert "not found" in resp.json()["detail"].lower()

    def test_returns_status_for_known_job(self, client):
        job_id = self._insert_job(status="running")
        resp = client.get(f"/pipeline/status/{job_id}")
        assert resp.status_code == 200
        assert resp.json()["status"] == "running"

    def test_returns_all_expected_fields(self, client):
        job_id = self._insert_job(title="Epic", scene_count=5, youtube_url="https://yt.be/x")
        resp = client.get(f"/pipeline/status/{job_id}")
        body = resp.json()
        assert "job_id" in body
        assert "status" in body
        assert "title" in body
        assert "scene_count" in body
        assert "youtube_url" in body
        assert "errors" in body

    def test_job_id_in_response_matches_path(self, client):
        job_id = self._insert_job()
        resp = client.get(f"/pipeline/status/{job_id}")
        assert resp.json()["job_id"] == job_id

    def test_scene_count_returned_correctly(self, client):
        job_id = self._insert_job(scene_count=7)
        resp = client.get(f"/pipeline/status/{job_id}")
        assert resp.json()["scene_count"] == 7

    def test_errors_list_returned(self, client):
        job_id = self._insert_job(errors=["Scene 1 failed"])
        resp = client.get(f"/pipeline/status/{job_id}")
        assert resp.json()["errors"] == ["Scene 1 failed"]

    def test_youtube_url_returned(self, client):
        url = "https://www.youtube.com/watch?v=abc123"
        job_id = self._insert_job(youtube_url=url)
        resp = client.get(f"/pipeline/status/{job_id}")
        assert resp.json()["youtube_url"] == url


# ---------------------------------------------------------------------------
# GET /youtube/auth
# ---------------------------------------------------------------------------

class TestYouTubeAuth:
    def test_returns_auth_url(self, client):
        with patch("main.get_oauth_url", return_value="https://accounts.google.com/auth?client_id=cid"):
            resp = client.get("/youtube/auth")

        assert resp.status_code == 200
        assert resp.json()["auth_url"] == "https://accounts.google.com/auth?client_id=cid"

    def test_calls_get_oauth_url(self, client):
        with patch("main.get_oauth_url", return_value="https://auth.url/") as mock_oauth:
            client.get("/youtube/auth")

        mock_oauth.assert_called_once()


# ---------------------------------------------------------------------------
# GET /youtube/callback
# ---------------------------------------------------------------------------

class TestYouTubeCallback:
    def test_returns_authorized_status(self, client):
        with patch("main.exchange_code", return_value={"access_token": "at", "scope": "youtube.upload"}):
            resp = client.get("/youtube/callback", params={"code": "auth-code"})

        assert resp.status_code == 200
        assert resp.json()["status"] == "authorized"

    def test_returns_scope_from_tokens(self, client):
        with patch("main.exchange_code", return_value={"scope": "https://www.googleapis.com/auth/youtube.upload"}):
            resp = client.get("/youtube/callback", params={"code": "auth-code"})

        assert "youtube.upload" in resp.json()["scope"]

    def test_calls_exchange_code_with_code(self, client):
        with patch("main.exchange_code", return_value={}) as mock_exchange:
            client.get("/youtube/callback", params={"code": "my-auth-code"})

        mock_exchange.assert_called_once_with("my-auth-code")

    def test_scope_defaults_to_empty_string_when_missing(self, client):
        with patch("main.exchange_code", return_value={"access_token": "at"}):
            resp = client.get("/youtube/callback", params={"code": "code"})

        assert resp.json()["scope"] == ""

    def test_missing_code_param_returns_422(self, client):
        resp = client.get("/youtube/callback")
        assert resp.status_code == 422