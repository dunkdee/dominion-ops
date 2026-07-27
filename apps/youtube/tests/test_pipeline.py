"""
Tests for pipeline.py

Covers: PipelineResult dataclass, _parse_scene_breakdown, _download_video,
_concatenate_clips, and run_pipeline (with all external dependencies mocked).
"""
import json
import os
import pytest
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch, call, mock_open


# ---------------------------------------------------------------------------
# PipelineResult
# ---------------------------------------------------------------------------

class TestPipelineResult:
    def test_defaults(self):
        from pipeline import PipelineResult

        r = PipelineResult(title="My Film", script="...", scene_count=3)
        assert r.youtube_video_id == ""
        assert r.youtube_url == ""
        assert r.errors == []
        assert r.status == "pending"

    def test_errors_list_is_independent_per_instance(self):
        from pipeline import PipelineResult

        r1 = PipelineResult(title="A", script="", scene_count=0)
        r2 = PipelineResult(title="B", script="", scene_count=0)
        r1.errors.append("err")
        assert r2.errors == []


# ---------------------------------------------------------------------------
# _parse_scene_breakdown
# ---------------------------------------------------------------------------

class TestParseSceneBreakdown:
    def test_parses_valid_json_array(self):
        from pipeline import _parse_scene_breakdown

        scenes = [
            {"scene_number": 1, "description": "Opening shot", "duration_seconds": 30},
            {"scene_number": 2, "description": "Climax", "duration_seconds": 45},
        ]
        script = f"Some text before\n{json.dumps(scenes)}\nSome text after"
        result = _parse_scene_breakdown(script)
        assert len(result) == 2
        assert result[0]["scene_number"] == 1
        assert result[1]["description"] == "Climax"

    def test_falls_back_to_single_scene_when_no_json(self):
        from pipeline import _parse_scene_breakdown

        result = _parse_scene_breakdown("There is no JSON array here at all.")
        assert len(result) == 1
        assert result[0]["scene_number"] == 1
        assert result[0]["location"] == "Various"
        assert result[0]["duration_seconds"] == 60

    def test_falls_back_when_json_is_invalid(self):
        from pipeline import _parse_scene_breakdown

        result = _parse_scene_breakdown("[not valid json}")
        assert len(result) == 1
        assert result[0]["scene_number"] == 1

    def test_fallback_description_truncated_to_500_chars(self):
        from pipeline import _parse_scene_breakdown

        long_script = "x" * 1000
        result = _parse_scene_breakdown(long_script)
        assert len(result[0]["description"]) == 500

    def test_parses_json_embedded_in_larger_text(self):
        from pipeline import _parse_scene_breakdown

        scenes = [{"scene_number": 1, "description": "intro", "duration_seconds": 10}]
        script = f"LOGLINE\nHere is the scene breakdown:\n{json.dumps(scenes)}\nEnd of script."
        result = _parse_scene_breakdown(script)
        assert result[0]["scene_number"] == 1

    def test_fallback_single_scene_has_required_keys(self):
        from pipeline import _parse_scene_breakdown

        result = _parse_scene_breakdown("plain text script")
        scene = result[0]
        assert "scene_number" in scene
        assert "location" in scene
        assert "description" in scene
        assert "duration_seconds" in scene

    def test_empty_script_returns_fallback(self):
        from pipeline import _parse_scene_breakdown

        result = _parse_scene_breakdown("")
        assert len(result) == 1


# ---------------------------------------------------------------------------
# _download_video
# ---------------------------------------------------------------------------

class TestDownloadVideo:
    def test_writes_streamed_chunks_to_file(self, tmp_path):
        from pipeline import _download_video

        dest = str(tmp_path / "clip.mp4")
        chunk1 = b"chunk_one"
        chunk2 = b"chunk_two"

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.iter_bytes.return_value = iter([chunk1, chunk2])

        mock_ctx = MagicMock()
        mock_ctx.__enter__ = MagicMock(return_value=mock_response)
        mock_ctx.__exit__ = MagicMock(return_value=False)

        with patch("pipeline.httpx.stream", return_value=mock_ctx):
            _download_video("https://example.com/video.mp4", dest)

        assert Path(dest).read_bytes() == b"chunk_onechunk_two"

    def test_raises_on_http_error(self, tmp_path):
        import httpx
        from pipeline import _download_video

        dest = str(tmp_path / "clip.mp4")

        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "404", request=MagicMock(), response=MagicMock()
        )

        mock_ctx = MagicMock()
        mock_ctx.__enter__ = MagicMock(return_value=mock_response)
        mock_ctx.__exit__ = MagicMock(return_value=False)

        with patch("pipeline.httpx.stream", return_value=mock_ctx):
            with pytest.raises(httpx.HTTPStatusError):
                _download_video("https://example.com/missing.mp4", dest)

    def test_uses_get_method_with_correct_url(self, tmp_path):
        from pipeline import _download_video

        dest = str(tmp_path / "clip.mp4")
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.iter_bytes.return_value = iter([])

        mock_ctx = MagicMock()
        mock_ctx.__enter__ = MagicMock(return_value=mock_response)
        mock_ctx.__exit__ = MagicMock(return_value=False)

        with patch("pipeline.httpx.stream", return_value=mock_ctx) as mock_stream:
            _download_video("https://cdn.example.com/video.mp4", dest)

        args, _ = mock_stream.call_args
        assert args[0] == "GET"
        assert args[1] == "https://cdn.example.com/video.mp4"


