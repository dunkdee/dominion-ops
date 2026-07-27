"""
Tests for video_generator.py

Covers: VideoJob dataclass, VideoGenerator.wait_for_completion, HigginsVideoGenerator,
StubVideoGenerator, and get_video_generator factory.
"""
import os
import time
import pytest
from unittest.mock import MagicMock, patch, call
from dataclasses import asdict


# ---------------------------------------------------------------------------
# VideoJob
# ---------------------------------------------------------------------------

class TestVideoJob:
    def test_defaults(self):
        from video_generator import VideoJob

        job = VideoJob(job_id="abc", status="queued")
        assert job.job_id == "abc"
        assert job.status == "queued"
        assert job.video_url is None
        assert job.error is None

    def test_full_construction(self):
        from video_generator import VideoJob

        job = VideoJob(job_id="j1", status="completed", video_url="https://example.com/v.mp4", error=None)
        assert job.video_url == "https://example.com/v.mp4"

    def test_failed_job_carries_error(self):
        from video_generator import VideoJob

        job = VideoJob(job_id="j2", status="failed", error="GPU OOM")
        assert job.status == "failed"
        assert job.error == "GPU OOM"


# ---------------------------------------------------------------------------
# VideoGenerator.wait_for_completion (tested via a concrete subclass)
# ---------------------------------------------------------------------------

class TestWaitForCompletion:
    def _make_generator(self, statuses: list[str]):
        """Build a concrete VideoGenerator whose get_status cycles through statuses."""
        from video_generator import VideoGenerator, VideoJob

        class _FakeGen(VideoGenerator):
            def __init__(self):
                self._calls = iter(statuses)

            def create_video(self, visual_prompt, duration_seconds, voiceover_text=""):
                return VideoJob(job_id="fake", status="queued")

            def get_status(self, job_id):
                status = next(self._calls, "completed")
                return VideoJob(job_id=job_id, status=status,
                                video_url="/tmp/video.mp4" if status == "completed" else None)

        return _FakeGen()

    def test_returns_immediately_when_already_completed(self):
        gen = self._make_generator(["completed"])
        with patch("time.sleep"):
            job = gen.wait_for_completion("fake", timeout=10, poll_interval=1)
        assert job.status == "completed"

    def test_returns_immediately_when_already_failed(self):
        gen = self._make_generator(["failed"])
        with patch("time.sleep"):
            job = gen.wait_for_completion("fake", timeout=10, poll_interval=1)
        assert job.status == "failed"

    def test_polls_until_completed(self):
        gen = self._make_generator(["queued", "processing", "completed"])
        with patch("time.sleep") as mock_sleep:
            job = gen.wait_for_completion("fake", timeout=60, poll_interval=5)
        assert job.status == "completed"
        assert mock_sleep.call_count == 2  # slept while queued and processing

    def test_raises_timeout_error_when_deadline_passed(self):
        from video_generator import VideoGenerator, VideoJob

        class _NeverDone(VideoGenerator):
            def create_video(self, *args, **kwargs):
                return VideoJob(job_id="nd", status="queued")

            def get_status(self, job_id):
                return VideoJob(job_id=job_id, status="processing")

        gen = _NeverDone()
        # Use a very small timeout so the loop exits quickly
        with patch("time.sleep"), \
             patch("time.time", side_effect=[0, 0, 100]):  # start, first check, second check exceeds timeout
            with pytest.raises(TimeoutError, match="did not complete within"):
                gen.wait_for_completion("nd", timeout=50, poll_interval=1)

    def test_timeout_error_includes_job_id(self):
        from video_generator import VideoGenerator, VideoJob

        class _NeverDone(VideoGenerator):
            def create_video(self, *args, **kwargs):
                return VideoJob(job_id="xyz-job", status="queued")

            def get_status(self, job_id):
                return VideoJob(job_id=job_id, status="processing")

        gen = _NeverDone()
        with patch("time.sleep"), \
             patch("time.time", side_effect=[0, 0, 999]):
            with pytest.raises(TimeoutError) as exc_info:
                gen.wait_for_completion("xyz-job", timeout=50, poll_interval=1)
        assert "xyz-job" in str(exc_info.value)


