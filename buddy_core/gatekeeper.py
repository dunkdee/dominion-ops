
from flask import Flask, request, jsonify, make_response
import base64
import datetime
import hmac
import json
import os
import smtplib
import subprocess
import threading
import time
from collections import defaultdict, deque
from email.mime.text import MIMEText
from pathlib import Path
import requests as _req
from filelock import FileLock, Timeout

app = Flask(__name__)

SECRET_PATH = Path("/home/malachisingleton8/buddy_core/core/webhook_secret.key")
with SECRET_PATH.open("r", encoding="utf-8") as handle:
    SECRET_KEY = handle.read().strip()
if not SECRET_KEY:
    raise RuntimeError("Dominion webhook secret is empty; refusing to start")

LEADS_FILE = Path(os.getenv("GATEKEEPER_LEADS_FILE", "/home/malachisingleton8/leads_captured.json"))
SUPPRESSION_FILE = Path(os.getenv("GATEKEEPER_SUPPRESSION_FILE", "/home/malachisingleton8/buddy_core/email_suppression.json"))
DRIP_URL = os.getenv("GATEKEEPER_DRIP_URL", "http://127.0.0.1:8099/api/email-capture")
UNSUBSCRIBE_BASE_URL = os.getenv("UNSUBSCRIBE_BASE_URL", "https://dominionhealing.org/api/unsubscribe")
NOTIFY_MODE = os.getenv("GATEKEEPER_NOTIFY_MODE", "hold").strip().lower()

LEADS_LOCK = FileLock(str(LEADS_FILE) + ".lock", timeout=5)
SUPPRESSION_LOCK = FileLock(str(SUPPRESSION_FILE) + ".lock", timeout=5)

RATE_LIMIT = 5
RATE_WINDOW = 60.0
_rate_data = defaultdict(deque)
_rate_lock = threading.Lock()


