import os
import json
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, BackgroundTasks, HTTPException, Query
from fastapi.responses import JSONResponse, FileResponse
from pydantic import BaseModel

import wix_client as wix
import sync_engine as sync
import fulfillment as fulfill
import store_setup as store

app = FastAPI(title="Wix Agent", version="2.0.0")

LOG_DIR = Path(__file__).parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

CATALOG_VERSION = None


def _catalog_version() -> str:
    global CATALOG_VERSION
    if CATALOG_VERSION is None:
        CATALOG_VERSION = wix.detect_catalog_version()
    return CATALOG_VERSION


class FixRequest(BaseModel):
    product_ids: list[str]
    dry_run: bool = False


# ── Core ───────────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "wix-agent",
        "version": "2.0.0",
        "site_id": wix.WIX_SITE_ID,
        "catalog_version": _catalog_version(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ── Inventory ──────────────────────────────────────────────────────────────────

@app.get("/audit")
def audit_inventory():
    try:
        return JSONResponse(content=sync.audit_inventory(_catalog_version()))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def _run_sync_bg():
    try:
        sync.full_sync(_catalog_version())
    except Exception as e:
        print(f"[sync] background error: {e}")


@app.post("/sync")
def trigger_sync(background_tasks: BackgroundTasks):
    background_tasks.add_task(_run_sync_bg)
    return {"status": "sync started", "timestamp": datetime.now(timezone.utc).isoformat()}


@app.post("/sync/fix")
def fix_specific_products(req: FixRequest):
    try:
        report = sync.audit_inventory(_catalog_version())
        broken = report["broken"]
        result = sync.fix_inventory(
            wix_items=broken,
            confirmed_product_ids=req.product_ids,
            catalog_version=_catalog_version(),
            dry_run=req.dry_run,
        )
        return JSONResponse(content=result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Orders & Fulfillment ───────────────────────────────────────────────────────

@app.get("/orders")
def get_orders():
    try:
        orders = wix.get_orders(fulfillment_status="NOT_FULFILLED")
        return {
            "count": len(orders),
            "orders": orders,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def _run_fulfill_bg():
    try:
        fulfill.run_fulfillment_cycle(_catalog_version())
        fulfill.check_pending_fulfillments(_catalog_version())
    except Exception as e:
        print(f"[fulfill] background error: {e}")


@app.post("/fulfill")
def trigger_fulfillment(background_tasks: BackgroundTasks):
    background_tasks.add_task(_run_fulfill_bg)
    return {"status": "fulfillment cycle started", "timestamp": datetime.now(timezone.utc).isoformat()}


@app.get("/fulfillments/status")
def fulfillment_status():
    try:
        return fulfill.get_fulfillment_summary()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Dashboard ──────────────────────────────────────────────────────────────────

@app.get("/dashboard")
def dashboard():
    try:
        orders = wix.get_orders(fulfillment_status="NOT_FULFILLED")
        fulfill_summary = fulfill.get_fulfillment_summary()
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "site_id": wix.WIX_SITE_ID,
            "catalog_version": _catalog_version(),
            "orders": {
                "unfulfilled": len(orders),
                "submitted_to_zendrop": fulfill_summary.get("submitted", 0),
                "fulfilled_with_tracking": fulfill_summary.get("fulfilled", 0),
            },
            "fulfillment_db": fulfill_summary,
            "recent_unfulfilled_orders": [
                {
                    "id": o.get("id"),
                    "number": o.get("number"),
                    "buyer_email": o.get("buyerInfo", {}).get("email"),
                    "created_date": o.get("createdDate"),
                    "price": o.get("priceSummary", {}).get("total", {}).get("formattedAmount"),
                }
                for o in orders[:10]
            ],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Store Setup ────────────────────────────────────────────────────────────────

@app.get("/store/audit")
def store_audit():
    """Full store health check — pages, policies, product quality."""
    try:
        return JSONResponse(content=store.audit_store(_catalog_version()))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def _run_store_setup_bg():
    try:
        store.full_store_setup(_catalog_version())
    except Exception as e:
        print(f"[store-setup] error: {e}")


@app.post("/store/setup")
def trigger_store_setup(background_tasks: BackgroundTasks):
    """Run full store setup: policies, pages, product descriptions, SEO."""
    background_tasks.add_task(_run_store_setup_bg)
    return {"status": "store setup started", "timestamp": datetime.now(timezone.utc).isoformat()}


@app.post("/store/setup/products")
def setup_products(dry_run: bool = Query(default=True)):
    """Enhance product descriptions and SEO. dry_run=true to preview changes."""
    try:
        return JSONResponse(content=store.enhance_products(_catalog_version(), dry_run=dry_run))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/store/pages")
def store_pages_content():
    """Return all policy page HTML content — paste into Wix Editor for each page."""
    return {
        p["slug"]: {"title": p["title"], "url": f"https://voltedgegoods.com/{p['slug']}", "html": p["content"]}
        for p in store.PAGES_TO_CREATE
    }


@app.post("/store/policies")
def update_policies_only():
    """Update checkout policies in Wix store settings only."""
    try:
        return JSONResponse(content=store.setup_store_policies())
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Logs ───────────────────────────────────────────────────────────────────────

@app.get("/logs")
def list_logs():
    files = sorted(LOG_DIR.glob("*.json"), reverse=True)
    return {"count": len(files), "files": [f.name for f in files]}


@app.get("/logs/{filename}")
def get_log(filename: str):
    path = LOG_DIR / filename
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="Log file not found")
    if not str(path.resolve()).startswith(str(LOG_DIR.resolve())):
        raise HTTPException(status_code=400, detail="Invalid path")
    return FileResponse(path, media_type="application/json", filename=filename)
