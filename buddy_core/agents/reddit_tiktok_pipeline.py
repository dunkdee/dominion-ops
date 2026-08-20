"""
reddit_tiktok_pipeline.py — Faceless Reddit Story TikTok Generator
===================================================================
Generates viral faceless TikTok videos using:
  - Top Reddit stories (from free JSON API)
  - AI voiceover (edge_tts)
  - Text-on-screen with word highlighting
  - Background gameplay/satisfying footage (stock or generated)
  - 60-90 second runtime (qualifies for Creator Rewards)

Runs 4x daily via cron. Replaces old Dominion-branded pipeline.

Usage:
  python reddit_tiktok_pipeline.py --slot 0
  python reddit_tiktok_pipeline.py --render-only
"""
import os, sys, re, json, subprocess, time, textwrap, tempfile, random, math
from datetime import datetime, timedelta
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    print("pip install Pillow"); sys.exit(1)

import sys as _sys; _sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent))
# Voice engine: Piper TTS (natural, free, open source)
try:
    from utils.dominion_voice import generate_voice as piper_voice, get_audio_duration as piper_duration, is_available as piper_ok
    PIPER_AVAILABLE = piper_ok()
except ImportError:
    PIPER_AVAILABLE = False
    piper_voice = None

try:
    import requests
except ImportError:
    requests = None

HOME      = Path.home()
VIDEO_DIR = HOME / "tiktok_videos"
AUDIO_DIR = HOME / "tiktok_audio"
LOG_FILE  = HOME / "logs" / "tiktok_pipeline.log"
CACHE_DIR = HOME / "reddit_cache"

for d in [VIDEO_DIR, AUDIO_DIR, CACHE_DIR]:
    d.mkdir(parents=True, exist_ok=True)
LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

# ── Config ────────────────────────────────────────────────────
# Subreddits that generate viral content
SUBREDDITS = [
    "AmItheAsshole", "tifu", "MaliciousCompliance",
    "ProRevenge", "pettyrevenge", "TrueOffMyChest",
    "entitledparents", "relationship_advice", "confession",
    "AskReddit", "TwoSentenceHorror", "nosleep",
]

# TTS voice — natural sounding male
TTS_VOICE = "en-US-ChristopherNeural"
TTS_RATE = "+10%"  # slightly faster for engagement

# Video settings
WIDTH, HEIGHT = 1080, 1920  # 9:16 vertical
FPS = 30
TARGET_DURATION = 75  # seconds — sweet spot for Creator Rewards (>60s required)

# Colors
BG_COLOR     = (15, 15, 20)
TEXT_COLOR    = (240, 240, 245)
HIGHLIGHT     = (255, 90, 60)   # orange-red for current word
ACCENT       = (100, 200, 255)  # blue accent
DIM          = (120, 120, 140)
REDDIT_ORANGE = (255, 69, 0)

# Hashtags for discoverability
HASHTAGS = [
    "#reddit", "#redditstories", "#askreddit", "#storytime",
    "#fyp", "#viral", "#foryou", "#story", "#drama",
]


def _log(msg):
    ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")


# ── Reddit Story Fetcher ──────────────────────────────────────

def fetch_reddit_stories(subreddit: str = None, limit: int = 10) -> list:
    """Generate viral Reddit-style stories using Gemini AI."""
    sub = subreddit or random.choice(SUBREDDITS)

    GEMINI_KEY = os.getenv("GEMINI_API_KEY", "")
    if not GEMINI_KEY or not requests:
        return _fallback_stories()

    prompt = (
        f"Write a single compelling Reddit story as if posted to r/{sub}. "
        "Make it dramatic, relatable, and satisfying to read. "
        "Include a clear conflict and resolution. "
        "200-400 words, first person, conversational tone. "
        "Format: first line is the title (no quotes), blank line, then story body. "
        "No markdown. Make it viral-worthy."
    )

    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_KEY}"
        r = requests.post(url, json={
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"maxOutputTokens": 1024, "temperature": 0.9}
        }, timeout=30)
        r.raise_for_status()
        text = r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()

        lines = text.split("\n", 1)
        title = lines[0].strip()
        body = lines[1].strip() if len(lines) > 1 else text

        _log(f"Gemini generated story: {title[:60]}...")
        return [{
            "title": title,
            "body": body,
            "subreddit": sub,
            "score": random.randint(5000, 30000),
            "awards": random.randint(2, 15),
        }]
    except Exception as e:
        _log(f"Gemini story error: {e}")
        return _fallback_stories()


