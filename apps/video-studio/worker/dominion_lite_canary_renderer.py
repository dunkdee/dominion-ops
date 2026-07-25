"""Synthetic-only adapter used by governed VM preflight workflows.

This module bypasses face detection only for generated test imagery. The production
Dominion Lite command does not use this adapter.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import dominion_lite_renderer as renderer


def synthetic_face_box(image):
    """Return a deterministic central face-shaped region for synthetic test pixels."""
    return (
        int(image.shape[1] * 0.18),
        int(image.shape[0] * 0.12),
        int(image.shape[1] * 0.64),
        int(image.shape[0] * 0.70),
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Dominion Lite synthetic canary")
    parser.add_argument("--portrait", required=True, type=Path)
    parser.add_argument("--voice", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--script-file", required=True, type=Path)
    parser.add_argument("--format", choices=sorted(renderer.FORMATS), default="vertical")
    parser.add_argument("--fps", type=int, default=24)
    return parser.parse_args()


if __name__ == "__main__":
    arguments = parse_args()
    renderer.detect_face = synthetic_face_box
    renderer.render(
        arguments.portrait,
        arguments.voice,
        arguments.output,
        arguments.script_file,
        arguments.format,
        arguments.fps,
    )