# ---------------------------------------------------------------------------
# _concatenate_clips
# ---------------------------------------------------------------------------

class TestConcatenateClips:
    def test_raises_on_nonzero_exit(self, tmp_path):
        from pipeline import _concatenate_clips

        clips = ["/tmp/a.mp4", "/tmp/b.mp4"]
        output = str(tmp_path / "out.mp4")

        with patch("pipeline.os.system", return_value=1), \
             patch("pipeline.os.unlink"):
            with pytest.raises(RuntimeError, match="ffmpeg concat failed"):
                _concatenate_clips(clips, output)

    def test_writes_list_file_before_ffmpeg(self, tmp_path):
        from pipeline import _concatenate_clips

        clips = ["/tmp/clip_001.mp4", "/tmp/clip_002.mp4"]
        output = str(tmp_path / "out.mp4")

        written_content = {}

        original_open = open

        def capture_open(path, mode="r", *args, **kwargs):
            if mode == "w" and path.endswith(".txt"):
                fh = original_open(path, mode, *args, **kwargs)
                written_content["path"] = path
                return fh
            return original_open(path, mode, *args, **kwargs)

        with patch("builtins.open", side_effect=capture_open), \
             patch("pipeline.os.system", return_value=0), \
             patch("pipeline.os.unlink"):
            _concatenate_clips(clips, output)

        assert "path" in written_content

    def test_deletes_list_file_on_success(self, tmp_path):
        from pipeline import _concatenate_clips

        clips = ["/tmp/a.mp4"]
        output = str(tmp_path / "out.mp4")

        with patch("pipeline.os.system", return_value=0) as mock_sys, \
             patch("pipeline.os.unlink") as mock_unlink:
            _concatenate_clips(clips, output)

        mock_unlink.assert_called_once()

    def test_deletes_list_file_on_failure(self, tmp_path):
        from pipeline import _concatenate_clips

        clips = ["/tmp/a.mp4"]
        output = str(tmp_path / "out.mp4")

        with patch("pipeline.os.system", return_value=1), \
             patch("pipeline.os.unlink") as mock_unlink:
            with pytest.raises(RuntimeError):
                _concatenate_clips(clips, output)

        mock_unlink.assert_called_once()


# ---------------------------------------------------------------------------
# run_pipeline
# ---------------------------------------------------------------------------

