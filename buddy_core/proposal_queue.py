#!/usr/bin/env python3
"""
proposal_queue.py — Web-based proposal review & submission queue
Accessible from phone at http://34.135.158.163:5101/proposals
DeWayne can review, approve, and copy proposals for submission.
"""
import json
import os
import time
from datetime import datetime
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.responses import HTMLResponse
import uvicorn
import hmac
import hashlib
import secrets
import threading
from datetime import datetime, timezone

app = FastAPI(title="Dominion Proposal Queue")

PROPOSAL_OPERATOR_KEY = os.getenv("PROPOSAL_OPERATOR_KEY", "")


def _verify_proposal_operator(request: Request):
    """Verify PROPOSAL_OPERATOR_KEY via Authorization: Bearer header only.
    Fail closed: 503 if key not configured; 401 if auth missing or invalid.
    No query-parameter path. Key never appears in URLs, logs, or HTML."""
    if not PROPOSAL_OPERATOR_KEY:
        raise HTTPException(status_code=503, detail="Operator key not configured")
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer ") and hmac.compare_digest(auth[7:], PROPOSAL_OPERATOR_KEY):
        return
    raise HTTPException(status_code=401, detail="Unauthorized")

HOME = Path.home()
READY_DIR = HOME / "buddy_core" / "ready_to_submit"
SUBMITTED_DIR = HOME / "buddy_core" / "submitted_proposals"
CONTENT_Q = HOME / "content_queue"


def _get_proposals():
    """Load all staged proposals."""
    proposals = []
    if not READY_DIR.exists():
        return proposals
    for f in sorted(READY_DIR.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True):
        try:
            with open(f) as fh:
                data = json.load(fh)
                data["_filename"] = f.name
                data["_path"] = str(f)
                proposals.append(data)
        except:
            pass
    return proposals


def _get_content_queue():
    """Load today's social content for review."""
    today = datetime.utcnow().strftime("%Y-%m-%d")
    content = {}
    for platform in ["facebook", "tiktok", "instagram", "youtube", "linkedin", "twitter"]:
        d = CONTENT_Q / platform
        if not d.exists():
            continue
        for f in sorted(d.glob(f"{today}*.txt")):
            text = f.read_text().strip()
            if text:
                if platform not in content:
                    content[platform] = []
                content[platform].append({"file": f.name, "text": text})
    return content


def _get_email_outbox():
    """Load pending emails from outbox."""
    outbox_dir = HOME / "email_outbox"
    if not outbox_dir.exists():
        return []
    emails = []
    for f in sorted(outbox_dir.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True)[:20]:
        try:
            with open(f) as fh:
                data = json.load(fh)
                data["_filename"] = f.name
                emails.append(data)
        except:
            pass
    return emails




SCHEME = "https" + ":" + "//"

_SESSION_TTL       = 3600  # seconds
_SESSION_MAX_COUNT = 20    # max concurrent live sessions
_sessions          = {}    # sha256(token) -> expiry_unix_timestamp (float)
_sessions_lock     = threading.RLock()


def _prune_sessions():
    """Evict expired sessions, then oldest by expiry if still over max count.
    Caller must hold _sessions_lock."""
    now = datetime.now(timezone.utc).timestamp()
    for k in [k for k, exp in _sessions.items() if exp <= now]:
        del _sessions[k]
    while len(_sessions) >= _SESSION_MAX_COUNT:
        oldest = min(_sessions, key=_sessions.__getitem__)
        del _sessions[oldest]


def _valid_origin(request: Request) -> bool:
    """CSRF guard with strict header precedence.
    Origin present  -> it MUST match exactly.
    Referer present -> fallback only when Origin is absent.
    Neither present -> False (deny)."""
    allowed = SCHEME + "buddy.dominionhealing.org"
    origin = request.headers.get("Origin", "")
    referer = request.headers.get("Referer", "")
    if origin:
        return origin == allowed
    if referer:
        return referer.startswith(allowed + "/")
    return False


def _session_auth(request: Request):
    """Authenticate via pq_session cookie. Raises 401 if missing, expired, or invalid."""
    token = request.cookies.get("pq_session", "")
    if not token:
        raise HTTPException(status_code=401, detail="Unauthorized")
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    now = datetime.now(timezone.utc).timestamp()
    with _sessions_lock:
        exp = _sessions.get(token_hash)
        if exp is None or exp <= now:
            _sessions.pop(token_hash, None)
            raise HTTPException(status_code=401, detail="Unauthorized")