# ---------------------------------------------------------------------------
# StubVideoGenerator
# ---------------------------------------------------------------------------

class TestStubVideoGenerator:
    def test_create_video_returns_completed_job(self):
        from video_generator import StubVideoGenerator

        gen = StubVideoGenerator()
        job = gen.create_video("a lush forest", 30)
        assert job.status == "completed"
        assert job.video_url == "/tmp/stub_video.mp4"

    def test_create_video_always_same_job_id(self):
        from video_generator import StubVideoGenerator

        gen = StubVideoGenerator()
        job = gen.create_video("scene 1", 15)
        assert job.job_id == "stub-001"

    def test_get_status_returns_completed(self):
        from video_generator import StubVideoGenerator

        gen = StubVideoGenerator()
        job = gen.get_status("any-id")
        assert job.status == "completed"
        assert job.video_url == "/tmp/stub_video.mp4"

    def test_get_status_preserves_job_id(self):
        from video_generator import StubVideoGenerator

        gen = StubVideoGenerator()
        job = gen.get_status("my-job-id")
        assert job.job_id == "my-job-id"

    def test_create_video_with_voiceover(self):
        from video_generator import StubVideoGenerator

        gen = StubVideoGenerator()
        job = gen.create_video("scene", 10, voiceover_text="In the beginning...")
        assert job.status == "completed"

    def test_create_video_empty_prompt(self):
        from video_generator import StubVideoGenerator

        gen = StubVideoGenerator()
        job = gen.create_video("", 5)
        assert isinstance(job.job_id, str)


# ---------------------------------------------------------------------------
# HigginsVideoGenerator
# ---------------------------------------------------------------------------

