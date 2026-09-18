from __future__ import annotations

import hashlib
import hmac
import html
import os
import re
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel, Field

from .attribution_bridge import AttributionBridgeStore
from .core import deterministic_variant
from .evaluator import load_policy, run_cycle
from .store import RevenueStore
from . import wix_adapter

POLICY = load_policy()
DB_PATH = Path(os.getenv("DOMINION_REVENUE_DB", str(Path.home() / ".dominion/revenue-runtime/revenue.db"))).expanduser()
STORE = RevenueStore(DB_PATH)
BRIDGE = AttributionBridgeStore(DB_PATH)
OPERATOR_TOKEN = os.getenv("WIX_AGENT_OPERATOR_TOKEN", "")
COOKIE_NAME = POLICY["traffic"]["cookie_name"]
COOKIE_MAX_AGE = int(POLICY["traffic"]["cookie_days"]) * 86400
VID_RE = re.compile(r"^[a-f0-9]{32}$")
VOLT_EDGE_ORIGINS = ["https://www.voltedgegoods.com", "https://voltedgegoods.com"]


def _signing_key() -> bytes:
    path = Path(os.getenv("DOMINION_REVENUE_SIGNING_KEY_FILE", str(Path.home() / ".dominion/revenue-runtime/signing.key"))).expanduser()
    try:
        data = path.read_bytes().strip()
    except OSError as exc:
        raise RuntimeError("revenue signing key unavailable") from exc
    if len(data) < 32:
        raise RuntimeError("revenue signing key too short")
    return data


def _signature(exp_id: str, visitor_id: str, variant: str) -> str:
    msg = f"{exp_id}:{visitor_id}:{variant}".encode("utf-8")
    return hmac.new(_signing_key(), msg, hashlib.sha256).hexdigest()


def _authorized(request: Request) -> bool:
    if not OPERATOR_TOKEN:
        return False
    supplied = request.headers.get("X-Operator-Token", "")
    if not supplied:
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            supplied = auth[7:]
    return hmac.compare_digest(supplied, OPERATOR_TOKEN)


def _require_auth(request: Request) -> None:
    if not OPERATOR_TOKEN:
        raise HTTPException(status_code=503, detail="Operator access is not configured")
    if not _authorized(request):
        raise HTTPException(status_code=401, detail="Unauthorized")


def _guard_text(value: str) -> None:
    lowered = value.lower()
    for fragment in POLICY["copy_guard"]["forbidden_fragments"]:
        if fragment.lower() in lowered:
            raise HTTPException(status_code=422, detail=f"copy guard rejected fragment: {fragment}")
    if len(value) > int(POLICY["wix"]["max_plain_description_chars"]):
        raise HTTPException(status_code=422, detail="copy exceeds governed length")


def _variant_guard(value: dict[str, Any]) -> None:
    required = {"headline", "body_text", "cta_text", "wix_value"}
    if set(value) != required:
        raise HTTPException(status_code=422, detail="variant fields must be headline, body_text, cta_text, wix_value")
    for key in required:
        if not isinstance(value[key], str) or not value[key].strip():
            raise HTTPException(status_code=422, detail=f"variant field invalid: {key}")
        _guard_text(value[key])
    if len(value["headline"]) > 140 or len(value["cta_text"]) > 60:
        raise HTTPException(status_code=422, detail="headline or CTA exceeds governed length")


def _target_guard(url: str) -> None:
    parsed = urlparse(url)
    allowed = set(POLICY["traffic"]["allowed_target_hosts"])
    if parsed.scheme != "https" or parsed.hostname not in allowed:
        raise HTTPException(status_code=422, detail="target URL is outside governed VoltEdge hosts")


def _tracked_target(url: str, exp_id: str, variant: str, bridge_token: str) -> str:
    parsed = urlparse(url)
    pairs = dict(parse_qsl(parsed.query, keep_blank_values=True))
    pairs.update({
        "utm_source": "dominion_revenue",
        "utm_medium": "experiment",
        "utm_campaign": exp_id,
        "utm_content": variant,
        "dr_token": bridge_token,
    })
    return urlunparse(parsed._replace(query=urlencode(pairs)))


class ExperimentCreate(BaseModel):
    id: str | None = None
    name: str = Field(min_length=3, max_length=120)
    product_id: str = Field(min_length=1, max_length=64)
    target_url: str
    success_event: str = "purchase"
    wix_field: str = "plainDescription"
    treatment_pct: int = 50
    auto_promote: bool = True
    control: dict[str, Any]
    treatment: dict[str, Any]


