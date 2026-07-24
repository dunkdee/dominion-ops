from __future__ import annotations

import os
import shutil
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from .routes_public import router as public_router
from .routes_worker import router as worker_router
from .state import APP_NAME, DATA_DIR, DB_PATH, WORKER_TOKEN, init_storage, utc_now
from .worker_loop import start as start_worker
from .worker_loop import stop as stop_worker


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    init_storage()
    start_worker()
    try:
        yield
    finally:
        stop_worker()


app = FastAPI(title=APP_NAME, version="0.1.0", lifespan=lifespan)
app.include_router(public_router)
app.include_router(worker_router)


@app.get("/", response_class=HTMLResponse)
def home() -> str:
    return (Path(__file__).parent / "static" / "index.html").read_text(encoding="utf-8")


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": APP_NAME, "time": utc_now()}


@app.get("/ready")
def ready() -> dict:
    checks = {
        "database": DB_PATH.exists(),
        "ffmpeg": shutil.which("ffmpeg") is not None,
        "ffprobe": shutil.which("ffprobe") is not None,
        "data_writable": os.access(DATA_DIR, os.W_OK),
    }
    return {
        "status": "ready" if all(checks.values()) else "degraded",
        "checks": checks,
        "external_worker_configured": bool(WORKER_TOKEN),
    }
