from __future__ import annotations

import subprocess
from pathlib import Path

from .state import EXPORT_DIR, db, get_project, latest_asset, update_job, utc_now


def dimensions(output_format: str) -> tuple[int, int]:
    if output_format == "landscape":
        return 1280, 720
    if output_format == "square":
        return 1080, 1080
    return 720, 1280


def media_duration(path: Path) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return max(float(result.stdout.strip()), 1.0)


def srt_timestamp(seconds: float) -> str:
    milliseconds = int(round(seconds * 1000))
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, millis = divmod(remainder, 1000)
    return f"{hours:02}:{minutes:02}:{secs:02},{millis:03}"


def make_srt(script: str, duration: float, destination: Path) -> None:
    words = script.split()
    chunks = [" ".join(words[index:index + 8]) for index in range(0, len(words), 8)]
    if not chunks:
        destination.write_text("", encoding="utf-8")
        return
    interval = duration / len(chunks)
    blocks = []
    for index, chunk in enumerate(chunks, start=1):
        start = (index - 1) * interval
        end = duration if index == len(chunks) else index * interval
        blocks.append(f"{index}\n{srt_timestamp(start)} --> {srt_timestamp(end)}\n{chunk}\n")
    destination.write_text("\n".join(blocks), encoding="utf-8")


def render_proof_job(job_id: str) -> None:
    try:
        update_job(job_id, status="running", progress=5)
        with db() as connection:
            job = connection.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
            if job is None:
                return
            project = get_project(connection, job["project_id"])
            portrait = latest_asset(connection, project["id"], "portrait")
            voice = latest_asset(connection, project["id"], "voice")
            if portrait is None or voice is None:
                raise RuntimeError("A portrait and voice recording are required")

        portrait_path = Path(portrait["stored_path"])
        voice_path = Path(voice["stored_path"])
        output_path = EXPORT_DIR / f"{job_id}.mp4"
        subtitle_path = EXPORT_DIR / f"{job_id}.srt"
        duration = media_duration(voice_path)
        make_srt(project["script"], duration, subtitle_path)
        width, height = dimensions(project["output_format"])
        scale = f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},format=yuv420p"
        captions = f"{scale},subtitles={subtitle_path}:force_style='Alignment=2,Fontsize=22,Outline=2,MarginV=45'"
        base = [
            "ffmpeg", "-y", "-loop", "1", "-i", str(portrait_path), "-i", str(voice_path),
            "-c:v", "libx264", "-preset", "veryfast", "-tune", "stillimage",
            "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart",
        ]
        update_job(job_id, status="running", progress=35)
        result = subprocess.run(base + ["-vf", captions, "-r", "30", str(output_path)], capture_output=True, text=True, timeout=900)
        if result.returncode != 0:
            result = subprocess.run(base + ["-vf", scale, "-r", "30", str(output_path)], capture_output=True, text=True, timeout=900)
        if result.returncode != 0 or not output_path.exists():
            raise RuntimeError(result.stderr[-2000:] or "FFmpeg rendering failed")
        update_job(job_id, status="completed", progress=100, output_path=str(output_path))
        with db() as connection:
            connection.execute("UPDATE projects SET status = ?, updated_at = ? WHERE id = ?", ("review_ready", utc_now(), project["id"]))
    except Exception as exc:  # noqa: BLE001
        update_job(job_id, status="failed", progress=100, error=str(exc))