def _require_operator_auth(request: Request):
    """Accept PROPOSAL_OPERATOR_KEY Bearer token OR valid session cookie.
    Cookie path: cookie presence checked first (-> 401 if absent),
    then CSRF Origin/Referer guard (-> 403 if bad), then session validity.
    Bearer path: no CSRF required -- key possession is sufficient."""
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        if not PROPOSAL_OPERATOR_KEY:
            raise HTTPException(status_code=503, detail="Operator key not configured")
        if hmac.compare_digest(auth[7:], PROPOSAL_OPERATOR_KEY):
            return
        raise HTTPException(status_code=401, detail="Unauthorized")
    # Cookie path -- must confirm cookie is present before CSRF check
    if not request.cookies.get("pq_session", ""):
        raise HTTPException(status_code=401, detail="Unauthorized")
    if not _valid_origin(request):
        raise HTTPException(status_code=403, detail="Forbidden")
    _session_auth(request)


@app.post("/api/auth/session")
def create_session(
    request: Request,
    _: None = Depends(_verify_proposal_operator),
):
    """Exchange PROPOSAL_OPERATOR_KEY Bearer for a session cookie.
    CSRF guard: Origin/Referer must match buddy.dominionhealing.org (strict precedence).
    Server stores sha256(token) only -- raw token never persisted server-side.
    Bounded to _SESSION_MAX_COUNT concurrent sessions; oldest evicted on overflow."""
    if not _valid_origin(request):
        raise HTTPException(status_code=403, detail="Forbidden")
    token = secrets.token_hex(32)
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    exp = datetime.now(timezone.utc).timestamp() + _SESSION_TTL
    with _sessions_lock:
        _prune_sessions()
        _sessions[token_hash] = exp
    response = JSONResponse({"ok": True})
    response.set_cookie(
        key="pq_session",
        value=token,
        httponly=True,
        secure=True,
        samesite="strict",
        max_age=_SESSION_TTL,
        path="/api/",
    )
    return response


@app.post("/api/auth/logout")
def logout(
    request: Request,
    _: None = Depends(_session_auth),
):
    """Revoke session cookie. CSRF guard applied."""
    if not _valid_origin(request):
        raise HTTPException(status_code=403, detail="Forbidden")
    token = request.cookies.get("pq_session", "")
    if token:
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        with _sessions_lock:
            _sessions.pop(token_hash, None)
    response = JSONResponse({"ok": True})
    response.delete_cookie(
        key="pq_session",
        path="/api/",
        httponly=True,
        secure=True,
        samesite="strict",
    )
    return response


@app.post("/api/proposals/{filename}/mark-submitted")
def mark_submitted(filename: str, _: None = Depends(_require_operator_auth)):
    """Mark a proposal as submitted (move to submitted dir)."""
    # path traversal guard
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(400, "Invalid filename")
    safe_path = (READY_DIR / filename).resolve()
    if safe_path.parent != READY_DIR.resolve():
        raise HTTPException(400, "Invalid filename")
    src = safe_path
    if not src.exists():
        raise HTTPException(404, "Proposal not found")
    SUBMITTED_DIR.mkdir(exist_ok=True)
    dst = SUBMITTED_DIR / f"submitted_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{filename}"
    # Read, update status, write to submitted
    with open(src) as f:
        data = json.load(f)
    data["status"] = "submitted"
    data["submitted_at"] = datetime.utcnow().isoformat()
    _tmp = str(dst) + ".tmp"
    with open(_tmp, "w") as f:
        json.dump(data, f, indent=2)
    os.replace(_tmp, str(dst))
    os.remove(src)
    return {"status": "ok", "moved_to": str(dst)}


@app.get("/api/proposals")
def api_proposals():
    return _get_proposals()


@app.get("/api/content")
def api_content():
    return _get_content_queue()


@app.get("/api/email-outbox")
def api_email_outbox():
    return _get_email_outbox()


