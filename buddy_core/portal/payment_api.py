"""
portal/payment_api.py — Dominion Healing Payment API
Handles Stripe payment intents for the storefront.
Port: 5080
"""
import os, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import stripe
import uvicorn

from dotenv import load_dotenv
load_dotenv(dotenv_path=Path.home() / "buddy_core" / ".env")
load_dotenv(dotenv_path=Path.home() / "conductor" / ".env")

stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
app = FastAPI(title="Dominion Store", docs_url=None)

@app.post("/api/create-payment-intent")
async def create_payment_intent(request: Request):
    body = await request.json()
    amount = body.get("amount", 0)  # in cents
    if amount < 100:  # minimum $1
        return JSONResponse({"error": "Invalid amount"}, status_code=400)
    try:
        intent = stripe.PaymentIntent.create(
            amount=amount,
            currency="usd",
            metadata={"source": "dominion_storefront"}
        )
        return JSONResponse({"clientSecret": intent.client_secret})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

@app.post("/api/subscribe")
async def subscribe(request: Request):
    body = await request.json()
    email = body.get("email", "")
    if not email or "@" not in email:
        return JSONResponse({"error": "Invalid email"}, status_code=400)
    # Log to file for now (can wire to Mailchimp/n8n later)
    from utils.safe_io import atomic_json_write, load_json
    subs_file = Path.home() / "buddy_core" / "subscribers.json"
    subs = load_json(subs_file, default=[])
    from datetime import datetime
    subs.append({"email": email, "ts": datetime.utcnow().isoformat()})
    atomic_json_write(subs_file, subs, default=str)
    return JSONResponse({"status": "subscribed"})

# ── AI Advisor Endpoints ──────────────────────────────────────

@app.post("/api/alchemist")
async def alchemist_query(request: Request):
    """Forward health question to Alchemist via four-part protocol."""
    body = await request.json()
    query = body.get("query", "").strip()
    if not query:
        return JSONResponse({"error": "Empty query"}, status_code=400)
    try:
        from core.alchemist_protocol import AlchemistProtocol
        ap = AlchemistProtocol()
        result = ap.run(task=query, task_type="health_query", rollback_path="No action - advisory only")
        outcome = result.get("outcome")
        if outcome == "VETOED":
            return JSONResponse({"protocol": "This question was flagged by our safety review. Please rephrase or consult a healthcare professional."})
        if outcome == "ESCALATE":
            return JSONResponse({"protocol": "This question needs additional review. Please try a more specific question."})
        action_result = result.get("action_result", {})
        return JSONResponse({"protocol": action_result.get("response", "No response generated."), "status": "ok"})
    except Exception as e:
        # Fallback to direct brain.ask
        try:
            from core.brain import ask
            resp = ask(f"You are Alchemist, a holistic health intelligence. Wellness education only, not medical advice. Answer: {query}")
            return JSONResponse({"protocol": resp, "status": "ok"})
        except Exception:
            return JSONResponse({"protocol": "Service temporarily unavailable.", "status": "error"})


@app.post("/api/juris")
async def juris_query(request: Request):
    """Forward legal question to Juris via four-part protocol."""
    body = await request.json()
    query = body.get("query", "").strip()
    if not query:
        return JSONResponse({"error": "Empty query"}, status_code=400)
    try:
        from core.juris_protocol import JurisProtocol
        jp = JurisProtocol()
        result = jp.run(task=query, task_type="legal_query", rollback_path="No action - advisory only")
        outcome = result.get("outcome")
        if outcome == "VETOED":
            return JSONResponse({"response": "This question is outside our scope. Juris covers trust formation, FDCPA, and FCRA only."})
        if outcome == "ESCALATE":
            return JSONResponse({"response": "This question needs additional review. Please try a more specific question."})
        action_result = result.get("action_result", {})
        resp = action_result.get("response")
        if resp is None:
            return JSONResponse({"response": action_result.get("reason", "Question out of scope.")})
        return JSONResponse({"response": resp, "status": "ok"})
    except Exception as e:
        try:
            from core.brain import ask
            resp = ask(f"You are Juris, legal intelligence. Trust formation, FDCPA, FCRA only. General info, not legal advice. Answer: {query}")
            return JSONResponse({"response": resp, "status": "ok"})
        except Exception:
            return JSONResponse({"response": "Service temporarily unavailable.", "status": "error"})


# ── TikTok OAuth Callback ─────────────────────────────────────

@app.get("/api/tiktok/callback")
async def tiktok_callback(request: Request):
    """Handle TikTok OAuth redirect — exchange code for token."""
    code = request.query_params.get("code", "")
    if not code:
        return JSONResponse({"error": "No code received"}, status_code=400)
    try:
        from agents.tiktok_api_agent import exchange_code
        result = exchange_code(code)
        if "access_token" in result:
            return HTMLResponse("<html><body style='background:#080d09;color:#c9a22a;font-family:sans-serif;display:flex;align-items:center;justify-content:center;height:100vh;text-align:center'><div><h1>TikTok Connected</h1><p>You can close this window.</p></div></body></html>")
        return JSONResponse({"error": "Token exchange failed", "details": result}, status_code=500)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


# Serve storefront
PORTAL_DIR = Path(__file__).resolve().parent

@app.get("/")
async def index():
    return FileResponse(PORTAL_DIR / "storefront.html")

@app.get("/{path:path}")
async def catch_all(path: str):
    f = PORTAL_DIR / path
    if f.exists() and f.is_file():
        return FileResponse(f)
    return FileResponse(PORTAL_DIR / "storefront.html")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=5080, log_level="info")
