"""
Tests for youtube_uploader.py

Covers: _load_tokens, _save_tokens, _refresh_access_token, upload_video,
get_oauth_url, exchange_code.
"""
import json
import os
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch, mock_open


# ---------------------------------------------------------------------------
# _load_tokens / _save_tokens
# ---------------------------------------------------------------------------

class TestLoadTokens:
    def test_returns_empty_dict_when_file_missing(self, token_file):
        import youtube_uploader

        # token_file fixture points to a non-existent path initially
        result = youtube_uploader._load_tokens()
        assert result == {}

    def test_returns_parsed_json_when_file_exists(self, token_file):
        import youtube_uploader

        tokens = {"access_token": "at1", "refresh_token": "rt1"}
        Path(token_file).parent.mkdir(parents=True, exist_ok=True)
        Path(token_file).write_text(json.dumps(tokens))

        result = youtube_uploader._load_tokens()
        assert result == tokens

    def test_returns_empty_dict_for_empty_key(self, token_file):
        import youtube_uploader

        tokens = {"refresh_token": ""}
        Path(token_file).parent.mkdir(parents=True, exist_ok=True)
        Path(token_file).write_text(json.dumps(tokens))

        result = youtube_uploader._load_tokens()
        assert result["refresh_token"] == ""


class TestSaveTokens:
    def test_creates_file_and_directory(self, token_file):
        import youtube_uploader

        tokens = {"access_token": "tok", "refresh_token": "ref"}
        youtube_uploader._save_tokens(tokens)

        assert Path(token_file).exists()
        saved = json.loads(Path(token_file).read_text())
        assert saved == tokens

    def test_overwrites_existing_file(self, token_file):
        import youtube_uploader

        Path(token_file).parent.mkdir(parents=True, exist_ok=True)
        Path(token_file).write_text(json.dumps({"old": "data"}))

        new_tokens = {"access_token": "new_at"}
        youtube_uploader._save_tokens(new_tokens)
        saved = json.loads(Path(token_file).read_text())
        assert saved == new_tokens

    def test_round_trip(self, token_file):
        import youtube_uploader

        tokens = {"access_token": "at", "refresh_token": "rt", "scope": "upload"}
        youtube_uploader._save_tokens(tokens)
        loaded = youtube_uploader._load_tokens()
        assert loaded == tokens


# ---------------------------------------------------------------------------
# _refresh_access_token
# ---------------------------------------------------------------------------

class TestRefreshAccessToken:
    def test_raises_when_no_refresh_token(self, token_file, monkeypatch):
        import youtube_uploader

        # No token file → empty dict → no refresh_token
        with pytest.raises(RuntimeError, match="No YouTube refresh_token"):
            youtube_uploader._refresh_access_token()

    def test_raises_when_refresh_token_empty(self, token_file):
        import youtube_uploader

        youtube_uploader._save_tokens({"refresh_token": ""})
        with pytest.raises(RuntimeError, match="No YouTube refresh_token"):
            youtube_uploader._refresh_access_token()

    def test_posts_to_google_token_endpoint(self, token_file, monkeypatch):
        import youtube_uploader

        youtube_uploader._save_tokens({"refresh_token": "valid_rt"})
        monkeypatch.setenv("YOUTUBE_CLIENT_ID", "cid")
        monkeypatch.setenv("YOUTUBE_CLIENT_SECRET", "csec")

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"access_token": "new_at"}

        with patch("youtube_uploader.httpx.post", return_value=mock_resp) as mock_post:
            token = youtube_uploader._refresh_access_token()

        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        assert args[0] == "https://oauth2.googleapis.com/token"
        assert kwargs["data"]["grant_type"] == "refresh_token"
        assert kwargs["data"]["refresh_token"] == "valid_rt"

    def test_returns_new_access_token(self, token_file, monkeypatch):
        import youtube_uploader

        youtube_uploader._save_tokens({"refresh_token": "rt"})
        monkeypatch.setenv("YOUTUBE_CLIENT_ID", "cid")
        monkeypatch.setenv("YOUTUBE_CLIENT_SECRET", "csec")

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"access_token": "brand_new_token"}
        with patch("youtube_uploader.httpx.post", return_value=mock_resp):
            token = youtube_uploader._refresh_access_token()

        assert token == "brand_new_token"

    def test_persists_new_access_token(self, token_file, monkeypatch):
        import youtube_uploader

        youtube_uploader._save_tokens({"refresh_token": "rt"})
        monkeypatch.setenv("YOUTUBE_CLIENT_ID", "cid")
        monkeypatch.setenv("YOUTUBE_CLIENT_SECRET", "csec")

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"access_token": "saved_token"}
        with patch("youtube_uploader.httpx.post", return_value=mock_resp):
            youtube_uploader._refresh_access_token()

        persisted = youtube_uploader._load_tokens()
        assert persisted["access_token"] == "saved_token"


