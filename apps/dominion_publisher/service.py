from __future__ import annotations

import hmac
import os
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException, status
from pydantic import BaseModel, Field

from .adapters import MetaFacebookAdapter, MetaInstagramAdapter
from .core import PublisherCore, PublisherStore
from .models import Asset, PublishJob


class AssetInput(BaseModel):
    uri: str
    sha256: str
    provenance: str
    media_type: str = "application/octet-stream"


class PublishJobInput(BaseModel):
    campaign_id: str
    platform: str
    account_id: str
    caption: str
    destination_url: str
    assets: list[AssetInput] = Field(default_factory=list)
    approved_by: str | None = None
    approved_at: str | None = None
    scheduled_at: str | None = None
    metadata: dict = Field(default_factory=dict)

    def to_domain(self) -> PublishJob:
        return PublishJob(
            campaign_id=self.campaign_id,
            platform=self.platform,
            account_id=self.account_id,
            caption=self.caption,
            destination_url=self.destination_url,
            assets=[Asset(**asset.model_dump()) for asset in self.assets],
            approved_by=self.approved_by,
            approved_at=self.approved_at,
            scheduled_at=self.scheduled_at,
            metadata=self.metadata,
        )


DB_PATH = Path(os.getenv("DOMINION_PUBLISHER_DB", "~/DominionsArk/data/dominion_publisher.db")).expanduser()
DB_PATH.parent.mkdir(parents=True, exist_ok=True)
OPERATOR_TOKEN = os.getenv("DOMINION_PUBLISHER_OPERATOR_TOKEN", "").strip()

store = PublisherStore(DB_PATH)
core = PublisherCore(store)
core.register_adapter(MetaInstagramAdapter())
core.register_adapter(MetaFacebookAdapter())

app = FastAPI(title="Dominion Publisher", version="1.0.0")


def _require_operator(token: str | None) -> None:
    if not OPERATOR_TOKEN:
        raise HTTPException(status_code=503, detail="publisher operator token is not configured")
    if not hmac.compare_digest(token or "", OPERATOR_TOKEN):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid operator token")


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "service": "dominion-publisher",
        "database": str(DB_PATH),
        "operator_gate_configured": bool(OPERATOR_TOKEN),
        "meta_token_configured": bool(os.getenv("META_ACCESS_TOKEN", "").strip()),
        "meta_graph_version_configured": bool(os.getenv("META_GRAPH_VERSION", "").strip()),
        "platforms": ["instagram", "facebook"],
    }


@app.post("/jobs/queue")
def queue_job(
    payload: PublishJobInput,
    x_operator_token: str | None = Header(default=None, alias="X-Operator-Token"),
) -> dict:
    _require_operator(x_operator_token)
    try:
        receipt = core.queue(payload.to_domain())
    except (ValueError, PermissionError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        "receipt_id": receipt.receipt_id,
        "idempotency_key": receipt.idempotency_key,
        "status": receipt.status.value,
        "destination_url": receipt.destination_url,
    }


@app.post("/jobs/publish")
def publish_job(
    payload: PublishJobInput,
    x_operator_token: str | None = Header(default=None, alias="X-Operator-Token"),
    x_human_approval: str | None = Header(default=None, alias="X-Human-Approval"),
) -> dict:
    _require_operator(x_operator_token)
    if x_human_approval != "APPROVED":
        raise HTTPException(status_code=403, detail="explicit human approval header is required")
    try:
        receipt = core.publish(payload.to_domain())
    except (ValueError, PermissionError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        "receipt_id": receipt.receipt_id,
        "idempotency_key": receipt.idempotency_key,
        "status": receipt.status.value,
        "platform": receipt.platform,
        "provider_post_id": receipt.provider_post_id,
        "destination_url": receipt.destination_url,
        "error": receipt.error,
    }


@app.get("/receipts/{idempotency_key}")
def get_receipts(
    idempotency_key: str,
    x_operator_token: str | None = Header(default=None, alias="X-Operator-Token"),
) -> dict:
    _require_operator(x_operator_token)
    return {"idempotency_key": idempotency_key, "receipts": store.receipts_for(idempotency_key)}
