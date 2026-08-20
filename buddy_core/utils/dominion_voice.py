"""
dominion_voice.py — Unified Voice Engine for All Content Pipelines
==================================================================
Uses Piper TTS (free, open source, natural-sounding).
Drop-in replacement for edge_tts across all pipelines.

Usage:
    from utils.dominion_voice import generate_voice
    wav_path = generate_voice("Your text here", output_path="output.wav")

Converts to MP3 automatically if ffmpeg is available.
"""
import os, subprocess, tempfile
from pathlib import Path

PIPER_DIR = Path.home() / "piper"
PIPER_BIN = PIPER_DIR / "piper"
VOICE_MODEL = PIPER_DIR / "lessac.onnx"

# Set LD_LIBRARY_PATH for piper shared libs
os.environ["LD_LIBRARY_PATH"] = str(PIPER_DIR) + ":" + os.environ.get("LD_LIBRARY_PATH", "")


def generate_voice(text: str, output_path: str = None, format: str = "mp3") -> str:
    """
    Generate natural voice audio from text using Piper TTS.

    Args:
        text: Text to speak
        output_path: Where to save the file. Auto-generated if None.
        format: 'wav' or 'mp3' (mp3 requires ffmpeg)

    Returns:
        Path to generated audio file.
    """
    if not PIPER_BIN.exists():
        raise RuntimeError(f"Piper not installed at {PIPER_BIN}")
    if not VOICE_MODEL.exists():
        raise RuntimeError(f"Voice model not found at {VOICE_MODEL}")

    # Clean text for TTS
    text = text.strip()
    if not text:
        raise ValueError("Empty text")

    # Generate WAV first
    if output_path:
        wav_path = output_path if format == "wav" else output_path.rsplit(".", 1)[0] + ".wav"
    else:
        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        wav_path = tmp.name
        tmp.close()

    # Run piper
    proc = subprocess.run(
        [str(PIPER_BIN), "--model", str(VOICE_MODEL), "--output_file", wav_path],
        input=text.encode("utf-8"),
        capture_output=True,
        timeout=120,
        env={**os.environ, "LD_LIBRARY_PATH": str(PIPER_DIR)},
    )

    if proc.returncode != 0:
        raise RuntimeError(f"Piper failed: {proc.stderr.decode()[:300]}")

    if not Path(wav_path).exists() or Path(wav_path).stat().st_size < 100:
        raise RuntimeError("Piper produced no output")

    # Convert to MP3 if requested
    if format == "mp3":
        mp3_path = output_path or wav_path.replace(".wav", ".mp3")
        try:
            subprocess.run(
                ["ffmpeg", "-y", "-i", wav_path, "-codec:a", "libmp3lame",
                 "-b:a", "128k", "-ar", "22050", mp3_path],
                capture_output=True, timeout=30,
            )
            # Clean up wav if mp3 succeeded
            if Path(mp3_path).exists() and Path(mp3_path).stat().st_size > 100:
                Path(wav_path).unlink(missing_ok=True)
                return mp3_path
        except Exception:
            pass  # Fall back to wav
        return wav_path

    return wav_path


def get_audio_duration(path: str) -> float:
    """Get duration of audio file in seconds."""
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
             "-of", "csv=p=0", path],
            capture_output=True, text=True, timeout=10,
        )
        return float(result.stdout.strip())
    except Exception:
        return 0.0


def is_available() -> bool:
    """Check if Piper TTS is installed and ready."""
    return PIPER_BIN.exists() and VOICE_MODEL.exists()


# Quick test when run directly
if __name__ == "__main__":
    if not is_available():
        print("Piper TTS not installed")
        exit(1)
    test_text = "Dominion voice engine activated. Natural speech, zero robotic tone. This is what premium content sounds like."
    out = generate_voice(test_text, "/tmp/dominion_voice_test.mp3")
    dur = get_audio_duration(out)
    size = Path(out).stat().st_size / 1024
    print(f"Generated: {out} ({size:.0f}KB, {dur:.1f}s)")
    print("Piper TTS: ONLINE")