@app.get("/", response_class=HTMLResponse)
@app.get("/proposals", response_class=HTMLResponse)
def proposals_page():
    return """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Dominion — Proposal Queue</title>
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, sans-serif; background: #0a0a0f; color: #e0e0e0; padding: 16px; max-width: 800px; margin: 0 auto; }
h1 { color: #c9a227; font-size: 1.4em; margin-bottom: 16px; }
h2 { color: #c9a227; font-size: 1.1em; margin: 20px 0 10px; }
.proposal { background: #141420; border: 1px solid #2a2a3a; border-radius: 8px; padding: 16px; margin-bottom: 16px; }
.proposal .title { color: #fff; font-weight: 700; font-size: 1em; margin-bottom: 4px; }
.proposal .meta { color: #888; font-size: 0.8em; margin-bottom: 8px; }
.proposal .text { background: #1a1a2a; padding: 12px; border-radius: 4px; font-size: 0.85em; line-height: 1.5; white-space: pre-wrap; margin-bottom: 10px; }
.proposal .url { color: #4fc3f7; font-size: 0.8em; word-break: break-all; }
.btn { display: inline-block; padding: 8px 16px; border-radius: 4px; border: none; cursor: pointer; font-size: 0.85em; font-weight: 600; margin-right: 8px; margin-top: 8px; }
.btn-copy { background: #1b5e20; color: #4caf50; }
.btn-submit { background: #c9a227; color: #000; }
.btn-skip { background: #333; color: #888; }
.content-item { background: #141420; border: 1px solid #2a2a3a; border-radius: 8px; padding: 12px; margin-bottom: 10px; }
.content-item .platform { color: #c9a227; font-weight: 600; text-transform: uppercase; font-size: 0.8em; }
.content-item .text { font-size: 0.85em; white-space: pre-wrap; margin-top: 6px; }
.tab-bar { display: flex; gap: 8px; margin-bottom: 16px; }
.tab { padding: 8px 16px; background: #1a1a2a; border-radius: 4px; cursor: pointer; font-size: 0.85em; }
.tab.active { background: #c9a227; color: #000; }
.badge { background: #c9a227; color: #000; padding: 2px 6px; border-radius: 10px; font-size: 0.7em; margin-left: 4px; }
.empty { color: #666; text-align: center; padding: 40px; }
#auth-panel { max-width: 420px; margin: 60px auto; background: #141420; border: 1px solid #2a2a3a; border-radius: 10px; padding: 32px; }
#auth-panel h2 { color: #c9a227; margin-bottom: 20px; }
#auth-panel input { width: 100%; padding: 10px; background: #0a0a0f; border: 1px solid #2a2a3a; border-radius: 4px; color: #e0e0e0; font-size: 1em; margin-bottom: 14px; }
#auth-panel .btn-login { background: #c9a227; color: #000; width: 100%; padding: 10px; font-size: 1em; border: none; border-radius: 4px; cursor: pointer; font-weight: 600; }
#auth-error { color: #f44336; font-size: 0.85em; margin-top: 8px; min-height: 1.2em; }
#logout-btn { float: right; background: #333; color: #888; padding: 6px 12px; border: none; border-radius: 4px; cursor: pointer; font-size: 0.8em; font-weight: 600; }
</style>
</head>
<body>

<div id="auth-panel">
  <h2>DOMINION — Operator Login</h2>
  <input
    id="op-key-input"
    type="password"
    autocomplete="off"
    autocapitalize="none"
    spellcheck="false"
    placeholder="Operator key"
  >
  <button class="btn-login" onclick="login()">Login</button>
  <div id="auth-error"></div>
</div>

<div id="main-panel" style="display:none">
<h1>DOMINION — Review Queue <button id="logout-btn" onclick="logout()">Logout</button></h1>
<div class="tab-bar">
    <div class="tab active" onclick="showTab('proposals')">Proposals <span class="badge" id="p-count">0</span></div>
    <div class="tab" onclick="showTab('content')">Content <span class="badge" id="c-count">0</span></div>
    <div class="tab" onclick="showTab('emails')">Emails <span class="badge" id="e-count">0</span></div>
</div>
<div id="proposals-tab"></div>
<div id="content-tab" style="display:none"></div>
<div id="emails-tab" style="display:none"></div>
</div>

<script>
function showLogin() {
    document.getElementById('auth-panel').style.display = 'block';
    document.getElementById('main-panel').style.display  = 'none';
}

function showMain() {
    document.getElementById('auth-panel').style.display = 'none';
    document.getElementById('main-panel').style.display  = 'block';
}

async function login() {
    const inp = document.getElementById('op-key-input');
    let key = inp.value;
    inp.value = '';
    document.getElementById('auth-error').textContent = '';
    try {
        const r = await fetch('/api/auth/session', {
            method: 'POST',
            headers: { 'Authorization': 'Bearer ' + key }
        });
        if (r.ok) {
            showMain();
            loadAll();
        } else {
            document.getElementById('auth-error').textContent =
                r.status === 401 ? 'Invalid key.' : 'Login failed (' + r.status + ').';
        }
    } finally {
        key = '';
    }
}

async function logout() {
    try {
        await fetch('/api/auth/logout', { method: 'POST' });
    } finally {
        showLogin();
    }
}

function showTab(name) {
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    event.target.classList.add('active');
    document.getElementById('proposals-tab').style.display = name === 'proposals' ? 'block' : 'none';
    document.getElementById('content-tab').style.display = name === 'content' ? 'block' : 'none';
    document.getElementById('emails-tab').style.display = name === 'emails' ? 'block' : 'none';
}

function copyText(text) {
    navigator.clipboard.writeText(text).then(() => {
        alert('Copied to clipboard!');
    });
}

async function markSubmitted(filename) {
    if (!confirm('Mark as submitted?')) return;
    const r = await fetch('/api/proposals/' + encodeURIComponent(filename) + '/mark-submitted', {method: 'POST'});
    if (r.status === 401) { showLogin(); alert('Session expired — please log in again.'); return; }
    if (r.ok) { alert('Marked as submitted!'); loadAll(); }
}

async function loadAll() {
    // Proposals
    const pr = await fetch('/api/proposals');
    const proposals = await pr.json();
    document.getElementById('p-count').textContent = proposals.length;
    let html = '';
    if (!proposals.length) {
        html = '<div class="empty">No proposals pending</div>';
    }
    for (const p of proposals) {
        html += `<div class="proposal">
            <div class="title">${p.job_title || 'Untitled'}</div>
            <div class="meta">${p.platform || 'pph'} | ${p.budget || '?'} | Score: ${(p.composite_score || 0).toFixed(2)} | ${p.posted || ''}</div>
            <div class="url">${p.job_url || ''}</div>
            <div class="text">${p.proposal || ''}</div>
            <button class="btn btn-copy" onclick="copyText(\`${(p.proposal||'').replace(/`/g,"'").replace(/\\\\/g,"\\\\\\\\")}\`)">Copy Proposal</button>
            <button class="btn btn-submit" onclick="markSubmitted('${p._filename}')">Mark Submitted</button>
        </div>`;
    }
    document.getElementById('proposals-tab').innerHTML = html;

    // Content
    const cr = await fetch('/api/content');
    const content = await cr.json();
    let chtml = '';
    let ccount = 0;
    for (const [platform, items] of Object.entries(content)) {
        for (const item of items) {
            ccount++;
            chtml += `<div class="content-item">
                <div class="platform">${platform}</div>
                <div class="text">${item.text}</div>
                <button class="btn btn-copy" onclick="copyText(\`${item.text.replace(/`/g,"'").replace(/\\\\/g,"\\\\\\\\")}\`)">Copy</button>
            </div>`;
        }
    }
    document.getElementById('c-count').textContent = ccount;
    document.getElementById('content-tab').innerHTML = chtml || '<div class="empty">No content for today</div>';

    // Emails
    const er = await fetch('/api/email-outbox');
    const emails = await er.json();
    document.getElementById('e-count').textContent = emails.length;
    let ehtml = '';
    for (const e of emails) {
        ehtml += `<div class="content-item">
            <div class="platform">To: ${e.to} | ${e.queued_at || ''}</div>
            <div class="text"><strong>${e.subject || ''}</strong>\\n\\n${e.body || ''}</div>
        </div>`;
    }
    document.getElementById('emails-tab').innerHTML = ehtml || '<div class="empty">No pending emails</div>';
}

showLogin();
setInterval(function() {
    if (document.getElementById('main-panel').style.display !== 'none') {
        loadAll();
    }
}, 30000);
</script>
</body>
</html>"""


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=5101, log_level="info")
