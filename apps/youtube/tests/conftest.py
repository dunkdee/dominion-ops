"""
Shared pytest fixtures and environment setup for apps/youtube tests.

All env vars required by module-level code (e.g. anthropic.Anthropic(api_key=...))
are set here before any test module is imported.
"""
import os
import sys
import pytest

# ---------------------------------------------------------------------------
# Set required env vars before any app module is imported at collection time.
# script_generator.py instantiates anthropic.Anthropic at module level, so
# ANTHROPIC_API_KEY must be present before that module is first imported.
# ---------------------------------------------------------------------------
os.environ.setdefault("ANTHROPIC_API_KEY", "test-anthropic-key")
os.environ.setdefault("YOUTUBE_CLIENT_ID", "test-yt-client-id")
os.environ.setdefault("YOUTUBE_CLIENT_SECRET", "test-yt-client-secret")
os.environ.setdefault("HIGGINS_API_KEY", "test-higgins-key")

# Make the app source importable without installing it
APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)


@pytest.fixture
def token_file(tmp_path, monkeypatch):
    """Redirect the TOKEN_FILE path to a temp directory for isolation."""
    import youtube_uploader

    token_path = str(tmp_path / "youtube_tokens.json")
    monkeypatch.setattr(youtube_uploader, "TOKEN_FILE", token_path)
    return token_path