# ---------------------------------------------------------------------------
# upload_video
# ---------------------------------------------------------------------------

class TestUploadVideo:
    def _setup_upload(self, tmp_path, token_file, monkeypatch):
        import youtube_uploader

        # Prepare a fake video file
        video_file = tmp_path / "video.mp4"
        video_file.write_bytes(b"fake_mp4_data")

        # Prepare tokens
        youtube_uploader._save_tokens({"refresh_token": "rt"})
        monkeypatch.setenv("YOUTUBE_CLIENT_ID", "cid")
        monkeypatch.setenv("YOUTUBE_CLIENT_SECRET", "csec")

        return str(video_file)

    def test_initiates_resumable_upload_session(self, tmp_path, token_file, monkeypatch):
        video_path = self._setup_upload(tmp_path, token_file, monkeypatch)
        import youtube_uploader

        # Mock refresh token call
        mock_refresh_resp = MagicMock()
        mock_refresh_resp.json.return_value = {"access_token": "at"}

        # Mock init session response
        mock_init_resp = MagicMock()
        mock_init_resp.headers = {"Location": "https://upload.googleapis.com/resume123"}

        # Mock upload PUT response
        mock_upload_resp = MagicMock()
        mock_upload_resp.json.return_value = {"id": "yt_vid_id"}

        with patch("youtube_uploader.httpx.post", side_effect=[mock_refresh_resp, mock_init_resp]), \
             patch("youtube_uploader.httpx.put", return_value=mock_upload_resp):
            result = youtube_uploader.upload_video(video_path, "My Film", "A great movie.", ["tag1"], privacy="private")

        assert result == {"id": "yt_vid_id"}

    def test_truncates_title_to_100_chars(self, tmp_path, token_file, monkeypatch):
        video_path = self._setup_upload(tmp_path, token_file, monkeypatch)
        import youtube_uploader

        long_title = "T" * 150

        mock_refresh_resp = MagicMock()
        mock_refresh_resp.json.return_value = {"access_token": "at"}
        mock_init_resp = MagicMock()
        mock_init_resp.headers = {"Location": "https://upload.googleapis.com/x"}
        mock_upload_resp = MagicMock()
        mock_upload_resp.json.return_value = {"id": "vid"}

        captured_json = {}

        def capture_post(url, **kwargs):
            if "googleapis.com/token" in url:
                return mock_refresh_resp
            captured_json.update(kwargs.get("json", {}))
            return mock_init_resp

        with patch("youtube_uploader.httpx.post", side_effect=capture_post), \
             patch("youtube_uploader.httpx.put", return_value=mock_upload_resp):
            youtube_uploader.upload_video(video_path, long_title, "desc", [])

        assert len(captured_json["snippet"]["title"]) == 100

    def test_sets_privacy_status(self, tmp_path, token_file, monkeypatch):
        video_path = self._setup_upload(tmp_path, token_file, monkeypatch)
        import youtube_uploader

        mock_refresh_resp = MagicMock()
        mock_refresh_resp.json.return_value = {"access_token": "at"}
        mock_init_resp = MagicMock()
        mock_init_resp.headers = {"Location": "https://upload.googleapis.com/x"}
        mock_upload_resp = MagicMock()
        mock_upload_resp.json.return_value = {"id": "vid"}

        captured_json = {}

        def capture_post(url, **kwargs):
            if "googleapis.com/token" in url:
                return mock_refresh_resp
            captured_json.update(kwargs.get("json", {}))
            return mock_init_resp

        with patch("youtube_uploader.httpx.post", side_effect=capture_post), \
             patch("youtube_uploader.httpx.put", return_value=mock_upload_resp):
            youtube_uploader.upload_video(video_path, "Title", "desc", [], privacy="public")

        assert captured_json["status"]["privacyStatus"] == "public"

    def test_sends_video_bytes_in_put(self, tmp_path, token_file, monkeypatch):
        video_path = self._setup_upload(tmp_path, token_file, monkeypatch)
        import youtube_uploader

        mock_refresh_resp = MagicMock()
        mock_refresh_resp.json.return_value = {"access_token": "at"}
        mock_init_resp = MagicMock()
        mock_init_resp.headers = {"Location": "https://upload.googleapis.com/x"}
        mock_upload_resp = MagicMock()
        mock_upload_resp.json.return_value = {"id": "vid"}

        with patch("youtube_uploader.httpx.post", side_effect=[mock_refresh_resp, mock_init_resp]), \
             patch("youtube_uploader.httpx.put", return_value=mock_upload_resp) as mock_put:
            youtube_uploader.upload_video(video_path, "Title", "desc", [])

        _, kwargs = mock_put.call_args
        assert kwargs["content"] == b"fake_mp4_data"

    def test_upload_url_comes_from_location_header(self, tmp_path, token_file, monkeypatch):
        video_path = self._setup_upload(tmp_path, token_file, monkeypatch)
        import youtube_uploader

        upload_url = "https://upload.googleapis.com/unique-session-uri"

        mock_refresh_resp = MagicMock()
        mock_refresh_resp.json.return_value = {"access_token": "at"}
        mock_init_resp = MagicMock()
        mock_init_resp.headers = {"Location": upload_url}
        mock_upload_resp = MagicMock()
        mock_upload_resp.json.return_value = {"id": "vid"}

        with patch("youtube_uploader.httpx.post", side_effect=[mock_refresh_resp, mock_init_resp]), \
             patch("youtube_uploader.httpx.put", return_value=mock_upload_resp) as mock_put:
            youtube_uploader.upload_video(video_path, "Title", "desc", [])

        args, _ = mock_put.call_args
        assert args[0] == upload_url


