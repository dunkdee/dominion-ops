from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from intelligence import route_intelligence

APP_DIR = Path(__file__).resolve().parent
VAULT_PATH = Path(os.getenv("VAULT_PATH", "/vault"))
MEMORY_PATH = Path(os.getenv("MEMORY_PATH", "/data/memory"))
NEMOTRON_BASE_URL = os.getenv("NEMOTRON_BASE_URL", "").rstrip("/")
NEMOTRON_MODEL = os.getenv("NEMOTRON_MODEL", "nemotron-3")

app = FastAPI(title="Dominion Command Center", version="0.2.0")


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=8000)


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
    return "\n".join(
        [
            "Mission: Build Dominion into an elite, truthful, scalable, AI-operated business ecosystem.",
            "Operating order: cash flow, systems, scale.",
            "Founder retains final authority.",
            "Current focus: launch the first revenue vertical and close the traffic-to-revenue loop.",
            "Recent Obsidian notes:",
            *(note_lines or ["- No readable notes available."]),
        ]
    )


def record_exchange(message: str, answer: str, source: str) -> None:
    try:
        MEMORY_PATH.mkdir(parents=True, exist_ok=True)
        day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        path = MEMORY_PATH / f"command-center-{day}.jsonl"
        entry = {
            "time": utc_now(),
            "message": message,
            "answer": answer,
            "source": source,
        }
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        pass


@app.get("/")
def dashboard() -> FileResponse:
    return FileResponse(APP_DIR / "index.html")


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "service": "dominion-command-center",
        "version": app.version,
        "time": utc_now(),
        "vault_connected": VAULT_PATH.exists(),
        "memory_writable": MEMORY_PATH.exists() and os.access(MEMORY_PATH, os.W_OK),
        "nemotron_configured": bool(NEMOTRON_BASE_URL),
        "nemotron_model": NEMOTRON_MODEL,
    }


@app.get("/api/status")
def status() -> dict[str, Any]:
    return {
        "time": utc_now(),
        "systems": {
            "command_center": "online",
            "obsidian": "online" if VAULT_PATH.exists() else "unavailable",
            "metatron": "configured",
            "nemotron": "configured" if NEMOTRON_BASE_URL else "awaiting_worker",
            "conductor": "fallback_ready",
            "memory": "online" if MEMORY_PATH.exists() else "initializing",
        },
        "sprint": {
            "day": 1,
            "focus": "First revenue vertical and traffic loop",
            "revenue": 0,
            "traffic": 0,
            "published": 0,
            "approvals": 0,
        },
        "recent_notes": list_recent_notes(),
        "missions": [
            {"title": "Connect Nemotron primary worker", "state": "active"},
            {"title": "Feed Dominion mission and operating memory", "state": "active"},
            {"title": "Launch first revenue vertical", "state": "queued"},
            {"title": "Close research-create-publish-measure loop", "state": "queued"},
        ],
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
