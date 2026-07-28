from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from intelligence import route_intelligence
from revenue import record_funnel_event, revenue_state

APP_DIR = Path(__file__).resolve().parent
VAULT_PATH = Path(os.getenv("VAULT_PATH", "/vault"))
MEMORY_PATH = Path(os.getenv("MEMORY_PATH", "/data/memory"))
NEMOTRON_BASE_URL = os.getenv("NEMOTRON_BASE_URL", "").rstrip("/")
NEMOTRON_MODEL = os.getenv("NEMOTRON_MODEL", "nemotron-3")

app = FastAPI(title="Dominion Command Center", version="0.3.0")


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=8000)


class FunnelEvent(BaseModel):
    event_type: str = Field(min_length=1, max_length=40)
    offer_slug: str = Field(min_length=1, max_length=100)
    source: str = Field(default="unknown", max_length=120)
    value_usd: float = Field(default=0, ge=0)
    external_id: str = Field(default="", max_length=200)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def list_recent_notes(limit: int = 8) -> list[dict[str, Any]]:
    if not VAULT_PATH.exists():
        return []
    notes: list[dict[str, Any]] = []
    try:
        files = sorted(
            VAULT_PATH.rglob("*.md"),
            key=lambda item: item.stat().st_mtime,
            reverse=True,
        )[:limit]
        for path in files:
            stat = path.stat()
            notes.append(
                {
                    "name": path.stem,
                    "path": str(path.relative_to(VAULT_PATH)),
                    "updated": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
                }
            )
    except OSError:
        return []
    return notes


def build_context() -> str:
    recent = list_recent_notes(limit=5)
    note_lines = [f"- {item['name']} ({item['path']})" for item in recent]
    revenue = revenue_state()
    return "\n".join(
        [
            "Mission: Build Dominion into an elite, truthful, scalable, AI-operated business ecosystem.",
            "Operating order: cash flow, systems, scale.",
            "Founder retains final authority.",
            "Current focus: launch Dominion digital products and close the traffic-to-revenue loop.",
            f"Revenue vertical status: {revenue['vertical_status']} with {revenue['ready_offer_count']} ready offers.",
            "Recent Obsidian notes:",
            *(note_lines or ["- No readable notes available."]),
        ]
    )


def record_exchange(message: str, answer: str, source: str) -> None:
    try:
        MEMORY_PATH.mkdir(parents=True, exist_ok=True)
        day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        path = MEMORY_PATH / f"command-center-{day}.jsonl"
        entry = {"time": utc_now(), "message": message, "answer": answer, "source": source}
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        pass


@app.get("/")
def dashboard() -> FileResponse:
    return FileResponse(APP_DIR / "index.html")


@app.get("/health")
def health() -> dict[str, Any]:
    revenue = revenue_state()
    return {
        "status": "ok",
        "service": "dominion-command-center",
        "version": app.version,
        "time": utc_now(),
        "vault_connected": VAULT_PATH.exists(),
        "memory_writable": MEMORY_PATH.exists() and os.access(MEMORY_PATH, os.W_OK),
        "nemotron_configured": bool(NEMOTRON_BASE_URL),
        "nemotron_model": NEMOTRON_MODEL,
        "revenue_vertical_status": revenue["vertical_status"],
        "ready_offer_count": revenue["ready_offer_count"],
    }


@app.get("/api/revenue")
def revenue() -> dict[str, Any]:
    return revenue_state()


@app.post("/api/revenue/events")
def revenue_event(body: FunnelEvent) -> dict[str, Any]:
    try:
        saved = record_funnel_event(MEMORY_PATH, body.model_dump())
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"accepted": True, "event": saved}


@app.get("/api/status")
def status() -> dict[str, Any]:
    revenue = revenue_state()
    return {
        "time": utc_now(),
        "systems": {
            "command_center": "online",
            "obsidian": "online" if VAULT_PATH.exists() else "unavailable",
            "metatron": "configured",
            "nemotron": "configured" if NEMOTRON_BASE_URL else "awaiting_worker",
            "conductor": "fallback_ready",
            "memory": "online" if MEMORY_PATH.exists() else "initializing",
            "revenue_loop": revenue["vertical_status"],
        },
        "sprint": {
            "day": 1,
            "focus": "Dominion digital products revenue loop",
            "revenue": 0,
            "traffic": 0,
            "published": 0,
            "approvals": 0,
            "ready_offers": revenue["ready_offer_count"],
        },
        "recent_notes": list_recent_notes(),
        "missions": [
            {"title": "Connect Nemotron primary worker", "state": "active"},
            {"title": "Configure verified checkout and delivery", "state": "active"},
            {"title": "Publish tracked traffic campaigns", "state": "blocked" if not revenue["ready_offer_count"] else "queued"},
            {"title": "Verify purchase-to-delivery telemetry", "state": "blocked" if not revenue["ready_offer_count"] else "queued"},
        ],
        "revenue": revenue,
    }


@app.post("/api/chat")
def chat(body: ChatRequest) -> dict[str, Any]:
    routed = route_intelligence(body.message, build_context())
    if routed:
        answer = str(routed["answer"])
        source = str(routed["source"])
        record_exchange(body.message, answer, source)
        return {"answer": answer, "source": source, "time": utc_now()}

    answer = (
        "Command Center is online, but neither the Nemotron primary worker nor the "
        "Conductor fallback responded. The command was not marked complete. Check "
        "NEMOTRON_BASE_URL and CONDUCTOR_URL, then retry."
    )
    record_exchange(body.message, answer, "command-center-fallback")
    return {"answer": answer, "source": "command-center-fallback", "time": utc_now()}
