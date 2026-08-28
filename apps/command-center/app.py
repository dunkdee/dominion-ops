from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from intelligence import route_intelligence
from revenue import record_funnel_event, revenue_state
from runtime_state import runtime_state as canonical_runtime_state

# The read-only Alpaca paper bridge is additive. If it cannot load, the
# Command Center must still serve every pre-existing surface, so the failure is
# recorded and reported rather than raised at import time.
try:
    from trading_api import router as trading_router

    TRADING_BRIDGE_IMPORT_ERROR: str | None = None
except Exception as exc:  # noqa: BLE001 - must never break the live service
    trading_router = None
    TRADING_BRIDGE_IMPORT_ERROR = f"{type(exc).__name__}: {exc}"

APP_DIR = Path(__file__).resolve().parent
VAULT_PATH = Path(os.getenv("VAULT_PATH", "/vault"))
MEMORY_PATH = Path(os.getenv("MEMORY_PATH", "/data/memory"))
LANE_POLICY_PATH = Path(os.getenv("LANE_POLICY_PATH", "/governance/lane_access_policy.json"))
NEMOTRON_BASE_URL = os.getenv("NEMOTRON_BASE_URL", "").rstrip("/")
NEMOTRON_MODEL = os.getenv("NEMOTRON_MODEL", "nemotron-3")

app = FastAPI(title="Dominion Command Center", version="1.0.0")

if trading_router is not None:
    app.include_router(trading_router)


BUDDY_VOICE_SCRIPT = r"""
<script id="buddy-voice-runtime">
(() => {
  const synth = window.speechSynthesis;
  const supported = !!(synth && window.SpeechSynthesisUtterance);
  const stateKey = 'dominion.buddy.voice.enabled';
  let enabled = localStorage.getItem(stateKey) !== 'off';
  let selectedVoice = null;

  const scoreVoice = (voice) => {
    const name = String(voice.name || '').toLowerCase();
    const lang = String(voice.lang || '').toLowerCase();
    let score = 0;
    if (lang === 'en-us') score += 100;
    else if (lang.startsWith('en-')) score += 40;
    if (/guy|davis|christopher|eric|andrew|aaron|roger|male/.test(name)) score += 18;
    if (/natural|online|neural|premium/.test(name)) score += 8;
    return score;
  };

  const refreshVoice = () => {
    if (!supported) return;
    const voices = synth.getVoices();
    selectedVoice = voices.slice().sort((a, b) => scoreVoice(b) - scoreVoice(a))[0] || null;
  };

  const speak = (text) => {
    if (!supported || !enabled || !text) return;
    synth.cancel();
    const utterance = new SpeechSynthesisUtterance(text);
    refreshVoice();
    if (selectedVoice) utterance.voice = selectedVoice;
    utterance.lang = (selectedVoice && selectedVoice.lang) || 'en-US';
    utterance.rate = 0.96;
    utterance.pitch = 0.82;
    utterance.volume = 1.0;
    synth.speak(utterance);
  };

  const install = () => {
    const chat = document.getElementById('chat');
    const head = document.querySelector('.chathead');
    if (!chat || !head) return;

    const control = document.createElement('button');
    control.type = 'button';
    control.id = 'buddyVoiceToggle';
    control.setAttribute('aria-pressed', String(enabled));
    control.style.marginLeft = 'auto';
    control.style.border = '1px solid rgba(244,214,124,.58)';
    control.style.background = '#171006';
    control.style.color = '#f4d67c';
    control.style.padding = '8px 10px';
    control.style.fontFamily = 'Georgia, serif';
    control.style.fontSize = '9px';
    control.style.letterSpacing = '.08em';

    const updateLabel = () => {
      control.textContent = supported ? `BUDDY VOICE: ${enabled ? 'ON' : 'OFF'}` : 'BUDDY VOICE: UNSUPPORTED';
      control.setAttribute('aria-pressed', String(enabled));
    };
    updateLabel();
    head.appendChild(control);

    control.addEventListener('click', () => {
      if (!supported) return;
      enabled = !enabled;
      localStorage.setItem(stateKey, enabled ? 'on' : 'off');
      if (!enabled) synth.cancel();
      updateLabel();
    });

    const seen = new WeakSet(Array.from(chat.querySelectorAll('.msg')));
    const observer = new MutationObserver((mutations) => {
      for (const mutation of mutations) {
        for (const node of mutation.addedNodes) {
          if (!(node instanceof HTMLElement)) continue;
          const messages = node.matches('.msg') ? [node] : Array.from(node.querySelectorAll('.msg'));
          for (const message of messages) {
            if (seen.has(message)) continue;
            seen.add(message);
            if (!message.classList.contains('user')) speak(message.textContent.trim());
          }
        }
      }
    });
    observer.observe(chat, {childList: true, subtree: true});
  };

  if (supported) {
    refreshVoice();
    if ('onvoiceschanged' in synth) synth.onvoiceschanged = refreshVoice;
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', install, {once: true});
  else install();
})();
</script>
"""


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
        files = sorted(VAULT_PATH.rglob("*.md"), key=lambda item: item.stat().st_mtime, reverse=True)[:limit]
        for path in files:
            stat = path.stat()
            notes.append({
                "name": path.stem,
                "path": str(path.relative_to(VAULT_PATH)),
                "updated": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
            })
    except OSError:
        return []
    return notes


