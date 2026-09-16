from __future__ import annotations

import hmac
import html
import os
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException, Query, status
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from .adapters import MetaFacebookAdapter, MetaInstagramAdapter
from .core import PublisherCore, PublisherStore
from .meta_binding import META_SCOPES, MetaBindingManager
from .models import Asset, PublishJob
from .paths import vault_root
from .vault import CredentialVault


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

    @staticmethod
    def _model_data(model: BaseModel) -> dict:
        if hasattr(model, "model_dump"):
            return model.model_dump()
        return model.dict()

    def to_domain(self) -> PublishJob:
        return PublishJob(
            campaign_id=self.campaign_id,
            platform=self.platform,
            account_id=self.account_id,
            caption=self.caption,
            destination_url=self.destination_url,
            assets=[Asset(**self._model_data(asset)) for asset in self.assets],
            approved_by=self.approved_by,
            approved_at=self.approved_at,
            scheduled_at=self.scheduled_at,
            metadata=self.metadata,
        )


class MetaBindInput(BaseModel):
    page_id: str
    approved_by: str


DB_PATH = Path(os.getenv("DOMINION_PUBLISHER_DB", "~/DominionsArk/data/dominion_publisher.db")).expanduser()
DB_PATH.parent.mkdir(parents=True, exist_ok=True)
# Resolved through the shared helper so the reader and configure_meta (the
# writer) can never fall back to different directories.
VAULT_ROOT = vault_root()
OPERATOR_TOKEN = os.getenv("DOMINION_PUBLISHER_OPERATOR_TOKEN", "").strip()
FRONTEND_PUBLIC_URL = (
    os.getenv("DOMINION_FRONTEND_PUBLIC_URL", "https://app.dominionhealing.org").strip().rstrip("/")
    or "https://app.dominionhealing.org"
)

store = PublisherStore(DB_PATH)
vault = CredentialVault(VAULT_ROOT)
meta_binding = MetaBindingManager(vault)
core = PublisherCore(store)
core.register_adapter(
    MetaInstagramAdapter(token_resolver=vault.token_for, version_resolver=vault.graph_version)
)
core.register_adapter(
    MetaFacebookAdapter(token_resolver=vault.token_for, version_resolver=vault.graph_version)
)

app = FastAPI(title="Dominion Publisher", version="1.1.0")


def _require_operator(token: str | None) -> None:
    if not OPERATOR_TOKEN:
        raise HTTPException(status_code=503, detail="publisher operator token is not configured")
    if not hmac.compare_digest(token or "", OPERATOR_TOKEN):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid operator token")


def _meta_status() -> dict:
    bound = vault.bound_accounts_safe()
    return {
        "app_configured": vault.meta_app() is not None,
        "facebook_accounts": len(bound["facebook"]),
        "instagram_accounts": len(bound["instagram"]),
        "bound_accounts": bound,
    }


@app.get("/health")
def health() -> dict:
    meta = _meta_status()
    return {
        "status": "ok",
        "service": "dominion-publisher",
        "database": str(DB_PATH),
        "operator_gate_configured": bool(OPERATOR_TOKEN),
        "meta_app_configured": meta["app_configured"],
        "meta_token_configured": bool(meta["facebook_accounts"] or meta["instagram_accounts"]),
        "meta_graph_version_configured": bool(vault.graph_version()),
        "meta_bound_counts": {
            "facebook": meta["facebook_accounts"],
            "instagram": meta["instagram_accounts"],
        },
        "platforms": ["instagram", "facebook"],
    }


@app.get("/accounts")
def accounts(
    x_operator_token: str | None = Header(default=None, alias="X-Operator-Token"),
) -> dict:
    _require_operator(x_operator_token)
    return _meta_status()


@app.post("/oauth/meta/start")
def start_meta_binding(
    x_operator_token: str | None = Header(default=None, alias="X-Operator-Token"),
) -> dict:
    _require_operator(x_operator_token)
    try:
        authorization_url = meta_binding.authorization_url()
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {
        "authorization_url": authorization_url,
        "scopes": list(META_SCOPES),
        "expires_in_seconds": meta_binding.state_ttl_seconds,
    }


@app.get("/oauth/meta/callback", response_class=HTMLResponse)
def complete_meta_binding(
    code: str | None = Query(default=None),
    state_value: str | None = Query(default=None, alias="state"),
    error: str | None = Query(default=None),
) -> HTMLResponse:
    if error:
        safe = html.escape(error, quote=True)
        return HTMLResponse(
            f"<h1>Dominion Publisher Meta authorization failed</h1><p>{safe}</p>",
            status_code=400,
        )
    if not code or not state_value:
        return HTMLResponse(
            "<h1>Dominion Publisher Meta authorization failed</h1><p>Missing code or state.</p>",
            status_code=400,
        )
    try:
        candidates = meta_binding.complete_callback(code=code, state=state_value)
    except (ValueError, PermissionError, RuntimeError) as exc:
        safe = html.escape(str(exc), quote=True)
        return HTMLResponse(
            f"<h1>Dominion Publisher Meta authorization failed</h1><p>{safe}</p>",
            status_code=400,
        )
    rows = "".join(
        "<li>"
        + html.escape(item["page_name"], quote=True)
        + " — Facebook Page "
        + html.escape(item["page_id"], quote=True)
        + (
            " — Instagram " + html.escape(item["instagram_account_id"], quote=True)
            if item.get("instagram_account_id")
            else " — no linked Instagram professional account returned"
        )
        + "</li>"
        for item in candidates
    )
    return_url = html.escape(f"{FRONTEND_PUBLIC_URL}/publisher?meta=authorized", quote=True)
    return HTMLResponse(
        "<h1>Dominion Publisher authorization received</h1>"
        "<p>No account has been bound or published yet. Explicit approval is still required.</p>"
        f"<ul>{rows}</ul>"
        f'<p><a href="{return_url}">Return to Dominion Control to review and approve one Page</a></p>'
    )


@app.get("/oauth/meta/candidates")
def meta_candidates(
    x_operator_token: str | None = Header(default=None, alias="X-Operator-Token"),
) -> dict:
    _require_operator(x_operator_token)
    return {"candidates": vault.pending_meta_safe()}


@app.post("/oauth/meta/bind")
def bind_meta_account(
    payload: MetaBindInput,
    x_operator_token: str | None = Header(default=None, alias="X-Operator-Token"),
    x_human_approval: str | None = Header(default=None, alias="X-Human-Approval"),
) -> dict:
    _require_operator(x_operator_token)
    if x_human_approval != "APPROVED":
        raise HTTPException(status_code=403, detail="explicit human approval header is required")
    try:
        binding = vault.bind_page(page_id=payload.page_id, approved_by=payload.approved_by)
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"status": "BOUND", "binding": binding}


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
