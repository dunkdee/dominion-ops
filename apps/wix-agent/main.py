import hmac
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

import empire
import fulfillment as fulfill
import store_setup as store
import sync_engine as sync
import wix_client as wix
import zendrop_client as zendrop


LOG_DIR = Path(__file__).parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

OPERATOR_TOKEN = os.getenv("WIX_AGENT_OPERATOR_TOKEN", "")
CATALOG_VERSION = None


@asynccontextmanager
async def lifespan(_: FastAPI):
    fulfill.init_db()
    yield


app = FastAPI(
    title="Wix Agent",
    version="2.1.0",
    docs_url=None,
    redoc_url=None,
    lifespan=lifespan,
)


@app.middleware("http")
async def require_operator_token(request: Request, call_next):
    if request.url.path in {"/health", "/ready"}:
        return await call_next(request)
    if not OPERATOR_TOKEN:
        return JSONResponse(
            status_code=503,
            content={"detail": "Operator access is not configured"},
        )
    supplied = request.headers.get("X-Operator-Token", "")
    if not hmac.compare_digest(supplied, OPERATOR_TOKEN):
        return JSONResponse(status_code=401, content={"detail": "Unauthorized"})
    return await call_next(request)


def _catalog_version() -> str:
    global CATALOG_VERSION
    if CATALOG_VERSION is None:
        CATALOG_VERSION = wix.detect_catalog_version()
    return CATALOG_VERSION


def _readiness() -> dict:
    database = fulfill.database_health()
    fulfillment_mode = fulfill.fulfillment_mode()
    variant_mapping = fulfill.variant_mapping_health()
    integrations = {
        "wix_api_key": bool(wix.WIX_API_KEY),
        "wix_site_id": bool(wix.WIX_SITE_ID),
        "zendrop_api_key": bool(zendrop.ZENDROP_API_KEY),
        "operator_token": bool(OPERATOR_TOKEN),
        "n8n_webhook": bool(empire.N8N_WEBHOOK_URL),
    }
    catalog = {"status": "not_checked", "version": None}
    blockers = []
    if database.get("status") != "ok":
        blockers.append("fulfillment_database")
    for required in (
        "wix_api_key",
        "wix_site_id",
        "operator_token",
    ):
        if not integrations[required]:
            blockers.append(required)
    if fulfillment_mode not in fulfill.VALID_FULFILLMENT_MODES:
        blockers.append("fulfillment_mode")
    if fulfillment_mode == "live":
        if not integrations["zendrop_api_key"]:
            blockers.append("zendrop_api_key")
        if variant_mapping.get("status") != "ok":
            blockers.append("zendrop_variant_mapping")
    if integrations["wix_api_key"] and integrations["wix_site_id"]:
        try:
            catalog_version = _catalog_version()
            catalog = {"status": "ok", "version": catalog_version}
        except Exception as exc:
            catalog = {
                "status": "error",
                "version": None,
                "error_type": exc.__class__.__name__,
            }
            blockers.append("wix_catalog_access")
    return {
        "ready": not blockers,
        "database": database,
        "catalog": catalog,
        "fulfillment": {
            "mode": fulfillment_mode,
            "variant_mapping": variant_mapping,
        },
        "integrations": integrations,
        "blockers": blockers,
    }


class FixRequest(BaseModel):
    product_ids: list[str]
    dry_run: bool = True


# Core


@app.get("/health")
def health():
    readiness = _readiness()
    return {
        "status": "ok" if readiness["ready"] else "degraded",
        "service": "wix-agent",
        "version": "2.1.0",
        **readiness,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/ready")
def ready():
    readiness = _readiness()
    payload = {
        "status": "ready" if readiness["ready"] else "not_ready",
        **readiness,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    return JSONResponse(status_code=200 if readiness["ready"] else 503, content=payload)


# Inventory


@app.get("/audit")
def audit_inventory():
    try:
        return JSONResponse(content=sync.audit_inventory(_catalog_version()))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


def _run_audit_bg():
    try:
        sync.audit_inventory(_catalog_version())
    except Exception as exc:
        print(f"[sync] background audit error: {exc}")


@app.post("/sync")
def trigger_sync(background_tasks: BackgroundTasks):
    background_tasks.add_task(_run_audit_bg)
    return {
        "status": "inventory audit started",
        "note": "No inventory is changed by this endpoint",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.post("/sync/fix")
def fix_specific_products(req: FixRequest):
    try:
        catalog_version = _catalog_version()
        if not req.dry_run:
            raise HTTPException(
                status_code=409,
                detail=(
                    "Inventory writes are disabled until supplier variants are "
                    "mapped explicitly and revision-safe writes are reviewed; "
                    "rerun with dry_run=true"
                ),
            )
        report = sync.audit_inventory(catalog_version)
        result = sync.fix_inventory(
            wix_items=report["broken"],
            confirmed_product_ids=req.product_ids,
            catalog_version=catalog_version,
            dry_run=req.dry_run,
        )
        return JSONResponse(content=result)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# Orders and fulfillment


@app.get("/orders")
def get_orders():
    try:
        orders = wix.get_orders(fulfillment_status="NOT_FULFILLED")
        return {
            "count": len(orders),
            "orders": orders,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


def _run_fulfill_bg():
    try:
        fulfill.run_fulfillment_cycle(_catalog_version())
        fulfill.check_pending_fulfillments(_catalog_version())
    except Exception as exc:
        print(f"[fulfill] background error: {exc}")


@app.post("/fulfill")
def trigger_fulfillment(background_tasks: BackgroundTasks):
    if fulfill.fulfillment_mode() != "live":
        raise HTTPException(
            status_code=409,
            detail=(
                "Automated fulfillment is in record-only mode; use the approved "
                "manual fulfillment runbook"
            ),
        )
    if not zendrop.ZENDROP_API_KEY:
        raise HTTPException(status_code=503, detail="Zendrop integration is not configured")
    background_tasks.add_task(_run_fulfill_bg)
    return {
        "status": "fulfillment cycle started",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/fulfillments/status")
def fulfillment_status():
    try:
        return fulfill.get_fulfillment_summary()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# Dashboard


@app.get("/dashboard")
def dashboard():
    try:
        orders = wix.get_orders(fulfillment_status="NOT_FULFILLED")
        fulfill_summary = fulfill.get_fulfillment_summary()
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "catalog_version": _catalog_version(),
            "orders": {
                "unfulfilled": len(orders),
                "submitted_to_zendrop": fulfill_summary.get("submitted", 0),
                "fulfilled_with_tracking": fulfill_summary.get("fulfilled", 0),
            },
            "fulfillment_db": fulfill_summary,
            "recent_unfulfilled_orders": [
                {
                    "id": order.get("id"),
                    "number": order.get("number"),
                    "created_date": order.get("createdDate"),
                    "price": order.get("priceSummary", {})
                    .get("total", {})
                    .get("formattedAmount"),
                }
                for order in orders[:10]
            ],
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# Store audit


@app.get("/store/audit")
def store_audit():
    try:
        return JSONResponse(content=store.audit_store(_catalog_version()))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# Logs


@app.get("/logs")
def list_logs():
    files = sorted(LOG_DIR.glob("*.json"), reverse=True)
    return {"count": len(files), "files": [path.name for path in files]}


@app.get("/logs/{filename}")
def get_log(filename: str):
    path = LOG_DIR / filename
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="Log file not found")
    if not str(path.resolve()).startswith(str(LOG_DIR.resolve())):
        raise HTTPException(status_code=400, detail="Invalid path")
    return FileResponse(path, media_type="application/json", filename=filename)
