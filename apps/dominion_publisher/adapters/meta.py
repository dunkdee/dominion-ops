from __future__ import annotations

import os
from urllib.parse import urlsplit

import requests

from ..models import PublishJob


class _MetaBase:
    timeout_seconds = 30

    def __init__(
        self,
        access_token: str | None = None,
        graph_version: str | None = None,
        session: requests.Session | None = None,
    ) -> None:
        self.access_token = (access_token or os.getenv("META_ACCESS_TOKEN", "")).strip()
        self.graph_version = (graph_version or os.getenv("META_GRAPH_VERSION", "")).strip()
        self.session = session or requests.Session()

    @property
    def base_url(self) -> str:
        if not self.graph_version:
            raise RuntimeError("META_GRAPH_VERSION is not configured")
        version = self.graph_version if self.graph_version.startswith("v") else f"v{self.graph_version}"
        return f"https://graph.facebook.com/{version}"

    def validate_credentials(self, account_id: str) -> None:
        if not self.access_token:
            raise RuntimeError("META_ACCESS_TOKEN is not configured")
        if not account_id.strip():
            raise RuntimeError("Meta account_id is required")
        _ = self.base_url

    @staticmethod
    def _require_remote_asset(job: PublishJob) -> str:
        if len(job.assets) != 1:
            raise ValueError("Meta V1 canary requires exactly one media asset")
        asset = job.assets[0]
        parsed = urlsplit(asset.uri)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("Meta media asset must be an externally reachable http(s) URL")
        return asset.uri

    @staticmethod
    def _raise_provider_error(response: requests.Response, operation: str) -> None:
        if response.ok:
            return
        raise RuntimeError(f"Meta {operation} failed with HTTP {response.status_code}")


class MetaInstagramAdapter(_MetaBase):
    """Instagram professional-account image publisher through the official Meta Graph API."""

    platform = "instagram"

    def validate_job(self, job: PublishJob) -> None:
        asset_url = self._require_remote_asset(job)
        if not job.assets[0].media_type.startswith("image/"):
            raise ValueError("Instagram V1 canary supports one image asset")
        if not asset_url:
            raise ValueError("Instagram media URL is required")

    def publish(self, job: PublishJob) -> str:
        self.validate_credentials(job.account_id)
        self.validate_job(job)
        asset_url = job.assets[0].uri
        caption = f"{job.caption.strip()}\n\n{job.attributed_url()}"

        create_response = self.session.post(
            f"{self.base_url}/{job.account_id}/media",
            data={
                "image_url": asset_url,
                "caption": caption,
                "access_token": self.access_token,
            },
            timeout=self.timeout_seconds,
        )
        self._raise_provider_error(create_response, "Instagram media-container creation")
        creation_id = create_response.json().get("id")
        if not isinstance(creation_id, str) or not creation_id:
            raise RuntimeError("Meta returned no Instagram creation id")

        publish_response = self.session.post(
            f"{self.base_url}/{job.account_id}/media_publish",
            data={
                "creation_id": creation_id,
                "access_token": self.access_token,
            },
            timeout=self.timeout_seconds,
        )
        self._raise_provider_error(publish_response, "Instagram publish")
        post_id = publish_response.json().get("id")
        if not isinstance(post_id, str) or not post_id:
            raise RuntimeError("Meta returned no Instagram post id")
        return post_id


class MetaFacebookAdapter(_MetaBase):
    """Facebook Page image publisher through the official Meta Graph API."""

    platform = "facebook"

    def validate_job(self, job: PublishJob) -> None:
        self._require_remote_asset(job)
        if not job.assets[0].media_type.startswith("image/"):
            raise ValueError("Facebook V1 canary supports one image asset")

    def publish(self, job: PublishJob) -> str:
        self.validate_credentials(job.account_id)
        self.validate_job(job)
        message = f"{job.caption.strip()}\n\n{job.attributed_url()}"
        response = self.session.post(
            f"{self.base_url}/{job.account_id}/photos",
            data={
                "url": job.assets[0].uri,
                "caption": message,
                "access_token": self.access_token,
            },
            timeout=self.timeout_seconds,
        )
        self._raise_provider_error(response, "Facebook Page publish")
        post_id = response.json().get("post_id") or response.json().get("id")
        if not isinstance(post_id, str) or not post_id:
            raise RuntimeError("Meta returned no Facebook post id")
        return post_id
