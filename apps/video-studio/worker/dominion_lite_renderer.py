"""CPU-only Dominion portrait animation fallback.

This renderer is intentionally separate from the premium neural-clone path. It creates
an audio-reactive 2.5D preview with subtle camera movement and estimated mouth motion.
It does not claim phoneme-accurate neural lip sync or full expression synthesis.
"""

from __future__ import annotations

import argparse
import math
import subprocess
import tempfile
import wave
from pathlib import Path

import cv2
import numpy as np

FORMATS = {
    "vertical": (720, 1280),
    "landscape": (1280, 720),
    "square": (1080, 1080),
}


def run(command: list[str], *, timeout: int = 1800) -> None:
    """Run one subprocess and raise a bounded error on failure."""
    result = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout)[-3000:] or "command failed")


def decode_audio(audio: Path, wav: Path, sample_rate: int = 16_000) -> np.ndarray:
    """Decode supported audio into mono float PCM for deterministic analysis."""
    run([
        "ffmpeg", "-y", "-v", "error", "-i", str(audio), "-ac", "1",
        "-ar", str(sample_rate), "-c:a", "pcm_s16le", str(wav),
    ])
    with wave.open(str(wav), "rb") as source:
        samples = np.frombuffer(source.readframes(source.getnframes()), dtype=np.int16)
    return samples.astype(np.float32) / 32768.0


def energy_track(samples: np.ndarray, fps: int, sample_rate: int) -> np.ndarray:
    """Calculate a compressed and smoothed RMS speech-energy track."""
    hop = sample_rate / fps
    frame_count = max(1, int(math.ceil(len(samples) / hop)))
    values = np.zeros(frame_count, dtype=np.float32)
    for index in range(frame_count):
        start = int(index * hop)
        end = min(len(samples), int((index + 1) * hop))
        if end > start:
            values[index] = float(np.sqrt(np.mean(samples[start:end] ** 2) + 1e-9))
    reference = float(np.percentile(values, 95)) or 1.0
    values = np.clip(values / (reference * 1.05), 0.0, 1.0)
    return np.convolve(values, np.ones(5, dtype=np.float32) / 5.0, mode="same")


def detect_face(image: np.ndarray) -> tuple[int, int, int, int]:
    """Return the largest frontal face rectangle using OpenCV's bundled cascade."""
    cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    faces = cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(120, 120))
    if len(faces) == 0:
        raise RuntimeError("No frontal face was detected in the portrait")
    return tuple(int(value) for value in max(faces, key=lambda item: item[2] * item[3]))