def _fsync_dir(path: Path) -> None:
    try:
        fd = os.open(str(path), os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    except OSError:
        pass


def verify_handshake(provided_key):
    return hmac.compare_digest(str(provided_key or ""), SECRET_KEY)


def _atomic_json_write(path: Path, data, default_mode: int = 0o600):
    if not path.parent.exists():
        raise OSError(f"Parent directory missing: {path.parent}")

    if path.exists():
        st = path.stat()
        uid = st.st_uid
        gid = st.st_gid
        mode = st.st_mode & 0o777
    else:
        uid = os.getuid()
        gid = os.getgid()
        mode = default_mode

    temp = path.parent / f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp"
    try:
        with temp.open("w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2, ensure_ascii=False)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temp, mode)
        os.chown(temp, uid, gid)
        os.replace(temp, path)
        _fsync_dir(path.parent)
    finally:
        if temp.exists():
            try:
                temp.unlink()
            except OSError:
                pass


def _load_json(path: Path, default):
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _client_ip() -> str:
    remote = request.remote_addr or "unknown"
    if remote in ("127.0.0.1", "::1"):
        forwarded = request.headers.get("X-Forwarded-For", "")
        if forwarded:
            candidate = forwarded.split(",", 1)[0].strip()
            if candidate:
                return candidate
    return remote


def _rate_allowed(ip: str) -> bool:
    now = time.monotonic()
    with _rate_lock:
        queue = _rate_data[ip]
        while queue and now - queue[0] >= RATE_WINDOW:
            queue.popleft()
        if len(queue) >= RATE_LIMIT:
            return False
        queue.append(now)
        return True


def _suppression_state(email: str) -> str:
    try:
        with SUPPRESSION_LOCK:
            if not SUPPRESSION_FILE.exists():
                return "clear"
            data = _load_json(SUPPRESSION_FILE, {"emails": []})
            emails = data.get("emails", [])
            if not isinstance(emails, list):
                return "error"
            normalized = {str(value).strip().lower() for value in emails}
            return "suppressed" if email.strip().lower() in normalized else "clear"
    except (json.JSONDecodeError, OSError, Timeout, TypeError, ValueError):
        return "error"


def _unsubscribe_url(email: str) -> str:
    normalized = email.strip().lower()
    token = hmac.new(
        SECRET_KEY.encode("utf-8"),
        normalized.encode("utf-8"),
        "sha256",
    ).hexdigest()[:32]
    encoded = base64.urlsafe_b64encode(normalized.encode("utf-8")).decode("ascii").rstrip("=")
    return f"{UNSUBSCRIBE_BASE_URL}?e={encoded}&t={token}"


def _append_lead(record: dict):
    try:
        with LEADS_LOCK:
            leads = _load_json(LEADS_FILE, [])
            if not isinstance(leads, list):
                raise ValueError("Lead store root must be a list")
            leads.append(record)
            _atomic_json_write(LEADS_FILE, leads, default_mode=0o600)
    except (json.JSONDecodeError, OSError, Timeout, TypeError, ValueError) as exc:
        raise RuntimeError("lead_store_unavailable") from exc


def _notify(record: dict):
    if NOTIFY_MODE != "live":
        return False

    username = os.getenv("EMAIL_ADDRESS", "").strip()
    password = os.getenv("EMAIL_PASSWORD", "").strip()
    if not username or not password:
        return False

    body = (
        "New Dominion Lead\n\n"
        f"Name: {record.get('name', '')}\n"
        f"Email: {record.get('email', '')}\n"
        f"Challenge: {record.get('challenge', '')}\n"
        f"Source: {record.get('source', '')}\n"
        f"Message: {record.get('message', '')}\n"
        f"Time: {record.get('ts', '')}"
    )
    message = MIMEText(body)
    message["Subject"] = "[DOMINION LEAD] " + record.get("name", "")
    message["From"] = username
    message["To"] = "founder-personal@example.invalid"

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=10) as smtp:
            smtp.login(username, password)
            smtp.send_message(message)
        return True
    except Exception as exc:
        print("[LEAD EMAIL] notification failed:", type(exc).__name__)
        return False


@app.route("/strike", methods=["POST"])
def trigger_strike():
    provided_key = request.headers.get("X-Dominion-Auth")
    if not verify_handshake(provided_key):
        return jsonify({"status": "REJECTED", "reason": "Unauthorized Handshake"}), 403
    try:
        subprocess.run(["python3", "agents/alchemist.py", "leads_for_monday.txt"], check=True)
        subprocess.run(["python3", "agents/clawbot.py"], check=True)
        subprocess.run(["python3", "agents/transmuter.py"], check=True)
        return jsonify({"status": "SUCCESS", "message": "Pipeline Executed"}), 200
    except Exception as exc:
        return jsonify({"status": "FAILURE", "error": type(exc).__name__}), 500


@app.route("/execute-next", methods=["POST"])
def proxy_execute_next():
    try:
        response = _req.post("http://127.0.0.1:5060/execute-next", timeout=30)
        return jsonify(response.json()), response.status_code
    except Exception as exc:
        return jsonify({"status": "error", "detail": type(exc).__name__}), 500


@app.route("/run-pipeline", methods=["POST"])
def run_pipeline():
    try:
        response = _req.post("http://127.0.0.1:5060/execute-next", timeout=30)
        return jsonify(response.json()), response.status_code
    except Exception as exc:
        return jsonify({"status": "error", "detail": type(exc).__name__}), 500


@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "status": "ok",
        "service": "dominion-gatekeeper",
        "notify_mode": NOTIFY_MODE,
        "rate_limit": RATE_LIMIT,
        "rate_window_seconds": RATE_WINDOW,
    }), 200