class ServerEvent(BaseModel):
    id: str = Field(min_length=4, max_length=160)
    experiment_id: str
    visitor_id: str
    variant: str
    event_type: str
    revenue_cents: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)


class WixFlowBridge(BaseModel):
    token: str = Field(min_length=32, max_length=256)
    purchase_flow_id: str = Field(default="", max_length=64)
    checkout_id: str = Field(default="", max_length=64)
    order_id: str = Field(default="", max_length=64)


app = FastAPI(title="Dominion Revenue Runtime", version="1.1.0", docs_url=None, redoc_url=None)
app.add_middleware(
    CORSMiddleware,
    allow_origins=VOLT_EDGE_ORIGINS,
    allow_credentials=False,
    allow_methods=["POST", "OPTIONS"],
    allow_headers=["Content-Type"],
)


@app.get("/health")
def health() -> dict[str, Any]:
    enabled = os.getenv(POLICY["kill_switch"]["environment_variable"], "0") == POLICY["kill_switch"]["enabled_value"]
    return {
        "status": "ok",
        "mode": POLICY["mode"],
        "execution_enabled": enabled,
        "automatic_price_changes": False,
        "automatic_paid_spend": False,
        "experiments": len(STORE.list_experiments()),
    }


@app.get("/r/{experiment_id}", response_class=HTMLResponse)
def offer(experiment_id: str, request: Request):
    try:
        exp = STORE.get_experiment(experiment_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Experiment not found") from exc
    if exp["status"] != "active":
        raise HTTPException(status_code=409, detail="Experiment is not active")
    visitor_id = request.cookies.get(COOKIE_NAME, "")
    if not VID_RE.match(visitor_id):
        visitor_id = uuid.uuid4().hex
    variant = deterministic_variant(experiment_id, visitor_id, int(exp["treatment_pct"]))
    copy = exp[variant]
    sig = _signature(experiment_id, visitor_id, variant)
    event_id = "imp:" + hashlib.sha256(f"{experiment_id}:{visitor_id}".encode()).hexdigest()
    STORE.record_event(
        event_id=event_id,
        experiment_id=experiment_id,
        visitor_id=visitor_id,
        variant=variant,
        event_type="impression",
        metadata={"source": "revenue_router"},
    )
    click_url = f"/r/{experiment_id}/click?vid={visitor_id}&variant={variant}&sig={sig}"
    page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(copy['headline'])} | VoltEdge</title>