def _policy_lane_state() -> dict[str, Any]:
    if not LANE_POLICY_PATH.exists():
        return {"connected": False, "governing_name": "RADAH MEMSHALAH — רָדָה מֶמְשָׁלָה", "open_count": 0, "registered_count": 0, "lanes": []}
    try:
        policy = json.loads(LANE_POLICY_PATH.read_text(encoding="utf-8"))
        lane_map = policy.get("lanes", {})
        lanes = [
            {
                "slug": slug,
                "name": slug.replace("_", " ").title(),
                "internal_work_open": bool(state.get("internal_work_open")),
                "scheduler_eligible": bool(state.get("scheduler_eligible")),
                "external_readiness": "separate_founder_gate",
            }
            for slug, state in lane_map.items()
        ]
        return {
            "connected": True,
            "governing_name": policy.get("governing_name", "RADAH MEMSHALAH — רָדָה מֶמְשָׁלָה"),
            "open_count": sum(1 for lane in lanes if lane["internal_work_open"] and lane["scheduler_eligible"]),
            "registered_count": len(lanes),
            "lanes": lanes,
        }
    except (OSError, ValueError, TypeError):
        return {"connected": False, "governing_name": "RADAH MEMSHALAH — רָדָה מֶמְשָׁלָה", "open_count": 0, "registered_count": 0, "lanes": []}


def lane_state() -> dict[str, Any]:
    snapshot = canonical_runtime_state()
    live = snapshot.get("lanes", {}) if isinstance(snapshot, dict) else {}
    if snapshot.get("connected") and live.get("connected"):
        return {
            "connected": True,
            "governing_name": live.get("governing_name", "RADAH MEMSHALAH — רָדָה מֶמְשָׁלָה"),
            "open_count": int(live.get("open", 0) or 0),
            "registered_count": int(live.get("registered", 0) or 0),
            "lanes": live.get("items", []),
        }
    return _policy_lane_state()


def build_context() -> str:
    recent = list_recent_notes(limit=5)
    note_lines = [f"- {item['name']} ({item['path']})" for item in recent]
    revenue = revenue_state()
    lanes = lane_state()
    runtime = canonical_runtime_state()
    metrics = revenue.get("metrics", {})
    return "\n".join([
        "Mission: Build Dominion into an elite, truthful, scalable, AI-operated business ecosystem.",
        "Operating order: cash flow, systems, scale.",
        "Founder retains final authority over consequential external effects.",
        f"Lane state: {lanes['open_count']} of {lanes['registered_count']} registered lanes open for bounded internal production.",
        f"Revenue runtime: {revenue['vertical_status']}.",
        f"Revenue constraint: {revenue.get('constraint')}.",
        f"Revenue metrics: visitors={metrics.get('visitors')} clicks={metrics.get('clicks')} purchases={metrics.get('purchases')} revenue_usd={metrics.get('revenue_usd')}.",
        f"Runtime evidence observed_at: {runtime.get('observed_at')}.",
        "Recent Obsidian notes:",
        *(note_lines or ["- No readable notes available."]),
    ])


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


