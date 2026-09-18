from flask import Flask, jsonify, request
import glob, os, requests

from beta import beta_bp

app = Flask(__name__)
app.register_blueprint(beta_bp)

def flag(v):
    return "present" if (v and str(v).strip()) else "missing"

def gumroad_get(path, token, params=None):
    headers = {"Authorization": f"Bearer {token}"}
    return requests.get(
        f"https://api.gumroad.com/v2/{path}",
        headers=headers,
        params=params or {},
        timeout=20,
    )

@app.route("/")
def root():
    return {
        "status": "● Dominion Empire API — LIVE",
        "integrations": {
            "YouTube_API_KEY":    flag(os.getenv("YOUTUBE_API_KEY")),
            "Gumroad_Token":      flag(os.getenv("GUMROAD_TOKEN")),
            "OANDA_Account":      flag(os.getenv("OANDA_ACCOUNT_ID")),
            "BinanceUS_API":      flag(os.getenv("BINANCE_API_KEY")),
            "Brevo_API":          flag(os.getenv("BREVO_API_KEY")),
            "Gemini_VertexAI":    flag(os.getenv("GCP_PROJECT_ID")),
            "Google_Drive":       flag(os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")),
            "Google_Analytics":   flag(os.getenv("GA4_MEASUREMENT_ID")),
        }
    }

@app.route("/gemini")
def gemini_status():
    project = os.getenv("GCP_PROJECT_ID")
    if not project:
        return jsonify(error="GCP_PROJECT_ID not set"), 400
    try:
        import json as _json
        from google import genai
        from google.oauth2 import service_account
        sa_json = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
        location = os.getenv("GCP_REGION", "us-central1")
        if sa_json:
            info = _json.loads(sa_json)
            creds = service_account.Credentials.from_service_account_info(
                info, scopes=["https://www.googleapis.com/auth/cloud-platform"]
            )
            c = genai.Client(vertexai=True, project=project, location=location, credentials=creds)
        else:
            c = genai.Client(vertexai=True, project=project, location=location)
        r = c.models.generate_content(model="gemini-2.5-flash", contents="Reply with one word: ONLINE")
        return jsonify({"status": "connected", "engine": "vertex-ai", "response": r.text.strip()})
    except Exception as e:
        return jsonify({"status": "error", "detail": str(e)}), 500

@app.route("/youtube")
def youtube():
    key = os.getenv("YOUTUBE_API_KEY")
    if not key:
        return jsonify(error="Missing YOUTUBE_API_KEY"), 400
    r = requests.get(
        "https://www.googleapis.com/youtube/v3/videos",
        params={"part": "snippet", "chart": "mostPopular", "maxResults": 1, "key": key},
        timeout=20,
    )
    return jsonify(r.json()), r.status_code

@app.route("/gumroad")
def gumroad():
    token = os.getenv("GUMROAD_TOKEN")
    if not token:
        return jsonify(error="GUMROAD_TOKEN not set"), 400
    r = gumroad_get("products", token)
    data = r.json()
    if not data.get("success"):
        return jsonify(error="Gumroad rejected the token", detail=data.get("message", "unknown")), r.status_code
    products = data.get("products", [])
    return jsonify({
        "success": True,
        "product_count": len(products),
        "products": [
            {
                "name": p.get("name"),
                "published": p.get("published"),
                "price_cents": p.get("price"),
                "sales_count": p.get("sales_count"),
                "url": p.get("short_url"),
            }
            for p in products
        ],
    })

@app.route("/gumroad/sales")
def gumroad_sales():
    token = os.getenv("GUMROAD_TOKEN")
    if not token:
        return jsonify(error="GUMROAD_TOKEN not set"), 400
    r = gumroad_get("sales", token)
    data = r.json()
    if not data.get("success"):
        return jsonify(error="Gumroad rejected the token", detail=data.get("message", "unknown")), r.status_code
    sales = data.get("sales", [])
    total = sum(s.get("price", 0) for s in sales) / 100
    return jsonify({
        "success": True,
        "sale_count": len(sales),
        "total_revenue_usd": round(total, 2),
        "recent_sales": [
            {
                "product": s.get("product_name"),
                "amount_usd": s.get("price", 0) / 100,
                "email": s.get("email"),
                "created_at": s.get("created_at"),
                "refunded": s.get("refunded"),
            }
            for s in sales[:10]
        ],
    })

@app.route("/oanda")
def oanda():
    key  = os.getenv("OANDA_API_KEY")
    acct = os.getenv("OANDA_ACCOUNT_ID")
    if not key or not acct:
        return jsonify(error="Missing OANDA keys"), 400
    url = f"https://api-fxpractice.oanda.com/v3/accounts/{acct}/summary"
    r = requests.get(url, headers={"Authorization": f"Bearer {key}"}, timeout=20)
    return (r.json(), r.status_code)

@app.route("/binance")
def binance():
    r = requests.get("https://api.binance.us/api/v3/time", timeout=20)
    return (r.json(), r.status_code)

@app.route("/ask/juris", methods=["GET", "POST"])
def ask_juris():
    if request.method == "GET":
        return jsonify({
            "agent": "JURIS",
            "status": "legal intelligence online",
            "scope": ["trust_formation", "FDCPA", "FCRA", "surplus_recovery"],
            "usage": "POST {\"query\": \"your legal question\", \"mode\": \"general\"}"
        })
    data = request.get_json(force=True, silent=True) or {}
    query = data.get("query") or data.get("q", "")
    if not query:
        return jsonify(error="query is required"), 400
    mode = data.get("mode", "general")
    try:
        r = requests.post(
            "http://172.17.0.1:5055",
            json={"query": query, "mode": mode},
            timeout=120,
        )
        return jsonify(r.json()), r.status_code
    except Exception as e:
        return jsonify({
            "error": str(e),
            "hint": "Jurist not reachable — check: systemctl status dominion-juris"
        }), 503

@app.route("/vault/inbox", methods=["POST"])
def vault_inbox():
    try:
        from vault_io import create_note
    except ImportError:
        return jsonify(error="vault_io not available — VAULT_PATH not mounted"), 503
    data = request.get_json(force=True, silent=True) or {}
    if not data.get("content"):
        return jsonify(error="content is required"), 400
    path = create_note(
        lane="inbox",
        title=data.get("title", "Untitled"),
        content=data.get("content", ""),
        agent=data.get("agent", "baby-api"),
        note_type=data.get("type", "inbox"),
        tags=data.get("tags", []),
        extra_meta=data.get("meta"),
    )
    return jsonify({"status": "created", "path": path}), 201

@app.route("/vault/inbox", methods=["GET"])
def vault_inbox_list():
    try:
        from vault_io import list_lane
    except ImportError:
        return jsonify(error="vault_io not available"), 503
    status_filter = request.args.get("status")
    notes = list_lane("inbox", status_filter=status_filter)
    return jsonify({"count": len(notes), "notes": notes})

@app.route("/vault/health")
def vault_health():
    vault_path = os.getenv("VAULT_PATH", "/vault")
    if not os.path.isdir(vault_path):
        return jsonify({"vault": "not mounted", "path": vault_path}), 503
    notes = glob.glob(os.path.join(vault_path, "**/*.md"), recursive=True)
    lanes = {}
    for d in os.listdir(vault_path):
        full = os.path.join(vault_path, d)
        if os.path.isdir(full):
            lanes[d] = len([f for f in os.listdir(full) if f.endswith(".md")])
    return jsonify({"vault": "mounted", "path": vault_path, "total_notes": len(notes), "lanes": lanes})

@app.route("/gumroad/ping", methods=["POST"])
def gumroad_ping():
    if request.content_type and "json" in request.content_type:
        data = request.get_json(force=True, silent=True) or {}
    else:
        data = request.form.to_dict()

    sale_id  = data.get("sale_id", "unknown")
    product  = data.get("product_name", "Unknown Product")
    email    = data.get("email", "")
    cents    = int(data.get("price", 0) or 0)
    name     = data.get("full_name", "")
    sale_ts  = data.get("sale_timestamp", "")
    is_test  = str(data.get("test", "false")).lower() == "true"

    content = (
        f"## Sale: {product}\n\n"
        f"- **Sale ID:** {sale_id}\n"
        f"- **Customer:** {name} ({email})\n"
        f"- **Amount:** ${cents / 100:.2f}\n"
        f"- **Timestamp:** {sale_ts}\n"
        f"- **Country:** {data.get('ip_country', '')}\n"
        f"- **Order #:** {data.get('order_number', '')}\n"
        f"- **Test:** {is_test}\n"
    )

    try:
        from vault_io import create_note
        path = create_note(
            lane="deals",
            title=f"Sale — {product} — {email or sale_id}",
            content=content,
            agent="gumroad-webhook",
            note_type="sale",
            tags=["sale", "gumroad", "automated"],
            extra_meta={"sale_id": sale_id, "amount_usd": round(cents / 100, 2), "is_test": is_test},
        )
        app.logger.info(f"Vault note created: {path}")
    except Exception as e:
        app.logger.error(f"Vault write failed: {e}")

    return jsonify({"received": True, "sale_id": sale_id}), 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
