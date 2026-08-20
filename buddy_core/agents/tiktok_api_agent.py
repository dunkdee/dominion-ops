"""
agents/tiktok_api_agent.py — TIKTOK API POSTING AGENT
=======================================================
Posts videos to TikTok via the official Content Posting API.
No browser automation, no lockout risk.

Requires TikTok Developer App approval.
OAuth2 flow for access token, then direct video upload.

Usage:
    from agents.tiktok_api_agent import post_video, get_auth_url

    # Step 1: Get auth URL (one-time)
    url = get_auth_url()
    # User visits URL, authorizes, gets redirected with code

    # Step 2: Exchange code for token (one-time)
    exchange_code("CODE_FROM_REDIRECT")

    # Step 3: Post videos (ongoing)
    post_video("path/to/video.mp4", "Caption text #hashtags")
"""

import os
import sys
import json
import time
import requests
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
load_dotenv(override=True)

from utils.safe_io import atomic_json_write, load_json

CLIENT_KEY = os.getenv("TIKTOK_CLIENT_KEY", "")
CLIENT_SECRET = os.getenv("TIKTOK_CLIENT_SECRET", "")
REDIRECT_URI = "https://dominionhealing.org/api/tiktok/callback"
TOKEN_FILE = Path(__file__).resolve().parent.parent / "tiktok_token.json"
POST_LOG = Path(__file__).resolve().parent.parent / "tiktok_post_log.json"

SCOPES = "user.info.basic,video.publish,video.upload"

# TikTok API endpoints
AUTH_URL = "https://www.tiktok.com/v2/auth/authorize/"
TOKEN_URL = "https://open.tiktokapis.com/v2/oauth/token/"
UPLOAD_INIT_URL = "https://open.tiktokapis.com/v2/post/publish/inbox/video/init/"
UPLOAD_URL = "https://open.tiktokapis.com/v2/post/publish/video/init/"
USER_INFO_URL = "https://open.tiktokapis.com/v2/user/info/"


# ============================================================
# AUTH
# ============================================================

def get_auth_url() -> str:
    """Generate the OAuth2 authorization URL. User visits this to authorize."""
    import secrets
    state = secrets.token_urlsafe(16)
    url = (
        f"{AUTH_URL}"
        f"?client_key={CLIENT_KEY}"
        f"&scope={SCOPES}"
        f"&response_type=code"
        f"&redirect_uri={REDIRECT_URI}"
        f"&state={state}"
    )
    return url


def exchange_code(code: str) -> dict:
    """Exchange authorization code for access token."""
    resp = requests.post(TOKEN_URL, data={
        "client_key": CLIENT_KEY,
        "client_secret": CLIENT_SECRET,
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": REDIRECT_URI,
    }, headers={"Content-Type": "application/x-www-form-urlencoded"})

    data = resp.json()
    if "access_token" in data:
        token_data = {
            "access_token": data["access_token"],
            "refresh_token": data.get("refresh_token", ""),
            "expires_in": data.get("expires_in", 86400),
            "open_id": data.get("open_id", ""),
            "obtained_at": datetime.utcnow().isoformat(),
        }
        atomic_json_write(TOKEN_FILE, token_data, default=str)
        print(f"[TIKTOK] Token saved. Open ID: {token_data['open_id']}")
        return token_data
    else:
        print(f"[TIKTOK] Token exchange failed: {data}")
        return data


def refresh_token() -> dict:
    """Refresh the access token using refresh token."""
    token = load_json(TOKEN_FILE, default={})
    if not token.get("refresh_token"):
        return {"error": "No refresh token available"}

    resp = requests.post(TOKEN_URL, data={
        "client_key": CLIENT_KEY,
        "client_secret": CLIENT_SECRET,
        "grant_type": "refresh_token",
        "refresh_token": token["refresh_token"],
    }, headers={"Content-Type": "application/x-www-form-urlencoded"})

    data = resp.json()
    if "access_token" in data:
        token["access_token"] = data["access_token"]
        token["refresh_token"] = data.get("refresh_token", token["refresh_token"])
        token["expires_in"] = data.get("expires_in", 86400)
        token["obtained_at"] = datetime.utcnow().isoformat()
        atomic_json_write(TOKEN_FILE, token, default=str)
        print("[TIKTOK] Token refreshed")
        return token
    return data


def get_token() -> str:
    """Get current access token, refresh if needed."""
    token = load_json(TOKEN_FILE, default={})
    if not token.get("access_token"):
        return ""

    # Check expiry
    obtained = datetime.fromisoformat(token.get("obtained_at", "2000-01-01"))
    elapsed = (datetime.utcnow() - obtained).total_seconds()
    if elapsed > token.get("expires_in", 86400) - 300:
        refreshed = refresh_token()
        return refreshed.get("access_token", "")

    return token["access_token"]


# ============================================================
# POSTING
# ============================================================

