from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np

MODULE_PATH = Path(__file__).resolve().parents[1] / "worker" / "dominion_lite_renderer.py"
SPEC = importlib.util.spec_from_file_location("dominion_lite_renderer", MODULE_PATH)
assert SPEC and SPEC.loader
renderer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(renderer)


def test_energy_track_is_bounded_and_frame_aligned() -> None:
    sample_rate = 16_000
    fps = 20
    seconds = 2
    time = np.arange(sample_rate * seconds, dtype=np.float32) / sample_rate
    samples = (0.25 * np.sin(2 * np.pi * 220 * time)).astype(np.float32)

    track = renderer.energy_track(samples, fps, sample_rate)

    assert len(track) == fps * seconds
    assert float(track.min()) >= 0.0
    assert float(track.max()) <= 1.0
    assert float(track.max()) > 0.5


def test_animate_mouth_changes_only_a_local_region() -> None:
    image = np.zeros((240, 240, 3), dtype=np.uint8)
    for row in range(image.shape[0]):
        image[row, :, :] = row
    face = (40, 30, 160, 180)

    animated = renderer.animate_mouth(image.copy(), face, 0.85)

    assert animated.shape == image.shape
    assert np.any(animated != image)
    assert np.array_equal(animated[:80], image[:80])


def test_compose_respects_requested_output_format() -> None:
    image = np.full((320, 240, 3), 128, dtype=np.uint8)

    vertical = renderer.compose(image, elapsed=0.5, energy=0.4, output_format="vertical")
    square = renderer.compose(image, elapsed=0.5, energy=0.4, output_format="square")
    landscape = renderer.compose(image, elapsed=0.5, energy=0.4, output_format="landscape")

    assert vertical.shape == (1280, 720, 3)
    assert square.shape == (1080, 1080, 3)
    assert landscape.shape == (720, 1280, 3)


def test_write_subtitles_creates_timed_blocks(tmp_path: Path) -> None:
    destination = tmp_path / "captions.srt"

    written = renderer.write_subtitles(
        "one two three four five six seven eight nine ten",
        duration=2.0,
        destination=destination,
    )

    content = destination.read_text(encoding="utf-8")
    assert written is True
    assert "00:00:00,000 --> 00:00:01,000" in content
    assert "00:00:01,000 --> 00:00:02,000" in content
    assert "one two three four five six seven eight" in content
