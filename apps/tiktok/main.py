"""Governed TikTok OAuth and publishing API.

Publishing is disabled by default. A live upload requires all of the following:

* ``TIKTOK_PUBLISH_ENABLED=true``
* a configured ``TIKTOK_OPERATOR_TOKEN``
* a matching ``X-Operator-Token`` request header
* ``X-Human-Approval: APPROVED``
* a verified account matching ``TIKTOK_ALLOWED_USERNAME``

No credential, token payload, or full provider response is returned to callers.
"""

from __future__ import annotations

import hmac
import json
import os
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv
from fastapi import FastAPI, Form, Header, HTTPException, Query, UploadFile, status

ROOT = Path(os.getenv("TIKTOK_DATA_ROOT", "~/DominionsArk")).expanduser()
ENV_FILE = ROOT / ".env"
TOKEN_FILE = ROOT / "data" / "tiktok_tokens.json"
USER_FILE = ROOT / "data" / "tiktok_user.json"

load_dotenv(ENV_FILE)
CLIENT_ID = os.getenv("TIKTOK_CLIENT_ID", "").strip()
CLIENT_SECRET = os.getenv("TIKTOK_CLIENT_SECRET", "").strip()
REDIRECT_URI = os.getenv("TIKTOK_REDIRECT_URI", "").strip()
OAUTH_STATE = os.getenv("TIKTOK_OAUTH_STATE", "").strip()
OPERATOR_TOKEN = os.getenv("TIKTOK_OPERATOR_TOKEN", "").strip()
ALLOWED_USERNAME = os.getenv("TIKTOK_ALLOWED_USERNAME", "").strip()
PUBLISH_ENABLED = os.getenv("TIKTOK_PUBLISH_ENABLED", "false").lower() == "true"
MAX_UPLOAD_BYTES = int(os.getenv("TIKTOK_MAX_UPLOAD_BYTES", str(200 * 1024 * 1024)))

app = FastAPI(title="Dominion TikTok Gateway", version="2.0")


def _write_private_json(path: Path, data: dict[str, Any]) -> None:
    """Atomically persist JSON with owner-only permissions."""
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data), encoding="utf-8")
    os.chmod(temporary, 0o600)
    temporary.replace(path)
    os.chmod(path, 0o600)


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _require_operator(token: str | None) -> None:
    if not OPERATOR_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="TikTok operator token is not configured",
        )
    supplied = token or ""
    if not hmac.compare_digest(supplied, OPERATOR_TOKEN):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid operator token",
        )


def _verified_username() -> str | None:
    user_info = _read_json(USER_FILE)
    if not user_info:
        return None
    username = user_info.get("data", {}).get("user", {}).get("username")
    return username if isinstance(username, str) else None


def _access_token() -> str | None:
    tokens = _read_json(TOKEN_FILE)
    if not tokens:
        return None
    value = tokens.get("data", {}).get("access_token")
    return value if isinstance(value, str) and value else None


@app.get("/health")
def health() -> dict[str, Any]:
    """Expose configuration state without exposing secret values."""
    username = _verified_username()
    return {
        "status": "ok",
        "mode": "publish_enabled" if PUBLISH_ENABLED else "draft_only",
        "oauth_configured": all((CLIENT_ID, CLIENT_SECRET, REDIRECT_URI, OAUTH_STATE)),
        "operator_gate_configured": bool(OPERATOR_TOKEN),
        "allowed_account_configured": bool(ALLOWED_USERNAME),
        "verified_account": bool(username and username == ALLOWED_USERNAME),
    }