def post_video(video_path: str, caption: str, privacy: str = "PUBLIC_TO_EVERYONE") -> dict:
    """
    Upload and post a video to TikTok via the Content Posting API.

    Args:
        video_path: Path to the MP4 file
        caption: Video description/caption
        privacy: PUBLIC_TO_EVERYONE, MUTUAL_FOLLOW_FRIENDS, FOLLOWER_OF_CREATOR, SELF_ONLY

    Returns: dict with post_id and status
    """
    access_token = get_token()
    if not access_token:
        return {"status": "error", "error": "No access token. Run get_auth_url() and exchange_code() first."}

    video_path = Path(video_path)
    if not video_path.exists():
        return {"status": "error", "error": f"Video file not found: {video_path}"}

    file_size = video_path.stat().st_size
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }

    # Step 1: Initialize upload
    init_body = {
        "post_info": {
            "title": caption[:150],
            "privacy_level": privacy,
            "disable_duet": False,
            "disable_comment": False,
            "disable_stitch": False,
        },
        "source_info": {
            "source": "FILE_UPLOAD",
            "video_size": file_size,
            "chunk_size": file_size,
            "total_chunk_count": 1,
        }
    }

    print(f"[TIKTOK] Initializing upload for {video_path.name} ({file_size / 1024 / 1024:.1f} MB)...")
    resp = requests.post(UPLOAD_URL, json=init_body, headers=headers)
    data = resp.json()

    if data.get("error", {}).get("code") != "ok" and "data" not in data:
        return {"status": "error", "error": data}

    upload_url = data.get("data", {}).get("upload_url", "")
    publish_id = data.get("data", {}).get("publish_id", "")

    if not upload_url:
        return {"status": "error", "error": "No upload URL returned", "response": data}

    # Step 2: Upload video file
    print(f"[TIKTOK] Uploading video...")
    with open(video_path, "rb") as f:
        video_data = f.read()

    upload_headers = {
        "Content-Range": f"bytes 0-{file_size - 1}/{file_size}",
        "Content-Type": "video/mp4",
    }
    upload_resp = requests.put(upload_url, data=video_data, headers=upload_headers)

    if upload_resp.status_code not in (200, 201):
        return {"status": "error", "error": f"Upload failed: {upload_resp.status_code}", "body": upload_resp.text[:200]}

    print(f"[TIKTOK] Upload complete. Publish ID: {publish_id}")

    # Log the post
    log = load_json(POST_LOG, default=[])
    log.append({
        "ts": datetime.utcnow().isoformat(),
        "video": str(video_path),
        "caption": caption[:100],
        "publish_id": publish_id,
        "privacy": privacy,
        "status": "published",
    })
    if len(log) > 200:
        log = log[-200:]
    atomic_json_write(POST_LOG, log, default=str)

    return {
        "status": "ok",
        "publish_id": publish_id,
        "video": str(video_path),
        "caption": caption[:100],
    }


def check_post_status(publish_id: str) -> dict:
    """Check the status of a published video."""
    access_token = get_token()
    if not access_token:
        return {"error": "No access token"}

    resp = requests.post(
        "https://open.tiktokapis.com/v2/post/publish/status/fetch/",
        json={"publish_id": publish_id},
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }
    )
    return resp.json()


# ============================================================
# BATCH POSTING
# ============================================================

def post_batch(videos: list, delay_seconds: float = 30) -> list:
    """
    Post multiple videos with delay between each.

    Args:
        videos: list of (video_path, caption) tuples
        delay_seconds: wait between posts (default 30s)

    Returns: list of results
    """
    results = []
    for i, (path, caption) in enumerate(videos):
        print(f"\n[TIKTOK] Posting {i + 1}/{len(videos)}: {Path(path).name}")
        result = post_video(path, caption)
        results.append(result)
        print(f"  Result: {result.get('status')}")

        if i < len(videos) - 1:
            print(f"  Waiting {delay_seconds}s before next post...")
            time.sleep(delay_seconds)

    return results


# ============================================================
# CLI
# ============================================================

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="TikTok API Agent")
    parser.add_argument("--auth", action="store_true", help="Get authorization URL")
    parser.add_argument("--code", type=str, help="Exchange auth code for token")
    parser.add_argument("--post", type=str, help="Post a video (path)")
    parser.add_argument("--caption", type=str, default="", help="Video caption")
    parser.add_argument("--status", type=str, help="Check post status (publish_id)")
    parser.add_argument("--refresh", action="store_true", help="Refresh access token")
    args = parser.parse_args()

    if args.auth:
        url = get_auth_url()
        print(f"\nOpen this URL in your browser:\n{url}\n")
    elif args.code:
        result = exchange_code(args.code)
        print(json.dumps(result, indent=2))
    elif args.post:
        result = post_video(args.post, args.caption or "Dominion Healing #DominionHealing")
        print(json.dumps(result, indent=2))
    elif args.status:
        result = check_post_status(args.status)
        print(json.dumps(result, indent=2))
    elif args.refresh:
        result = refresh_token()
        print(json.dumps(result, indent=2))
    else:
        parser.print_help()
