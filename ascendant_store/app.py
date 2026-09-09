"""
Ascendant Digital -- Digital Products Storefront
FastAPI + Stripe + Affiliate Monetization
Port: 5090
"""
import os, json, stripe
import datetime as _dt

DEAD_LETTER_LOG = "/home/malachisingleton8/logs/stripe_dead_letter.jsonl"

def _dead_letter(event_id, event_type, payload_preview, error):
    import json as _json
    entry = {
        "timestamp": _dt.datetime.utcnow().isoformat(),
        "event_id": event_id,
        "event_type": event_type,
        "error": str(error),
        "payload_preview": str(payload_preview)[:200],
    }
    try:
        with open(DEAD_LETTER_LOG, "a") as dlf:
            dlf.write(_json.dumps(entry) + "\n")
    except Exception as e2:
        print("[DEAD-LETTER] CRITICAL cannot write: " + str(e2))
    print("[DEAD-LETTER] STRIPE FAIL: " + event_id + " | " + event_type + " | " + str(error))


from pathlib import Path
from datetime import datetime
from fastapi import FastAPI, Request, Form
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from filelock import FileLock, Timeout

load_dotenv(Path.home() / ".env")

STRIPE_KEY = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_PUB = os.getenv("STRIPE_PUBLISHABLE_KEY", "")
DOMAIN = os.getenv("ASCENDANT_DOMAIN", "https://ascendantdigital.store")

# Conversion tracking. Unset means no analytics script is emitted at all --
# an absent measurement id must not produce a broken tag or a silent 404.
GA4_MEASUREMENT_ID = os.getenv("GA4_MEASUREMENT_ID", "").strip()
stripe.api_key = STRIPE_KEY

app = FastAPI(title="Ascendant Digital", docs_url=None, redoc_url=None)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