class TestRunPipeline:
    """Integration-level tests for run_pipeline with all IO mocked."""

    _SCENES = [
        {"scene_number": 1, "description": "Opening", "duration_seconds": 30},
        {"scene_number": 2, "description": "Climax", "duration_seconds": 45},
    ]

    def _make_mock_generator(self, video_url="/tmp/stub_video.mp4", fail_scene=None):
        """Build a mock VideoGenerator."""
        from video_generator import VideoJob

        mock_gen = MagicMock()

        def create_video(prompt, duration, voiceover=""):
            return VideoJob(job_id="job-1", status="queued")

        def wait_for_completion(job_id, **kwargs):
            if fail_scene is not None:
                return VideoJob(job_id=job_id, status="failed", error="GPU error")
            return VideoJob(job_id=job_id, status="completed", video_url=video_url)

        mock_gen.create_video.side_effect = create_video
        mock_gen.wait_for_completion.side_effect = wait_for_completion
        return mock_gen

    def test_successful_pipeline_without_upload(self, tmp_path):
        from pipeline import run_pipeline

        mock_gen = self._make_mock_generator(video_url="/tmp/stub_video.mp4")

        with patch("pipeline.generate_script", return_value=f"SCRIPT\n{json.dumps(self._SCENES)}"), \
             patch("pipeline.generate_voiceover", return_value="Voiceover text"), \
             patch("pipeline.generate_scene_visuals", return_value="Visual prompt"), \
             patch("pipeline.generate_title_and_description", return_value={"title": "T", "description": "D", "tags": []}), \
             patch("pipeline.get_video_generator", return_value=mock_gen), \
             patch("pipeline._concatenate_clips"), \
             patch("pipeline.upload_video"):
            result = run_pipeline("A robot story", "ROBO", upload=False)

        assert result.status in ("completed", "completed_with_errors")
        assert result.scene_count == 2
        assert result.title == "ROBO"

    def test_status_completed_when_no_errors(self, tmp_path):
        from pipeline import run_pipeline

        mock_gen = self._make_mock_generator(video_url="/tmp/stub_video.mp4")

        with patch("pipeline.generate_script", return_value=f"SCRIPT\n{json.dumps(self._SCENES)}"), \
             patch("pipeline.generate_voiceover", return_value="Voiceover"), \
             patch("pipeline.generate_scene_visuals", return_value="Visuals"), \
             patch("pipeline.generate_title_and_description", return_value={"title": "T", "description": "D", "tags": []}), \
             patch("pipeline.get_video_generator", return_value=mock_gen), \
             patch("pipeline._concatenate_clips"), \
             patch("pipeline.upload_video"):
            result = run_pipeline("story", "Title", upload=False)

        assert result.status == "completed"
        assert result.errors == []

    def test_status_failed_when_no_clips_generated(self):
        from pipeline import run_pipeline
        from video_generator import VideoJob

        mock_gen = MagicMock()
        mock_gen.create_video.return_value = VideoJob(job_id="j1", status="queued")
        mock_gen.wait_for_completion.return_value = VideoJob(job_id="j1", status="failed", error="OOM")

        with patch("pipeline.generate_script", return_value=f"SCRIPT\n{json.dumps(self._SCENES)}"), \
             patch("pipeline.generate_voiceover", return_value=""), \
             patch("pipeline.generate_scene_visuals", return_value=""), \
             patch("pipeline.generate_title_and_description", return_value={}), \
             patch("pipeline.get_video_generator", return_value=mock_gen):
            result = run_pipeline("story", "Title")

        assert result.status == "failed"
        assert "No video clips generated" in result.errors

    def test_errors_collected_for_failed_scenes(self):
        from pipeline import run_pipeline
        from video_generator import VideoJob

        # Scene 1 fails, scene 2 succeeds
        call_count = {"n": 0}

        def wait(job_id, **kwargs):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return VideoJob(job_id=job_id, status="failed", error="GPU error")
            return VideoJob(job_id=job_id, status="completed", video_url="/tmp/stub_video.mp4")

        mock_gen = MagicMock()
        mock_gen.create_video.return_value = VideoJob(job_id="j1", status="queued")
        mock_gen.wait_for_completion.side_effect = wait

        with patch("pipeline.generate_script", return_value=f"SCRIPT\n{json.dumps(self._SCENES)}"), \
             patch("pipeline.generate_voiceover", return_value=""), \
             patch("pipeline.generate_scene_visuals", return_value=""), \
             patch("pipeline.generate_title_and_description", return_value={"title": "T", "description": "D", "tags": []}), \
             patch("pipeline.get_video_generator", return_value=mock_gen), \
             patch("pipeline._concatenate_clips"), \
             patch("pipeline.upload_video"):
            result = run_pipeline("story", "Title", upload=False)

        assert any("Scene 1 failed" in e for e in result.errors)
        assert result.status == "completed_with_errors"

    def test_upload_called_when_upload_true(self):
        from pipeline import run_pipeline

        mock_gen = self._make_mock_generator(video_url="/tmp/stub_video.mp4")
        mock_upload = MagicMock(return_value={"id": "yt123"})

        with patch("pipeline.generate_script", return_value=f"X\n{json.dumps(self._SCENES[:1])}"), \
             patch("pipeline.generate_voiceover", return_value=""), \
             patch("pipeline.generate_scene_visuals", return_value=""), \
             patch("pipeline.generate_title_and_description", return_value={"title": "T", "description": "D", "tags": []}), \
             patch("pipeline.get_video_generator", return_value=mock_gen), \
             patch("pipeline.upload_video", mock_upload):
            result = run_pipeline("story", "Title", upload=True)

        mock_upload.assert_called_once()
        assert result.youtube_video_id == "yt123"
        assert result.youtube_url == "https://www.youtube.com/watch?v=yt123"

    def test_upload_skipped_when_upload_false(self):
        from pipeline import run_pipeline

        mock_gen = self._make_mock_generator(video_url="/tmp/stub_video.mp4")
        mock_upload = MagicMock()

        with patch("pipeline.generate_script", return_value=f"X\n{json.dumps(self._SCENES[:1])}"), \
             patch("pipeline.generate_voiceover", return_value=""), \
             patch("pipeline.generate_scene_visuals", return_value=""), \
             patch("pipeline.generate_title_and_description", return_value={"title": "T", "description": "D", "tags": []}), \
             patch("pipeline.get_video_generator", return_value=mock_gen), \
             patch("pipeline.upload_video", mock_upload):
            result = run_pipeline("story", "Title", upload=False)

        mock_upload.assert_not_called()
        assert result.youtube_url == ""

    def test_single_clip_skips_concatenation(self):
        from pipeline import run_pipeline

        single_scene = [self._SCENES[0]]
        mock_gen = self._make_mock_generator(video_url="/tmp/stub_video.mp4")
        mock_concat = MagicMock()

        with patch("pipeline.generate_script", return_value=f"X\n{json.dumps(single_scene)}"), \
             patch("pipeline.generate_voiceover", return_value=""), \
             patch("pipeline.generate_scene_visuals", return_value=""), \
             patch("pipeline.generate_title_and_description", return_value={"title": "T", "description": "D", "tags": []}), \
             patch("pipeline.get_video_generator", return_value=mock_gen), \
             patch("pipeline._concatenate_clips", mock_concat), \
             patch("pipeline.upload_video"):
            run_pipeline("story", "Title", upload=False)

        mock_concat.assert_not_called()

    def test_multiple_clips_triggers_concatenation(self):
        from pipeline import run_pipeline

        mock_gen = self._make_mock_generator(video_url="/tmp/stub_video.mp4")
        mock_concat = MagicMock()

        with patch("pipeline.generate_script", return_value=f"X\n{json.dumps(self._SCENES)}"), \
             patch("pipeline.generate_voiceover", return_value=""), \
             patch("pipeline.generate_scene_visuals", return_value=""), \
             patch("pipeline.generate_title_and_description", return_value={"title": "T", "description": "D", "tags": []}), \
             patch("pipeline.get_video_generator", return_value=mock_gen), \
             patch("pipeline._concatenate_clips", mock_concat), \
             patch("pipeline.upload_video"):
            run_pipeline("story", "Title", upload=False)

        mock_concat.assert_called_once()

    def test_exception_in_wait_recorded_as_error(self):
        from pipeline import run_pipeline
        from video_generator import VideoJob

        mock_gen = MagicMock()
        mock_gen.create_video.return_value = VideoJob(job_id="j1", status="queued")
        mock_gen.wait_for_completion.side_effect = TimeoutError("timed out")

        with patch("pipeline.generate_script", return_value=f"X\n{json.dumps(self._SCENES[:1])}"), \
             patch("pipeline.generate_voiceover", return_value=""), \
             patch("pipeline.generate_scene_visuals", return_value=""), \
             patch("pipeline.generate_title_and_description", return_value={}), \
             patch("pipeline.get_video_generator", return_value=mock_gen):
            result = run_pipeline("story", "Title")

        assert result.status == "failed"
        assert any("error" in e.lower() for e in result.errors)

    def test_downloads_non_local_video_url(self):
        from pipeline import run_pipeline
        from video_generator import VideoJob

        mock_gen = MagicMock()
        mock_gen.create_video.return_value = VideoJob(job_id="j1", status="queued")
        mock_gen.wait_for_completion.return_value = VideoJob(
            job_id="j1", status="completed", video_url="https://cdn.example.com/vid.mp4"
        )

        mock_download = MagicMock()
        single_scene = [self._SCENES[0]]

        with patch("pipeline.generate_script", return_value=f"X\n{json.dumps(single_scene)}"), \
             patch("pipeline.generate_voiceover", return_value=""), \
             patch("pipeline.generate_scene_visuals", return_value=""), \
             patch("pipeline.generate_title_and_description", return_value={"title": "T", "description": "D", "tags": []}), \
             patch("pipeline.get_video_generator", return_value=mock_gen), \
             patch("pipeline._download_video", mock_download), \
             patch("pipeline.upload_video"):
            run_pipeline("story", "Title", upload=False)

        mock_download.assert_called_once()

    def test_local_video_url_skips_download(self):
        from pipeline import run_pipeline
        from video_generator import VideoJob

        mock_gen = MagicMock()
        mock_gen.create_video.return_value = VideoJob(job_id="j1", status="queued")
        mock_gen.wait_for_completion.return_value = VideoJob(
            job_id="j1", status="completed", video_url="/tmp/local_clip.mp4"
        )

        mock_download = MagicMock()
        single_scene = [self._SCENES[0]]

        with patch("pipeline.generate_script", return_value=f"X\n{json.dumps(single_scene)}"), \
             patch("pipeline.generate_voiceover", return_value=""), \
             patch("pipeline.generate_scene_visuals", return_value=""), \
             patch("pipeline.generate_title_and_description", return_value={"title": "T", "description": "D", "tags": []}), \
             patch("pipeline.get_video_generator", return_value=mock_gen), \
             patch("pipeline._download_video", mock_download), \
             patch("pipeline.upload_video"):
            run_pipeline("story", "Title", upload=False)

        mock_download.assert_not_called()