def feather_mask(height: int, width: int, feather: int = 18) -> np.ndarray:
    """Create a soft rectangular blend mask."""
    mask = np.zeros((height, width), dtype=np.float32)
    margin = min(feather, max(1, height // 4), max(1, width // 4))
    cv2.rectangle(mask, (margin, margin), (width - margin - 1, height - margin - 1), 1.0, -1)
    mask = cv2.GaussianBlur(mask, (0, 0), max(margin / 2.0, 1.0))
    return np.clip(mask, 0.0, 1.0)[..., None]


def animate_mouth(image: np.ndarray, face: tuple[int, int, int, int], energy: float) -> np.ndarray:
    """Apply conservative speech-energy motion to the estimated mouth region."""
    x, y, width, height = face
    x1 = max(0, x + int(0.19 * width))
    x2 = min(image.shape[1], x + int(0.81 * width))
    y1 = max(0, y + int(0.57 * height))
    y2 = min(image.shape[0], y + int(0.84 * height))
    original = image[y1:y2, x1:x2].copy()
    if original.size == 0:
        return image

    region_height, region_width = original.shape[:2]
    stretch = 1.0 + 0.18 * float(energy)
    stretched_height = max(2, int(region_height * stretch))
    stretched = cv2.resize(original, (region_width, stretched_height), interpolation=cv2.INTER_CUBIC)
    start = max(0, (stretched_height - region_height) // 2)
    warped = stretched[start:start + region_height]
    if warped.shape[0] != region_height:
        warped = cv2.resize(warped, (region_width, region_height), interpolation=cv2.INTER_CUBIC)

    if energy > 0.16:
        shadow = warped.copy()
        center = (region_width // 2, int(region_height * 0.46))
        axes = (
            max(5, int(region_width * 0.13)),
            max(2, int(region_height * (0.015 + 0.055 * energy))),
        )
        cv2.ellipse(shadow, center, axes, 0, 0, 360, (18, 15, 15), -1, cv2.LINE_AA)
        alpha = min(0.38, 0.12 + 0.32 * energy)
        warped = cv2.addWeighted(shadow, alpha, warped, 1.0 - alpha, 0)

    mask = feather_mask(region_height, region_width)
    image[y1:y2, x1:x2] = (warped * mask + original * (1.0 - mask)).astype(np.uint8)
    return image


def compose(image: np.ndarray, elapsed: float, energy: float, output_format: str) -> np.ndarray:
    """Create a subtle moving camera treatment on the requested canvas."""
    canvas_width, canvas_height = FORMATS[output_format]
    image_height, image_width = image.shape[:2]
    scale = 1.0 + 0.012 * math.sin(elapsed * 0.9) + 0.008 * energy
    moved_width = max(1, int(image_width * scale))
    moved_height = max(1, int(image_height * scale))
    moved = cv2.resize(image, (moved_width, moved_height), interpolation=cv2.INTER_CUBIC)
    offset_x = int(4 * math.sin(elapsed * 0.63))
    offset_y = int(3 * math.sin(elapsed * 0.47 + 1.2))
    start_x = max(0, (moved_width - image_width) // 2 - offset_x)
    start_y = max(0, (moved_height - image_height) // 2 - offset_y)
    crop = moved[start_y:start_y + image_height, start_x:start_x + image_width]
    if crop.shape[:2] != (image_height, image_width):
        crop = cv2.resize(crop, (image_width, image_height), interpolation=cv2.INTER_CUBIC)

    background_scale = max(canvas_width / image_width, canvas_height / image_height)
    bg_width = int(image_width * background_scale) + 2
    bg_height = int(image_height * background_scale) + 2
    background = cv2.resize(crop, (bg_width, bg_height), interpolation=cv2.INTER_AREA)
    bg_x = (bg_width - canvas_width) // 2
    bg_y = (bg_height - canvas_height) // 2
    background = background[bg_y:bg_y + canvas_height, bg_x:bg_x + canvas_width]
    background = (cv2.GaussianBlur(background, (0, 0), 24) * 0.58).astype(np.uint8)

    foreground_scale = min(canvas_width / image_width, (canvas_height - 120) / image_height)
    fg_width = max(1, int(image_width * foreground_scale))
    fg_height = max(1, int(image_height * foreground_scale))
    foreground = cv2.resize(crop, (fg_width, fg_height), interpolation=cv2.INTER_LANCZOS4)
    origin_x = (canvas_width - fg_width) // 2
    origin_y = (canvas_height - fg_height) // 2
    background[origin_y:origin_y + fg_height, origin_x:origin_x + fg_width] = foreground
    return background


def srt_timestamp(seconds: float) -> str:
    milliseconds = int(round(seconds * 1000))
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, millis = divmod(remainder, 1000)
    return f"{hours:02}:{minutes:02}:{secs:02},{millis:03}"


def write_subtitles(script: str, duration: float, destination: Path) -> bool:
    words = script.split()
    chunks = [" ".join(words[index:index + 8]) for index in range(0, len(words), 8)]
    if not chunks:
        return False
    interval = duration / len(chunks)
    blocks: list[str] = []
    for index, chunk in enumerate(chunks, start=1):
        start = (index - 1) * interval
        end = duration if index == len(chunks) else index * interval
        blocks.append(f"{index}\n{srt_timestamp(start)} --> {srt_timestamp(end)}\n{chunk}\n")
    destination.write_text("\n".join(blocks), encoding="utf-8")
    return True


def render(portrait: Path, voice: Path, output: Path, script_file: Path | None, output_format: str, fps: int) -> None:
    image = cv2.imread(str(portrait))
    if image is None:
        raise RuntimeError("Portrait could not be decoded")
    face = detect_face(image)

    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="dominion-lite-") as temporary:
        workspace = Path(temporary)
        wav = workspace / "voice.wav"
        silent_video = workspace / "motion.mp4"
        muxed_video = workspace / "muxed.mp4"
        subtitle_file = workspace / "captions.srt"
        samples = decode_audio(voice, wav)
        sample_rate = 16_000
        duration = max(len(samples) / sample_rate, 0.1)
        energies = energy_track(samples, fps, sample_rate)
        width, height = FORMATS[output_format]
        writer = cv2.VideoWriter(str(silent_video), cv2.VideoWriter_fourcc(*"mp4v"), fps, (width, height))
        if not writer.isOpened():
            raise RuntimeError("OpenCV video writer could not start")
        frame_count = max(1, int(math.ceil(duration * fps)))
        try:
            for index in range(frame_count):
                elapsed = index / fps
                energy = float(energies[min(index, len(energies) - 1)])
                animated = animate_mouth(image.copy(), face, energy)
                writer.write(compose(animated, elapsed, energy, output_format))
        finally:
            writer.release()

        run([
            "ffmpeg", "-y", "-v", "error", "-i", str(silent_video), "-i", str(voice),
            "-map", "0:v:0", "-map", "1:a:0", "-c:v", "libx264", "-preset", "veryfast",
            "-crf", "21", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k",
            "-shortest", "-movflags", "+faststart", str(muxed_video),
        ])

        script = script_file.read_text(encoding="utf-8").strip() if script_file and script_file.exists() else ""
        if write_subtitles(script, duration, subtitle_file):
            escaped = str(subtitle_file).replace("'", "\\'")
            run([
                "ffmpeg", "-y", "-v", "error", "-i", str(muxed_video),
                "-vf", f"subtitles='{escaped}':force_style='Alignment=2,Fontsize=20,Outline=2,MarginV=45'",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-c:a", "copy",
                "-movflags", "+faststart", str(output),
            ])
        else:
            muxed_video.replace(output)

    if not output.exists() or output.stat().st_size == 0:
        raise RuntimeError("Dominion Lite did not produce an output")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render a CPU-only Dominion portrait preview")
    parser.add_argument("--portrait", required=True, type=Path)
    parser.add_argument("--voice", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--script-file", type=Path)
    parser.add_argument("--format", choices=sorted(FORMATS), default="vertical")
    parser.add_argument("--fps", type=int, default=24, choices=range(12, 31))
    return parser.parse_args()


if __name__ == "__main__":
    arguments = parse_args()
    render(
        arguments.portrait,
        arguments.voice,
        arguments.output,
        arguments.script_file,
        arguments.format,
        arguments.fps,
    )