def _fallback_stories():
    """Pre-written viral-format stories if Reddit is unavailable."""
    return [{
        "title": "My neighbor tried to claim my backyard as their property",
        "body": (
            "So I've been living in my house for about 7 years now. Last month my new "
            "neighbor moved in and immediately started moving the fence line. I noticed "
            "one morning that my yard was about 3 feet smaller. I checked the property "
            "survey and sure enough they had moved the fence onto my land. When I "
            "confronted them they said the previous owner had agreed to it. I asked for "
            "proof and they couldn't provide any. I told them I'd give them 48 hours to "
            "move it back. They laughed in my face. So I called the county surveyor, got "
            "an official survey done, filed a complaint, and had the sheriff deliver a "
            "notice. The fence was back in the right place by the weekend. They haven't "
            "spoken to me since and honestly that's a bonus."
        ),
        "subreddit": "pettyrevenge",
        "score": 15000,
        "awards": 5,
    }]


def pick_story(slot: int = 0) -> dict:
    """Pick a story, avoiding repeats."""
    today = datetime.utcnow().strftime("%Y-%m-%d")
    used_file = CACHE_DIR / f"used_{today}.json"
    used = []
    if used_file.exists():
        try:
            used = json.loads(used_file.read_text())
        except Exception:
            pass

    # Rotate subreddits by slot
    sub = SUBREDDITS[slot % len(SUBREDDITS)]
    stories = fetch_reddit_stories(sub)

    if not stories:
        sub = random.choice(SUBREDDITS)
        stories = fetch_reddit_stories(sub)

    if not stories:
        stories = _fallback_stories()

    # Pick first unused story
    for story in stories:
        if story["title"] not in used:
            used.append(story["title"])
            used_file.write_text(json.dumps(used))
            return story

    # All used, just pick the top one
    return stories[0]


def trim_story(text: str, max_words: int = 280) -> str:
    """Trim story to fit target duration (~150 words/min for TTS)."""
    words = text.split()
    if len(words) <= max_words:
        return text
    # Find a good sentence break near the limit
    trimmed = " ".join(words[:max_words])
    # Try to end at a sentence
    last_period = trimmed.rfind(".")
    if last_period > len(trimmed) * 0.7:
        trimmed = trimmed[:last_period + 1]
    return trimmed


# ── TTS Audio Generation ─────────────────────────────────────

def generate_audio(text: str, slot: int = 0) -> str:
    """Generate voiceover audio using Piper TTS. Returns path to MP3."""
    today = datetime.utcnow().strftime("%Y-%m-%d")
    audio_path = str(AUDIO_DIR / f"voice_{today}_slot{slot}.mp3")

    if Path(audio_path).exists():
        return audio_path

    if not PIPER_AVAILABLE:
        _log("Piper TTS not available — generating silent video")
        return ""

    _log(f"Generating Piper TTS ({len(text.split())} words)...")

    try:
        result = piper_voice(text, audio_path, format="mp3")
        size_kb = Path(result).stat().st_size / 1024
        _log(f"Audio generated (Piper): {result} ({size_kb:.0f}KB)")
        return result
    except Exception as e:
        _log(f"Piper TTS error: {e}")
        return ""


def get_audio_duration(audio_path: str) -> float:
    """Get duration of audio file in seconds."""
    if PIPER_AVAILABLE:
        dur = piper_duration(audio_path)
        if dur > 0:
            return dur
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
             "-of", "csv=p=0", audio_path],
            capture_output=True, text=True, timeout=10
        )
        return float(result.stdout.strip())
    except Exception:
        return TARGET_DURATION


# ── Frame Renderer ────────────────────────────────────────────

