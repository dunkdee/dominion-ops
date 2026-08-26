from __future__ import annotations
import hashlib
import hmac
import json
import secrets
import time
from collections import defaultdict, deque
from typing import Any

from fastapi import Header, HTTPException, Request

from .config import settings


def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    if not x_api_key or not secrets.compare_digest(x_api_key, settings.api_key):
        raise HTTPException(status_code=401, detail="Unauthorized")


def canonical_json(data: Any) -> bytes:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def verify_radah_signature(payload: dict, signature: str | None, timestamp: str | None) -> None:
    """
    Optional HMAC verification for RADAH decision envelopes.
    Expected message: "<timestamp>.<canonical-json-payload>"
    Timestamp must be within five minutes to reduce replay risk.
    """
    if not settings.require_radah_signature:
        return
    if not signature or not timestamp:
        raise HTTPException(status_code=403, detail="Missing RADAH signature")
    try:
        ts = int(timestamp)
    except ValueError:
        raise HTTPException(status_code=403, detail="Invalid RADAH timestamp")
    if abs(int(time.time()) - ts) > 300:
        raise HTTPException(status_code=403, detail="Expired RADAH authorization")
    msg = str(ts).encode() + b"." + canonical_json(payload)
    expected = hmac.new(
        settings.radah_shared_secret.encode(),
        msg,
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(expected, signature):
        raise HTTPException(status_code=403, detail="Invalid RADAH signature")


class InMemoryRateLimiter:
    """
    Per-process defensive limiter. Put a gateway/reverse proxy in front for
    distributed production rate limiting.
    """
    def __init__(self, limit: int, window_seconds: int = 60):
        self.limit = limit
        self.window = window_seconds
        self.events: dict[str, deque[float]] = defaultdict(deque)

    def check(self, key: str) -> None:
        now = time.monotonic()
        q = self.events[key]
        cutoff = now - self.window
        while q and q[0] < cutoff:
            q.popleft()
        if len(q) >= self.limit:
            raise HTTPException(status_code=429, detail="Rate limit exceeded")
        q.append(now)


limiter = InMemoryRateLimiter(settings.rate_limit_per_minute)


async def request_guard(request: Request) -> None:
    client = request.client.host if request.client else "unknown"
    limiter.check(client)

    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > settings.max_body_bytes:
                raise HTTPException(status_code=413, detail="Request body too large")
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid content-length")
