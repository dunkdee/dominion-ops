import os
import tempfile

os.environ["VIDEO_STUDIO_DATA_DIR"] = tempfile.mkdtemp(prefix="video-studio-test-")
os.environ["VIDEO_STUDIO_WORKER_TOKEN"] = "test-worker-token"