def _system_summary(runtime: dict[str, Any]) -> dict[str, str]:
    summary: dict[str, str] = {}
    systems = runtime.get("systems", {}) if isinstance(runtime.get("systems"), dict) else {}
    for name, state in systems.items():
        if not isinstance(state, dict):
            summary[name] = "unavailable"
        elif "active" in state:
            summary[name] = "online" if state.get("active") else state.get("active_state", "not_verified")
        else:
            summary[name] = "online" if state.get("ok") else "not_verified"
    summary["nemotron"] = "configured" if NEMOTRON_BASE_URL else "awaiting_worker"
    summary["conductor_fallback"] = "configured"
    return summary


def _missions(constraint: str, revenue: dict[str, Any]) -> list[dict[str, str]]:
    first = {
        "QUALIFIED_TRAFFIC": "Drive qualified traffic into the live VoltEdge experiment",
        "OFFER_ENGAGEMENT": "Improve experiment offer engagement and CTA response",
        "PURCHASE_CONVERSION": "Diagnose click-to-purchase conversion friction",
        "STATISTICAL_EVIDENCE": "Accumulate clean purchase evidence until the winner gate resolves",
        "COMPOUND_WINNER": "Compound the verified winner and prepare the next controlled experiment",
    }.get(constraint, "Restore authoritative revenue runtime evidence")
    missions = [{"title": first, "state": "active"}]
    if revenue.get("active_experiment_count", 0):
        missions.append({"title": "Keep revenue attribution and evaluator receipts current", "state": "active"})
    missions.append({"title": "Keep all 11 internal production lanes schedulable", "state": "active"})
    missions.append({"title": "Surface consequential external effects for Founder action", "state": "governed"})
    return missions


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request) -> HTMLResponse:
    prefix = request.headers.get("x-forwarded-prefix", "").strip().rstrip("/")
    if prefix and (not prefix.startswith("/") or ".." in prefix):
        prefix = ""
    html = (APP_DIR / "index.html").read_text(encoding="utf-8")
    api_base = json.dumps(prefix)
    marker = "<script>\nconst $="
    replacement = f"<script>\nconst API_BASE={api_base};\nconst $="
    if marker not in html:
        raise HTTPException(status_code=500, detail="command-center-ui-marker-missing")
    html = html.replace(marker, replacement, 1)
    html = html.replace("fetch('/api/status'", "fetch(API_BASE+'/api/status'", 1)
    html = html.replace("fetch('/api/chat'", "fetch(API_BASE+'/api/chat'", 1)
    if "</body>" not in html:
        raise HTTPException(status_code=500, detail="command-center-body-marker-missing")
    html = html.replace("</body>", BUDDY_VOICE_SCRIPT + "\n</body>", 1)
    return HTMLResponse(content=html, headers={"Cache-Control": "no-store"})


def trading_bridge_state() -> dict[str, Any]:
    """Non-secret mount state for the read-only paper trading bridge."""
    if trading_router is None:
        return {
            "mounted": False,
            "read_only": True,
            "live_trading_enabled": False,
            "error": TRADING_BRIDGE_IMPORT_ERROR,
        }
    import alpaca_bridge

    config = alpaca_bridge.bridge_config()
    return {
        "mounted": True,
        "mode": config["mode"],
        "read_only": True,
        "live_trading_enabled": False,
        "order_execution_enabled": False,
        "credentials_present": config["credentials_present"],
        "authenticated": True,
        "prefix": "/api/trading/paper",
    }