@app.get("/tiktok/callback")
def tiktok_callback(
    code: str,
    oauth_state: str = Query(alias="state"),
) -> dict[str, str]:
    """Complete OAuth only when the preconfigured anti-CSRF state matches."""
    if not all((CLIENT_ID, CLIENT_SECRET, REDIRECT_URI, OAUTH_STATE)):
        raise HTTPException(status_code=503, detail="TikTok OAuth is not fully configured")
    if not hmac.compare_digest(oauth_state, OAUTH_STATE):
        raise HTTPException(status_code=403, detail="OAuth state validation failed")

    response = requests.post(
        "https://open-api.tiktok.com/oauth/access_token",
        data={
            "client_key": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": REDIRECT_URI,
        },
        timeout=30,
    )
    try:
        response.raise_for_status()
        token_data = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise HTTPException(status_code=502, detail="TikTok token exchange failed") from exc

    access_token = token_data.get("data", {}).get("access_token")
    if not isinstance(access_token, str) or not access_token:
        raise HTTPException(status_code=502, detail="TikTok returned no access token")

    user_response = requests.get(
        "https://open-api.tiktok.com/user/info/",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=30,
    )
    try:
        user_response.raise_for_status()
        user_info = user_response.json()
    except (requests.RequestException, ValueError) as exc:
        raise HTTPException(status_code=502, detail="TikTok account verification failed") from exc

    username = user_info.get("data", {}).get("user", {}).get("username")
    if not ALLOWED_USERNAME:
        raise HTTPException(status_code=503, detail="Allowed TikTok account is not configured")
    if username != ALLOWED_USERNAME:
        raise HTTPException(status_code=403, detail="TikTok account is not authorized")

    _write_private_json(TOKEN_FILE, token_data)
    _write_private_json(USER_FILE, user_info)
    return {"status": "ok", "username": ALLOWED_USERNAME}


@app.post("/tiktok/validate")
def validate_publish_request(
    caption: str = Form(...),
    x_operator_token: str | None = Header(default=None, alias="X-Operator-Token"),
) -> dict[str, Any]:
    """Validate a draft without uploading anything to TikTok."""
    _require_operator(x_operator_token)
    normalized = caption.strip()
    if not normalized:
        raise HTTPException(status_code=422, detail="Caption cannot be empty")
    return {
        "status": "ready_for_human_review",
        "mode": "publish_enabled" if PUBLISH_ENABLED else "draft_only",
        "caption_length": len(normalized),
        "account_verified": _verified_username() == ALLOWED_USERNAME,
    }


@app.post("/tiktok/upload")
async def upload_video(
    video: UploadFile,
    caption: str = Form(...),
    x_operator_token: str | None = Header(default=None, alias="X-Operator-Token"),
    x_human_approval: str | None = Header(default=None, alias="X-Human-Approval"),
) -> dict[str, Any]:
    """Publish only after explicit operator authentication and human approval."""
    _require_operator(x_operator_token)
    if not PUBLISH_ENABLED:
        raise HTTPException(status_code=403, detail="TikTok gateway is locked in draft-only mode")
    if x_human_approval != "APPROVED":
        raise HTTPException(status_code=403, detail="Explicit human approval is required")
    if not ALLOWED_USERNAME or _verified_username() != ALLOWED_USERNAME:
        raise HTTPException(status_code=403, detail="Authorized TikTok account is not verified")
    if not video.content_type or not video.content_type.startswith("video/"):
        raise HTTPException(status_code=415, detail="A video media type is required")

    payload = await video.read(MAX_UPLOAD_BYTES + 1)
    if len(payload) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Video exceeds the configured size limit")

    access_token = _access_token()
    if not access_token:
        raise HTTPException(status_code=401, detail="TikTok authentication is required")

    response = requests.post(
        "https://open-api.tiktokglobalshop.com/video/upload/",
        headers={"Authorization": f"Bearer {access_token}"},
        files={"video": (video.filename or "video.mp4", payload, video.content_type)},
        data={"caption": caption.strip()},
        timeout=120,
    )
    try:
        response.raise_for_status()
        result = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise HTTPException(status_code=502, detail="TikTok upload failed") from exc

    return {"status": "success", "provider_result": result}
