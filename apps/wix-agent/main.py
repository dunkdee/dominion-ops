import os
import json
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.responses import JSONResponse, FileResponse
from pydantic import BaseModel

import wix_client as wix
import sync_engine as sync
import fulfillment as fulfill

app = FastAPI(title="Wix Agent", version="1.0.0")

LOG_DIR = Path(__file__).parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

CATALOG_VERSION = None  # cached after first detection


def _catalog_version() -> str:
    global CATALOG_VERSION
    if CATALOG_VERSION is None:
        CATALOG_VERSION = wix.detect_catalog_version()
    return CATALOG_VERSION


class FixRequest(BaseModel):
    product_ids: list[str]
    dry_run: bool = False


# ─── Health & Status ─────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "wix-agent",
        "version": "1.0.0",
        "site_id": wix.WIX_SITE_ID,
        "catalog_version": _catalog_version(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ─── Inventory Audit ─────────────────────────────────────────────────────────

@app.get("/audit")
def audit_inventory():
    """
    Read-only audit: returns all products with broken inventory vs Zendrop stock.
    Does NOT write anything to Wix. Review this output before calling /sync/fix.
    """
    try:
        report = sync.audit_inventory(_catalog_version())
        return JSONResponse(content=report)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─── Sync ─────────────────────────────────────────────────────────────────────

def _run_sync_bg():
    try:
        sync.full_sync(_catalog_version())
    except Exception as e:
        print(f"[sync] background error: {e}")


@app.post("/sync")
def trigger_sync(background_tasks: BackgroundTasks):
    """
    Trigger a full automated sync in the background.
    Zendrop IN_STOCK → fix Wix. No manual confirmation needed for automated runs.
    """
    background_tasks.add_task(_run_sync_bg)
    return {"status": "sync started", "timestamp": datetime.now(timezone.utc).isoformat()}


@app.post("/sync/fix")
def fix_specific_products(req: FixRequest):
    """
    Fix inventory for specific confirmed product IDs only.
    Body: {"product_ids": ["id1", "id2"], "dry_run": false}
    Requires an audit first — fetches fresh audit to get inventory item details.
    """
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


# ─── Orders & Fulfillment ─────────────────────────────────────────────────────

@app.get("/orders")
def get_orders():
    """List all unfulfilled Wix orders."""
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
    """
    Submit unfulfilled Wix orders to Zendrop and check pending orders for tracking.
    Runs in background. Safe to call repeatedly — already-submitted orders are skipped.
    """
    background_tasks.add_task(_run_fulfill_bg)
    return {"status": "fulfillment cycle started", "timestamp": datetime.now(timezone.utc).isoformat()}


@app.get("/fulfillments/status")
def fulfillment_status():
    """Summary of fulfillment DB: how many orders in each state."""
    try:
        return fulfill.get_fulfillment_summary()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─── Dashboard ───────────────────────────────────────────────────────────────

@app.get("/dashboard")
def dashboard():
    """
    Revenue + operations summary.
    Pulls live data from Wix orders and fulfillment DB.
    """
    try:
        orders = wix.get_orders(fulfillment_status="NOT_FULFILLED")
        fulfill_summary = fulfill.get_fulfillment_summary()

        total_unfulfilled = len(orders)
        total_submitted = fulfill_summary.get("submitted", 0)
        total_fulfilled = fulfill_summary.get("fulfilled", 0)

        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "site_id": wix.WIX_SITE_ID,
            "catalog_version": _catalog_version(),
            "orders": {
                "unfulfilled": total_unfulfilled,
                "submitted_to_zendrop": total_submitted,
                "fulfilled_with_tracking": total_fulfilled,
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


# ─── Log Access ───────────────────────────────────────────────────────────────

@app.get("/logs")
def list_logs():
    """List all change log files (inventory audits, fix logs)."""
    files = sorted(LOG_DIR.glob("*.json"), reverse=True)
    return {
        "count": len(files),
        "files": [f.name for f in files],
    }


@app.get("/logs/{filename}")
def get_log(filename: str):
    """Download a specific log file by name."""
    path = LOG_DIR / filename
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="Log file not found")
    if not str(path.resolve()).startswith(str(LOG_DIR.resolve())):
        raise HTTPException(status_code=400, detail="Invalid path")
    return FileResponse(path, media_type="application/json", filename=filename)