@app.route("/lead", methods=["POST", "OPTIONS"])
@app.route("/api/lead", methods=["POST", "OPTIONS"])
def capture_lead():
    if request.method == "OPTIONS":
        response = make_response("", 200)
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Methods"] = "POST,OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type"
        return response

    ip = _client_ip()
    if not _rate_allowed(ip):
        response = make_response(jsonify({"ok": False, "error": "rate_limited"}), 429)
        response.headers["Access-Control-Allow-Origin"] = "*"
        return response

    lead = request.get_json(silent=True) or {}
    email = str(lead.get("email") or "").strip().lower()
    if not email or "@" not in email:
        response = make_response(jsonify({"ok": False, "error": "invalid_email"}), 400)
        response.headers["Access-Control-Allow-Origin"] = "*"
        return response

    suppression = _suppression_state(email)
    if suppression == "error":
        response = make_response(jsonify({
            "ok": False,
            "status": "governed",
            "reason": "suppression_check_failed",
        }), 503)
        response.headers["Access-Control-Allow-Origin"] = "*"
        return response

    if suppression == "suppressed":
        response = make_response(jsonify({"ok": True, "status": "suppressed"}), 200)
        response.headers["Access-Control-Allow-Origin"] = "*"
        return response

    name = str(lead.get("name") or "Friend").strip() or "Friend"
    source = str(lead.get("source") or lead.get("challenge") or "website").strip() or "website"

    record = dict(lead)
    record["email"] = email
    record["name"] = name
    record["source"] = source
    record["ts"] = datetime.datetime.now(datetime.timezone.utc).isoformat()

    try:
        _append_lead(record)
    except RuntimeError:
        response = make_response(jsonify({
            "ok": False,
            "status": "governed",
            "reason": "lead_store_unavailable",
        }), 503)
        response.headers["Access-Control-Allow-Origin"] = "*"
        return response

    print(f"[LEAD] Captured: {email} | source={source}")

    drip_status = "unavailable"
    try:
        drip_response = _req.post(
            DRIP_URL,
            json={
                "email": email,
                "name": name,
                "source": source,
                "unsubscribe_url": _unsubscribe_url(email),
            },
            timeout=5,
        )
        drip_status = "accepted" if 200 <= drip_response.status_code < 300 else "rejected"
    except Exception as exc:
        print("[LEAD DRIP] forward failed:", type(exc).__name__)

    _notify(record)

    response = make_response(jsonify({
        "ok": True,
        "status": "captured",
        "drip_status": drip_status,
    }), 200)
    response.headers["Access-Control-Allow-Origin"] = "*"
    return response


@app.route("/api/unsubscribe", methods=["GET"])
def unsubscribe():
    encoded = request.args.get("e", "")
    token = request.args.get("t", "")

    try:
        padding = "=" * ((4 - len(encoded) % 4) % 4)
        email = base64.urlsafe_b64decode((encoded + padding).encode("ascii")).decode("utf-8").strip().lower()
    except Exception:
        return jsonify({"ok": False, "error": "invalid_request"}), 400

    if not email or "@" not in email:
        return jsonify({"ok": False, "error": "invalid_request"}), 400

    expected = hmac.new(
        SECRET_KEY.encode("utf-8"),
        email.encode("utf-8"),
        "sha256",
    ).hexdigest()[:32]
    if not hmac.compare_digest(str(token), expected):
        return jsonify({"ok": False, "error": "invalid_token"}), 403

    try:
        with SUPPRESSION_LOCK:
            if SUPPRESSION_FILE.exists():
                data = _load_json(SUPPRESSION_FILE, {"emails": []})
                emails = data.get("emails", [])
                if not isinstance(emails, list):
                    raise ValueError("Invalid suppression schema")
            else:
                data = {"emails": []}
                emails = data["emails"]

            normalized = {str(value).strip().lower() for value in emails}
            if email not in normalized:
                emails.append(email)
                data["emails"] = emails
                _atomic_json_write(SUPPRESSION_FILE, data, default_mode=0o600)
    except (json.JSONDecodeError, OSError, Timeout, TypeError, ValueError):
        return jsonify({
            "ok": False,
            "status": "governed",
            "reason": "suppression_store_unavailable",
        }), 503

    return jsonify({"ok": True, "status": "unsubscribed"}), 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
