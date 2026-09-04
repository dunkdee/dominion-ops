import os
import shutil
import sys
import tempfile
from pathlib import Path

import pytest

# The `app` package lives one level up. Mirrors the same path insertion the
# radah-traffic-engine suite already uses, so this collects from the
# repository root as well as from its own directory.
APP_ROOT = Path(__file__).resolve().parents[1]

def _claim_app_package(app_root):
    """Ensure `app` resolves to THIS subproject.

    Two deployable subprojects in this repository each provide a top-level
    `app` package (OPS/radah-traffic-engine and apps/video-studio). Under a
    repository-wide pytest run whichever imports first wins, and the other
    collects against the wrong package. Each suite claims its own `app` before
    its tests import, which makes repo-wide collection order-independent
    without renaming either deployed package.
    """
    import sys
    entry = str(app_root)
    if entry in sys.path:
        sys.path.remove(entry)
    sys.path.insert(0, entry)
    existing = sys.modules.get("app")
    owned = getattr(existing, "__file__", "") or ""
    if existing is not None and not owned.startswith(entry):
        for name in [n for n in sys.modules if n == "app" or n.startswith("app.")]:
            del sys.modules[name]


_claim_app_package(APP_ROOT)

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
