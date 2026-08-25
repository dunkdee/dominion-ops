#!/usr/bin/env python3
from flask import Flask, request, jsonify
import hmac
import json
import os
import threading
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=Path.home() / "buddy_core" / ".env")
    load_dotenv(dotenv_path=Path.home() / "conductor" / ".env")
    load_dotenv(dotenv_path=Path.home() / ".env")
except ImportError:
    pass

from core.operator import get_operator
from core.revenue_runtime import (
    MAX_PAYLOAD_BYTES,
    run_compounding_payload,
    run_fast_cash_payload,
)

app = Flask(__name__)

BASE = Path("/home/malachisingleton8/buddy_core")
LOG = BASE / "buddy_bridge.log"
DEALS = BASE / "scored_deals.json"
BUDDY_WEB_TOKEN = os.getenv("BUDDY_WEB_TOKEN", "").strip()


def log(x):
    with LOG.open("a", encoding="utf-8") as f:
        f.write(str(x) + "\n")


def _authorized(req) -> bool:
    """Fail closed. Accept the same bearer token as Buddy web or X-Buddy-Token."""
    if not BUDDY_WEB_TOKEN:
        return False
    supplied = req.headers.get("X-Buddy-Token", "").strip()
    if supplied and hmac.compare_digest(supplied, BUDDY_WEB_TOKEN):
        return True
    auth = req.headers.get("Authorization", "")
    expected = f"Bearer {BUDDY_WEB_TOKEN}"
    return bool(auth) and hmac.compare_digest(auth, expected)


def _governed_revenue_request(runner, lane: str):
    if not _authorized(request):
        return jsonify(error="unauthorized"), 401
    if request.content_length is not None and request.content_length > MAX_PAYLOAD_BYTES:
        return jsonify(status="BLOCKED", error="payload_too_large"), 413
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify(status="BLOCKED", error="JSON object required"), 400
    try:
        result = runner(payload)
        log(
            f"[REVENUE_{lane}] publication_state=DRAFT_SHADOW "
            f"review_hold={result.get('review_hold', False)}"
        )
        return jsonify(result)
    except (KeyError, TypeError, ValueError) as exc:
        log(f"[REVENUE_{lane}_BLOCKED] {type(exc).__name__}")
        return jsonify(
            status="BLOCKED",
            publication_state="DRAFT_SHADOW",
            error=type(exc).__name__,
            detail=str(exc)[:400],
        ), 400
    except Exception as exc:
        log(f"[REVENUE_{lane}_ERROR] {type(exc).__name__}")
        return jsonify(
            status="BLOCKED",
            publication_state="DRAFT_SHADOW",
            error=type(exc).__name__,
        ), 500


@app.get("/health")
def health():
    return jsonify(ok=True, service="buddy_bridge", port=5052, operator="v2")


@app.post("/webhook/wholesale/trigger")
def wholesale_trigger():
    data = request.get_json(silent=True) or {}
    states = data.get("states", ["FL", "TX", "GA", "NC", "OH"])
    dry_run = bool(data.get("dry_run", False))

    def run_log():
        log(f"[WHOLESALE] states={states} dry_run={dry_run}")

    threading.Thread(target=run_log, daemon=True).start()
    return jsonify(status="started", states=states, dry_run=dry_run)


@app.get("/webhook/wholesale/deals")
def wholesale_deals():
    if not DEALS.exists():
        return jsonify(deals=[], count=0)
    try:
        rows = json.loads(DEALS.read_text(encoding="utf-8"))
    except Exception as e:
        return jsonify(error=str(e), deals=[], count=0), 500

    hot = []
    for d in rows:
        try:
            fee = float(d.get("assignment_fee_est", d.get("profit", 0)) or 0)
        except Exception:
            fee = 0
        if fee >= 10000:
            hot.append(d)
    return jsonify(deals=hot, count=len(hot))


@app.post("/webhook/wholesale/notify")
def wholesale_notify():
    data = request.get_json(silent=True) or {}
    message = data.get("message", "")
    log("[N8N] " + str(message))
    return jsonify(status="ok")


@app.post("/webhook/buddy/command")
def buddy_command():
    if not _authorized(request):
        return jsonify(error="unauthorized"), 401
    data = request.get_json(silent=True) or {}
    command = (data.get("command") or "").strip()
    if not command:
        return jsonify(error="no command"), 400
    session_id = (data.get("session_id") or "bridge").strip()[:120]
    simulate = bool(data.get("simulate", False))
    try:
        result = get_operator().handle(command, session_id=session_id, simulate=simulate)
        log(f"[COMMAND] status={result.get('status')} mission={result.get('mission_id','none')}")
        return jsonify(result)
    except Exception as exc:
        log(f"[COMMAND_ERROR] {type(exc).__name__}")
        return jsonify(status="BLOCKED", error=type(exc).__name__), 500


@app.post("/webhook/buddy/revenue/fast-cash")
def buddy_revenue_fast_cash():
    """Return a governed FAST CASH DRAFT_SHADOW package; never publish."""
    return _governed_revenue_request(run_fast_cash_payload, "FAST_CASH")


@app.post("/webhook/buddy/revenue/compounding")
def buddy_revenue_compounding():
    """Return a governed COMPOUNDING DRAFT_SHADOW result; never publish."""
    return _governed_revenue_request(run_compounding_payload, "COMPOUNDING")


@app.post("/webhook/conductor")
def conductor_webhook():
    data = request.get_json(silent=True) or {}
    log("[CONDUCTOR] " + json.dumps(data, ensure_ascii=False))
    return jsonify(status="received", service="buddy_bridge", route="conductor")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5052)