# ---------------------------------------------------------------------------
# get_oauth_url
# ---------------------------------------------------------------------------

class TestGetOAuthUrl:
    def test_returns_google_auth_url(self, monkeypatch):
        monkeypatch.setenv("YOUTUBE_CLIENT_ID", "my-client-id")
        import youtube_uploader

        url = youtube_uploader.get_oauth_url()
        assert url.startswith("https://accounts.google.com/o/oauth2/v2/auth")

    def test_includes_client_id_in_url(self, monkeypatch):
        monkeypatch.setenv("YOUTUBE_CLIENT_ID", "unique-cid-xyz")
        import youtube_uploader

        url = youtube_uploader.get_oauth_url()
        assert "unique-cid-xyz" in url

    def test_includes_youtube_upload_scope(self, monkeypatch):
        monkeypatch.setenv("YOUTUBE_CLIENT_ID", "cid")
        import youtube_uploader

        url = youtube_uploader.get_oauth_url()
        assert "youtube.upload" in url

    def test_includes_offline_access(self, monkeypatch):
        monkeypatch.setenv("YOUTUBE_CLIENT_ID", "cid")
        import youtube_uploader

        url = youtube_uploader.get_oauth_url()
        assert "offline" in url

    def test_includes_consent_prompt(self, monkeypatch):
        monkeypatch.setenv("YOUTUBE_CLIENT_ID", "cid")
        import youtube_uploader

        url = youtube_uploader.get_oauth_url()
        assert "consent" in url

    def test_default_redirect_uri(self, monkeypatch):
        monkeypatch.setenv("YOUTUBE_CLIENT_ID", "cid")
        monkeypatch.delenv("YOUTUBE_REDIRECT_URI", raising=False)
        import youtube_uploader

        url = youtube_uploader.get_oauth_url()
        assert "localhost%3A8000" in url or "localhost:8000" in url

    def test_custom_redirect_uri(self, monkeypatch):
        monkeypatch.setenv("YOUTUBE_CLIENT_ID", "cid")
        monkeypatch.setenv("YOUTUBE_REDIRECT_URI", "https://myapp.example.com/callback")
        import youtube_uploader

        url = youtube_uploader.get_oauth_url()
        assert "myapp.example.com" in url