@app.get("/health")
def health() -> dict[str, Any]:
    revenue = revenue_state()
    lanes = lane_state()
    runtime = canonical_runtime_state()
    return {
        "status": "ok",
        "service": "dominion-command-center",
        "version": app.version,
        "time": utc_now(),
        "truth_source_connected": bool(runtime.get("connected")),
        "truth_observed_at": runtime.get("observed_at"),
        "release_sha": runtime.get("release_sha"),
        "vault_connected": VAULT_PATH.exists(),
        "memory_writable": MEMORY_PATH.exists() and os.access(MEMORY_PATH, os.W_OK),
        "lane_policy_connected": lanes["connected"],
        "open_lane_count": lanes["open_count"],
        "registered_lane_count": lanes["registered_count"],
        "autopilot_connected": bool(runtime.get("autopilot", {}).get("connected")),
        "nemotron_configured": bool(NEMOTRON_BASE_URL),
        "nemotron_model": NEMOTRON_MODEL,
        "revenue_vertical_status": revenue["vertical_status"],
        "revenue_runtime_connected": revenue["runtime_connected"],
        "revenue_constraint": revenue["constraint"],
        "active_experiment_count": revenue["active_experiment_count"],
        "buddy_voice_surface": True,
        "buddy_voice_engine": "browser-speech-synthesis",
        "trading_bridge": trading_bridge_state(),
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
    return {"accepted": True, "authoritative": False, "event": saved}


@app.get("/api/status")
def status() -> dict[str, Any]:
    runtime = canonical_runtime_state()
    revenue = revenue_state()
    lanes = lane_state()
    metrics = revenue.get("metrics", {})
    founder_holds = runtime.get("founder_holds", []) if isinstance(runtime.get("founder_holds"), list) else []
    autopilot = runtime.get("autopilot", {}) if isinstance(runtime.get("autopilot"), dict) else {}
    receipts = runtime.get("latest_receipts", []) if isinstance(runtime.get("latest_receipts"), list) else []
    public_receipts = [{"source": item.get("source"), "name": item.get("name"), "observed_at": item.get("observed_at")} for item in receipts if isinstance(item, dict)]
    return {
        "time": utc_now(),
        "truth": {
            "connected": bool(runtime.get("connected")),
            "observed_at": runtime.get("observed_at"),
            "release_sha": runtime.get("release_sha"),
            "rule": "Current production state requires timestamped runtime receipts.",
        },
        "governing_name": lanes["governing_name"],
        "systems": _system_summary(runtime),
        "lane_summary": {
            "open": lanes["open_count"],
            "registered": lanes["registered_count"],
            "all_open": lanes["registered_count"] > 0 and lanes["open_count"] == lanes["registered_count"],
        },
        "lanes": lanes["lanes"],
        "autopilot": autopilot,
        "sprint": {
            "focus": revenue.get("constraint"),
            "revenue": metrics.get("revenue_usd"),
            "traffic": metrics.get("visitors"),
            "clicks": metrics.get("clicks"),
            "purchases": metrics.get("purchases"),
            "active_experiments": revenue.get("active_experiment_count"),
            "founder_holds": len(founder_holds),
        },
        "recent_notes": list_recent_notes(),
        "missions": _missions(str(revenue.get("constraint")), revenue),
        "revenue": revenue,
        "founder_holds": founder_holds,
        "latest_receipts": public_receipts,
        "buddy": {
            "voice_surface": True,
            "voice_engine": "browser-speech-synthesis",
            "voice_default": "on",
            "register": "natural Black American conversational; slang when appropriate; no caricature",
        },
    }


@app.post("/api/chat")
def chat(body: ChatRequest) -> dict[str, Any]:
    routed = route_intelligence(body.message, build_context())
    if routed:
        answer = str(routed["answer"])
        source = str(routed["source"])
        record_exchange(body.message, answer, source)
        return {
            "answer": answer,
            "source": source,
            "time": utc_now(),
            "speaker": "Buddy",
            "voice": "enabled",
        }
    answer = (
        "Command Center is online, but neither the Nemotron primary worker nor the "
        "Conductor fallback responded. The command was not marked complete. Check "
        "NEMOTRON_BASE_URL and CONDUCTOR_URL, then retry."
    )
    record_exchange(body.message, answer, "command-center-fallback")
    return {
        "answer": answer,
        "source": "command-center-fallback",
        "time": utc_now(),
        "speaker": "Buddy",
        "voice": "enabled",
    }
