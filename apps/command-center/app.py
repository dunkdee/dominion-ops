from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib import request

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

APP_DIR = Path(__file__).resolve().parent
VAULT_PATH = Path(os.getenv("VAULT_PATH", "/vault"))
CONDUCTOR_URL = os.getenv("CONDUCTOR_URL", "http://host.docker.internal:5060").rstrip("/")

app = FastAPI(title="Dominion Command Center", version="0.1.0")


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


def conductor_chat(message: str) -> dict[str, Any] | None:
    payload = json.dumps({"message": message, "source": "dominion-command-center"}).encode()
    candidates = ("/chat", "/api/chat", "/invoke")
    for endpoint in candidates:
        try:
            req = request.Request(
                f"{CONDUCTOR_URL}{endpoint}",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with request.urlopen(req, timeout=45) as response:
                body = response.read().decode("utf-8")
                parsed = json.loads(body)
                return parsed if isinstance(parsed, dict) else {"response": str(parsed)}
        except Exception:
            continue
    return None


@app.get("/")
def dashboard() -> FileResponse:
    return FileResponse(APP_DIR / "index.html")


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "service": "dominion-command-center",
        "time": utc_now(),
        "vault_connected": VAULT_PATH.exists(),
    }


@app.get("/api/status")
def status() -> dict[str, Any]:
    return {
        "time": utc_now(),
        "systems": {
            "command_center": "online",
            "obsidian": "online" if VAULT_PATH.exists() else "unavailable",
            "metatron": "configured",
            "conductor": "checking_on_chat",
        },
        "sprint": {
            "day": 1,
            "focus": "Store offers, digital products, and traffic",
            "revenue": 0,
            "traffic": 0,
            "published": 0,
            "approvals": 0,
        },
        "recent_notes": list_recent_notes(),
        "missions": [
            {"title": "Activate profitable offers", "state": "active"},
            {"title": "Launch traffic content loop", "state": "queued"},
            {"title": "Connect live revenue telemetry", "state": "queued"},
        ],
    }


@app.post("/api/chat")
def chat(body: ChatRequest) -> dict[str, Any]:
    routed = conductor_chat(body.message)
    if routed:
        answer = routed.get("response") or routed.get("answer") or routed.get("message")
        return {
            "answer": answer or json.dumps(routed),
            "source": "conductor",
            "time": utc_now(),
        }

    return {
        "answer": (
            "Command Center is online, but the reasoning router is not connected yet. "
            "I received your command and preserved the interface. Connect CONDUCTOR_URL "
            "to enable full Dominion intelligence and tool routing."
        ),
        "source": "command-center-fallback",
        "time": utc_now(),
    }