def render_frame(title: str, body_text: str, subreddit: str,
                 current_word_index: int = -1, total_words: int = 0,
                 progress: float = 0.0) -> Image.Image:
    """Render a single 1080x1920 frame with Reddit story styling."""
    img = Image.new("RGB", (WIDTH, HEIGHT), BG_COLOR)
    draw = ImageDraw.Draw(img)

    # Fonts
    font_dir = "/usr/share/fonts/truetype/freefont"
    try:
        f_sub    = ImageFont.truetype(font_dir + "/FreeSansBold.ttf", 32)
        f_title  = ImageFont.truetype(font_dir + "/FreeSansBold.ttf", 44)
        f_body   = ImageFont.truetype(font_dir + "/FreeSans.ttf", 40)
        f_small  = ImageFont.truetype(font_dir + "/FreeSans.ttf", 28)
    except Exception:
        f_sub = f_title = f_body = f_small = ImageFont.load_default()

    # ── Top bar: subreddit ──
    draw.rectangle([(0, 0), (WIDTH, 80)], fill=(30, 30, 40))
    # Reddit icon (orange circle)
    draw.ellipse([30, 18, 74, 62], fill=REDDIT_ORANGE)
    draw.text((88, 22), f"r/{subreddit}", fill=REDDIT_ORANGE, font=f_sub)

    # Upvote indicator
    draw.text((WIDTH - 200, 22), "Hot", fill=HIGHLIGHT, font=f_sub)

    # ── Title section ──
    draw.rectangle([(40, 100), (WIDTH - 40, 102)], fill=(40, 40, 55))
    wrapped_title = textwrap.fill(title, width=28)
    draw.text((60, 120), wrapped_title, fill=TEXT_COLOR, font=f_title)

    # Calculate title height
    title_lines = wrapped_title.count("\n") + 1
    title_bottom = 120 + title_lines * 52 + 20

    draw.rectangle([(40, title_bottom), (WIDTH - 40, title_bottom + 2)], fill=(40, 40, 55))

    # ── Body text with word highlighting ──
    words = body_text.split()
    y = title_bottom + 30
    x = 60
    line_height = 52
    max_x = WIDTH - 60

    word_idx = 0
    for word in words:
        # Measure word
        bbox = draw.textbbox((0, 0), word + " ", font=f_body)
        word_width = bbox[2] - bbox[0]

        # Wrap if needed
        if x + word_width > max_x:
            x = 60
            y += line_height

        if y > HEIGHT - 250:
            break

        # Color: highlight current word being spoken
        if word_idx == current_word_index:
            # Draw highlight background
            draw.rectangle([(x - 4, y - 2), (x + word_width - 4, y + 44)],
                          fill=(255, 90, 60, 40))
            color = HIGHLIGHT
        elif word_idx < current_word_index:
            color = TEXT_COLOR  # already spoken
        else:
            color = DIM  # not yet spoken

        draw.text((x, y), word, fill=color, font=f_body)
        x += word_width
        word_idx += 1

    # ── Progress bar at bottom ──
    bar_y = HEIGHT - 120
    draw.rectangle([(40, bar_y), (WIDTH - 40, bar_y + 6)], fill=(40, 40, 55))
    bar_width = int((WIDTH - 80) * progress)
    draw.rectangle([(40, bar_y), (40 + bar_width, bar_y + 6)], fill=REDDIT_ORANGE)

    # ── Bottom CTA ──
    cta = "Follow for more stories"
    bbox = draw.textbbox((0, 0), cta, font=f_small)
    cw = bbox[2] - bbox[0]
    draw.text(((WIDTH - cw) // 2, HEIGHT - 80), cta, fill=DIM, font=f_small)

    return img


# ── Video Assembly ────────────────────────────────────────────

def make_video(story: dict, slot: int = 0) -> str:
    """Generate the full video: frames + audio → MP4."""
    today = datetime.utcnow().strftime("%Y-%m-%d")
    out_path = str(VIDEO_DIR / f"tiktok_{today}_slot{slot}.mp4")

    if Path(out_path).exists():
        _log(f"Video already exists: {out_path}")
        return out_path

    title = story["title"]
    body = trim_story(story["body"])
    subreddit = story["subreddit"]

    # Full narration text (title + body)
    narration = f"{title}. {body}"

    # Generate audio
    audio_path = generate_audio(narration, slot)
    if audio_path and Path(audio_path).exists():
        duration = get_audio_duration(audio_path)
    else:
        duration = TARGET_DURATION

    # Ensure minimum 65 seconds
    duration = max(duration, 65)

    # Calculate word timing
    words = body.split()
    total_words = len(words)
    # Account for title reading time (~3 seconds)
    title_duration = 3.0
    body_duration = duration - title_duration
    words_per_sec = total_words / body_duration if body_duration > 0 else 2.5

    total_frames = int(duration * FPS)
    _log(f"Rendering {total_frames} frames ({duration:.1f}s, {total_words} words)...")

    # Render frames to temp directory
    with tempfile.TemporaryDirectory() as tmpdir:
        for frame_num in range(total_frames):
            t = frame_num / FPS
            progress = t / duration

            # Calculate which word is being spoken
            if t < title_duration:
                current_word = -1  # still reading title
            else:
                body_t = t - title_duration
                current_word = int(body_t * words_per_sec)
                current_word = min(current_word, total_words - 1)

            # Only render every 3rd frame (10fps effective, interpolate later)
            if frame_num % 3 != 0:
                continue

            frame = render_frame(title, body, subreddit,
                               current_word, total_words, progress)
            frame.save(f"{tmpdir}/frame_{frame_num:06d}.png", "PNG")

        # Fill gaps (copy every 3rd frame to adjacent slots)
        import shutil
        for frame_num in range(total_frames):
            src = frame_num - (frame_num % 3)
            src_path = f"{tmpdir}/frame_{src:06d}.png"
            dst_path = f"{tmpdir}/frame_{frame_num:06d}.png"
            if not Path(dst_path).exists() and Path(src_path).exists():
                shutil.copy2(src_path, dst_path)

        # Assemble with ffmpeg
        cmd = [
            "ffmpeg", "-y",
            "-framerate", str(FPS),
            "-i", f"{tmpdir}/frame_%06d.png",
        ]

        if audio_path and Path(audio_path).exists():
            cmd.extend(["-i", audio_path, "-c:a", "aac", "-b:a", "128k"])
        else:
            cmd.extend(["-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
                        "-c:a", "aac", "-shortest"])

        cmd.extend([
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "23",
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            "-t", str(duration),
            out_path,
        ])

        _log("Encoding video...")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)

        if result.returncode != 0:
            _log(f"ffmpeg error: {result.stderr[-500:]}")
            raise RuntimeError(f"ffmpeg failed: {result.returncode}")

    size_mb = Path(out_path).stat().st_size / (1024 * 1024)
    _log(f"Video generated: {out_path} ({size_mb:.1f}MB, {duration:.0f}s)")
    return out_path


# ── TikTok Upload (API or staged) ────────────────────────────

def upload_or_stage(video_path: str, story: dict):
    """Try TikTok API upload, fall back to staging for manual upload."""
    caption = f"{story['title']}\n\n{' '.join(random.sample(HASHTAGS, 6))}"

    # Stage the caption for manual upload or API
    today = datetime.utcnow().strftime("%Y%m%d")
    stage_file = HOME / "logs" / f"tiktok_staged_{today}.txt"
    with open(stage_file, "w") as f:
        f.write(f"VIDEO: {video_path}\n")
        f.write(f"CAPTION:\n{caption}\n")
        f.write(f"SUBREDDIT: r/{story['subreddit']}\n")
        f.write(f"SCORE: {story['score']}\n")

    _log(f"TikTok: caption staged at {stage_file}")
    _log(f"TikTok: video ready at {video_path}")

    # TODO: Wire TikTok Content Posting API here once app is approved
    # https://developers.tiktok.com/doc/content-posting-api-get-started
    tiktok_client_key = os.getenv("TIKTOK_CLIENT_KEY", "")
    if tiktok_client_key:
        _log(f"TikTok API: client key found ({tiktok_client_key[:8]}...) — API upload not yet wired")


# ── Main ──────────────────────────────────────────────────────

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--slot", type=int, default=0)
    parser.add_argument("--render-only", action="store_true")
    parser.add_argument("--subreddit", type=str, default=None)
    args = parser.parse_args()

    _log(f"Reddit TikTok pipeline: slot={args.slot}")

    # Pick a story
    story = pick_story(args.slot)
    _log(f"Story: r/{story['subreddit']} | {story['title'][:60]}... | score={story['score']}")

    # Generate video
    video_path = make_video(story, args.slot)

    if not args.render_only:
        upload_or_stage(video_path, story)

    _log("Done.")


if __name__ == "__main__":
    main()
