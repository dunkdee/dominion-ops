"""Generic detachable worker for Dominion Video Studio.

The worker does not bundle a specific model or model weights. A governed JSON engine spec
selects a legally approved renderer and declares its command, required assets, supported
formats, timeout, and license record. The command is always executed as an argument vector,
never through a shell.
"""

from __future__ import annotations

import json
import mimetypes
import os
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

from engine_adapter import load_engine_spec

BASE_URL = os.environ["VIDEO_STUDIO_URL"].rstrip("/")
TOKEN = os.environ["VIDEO_STUDIO_WORKER_TOKEN"]
ENGINE = load_engine_spec()
WORKER_ID = os.getenv("VIDEO_STUDIO_WORKER_ID", f"{ENGINE.engine_id}-worker-1")
POLL_SECONDS = max(float(os.getenv("VIDEO_STUDIO_POLL_SECONDS", "5")), 1.0)


def worker_headers(*, lease: str | None = None, content_type: str | None = None) -> dict[str, str]:
    headers = {"X-Worker-Token": TOKEN, "X-Worker-ID": WORKER_ID}
    if lease:
        headers["X-Worker-Lease"] = lease
    if content_type:
        headers["Content-Type"] = content_type
    return headers


def request_json(
    path: str,
    *,
    method: str = "GET",
    body: dict | None = None,
    lease: str | None = None,
) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(
        f"{BASE_URL}{path}",
        data=data,
        method=method,
        headers=worker_headers(lease=lease, content_type="application/json"),
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read().decode())


def download(path: str, destination: Path, *, lease: str) -> None:
    request = urllib.request.Request(
        f"{BASE_URL}{path}",
        headers=worker_headers(lease=lease),
    )
    with urllib.request.urlopen(request, timeout=300) as response, destination.open("wb") as output:
        while chunk := response.read(1024 * 1024):
            output.write(chunk)


def multipart_upload(path: str, file_path: Path, *, lease: str) -> dict:
    boundary = "----DominionWorkerBoundary"
    content_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
    prefix = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{file_path.name}"\r\n'
        f"Content-Type: {content_type}\r\n\r\n"
    ).encode()
    suffix = f"\r\n--{boundary}--\r\n".encode()
    data = prefix + file_path.read_bytes() + suffix
    headers = worker_headers(lease=lease, content_type=f"multipart/form-data; boundary={boundary}")
    headers["Content-Length"] = str(len(data))
    request = urllib.request.Request(
        f"{BASE_URL}{path}",
        data=data,
        method="POST",
        headers=headers,
    )
    with urllib.request.urlopen(request, timeout=600) as response:
        return json.loads(response.read().decode())


def fail(job_id: str, lease: str, message: str) -> None:
    try:
        request_json(
            f"/api/workers/jobs/{job_id}/complete",
            method="POST",
            body={"status": "failed", "error": message[-2000:]},
            lease=lease,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"Could not report failure for {job_id}: {exc}", flush=True)


def process(claim: dict) -> None:
    job = claim["job"]
    project = claim["project"]
    lease = claim.get("lease_token")
    if not lease:
        raise RuntimeError("Claim response did not include a worker lease")
    job_id = job["id"]
    with tempfile.TemporaryDirectory(prefix=f"dominion-{job_id}-") as temporary:
        workspace = Path(temporary)
        paths: dict[str, Path] = {}
        for asset in claim["assets"]:
            extension = Path(asset["original_name"]).suffix
            destination = workspace / f"{asset['kind']}{extension}"
            download(asset["download_url"], destination, lease=lease)
            paths[asset["kind"]] = destination
        script_file = workspace / "script.txt"
        script_file.write_text(project["script"], encoding="utf-8")
        output = workspace / "output.mp4"
        values = {
            "portrait": str(paths.get("portrait", "")),
            "voice": str(paths.get("voice", "")),
            "source_video": str(paths.get("source_video", "")),
            "script_file": str(script_file),
            "output_format": str(project.get("output_format", "vertical")),
            "output": str(output),
        }
        command = ENGINE.build_command(values)
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=ENGINE.timeout_seconds,
            check=False,
        )
        if result.returncode != 0 or not output.exists():
            raise RuntimeError(result.stderr[-2000:] or "Clone command failed without an output")
        response = multipart_upload(f"/api/workers/jobs/{job_id}/output", output, lease=lease)
        print(json.dumps(response), flush=True)


def main() -> None:
    print(
        json.dumps(
            {
                "event": "worker_connected",
                "worker_id": WORKER_ID,
                "base_url": BASE_URL,
                "engine_id": ENGINE.engine_id,
                "engine_version": ENGINE.engine_version,
                "license_status": ENGINE.license_status,
                "supported_formats": sorted(ENGINE.supported_formats),
            }
        ),
        flush=True,
    )
    while True:
        try:
            claim = request_json("/api/workers/claim", method="POST", body={"worker_id": WORKER_ID})
            if claim.get("job"):
                lease = claim.get("lease_token", "")
                try:
                    process(claim)
                except Exception as exc:  # noqa: BLE001
                    fail(claim["job"]["id"], lease, str(exc))
            else:
                time.sleep(POLL_SECONDS)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            print(f"Worker connection error: {exc}", flush=True)
            time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
