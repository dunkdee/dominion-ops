from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from hashlib import sha256
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


class PublishStatus(str, Enum):
    DRAFT = "draft"
    APPROVED = "approved"
    QUEUED = "queued"
    PUBLISHED = "published"
    FAILED = "failed"
    BLOCKED = "blocked"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class Asset:
    uri: str
    sha256: str
    provenance: str
    media_type: str = "application/octet-stream"

    def validate(self) -> None:
        if not self.uri.strip():
            raise ValueError("asset uri is required")
        if len(self.sha256) != 64 or any(c not in "0123456789abcdefABCDEF" for c in self.sha256):
            raise ValueError("asset sha256 must be a 64-character hex digest")
        if not self.provenance.strip():
            raise ValueError("asset provenance is required")


@dataclass
class PublishJob:
    campaign_id: str
    platform: str
    account_id: str
    caption: str
    destination_url: str
    assets: list[Asset] = field(default_factory=list)
    approved_by: str | None = None
    approved_at: str | None = None
    scheduled_at: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def idempotency_key(self) -> str:
        payload = "|".join(
            [
                self.campaign_id.strip(),
                self.platform.strip().lower(),
                self.account_id.strip(),
                self.caption.strip(),
                self.destination_url.strip(),
                ",".join(sorted(a.sha256.lower() for a in self.assets)),
            ]
        )
        return sha256(payload.encode("utf-8")).hexdigest()

    def validate(self) -> None:
        if not self.campaign_id.strip():
            raise ValueError("campaign_id is required")
        if not self.platform.strip():
            raise ValueError("platform is required")
        if not self.account_id.strip():
            raise ValueError("account_id is required")
        if not self.caption.strip():
            raise ValueError("caption is required")
        parsed = urlsplit(self.destination_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("destination_url must be an absolute http(s) URL")
        for asset in self.assets:
            asset.validate()

    def require_approval(self) -> None:
        if not self.approved_by or not self.approved_at:
            raise PermissionError("explicit approval is required before queueing")

    def attributed_url(self) -> str:
        parsed = urlsplit(self.destination_url)
        query = dict(parse_qsl(parsed.query, keep_blank_values=True))
        query.update(
            {
                "utm_source": self.platform.lower(),
                "utm_medium": "social",
                "utm_campaign": self.campaign_id,
            }
        )
        return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode(query), parsed.fragment))


@dataclass(frozen=True)
class PublishReceipt:
    receipt_id: str
    idempotency_key: str
    campaign_id: str
    platform: str
    account_id: str
    status: PublishStatus
    observed_at: str
    asset_hashes: tuple[str, ...]
    destination_url: str
    provider_post_id: str | None = None
    error: str | None = None