class TestHigginsVideoGenerator:
    def _make_higgins(self, monkeypatch):
        """Build HigginsVideoGenerator with a mocked httpx.Client."""
        monkeypatch.setenv("HIGGINS_API_KEY", "test-key-higgins")
        from video_generator import HigginsVideoGenerator

        mock_client = MagicMock()
        with patch("video_generator.httpx.Client", return_value=mock_client):
            gen = HigginsVideoGenerator()
        gen.client = mock_client
        return gen

    def test_create_video_posts_to_videos_endpoint(self, monkeypatch):
        gen = self._make_higgins(monkeypatch)
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"id": "v123", "status": "queued"}
        gen.client.post.return_value = mock_resp

        job = gen.create_video("a dark forest", 30)

        gen.client.post.assert_called_once()
        args, kwargs = gen.client.post.call_args
        assert args[0] == "/videos"
        assert kwargs["json"]["prompt"] == "a dark forest"
        assert kwargs["json"]["duration"] == 30

    def test_create_video_returns_video_job(self, monkeypatch):
        gen = self._make_higgins(monkeypatch)
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"id": "v999", "status": "queued"}
        gen.client.post.return_value = mock_resp

        from video_generator import VideoJob
        job = gen.create_video("a beach at sunset", 15)
        assert isinstance(job, VideoJob)
        assert job.job_id == "v999"
        assert job.status == "queued"

    def test_create_video_includes_voiceover_when_provided(self, monkeypatch):
        gen = self._make_higgins(monkeypatch)
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"id": "v1", "status": "queued"}
        gen.client.post.return_value = mock_resp

        gen.create_video("scene", 10, voiceover_text="Narration here")
        _, kwargs = gen.client.post.call_args
        assert kwargs["json"]["voiceover"] == "Narration here"

    def test_create_video_omits_voiceover_when_empty(self, monkeypatch):
        gen = self._make_higgins(monkeypatch)
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"id": "v2", "status": "queued"}
        gen.client.post.return_value = mock_resp

        gen.create_video("scene", 10, voiceover_text="")
        _, kwargs = gen.client.post.call_args
        assert "voiceover" not in kwargs["json"]

    def test_create_video_always_requests_16_9_aspect_ratio(self, monkeypatch):
        gen = self._make_higgins(monkeypatch)
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"id": "v3", "status": "queued"}
        gen.client.post.return_value = mock_resp

        gen.create_video("wide scene", 20)
        _, kwargs = gen.client.post.call_args
        assert kwargs["json"]["aspect_ratio"] == "16:9"

    def test_get_status_calls_correct_endpoint(self, monkeypatch):
        gen = self._make_higgins(monkeypatch)
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"status": "processing", "video_url": None, "error": None}
        gen.client.get.return_value = mock_resp

        gen.get_status("abc-123")
        gen.client.get.assert_called_once_with("/videos/abc-123")

    def test_get_status_returns_video_job(self, monkeypatch):
        gen = self._make_higgins(monkeypatch)
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "status": "completed",
            "video_url": "https://cdn.higgins.ai/v.mp4",
            "error": None,
        }
        gen.client.get.return_value = mock_resp

        from video_generator import VideoJob
        job = gen.get_status("j42")
        assert isinstance(job, VideoJob)
        assert job.job_id == "j42"
        assert job.status == "completed"
        assert job.video_url == "https://cdn.higgins.ai/v.mp4"

    def test_get_status_maps_error_field(self, monkeypatch):
        gen = self._make_higgins(monkeypatch)
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"status": "failed", "video_url": None, "error": "OOM"}
        gen.client.get.return_value = mock_resp

        job = gen.get_status("j99")
        assert job.status == "failed"
        assert job.error == "OOM"

    def test_init_requires_higgins_api_key(self, monkeypatch):
        monkeypatch.delenv("HIGGINS_API_KEY", raising=False)
        from video_generator import HigginsVideoGenerator

        with pytest.raises(KeyError):
            HigginsVideoGenerator()

    def test_default_base_url(self, monkeypatch):
        monkeypatch.setenv("HIGGINS_API_KEY", "key")
        monkeypatch.delenv("HIGGINS_API_URL", raising=False)
        from video_generator import HigginsVideoGenerator

        with patch("video_generator.httpx.Client") as mock_client_cls:
            mock_client_cls.return_value = MagicMock()
            gen = HigginsVideoGenerator()
        assert gen.base_url == "https://api.higgins.ai/v1"

    def test_custom_base_url_from_env(self, monkeypatch):
        monkeypatch.setenv("HIGGINS_API_KEY", "key")
        monkeypatch.setenv("HIGGINS_API_URL", "https://custom.higgins.internal/v2")
        from video_generator import HigginsVideoGenerator

        with patch("video_generator.httpx.Client") as mock_client_cls:
            mock_client_cls.return_value = MagicMock()
            gen = HigginsVideoGenerator()
        assert gen.base_url == "https://custom.higgins.internal/v2"


# ---------------------------------------------------------------------------
# get_video_generator factory
# ---------------------------------------------------------------------------

class TestGetVideoGenerator:
    def test_returns_stub_when_no_higgins_key(self, monkeypatch):
        monkeypatch.delenv("HIGGINS_API_KEY", raising=False)
        from video_generator import get_video_generator, StubVideoGenerator

        gen = get_video_generator()
        assert isinstance(gen, StubVideoGenerator)

    def test_returns_higgins_when_key_set(self, monkeypatch):
        monkeypatch.setenv("HIGGINS_API_KEY", "real-key")
        from video_generator import get_video_generator, HigginsVideoGenerator

        with patch("video_generator.httpx.Client", return_value=MagicMock()):
            gen = get_video_generator()
        assert isinstance(gen, HigginsVideoGenerator)

    def test_returns_stub_for_empty_string_key(self, monkeypatch):
        monkeypatch.setenv("HIGGINS_API_KEY", "")
        from video_generator import get_video_generator, StubVideoGenerator

        gen = get_video_generator()
        assert isinstance(gen, StubVideoGenerator)