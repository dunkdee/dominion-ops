from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


RUNTIME_STATE_PATH = Path(os.getenv("RUNTIME_STATE_PATH", "/runtime/runtime-state.json"))


def _empty() -> dict[str, Any]:
    return {
        "connected": False,
        "observed_at": None,
        "release_sha": None,
        "systems": {},
        "lanes": {"registered": 0, "open": 0, "all_open": False, "items": []},
        "autopilot": {"connected": False},
        "revenue": {
            "connected": False,
            "constraint": "RUNTIME_STATE_UNAVAILABLE",
            "active_experiment_count": 0,
            "experiments": [],
            "totals": {"visitors": None, "clicks": None, "purchases": None, "revenue_cents": None},
        },
        "founder_holds": [],
        "latest_receipts": [],
    }


def runtime_state() -> dict[str, Any]:
    if not RUNTIME_STATE_PATH.is_file():
        return _empty()
    try:
        payload = json.loads(RUNTIME_STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return _empty()
    if not isinstance(payload, dict):
        return _empty()
    payload = dict(payload)
    payload["connected"] = True
    payload.setdefault("systems", {})
    payload.setdefault("lanes", _empty()["lanes"])
    payload.setdefault("autopilot", {"connected": False})
    payload.setdefault("revenue", _empty()["revenue"])
    payload.setdefault("founder_holds", [])
    payload.setdefault("latest_receipts", [])
    return payload
