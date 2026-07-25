import os
import shutil
import tempfile

import pytest

os.environ["VIDEO_STUDIO_DATA_DIR"] = tempfile.mkdtemp(prefix="video-studio-test-")
os.environ["VIDEO_STUDIO_WORKER_TOKEN"] = "test-worker-token"

from app.state import ASSET_DIR, EXPORT_DIR, db, init_storage  # noqa: E402


@pytest.fixture(autouse=True)
def reset_video_studio_state() -> None:
    init_storage()
    with db() as connection:
        connection.execute("DELETE FROM project_revocations")
        connection.execute("DELETE FROM approvals")
        connection.execute("DELETE FROM jobs")
        connection.execute("DELETE FROM assets")
        connection.execute("DELETE FROM projects")
        connection.execute("DELETE FROM consents")
    for directory in (ASSET_DIR, EXPORT_DIR):
        shutil.rmtree(directory, ignore_errors=True)
        directory.mkdir(parents=True, exist_ok=True)
