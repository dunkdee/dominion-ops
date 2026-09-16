import hashlib
import os
import re
import uuid
from flask import Blueprint, jsonify, make_response, request

try:
    from . import vault_io
except ImportError:  # container runs api/app.py as a script
    import vault_io

beta_bp = Blueprint("creator_beta", __name__, url_prefix="/beta")

EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
ALLOWED_PLATFORMS = {"youtube", "tiktok", "instagram", "facebook", "multiple", "other"}
ALLOWED_CREATOR_TYPES = {"solo_creator", "small_business", "freelancer", "other"}
ALLOWED_PAINS = {"consistency", "time", "ideas", "publishing", "analytics", "growth", "other"}


def _allowed_origins():
    raw = os.getenv(
        "BETA_ALLOWED_ORIGINS",
        "https://dominionhealing.org,https://www.dominionhealing.org",
    )
    return {item.strip().rstrip("/") for item in raw.split(",") if item.strip()}


def _with_cors(response):
    origin = (request.headers.get("Origin") or "").rstrip("/")
    if origin in _allowed_origins():
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Vary"] = "Origin"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type"
        response.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS"
    return response


def _error(message, status=400):
    return _with_cors(make_response(jsonify({"accepted": False, "error": message}), status))


def _clean(value, max_len):
    return " ".join(str(value or "").strip().split())[:max_len]


def _existing_application(email_hash):
    for note in vault_io.list_lane("beta"):
        if note.get("email_hash") == email_hash:
            return note.get("application_id")
    return None


@beta_bp.route("/apply", methods=["OPTIONS"])
def beta_apply_options():
    return _with_cors(make_response("", 204))


@beta_bp.route("/apply", methods=["POST"])
def beta_apply():
    if request.content_length and request.content_length > 16_384:
        return _error("request_too_large", 413)
    if not request.is_json:
        return _error("json_required", 415)

    data = request.get_json(silent=True) or {}
    # Honeypot: real users never see/fill this field.
    if _clean(data.get("website"), 200):
        return _with_cors(make_response(jsonify({"accepted": True, "status": "received"}), 202))

    name = _clean(data.get("name"), 80)
    email = _clean(data.get("email"), 254).lower()
    creator_type = _clean(data.get("creator_type"), 32)
    platform = _clean(data.get("primary_platform"), 32)
    pain = _clean(data.get("biggest_pain"), 32)
    source = _clean(data.get("source"), 80) or "creator-beta"
    tried_recently = data.get("tried_last_7_days") is True
    consent = data.get("consent") is True

    try:
        weekly_posts = int(data.get("weekly_posts", 0))
    except (TypeError, ValueError):
        return _error("weekly_posts_invalid")

    if len(name) < 2:
        return _error("name_required")
    if not EMAIL_RE.match(email) or len(email) > 254:
        return _error("valid_email_required")
    if creator_type not in ALLOWED_CREATOR_TYPES:
        return _error("creator_type_invalid")
    if platform not in ALLOWED_PLATFORMS:
        return _error("primary_platform_invalid")
    if pain not in ALLOWED_PAINS:
        return _error("biggest_pain_invalid")
    if weekly_posts < 0 or weekly_posts > 100:
        return _error("weekly_posts_invalid")
    if not consent:
        return _error("consent_required")

    email_hash = hashlib.sha256(email.encode("utf-8")).hexdigest()
    existing_id = _existing_application(email_hash)
    if existing_id:
        return _with_cors(make_response(jsonify({
            "accepted": True,
            "application_id": existing_id,
            "status": "already_received",
        }), 200))

    score = 0
    score += 2 if tried_recently else 0
    score += 1 if weekly_posts >= 2 else 0
    score += 1 if weekly_posts >= 4 else 0
    score += 1 if platform != "other" else 0
    score += 1 if pain in {"consistency", "time", "publishing", "growth"} else 0
    score += 1 if creator_type in {"solo_creator", "small_business", "freelancer"} else 0
    cohort = "priority_review" if score >= 5 else "standard_review"
    application_id = f"beta_{uuid.uuid4().hex[:12]}"

    content = (
        "## Creator Beta Application\n\n"
        f"- **Application ID:** {application_id}\n"
        f"- **Name:** {name}\n"
        f"- **Email:** {email}\n"
        f"- **Creator type:** {creator_type}\n"
        f"- **Primary platform:** {platform}\n"
        f"- **Posts per week:** {weekly_posts}\n"
        f"- **Biggest pain:** {pain}\n"
        f"- **Tried to solve in last 7 days:** {tried_recently}\n"
        f"- **Qualification score:** {score}/7\n"
        f"- **Cohort:** {cohort}\n"
        f"- **Source:** {source}\n"
        "- **Consent:** private beta contact + product testing only\n"
    )

    try:
        vault_io.create_note(
            lane="beta",
            title=f"Creator Beta — {name} — {application_id}",
            content=content,
            agent="creator-beta-intake",
            note_type="beta_application",
            tags=["creator-beta", "lead", cohort],
            extra_meta={
                "application_id": application_id,
                "email_hash": email_hash,
                "qualification_score": score,
                "cohort": cohort,
                "source": source,
                "consent": True,
            },
        )
    except Exception:
        return _error("intake_temporarily_unavailable", 503)

    return _with_cors(make_response(jsonify({
        "accepted": True,
        "application_id": application_id,
        "status": cohort,
        "message": "Application received. Keep this receipt ID.",
    }), 201))