# ---------------------------------------------------------------------------
# exchange_code
# ---------------------------------------------------------------------------

class TestExchangeCode:
    def test_posts_to_token_endpoint(self, token_file, monkeypatch):
        import youtube_uploader

        monkeypatch.setenv("YOUTUBE_CLIENT_ID", "cid")
        monkeypatch.setenv("YOUTUBE_CLIENT_SECRET", "csec")

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"access_token": "at", "refresh_token": "rt", "scope": "upload"}

        with patch("youtube_uploader.httpx.post", return_value=mock_resp) as mock_post:
            youtube_uploader.exchange_code("auth-code-123")

        args, kwargs = mock_post.call_args
        assert args[0] == "https://oauth2.googleapis.com/token"
        assert kwargs["data"]["code"] == "auth-code-123"
        assert kwargs["data"]["grant_type"] == "authorization_code"

    def test_returns_tokens_dict(self, token_file, monkeypatch):
        import youtube_uploader

        monkeypatch.setenv("YOUTUBE_CLIENT_ID", "cid")
        monkeypatch.setenv("YOUTUBE_CLIENT_SECRET", "csec")

        tokens = {"access_token": "at", "refresh_token": "rt", "scope": "upload"}
        mock_resp = MagicMock()
        mock_resp.json.return_value = tokens

        with patch("youtube_uploader.httpx.post", return_value=mock_resp):
            result = youtube_uploader.exchange_code("code")

        assert result == tokens

    def test_persists_tokens_to_file(self, token_file, monkeypatch):
        import youtube_uploader

        monkeypatch.setenv("YOUTUBE_CLIENT_ID", "cid")
        monkeypatch.setenv("YOUTUBE_CLIENT_SECRET", "csec")

        tokens = {"access_token": "at", "refresh_token": "rt"}
        mock_resp = MagicMock()
        mock_resp.json.return_value = tokens

        with patch("youtube_uploader.httpx.post", return_value=mock_resp):
            youtube_uploader.exchange_code("code")

        saved = youtube_uploader._load_tokens()
        assert saved["refresh_token"] == "rt"

    def test_uses_default_redirect_uri(self, token_file, monkeypatch):
        import youtube_uploader

        monkeypatch.setenv("YOUTUBE_CLIENT_ID", "cid")
        monkeypatch.setenv("YOUTUBE_CLIENT_SECRET", "csec")
        monkeypatch.delenv("YOUTUBE_REDIRECT_URI", raising=False)

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"access_token": "at"}

        with patch("youtube_uploader.httpx.post", return_value=mock_resp) as mock_post:
            youtube_uploader.exchange_code("code")

        _, kwargs = mock_post.call_args
        assert "localhost:8000" in kwargs["data"]["redirect_uri"]

    def test_http_error_propagates(self, token_file, monkeypatch):
        import youtube_uploader
        import httpx

        monkeypatch.setenv("YOUTUBE_CLIENT_ID", "cid")
        monkeypatch.setenv("YOUTUBE_CLIENT_SECRET", "csec")

        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "401", request=MagicMock(), response=MagicMock()
        )

        with patch("youtube_uploader.httpx.post", return_value=mock_resp):
            with pytest.raises(httpx.HTTPStatusError):
                youtube_uploader.exchange_code("bad-code")