BASE = Path(__file__).parent
app.mount("/static", StaticFiles(directory=str(BASE / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE / "templates"))

# ── Product Catalog ────────────────────────────────────────────
PRODUCTS = [
    {
        "id": "word-search-golden-years",
        "name": "Golden Years Word Search: 50 Large Print Puzzles",
        "description": "50 themed large-print word search puzzles designed for relaxation and mental sharpness. Perfect gift for seniors.",
        "price": 997,  # cents
        "price_display": "$9.97",
        "category": "puzzles",
        "image": "/static/img/word-search.png",
        "affiliate_tag": "ascendant-20",
        "kdp_asin": "",
        "purchasable": False,
    },
    {
        "id": "sovereign-mind-journal",
        "name": "Sovereign Mind: 90-Day Gratitude & Goal Journal",
        "description": "Transform your mindset in 90 days with daily gratitude prompts, goal setting, and evening reflections.",
        "price": 1497,
        "price_display": "$14.97",
        "category": "wellness",
        "image": "/static/img/journal.png",
        "affiliate_tag": "ascendant-20",
        "kdp_asin": "",
        "purchasable": False,
    },
    {
        "id": "debt-freedom-planner",
        "name": "Debt Freedom Planner: Your Path to Financial Liberation",
        "description": "Complete debt payoff system with budgets, snowball trackers, and milestone celebrations.",
        "price": 1297,
        "price_display": "$12.97",
        "category": "finance",
        "image": "/static/img/planner.png",
        "affiliate_tag": "ascendant-20",
        "kdp_asin": "",
        "purchasable": False,
    },

    {
        "id": "divine-sovereignty",
        "name": "Divine Sovereignty: The Path to Freedom, Healing & Wealth",
        "description": "The definitive guide to financial, legal, and spiritual sovereignty. By Dewayne Singleton.",
        "price": 1900,
        "price_display": "$19.00",
        "category": "books",
        "image": "/static/img/divine-sovereignty.png",
        "affiliate_tag": "ascendant-20",
        "kdp_asin": "",
        "stripe_price_id": "price_1TcQzTHmqf1u43pdS24ngA0z",
        "purchasable": True,
    },
]

# ── Affiliate Tools (recurring commission products) ────────────
AFFILIATE_TOOLS = [
    {
        "name": "NordVPN",
        "description": "Protect your privacy online. #1 rated VPN.",
        "url": "https://nordvpn.com",
        "commission": "40% + 30% renewals",
        "category": "privacy",
    },
    {
        "name": "Jasper AI",
        "description": "AI writing assistant for content creators.",
        "url": "https://jasper.ai",
        "commission": "30% recurring",
        "category": "ai-tools",
    },
    {
        "name": "Bluehost",
        "description": "Start your website today. Reliable hosting.",
        "url": "https://bluehost.com",
        "commission": "$65+ per sale",
        "category": "hosting",
    },
]

# ── Email capture storage ──────────────────────────────────────
LEADS_FILE = BASE / "email_leads.json"
LEADS_LOCK = FileLock(str(LEADS_FILE) + ".lock", timeout=5)



def save_lead(email: str, source: str = "store") -> bool:
    try:
        with LEADS_LOCK:
            if LEADS_FILE.exists():
                with LEADS_FILE.open("r", encoding="utf-8") as handle:
                    leads = json.load(handle)
                if not isinstance(leads, list):
                    raise ValueError("email lead store root must be a list")
                st = LEADS_FILE.stat()
                uid, gid, mode = st.st_uid, st.st_gid, st.st_mode & 0o777
            else:
                leads = []
                uid, gid, mode = os.getuid(), os.getgid(), 0o600

            leads.append({
                "email": email,
                "source": source,
                "ts": datetime.utcnow().isoformat(),
            })

            temp = LEADS_FILE.parent / f".{LEADS_FILE.name}.{os.getpid()}.tmp"
            try:
                with temp.open("w", encoding="utf-8") as handle:
                    json.dump(leads, handle, indent=2)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.chmod(temp, mode)
                os.chown(temp, uid, gid)
                os.replace(temp, LEADS_FILE)
                try:
                    fd = os.open(str(LEADS_FILE.parent), os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
                    try:
                        os.fsync(fd)
                    finally:
                        os.close(fd)
                except OSError:
                    pass
            finally:
                if temp.exists():
                    try:
                        temp.unlink()
                    except OSError:
                        pass
        return True
    except (json.JSONDecodeError, OSError, Timeout, TypeError, ValueError) as exc:
        print(f"[LEADS] governed write blocked: {type(exc).__name__}")
        return False



# ── Routes ─────────────────────────────────────────────────────

@app.get("/")
async def home(request: Request):
    return templates.TemplateResponse(request, "index.html", {
        "products": PRODUCTS,
        "tools": AFFILIATE_TOOLS,
        "ga4_id": GA4_MEASUREMENT_ID,
    })


@app.get("/product/{product_id}")
async def product_detail(request: Request, product_id: str):
    product = next((p for p in PRODUCTS if p["id"] == product_id), None)
    if not product:
        return RedirectResponse("/")
    return templates.TemplateResponse(request, "product.html", {
        "product": product,
        "stripe_pub": STRIPE_PUB,
        "ga4_id": GA4_MEASUREMENT_ID,
    })


@app.post("/api/checkout")
async def create_checkout(request: Request):
    data = await request.json()
    product_id = data.get("product_id")
    product = next((p for p in PRODUCTS if p["id"] == product_id), None)
    if not product:
        return JSONResponse({"error": "Product not found"}, 400)

    if not product.get("purchasable", False):
        return JSONResponse({"error": "Product is not currently available for checkout."}, 409)

    if not STRIPE_KEY:
        return JSONResponse({"error": "Payments not configured"}, 503)

    utm_source   = str(data.get("utm_source")   or "").strip() or None
    utm_medium   = str(data.get("utm_medium")   or "").strip() or None
    utm_campaign = str(data.get("utm_campaign") or "").strip() or None
    utm_content  = str(data.get("utm_content")  or "").strip() or None

    metadata = {"product_id": product_id}
    if utm_source:   metadata["utm_source"]   = utm_source
    if utm_medium:   metadata["utm_medium"]   = utm_medium
    if utm_campaign: metadata["utm_campaign"] = utm_campaign
    if utm_content:  metadata["utm_content"]  = utm_content

    session = stripe.checkout.Session.create(
        payment_method_types=["card"],
        line_items=[{
            "price_data": {
                "currency": "usd",
                "product_data": {"name": product["name"]},
                "unit_amount": product["price"],
            },
            "quantity": 1,
        }],
        mode="payment",
        success_url=f"{DOMAIN}/success?product={product_id}",
        cancel_url=f"{DOMAIN}/product/{product_id}",
        metadata=metadata,
    )
    return JSONResponse({"url": session.url})


@app.get("/success")
async def success(request: Request, product: str | None = None):
    """Post-purchase page.

    The product id arrives as a query parameter from the Stripe success_url, so
    the conversion event can name what was bought. It is looked up against the
    catalogue rather than trusted: a tampered id resolves to None and the page
    still renders, it simply reports no product.
    """
    known = next((p for p in PRODUCTS if p["id"] == product), None)
    return templates.TemplateResponse(request, "success.html", {
        "ga4_id": GA4_MEASUREMENT_ID,
        "product": known,
    })


@app.get("/policies")
async def policies(request: Request):
    return templates.TemplateResponse(request, "policies.html", {
        "ga4_id": GA4_MEASUREMENT_ID,
    })


@app.post("/api/subscribe")

async def email_subscribe(email: str = Form(...)):
    if not save_lead(email, "newsletter"):
        return JSONResponse({"error": "Lead store unavailable"}, 503)
    return RedirectResponse("/?subscribed=1", status_code=303)



@app.get("/health")
async def health():
    return {"status": "ok", "service": "ascendant-digital", "products": len(PRODUCTS)}




# ── Database connection ────────────────────────────────────────
import psycopg2

def _get_db():
    return psycopg2.connect(
        host="127.0.0.1", port=5432,
        dbname="dominion", user="dominion",
        password=os.getenv("DB_PASSWORD", ""),
    )

STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")



def _send_fulfillment_email(to_email, product_id, product_name):
    """Send purchase confirmation + download link for digital products."""

    download_links = {
        "divine-sovereignty": "https://drive.google.com/file/d/1lrKrJAsyyYXV_yRk1tJtS9N1j5F09Sge/view",
    }
    link = download_links.get(product_id, "")
    subject = f"Your copy of {product_name} is ready"
    body = f"""<!DOCTYPE html>
<html><body style="font-family:Georgia,serif;max-width:600px;margin:0 auto;padding:20px;color:#2d2d2d;">
<h2 style="color:#d4af37;">Thank you for your purchase!</h2>
<p>Your copy of <strong>{product_name}</strong> is ready.</p>
<p style="text-align:center;margin:25px 0;">
<a href="{link}" style="background:linear-gradient(135deg,#d4af37,#a07830);color:#000;padding:14px 28px;text-decoration:none;border-radius:6px;font-weight:bold;">Download Your Book</a></p>
<p>If you have any questions, reply to this email.</p>
<p>The pillars stand. The mission advances.</p>
<p><strong>Dewayne Singleton</strong><br>Dominion Healing</p>
</body></html>"""
    try:
        import smtplib
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart
        gmail_addr = os.getenv("EMAIL_ADDRESS", "")
        gmail_pass = os.getenv("EMAIL_PASSWORD", "")
        if gmail_addr and gmail_pass:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = gmail_addr
            msg["To"] = to_email
            msg.attach(MIMEText(body, "html"))
            with smtplib.SMTP("smtp.gmail.com", 587) as srv:
                srv.starttls()
                srv.login(gmail_addr, gmail_pass)
                srv.send_message(msg)
            print(f"[FULFILLMENT] Sent to {to_email} for {product_id}")
        else:
            print(f"[FULFILLMENT] No email creds -- logged for {to_email}")
    except Exception as e:
        print(f"[FULFILLMENT] Error sending to {to_email}: {e}")


@app.post("/webhook/stripe")
async def stripe_webhook(request: Request):
    """Handle Stripe webhook events -- records payments to DB."""
    payload = await request.body()
    sig = request.headers.get("stripe-signature", "")

    try:
        event = stripe.Webhook.construct_event(
            payload, sig, STRIPE_WEBHOOK_SECRET
        )
    except stripe.error.SignatureVerificationError:
        return JSONResponse({"error": "Invalid signature"}, 400)
    except Exception as e:
        return JSONResponse({"error": str(e)}, 400)

    # Record raw event
    try:
        conn = _get_db()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO stripe_events (stripe_event_id, event_type, payload_json) VALUES (%s, %s, %s) ON CONFLICT (stripe_event_id) DO NOTHING",
            (event["id"], event["type"], json.dumps(event["data"]))
        )
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        _dead_letter(
            event.get("id", "UNKNOWN"),
            event.get("type", "UNKNOWN"),
            payload.decode("utf-8", errors="replace")[:500],
            e
        )

    # Process checkout.session.completed
    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        email = session.get("customer_details", {}).get("email", "")
        amount = session.get("amount_total", 0)
        pi = session.get("payment_intent", "")
        sid = session.get("id", "")

        meta = session.get("metadata", {})
        product_id   = meta.get("product_id", "")
        utm_source   = meta.get("utm_source")   or None
        utm_medium   = meta.get("utm_medium")   or None
        utm_campaign = meta.get("utm_campaign") or None
        utm_content  = meta.get("utm_content")  or None

        product_name = ""
        if not product_id:
            # Match by amount
            for p in PRODUCTS:
                if p["price"] == amount:
                    product_id = p["id"]
                    product_name = p["name"]
                    break

        try:
            conn = _get_db()
            cur = conn.cursor()
            cur.execute(
                """INSERT INTO orders (stripe_session_id, stripe_payment_intent, customer_email, product_id, product_name, amount_cents, currency, utm_source, utm_medium, utm_campaign, utm_content)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                   ON CONFLICT (stripe_session_id) WHERE stripe_session_id IS NOT NULL DO NOTHING""",
                (sid, pi, email, product_id, product_name, amount, session.get("currency", "usd"),
                 utm_source, utm_medium, utm_campaign, utm_content)
            )
            conn.commit()
            cur.close()
            conn.close()
            print(f"[ORDER] {email} | ${amount/100:.2f} | {product_name or product_id}")
        except Exception as e:
            _dead_letter(sid, event["type"], str(session)[:200], e)

        # Fulfill digital product
        if email and product_id:
            _send_fulfillment_email(email, product_id, product_name)

        # Save lead from purchase
        if email:
            save_lead(email, "purchase")

    return JSONResponse({"received": True})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5090)