<style>body{{margin:0;background:#090a0c;color:#f5f1e8;font:16px/1.55 system-ui,sans-serif}}main{{max-width:760px;margin:0 auto;padding:64px 24px}}.eyebrow{{letter-spacing:.16em;text-transform:uppercase;color:#c6a65b;font-size:12px}}h1{{font-size:clamp(36px,7vw,64px);line-height:1.02;margin:16px 0 24px}}.copy{{font-size:18px;color:#d9d5cc;white-space:pre-line}}a{{display:inline-block;margin-top:28px;padding:15px 22px;background:#e7c66f;color:#111;text-decoration:none;border-radius:14px;font-weight:750}}small{{display:block;margin-top:32px;color:#8f8b82}}</style></head>
<body><main><div class="eyebrow">VoltEdge · governed offer experiment</div><h1>{html.escape(copy['headline'])}</h1><div class="copy">{html.escape(copy['body_text'])}</div><a href="{html.escape(click_url, quote=True)}">{html.escape(copy['cta_text'])}</a><small>Secure checkout is completed on VoltEdge.</small></main></body></html>"""
    response = HTMLResponse(page)
    response.set_cookie(COOKIE_NAME, visitor_id, max_age=COOKIE_MAX_AGE, httponly=True, secure=True, samesite="lax")
    response.headers["Cache-Control"] = "no-store"
    response.headers["Content-Security-Policy"] = "default-src 'none'; style-src 'unsafe-inline'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"
    response.headers["X-Robots-Tag"] = "noindex, nofollow"
    return response


@app.get("/r/{experiment_id}/click")
def click(experiment_id: str, vid: str, variant: str, sig: str):
    if not VID_RE.match(vid) or variant not in {"control", "treatment"}:
        raise HTTPException(status_code=400, detail="Invalid experiment identity")
    if not hmac.compare_digest(sig, _signature(experiment_id, vid, variant)):
        raise HTTPException(status_code=401, detail="Invalid experiment signature")
    try:
        exp = STORE.get_experiment(experiment_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Experiment not found") from exc
    expected = deterministic_variant(experiment_id, vid, int(exp["treatment_pct"]))
    if expected != variant or exp["status"] != "active":
        raise HTTPException(status_code=409, detail="Experiment assignment is not active")
    event_id = "click:" + hashlib.sha256(f"{experiment_id}:{vid}".encode()).hexdigest()
    STORE.record_event(
        event_id=event_id,
        experiment_id=experiment_id,
        visitor_id=vid,
        variant=variant,
        event_type="click",
        metadata={"source": "revenue_router"},
    )
    bridge_token = BRIDGE.issue_token(experiment_id=experiment_id, visitor_id=vid, variant=variant)
    return RedirectResponse(_tracked_target(exp["target_url"], experiment_id, variant, bridge_token), status_code=302)


@app.post("/r/{experiment_id}/bridge")
def wix_flow_bridge(experiment_id: str, payload: WixFlowBridge):
    try:
        result = BRIDGE.bind_token(
            token=payload.token,
            expected_experiment_id=experiment_id,
            purchase_flow_id=payload.purchase_flow_id,
            checkout_id=payload.checkout_id,
            order_id=payload.order_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"status": "accepted", "experiment_id": experiment_id, "bound": result["bound"]}


@app.post("/revenue/events")
def server_event(payload: ServerEvent, request: Request):
    _require_auth(request)
    if payload.event_type not in {"add_to_cart", "checkout", "purchase", "refund"}:
        raise HTTPException(status_code=422, detail="Unsupported server event")
    try:
        exp = STORE.get_experiment(payload.experiment_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Experiment not found") from exc
    expected = deterministic_variant(payload.experiment_id, payload.visitor_id, int(exp["treatment_pct"]))
    if payload.variant != expected:
        raise HTTPException(status_code=409, detail="Variant does not match deterministic assignment")
    inserted = STORE.record_event(
        event_id=payload.id,
        experiment_id=payload.experiment_id,
        visitor_id=payload.visitor_id,
        variant=payload.variant,
        event_type=payload.event_type,
        revenue_cents=payload.revenue_cents,
        metadata=payload.metadata,
    )
    return {"status": "accepted" if inserted else "duplicate", "id": payload.id}


@app.post("/control/experiments")
def create_experiment(payload: ExperimentCreate, request: Request):
    _require_auth(request)
    if payload.treatment_pct > int(POLICY["traffic"]["max_treatment_percent"]):
        raise HTTPException(status_code=422, detail="Treatment allocation exceeds policy")
    if payload.wix_field not in POLICY["wix"]["allowed_product_fields"]:
        raise HTTPException(status_code=422, detail="Wix field is not allowlisted")
    if payload.auto_promote and payload.success_event != POLICY["attribution"]["auto_promotion_requires_success_event"]:
        raise HTTPException(status_code=422, detail="Automatic promotion requires purchase evidence")
    _target_guard(payload.target_url)
    _variant_guard(payload.control)
    _variant_guard(payload.treatment)
    try:
        created = STORE.create_experiment(payload.model_dump())
    except Exception as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return created


@app.post("/control/experiments/{experiment_id}/activate")
def activate(experiment_id: str, request: Request):
    _require_auth(request)
    try:
        return STORE.activate(experiment_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Experiment not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/control/experiments/{experiment_id}/pause")
def pause(experiment_id: str, request: Request):
    _require_auth(request)
    try:
        return STORE.pause(experiment_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Experiment not found") from exc


@app.get("/control/experiments/{experiment_id}")
def experiment_status(experiment_id: str, request: Request):
    _require_auth(request)
    try:
        return {"experiment": STORE.get_experiment(experiment_id), "metrics": STORE.metrics(experiment_id)}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Experiment not found") from exc


@app.post("/control/evaluate")
def evaluate(request: Request):
    _require_auth(request)
    return run_cycle(DB_PATH)


@app.post("/control/experiments/{experiment_id}/rollback")
def rollback(experiment_id: str, request: Request):
    _require_auth(request)
    try:
        promo = STORE.latest_promotion_for_experiment(experiment_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Active promotion receipt not found") from exc
    mutation = wix_adapter.rollback_plain_description(promo["product_id"], promo["before_value"])
    updated = STORE.mark_rolled_back(promo["id"], mutation["after_revision"])
    return {"status": "ROLLED_BACK", "promotion": updated, "wix_revision": mutation["after_revision"]}


@app.exception_handler(RuntimeError)
def runtime_error(_: Request, exc: RuntimeError):
    return JSONResponse(status_code=503, content={"detail": type(exc).__name__})
