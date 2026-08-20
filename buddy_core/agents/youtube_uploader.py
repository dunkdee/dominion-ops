#!/usr/bin/env python3
"""
youtube_uploader.py — Auto-upload faceless videos to YouTube
Uses YouTube Data API v3 with OAuth2 (service account or user auth).
Picks up videos from ~/youtube_videos/ and uploads with SEO metadata.

First run: opens browser for OAuth consent (one-time).
After that: uses saved token, fully automated.
"""
import os
import json
import logging
import glob
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(Path.home() / ".env")
load_dotenv(Path.home() / "buddy_core/.env")

try:
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    HAS_GOOGLE = True
except ImportError:
    HAS_GOOGLE = False

HOME = Path.home()
VIDEO_DIR = HOME / "youtube_videos"
UPLOADED_LOG = HOME / "youtube_videos" / "uploaded.json"
TOKEN_FILE = HOME / "buddy_core" / "youtube_token.json"
CREDENTIALS_FILE = HOME / "buddy_core" / "youtube_credentials.json"

SCOPES = ["https://www.googleapis.com/auth/youtube.upload",
          "https://www.googleapis.com/auth/youtube"]

LOG_DIR = HOME / "logs"
LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [YT-UPLOAD] %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "youtube_upload.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("yt_upload")


def get_youtube_service():
    """Authenticate and return YouTube API service."""
    if not HAS_GOOGLE:
        log.error("google-api-python-client not installed. Run: pip install google-api-python-client google-auth-oauthlib")
        return None

    creds = None

    # Load existing token
    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)

    # Refresh or get new token
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not CREDENTIALS_FILE.exists():
                log.error("YouTube credentials file not found: %s", CREDENTIALS_FILE)
                log.info("To set up: go to https://console.cloud.google.com/apis/credentials")
                log.info("Create OAuth 2.0 Client ID (Desktop app), download JSON, save as %s", CREDENTIALS_FILE)
                return None

            flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_FILE), SCOPES)
            creds = flow.run_local_server(port=0)

        # Save token
        TOKEN_FILE.write_text(creds.to_json())
        log.info("YouTube token saved")

    return build("youtube", "v3", credentials=creds)


def load_uploaded():
    """Load list of already-uploaded video filenames."""
    if UPLOADED_LOG.exists():
        try:
            return json.loads(UPLOADED_LOG.read_text())
        except:
            pass
    return {}


def mark_uploaded(filename, video_id):
    """Record that a video was uploaded."""
    uploaded = load_uploaded()
    uploaded[filename] = {
        "video_id": video_id,
        "uploaded_at": datetime.utcnow().isoformat(),
    }
    tmp = str(UPLOADED_LOG) + ".tmp"
    with open(tmp, "w") as f:
        json.dump(uploaded, f, indent=2)
    os.replace(tmp, str(UPLOADED_LOG))


def upload_video(youtube, video_path, title, description, tags, thumbnail_path=None):
    """Upload a single video to YouTube."""
    body = {
        "snippet": {
            "title": title[:100],
            "description": description[:5000],
            "tags": [t.strip() for t in tags.split(",")][:30],
            "categoryId": "22",  # People & Blogs (safe default)
            "defaultLanguage": "en",
        },
        "status": {
            "privacyStatus": "public",
            "selfDeclaredMadeForKids": False,
        },
    }

    media = MediaFileUpload(video_path, mimetype="video/mp4", resumable=True)

    log.info("Uploading: %s", title[:50])
    request = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=media,
    )

    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            log.info("  Progress: %d%%", int(status.progress() * 100))

    video_id = response["id"]
    log.info("UPLOADED: https://youtube.com/watch?v=%s", video_id)

    # Set thumbnail if available
    if thumbnail_path and os.path.exists(thumbnail_path):
        try:
            youtube.thumbnails().set(
                videoId=video_id,
                media_body=MediaFileUpload(thumbnail_path, mimetype="image/png"),
            ).execute()
            log.info("Thumbnail set for %s", video_id)
        except Exception as e:
            log.warning("Thumbnail upload failed: %s", e)

    return video_id


def upload_pending():
    """Find and upload all un-uploaded videos."""
    youtube = get_youtube_service()
    if not youtube:
        return

    uploaded = load_uploaded()
    pending = []

    # Find videos with metadata files
    for meta_file in sorted(VIDEO_DIR.glob("**/*_meta.json"), key=lambda p: p.name):
        video_name = meta_file.stem.replace("_meta", "")
        if video_name in uploaded:
            continue

        try:
            meta = json.loads(meta_file.read_text())
            video_path = meta.get("video_path", "")
            if os.path.exists(video_path):
                pending.append((meta, video_path, meta_file))
        except:
            pass

    if not pending:
        log.info("No pending videos to upload")
        return

    log.info("Found %d videos to upload", len(pending))

    for meta, video_path, meta_file in pending:
        try:
            video_id = upload_video(
                youtube,
                video_path=video_path,
                title=meta.get("title", "Untitled"),
                description=meta.get("description", ""),
                tags=meta.get("tags", ""),
                thumbnail_path=meta.get("thumbnail_path"),
            )
            mark_uploaded(Path(video_path).stem, video_id)
        except Exception as e:
            log.error("Upload failed for %s: %s", meta.get("title", "?")[:30], e)


def setup_credentials():
    """Interactive setup for YouTube API credentials."""
    print("=" * 60)
    print("YOUTUBE API SETUP")
    print("=" * 60)
    print()
    print("Step 1: Go to https://console.cloud.google.com/apis/credentials")
    print(f"         Project: dominion-ascendant")
    print()
    print("Step 2: Click '+ CREATE CREDENTIALS' → 'OAuth client ID'")
    print("         Application type: Desktop app")
    print("         Name: Dominion YouTube Uploader")
    print()
    print("Step 3: Download the JSON file")
    print(f"         Save it as: {CREDENTIALS_FILE}")
    print()
    print("Step 4: Run this script again: python youtube_uploader.py --upload")
    print("         It will open a browser for one-time consent.")
    print()

    if CREDENTIALS_FILE.exists():
        print(f"✓ Credentials file found: {CREDENTIALS_FILE}")
    else:
        print(f"✗ Credentials file NOT found: {CREDENTIALS_FILE}")

    if TOKEN_FILE.exists():
        print(f"✓ Token file found: {TOKEN_FILE}")
    else:
        print(f"✗ Token file NOT found (will be created on first auth)")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="YouTube Auto-Uploader")
    parser.add_argument("--upload", action="store_true", help="Upload pending videos")
    parser.add_argument("--setup", action="store_true", help="Show setup instructions")
    parser.add_argument("--status", action="store_true", help="Show upload status")
    args = parser.parse_args()

    if args.setup:
        setup_credentials()
    elif args.upload:
        upload_pending()
    elif args.status:
        uploaded = load_uploaded()
        print(f"Uploaded: {len(uploaded)} videos")
        for name, info in uploaded.items():
            print(f"  {name} → https://youtube.com/watch?v={info['video_id']}")
    else:
        parser.print_help()
