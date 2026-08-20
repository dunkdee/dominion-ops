#!/usr/bin/env python3
from flask import Flask, request, jsonify
import json
import threading
from pathlib import Path

app = Flask(__name__)

BASE = Path("/home/malachisingleton8/buddy_core")
LOG = BASE / "buddy_bridge.log"
DEALS = BASE / "scored_deals.json"

def log(x):
    with LOG.open("a", encoding="utf-8") as f:
        f.write(str(x) + "\n")

@app.get("/health")
def health():
    return jsonify(ok=True, service="buddy_bridge", port=5052)

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
    data = request.get_json(silent=True) or {}
    command = (data.get("command") or "").strip()
    if not command:
        return jsonify(error="no command"), 400
    log("[COMMAND] " + command)
    return jsonify(status="received", command=command)

@app.post("/webhook/conductor")
def conductor_webhook():
    data = request.get_json(silent=True) or {}
    log("[CONDUCTOR] " + json.dumps(data, ensure_ascii=False))
    return jsonify(status="received", service="buddy_bridge", route="conductor")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5052)
