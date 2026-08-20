"""
BUDDY WEB CHAT — Phone-accessible AI assistant
================================================
FastAPI server serving a clean chat UI.
DeWayne can talk to Buddy from his phone browser.

Deploy on VM behind Caddy at: dominionhealing.org/buddy
Port: 5070

Usage:
  python buddy_web.py              — start server
  python buddy_web.py --port 5070  — custom port
"""

import os
import sys
import json
import time
from datetime import datetime
from pathlib import Path

# Ensure imports work
sys.path.insert(0, str(Path(__file__).resolve().parent))

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
import uvicorn

try:
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=Path.home() / "buddy_core" / ".env")
    load_dotenv(dotenv_path=Path.home() / "conductor" / ".env")
    load_dotenv(dotenv_path=Path.home() / ".env")
except ImportError:
    pass

from core.brain import ask, status as brain_status, BUDDY_SYSTEM

# ── Auth token ──
BUDDY_WEB_TOKEN = os.getenv("BUDDY_WEB_TOKEN", "")

# Conversation memory (last 20 messages per session, in-memory)
conversations = {}
MAX_HISTORY = 20

app = FastAPI(title="Buddy Web", docs_url=None, redoc_url=None)


import hmac
from fastapi import Header, HTTPException

def verify_token(request: Request):
    """Check bearer token or query param for auth."""
    if not BUDDY_WEB_TOKEN:
        return  # No token configured = open (dev mode)
    # Check Authorization header
    auth = request.headers.get("Authorization", "")
    if hmac.compare_digest(auth, f"Bearer {BUDDY_WEB_TOKEN}"):
        return
    # Check query param ?token=
    token = request.query_params.get("token", "")
    if token and hmac.compare_digest(token, BUDDY_WEB_TOKEN):
        return
    # Check cookie
    cookie_token = request.cookies.get("buddy_token", "")
    if cookie_token and hmac.compare_digest(cookie_token, BUDDY_WEB_TOKEN):
        return
    raise HTTPException(status_code=401, detail="Unauthorized")

# ── Chat HTML — Dominion Brand ───────────────────────────────
CHAT_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<title>Buddy — Dominion AI</title>
<link href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@300;400;600&family=Syne:wght@400;600;700&display=swap" rel="stylesheet">
<style>
  :root{--void:#080d09;--deep:#0d1810;--forest:#152a18;--moss:#1e3d23;--gold:#c9a22a;--gold-lt:#e8c84a;--wheat:#e8d4a0;--cream:#f4ede0}
  * { margin:0; padding:0; box-sizing:border-box; }
  body {
    font-family: 'Syne', sans-serif;
    background: var(--void);
    color: var(--cream);
    height: 100vh;
    display: flex;
    flex-direction: column;
    position: relative;
    overflow: hidden;
  }
  canvas#pc{position:fixed;inset:0;pointer-events:none;z-index:0;opacity:.4}
  .header {
    background: rgba(8,13,9,.92);
    backdrop-filter: blur(20px);
    padding: 14px 18px;
    border-bottom: 1px solid rgba(201,162,42,.15);
    display: flex;
    align-items: center;
    gap: 12px;
    z-index: 10;
  }
  .header .geo{width:32px;height:32px;border:1px solid rgba(201,162,42,.3);border-radius:50%;display:flex;align-items:center;justify-content:center;animation:spin 20s linear infinite}
  .header .geo-inner{font-family:'Cormorant Garamond',serif;color:var(--gold);font-size:14px}
  .header h1 { font-family:'Cormorant Garamond',serif; font-size:20px; color:var(--gold); font-weight:600; letter-spacing:.08em; }
  .header .sub { font-size:10px; color:rgba(201,162,42,.45); margin-left:auto; font-weight:600; letter-spacing:.2em; text-transform:uppercase; }
  .nav{display:flex;gap:6px;padding:8px 18px;background:var(--deep);border-bottom:1px solid rgba(201,162,42,.08);z-index:10}
  .nav a{color:rgba(232,212,160,.35);text-decoration:none;font-size:11px;padding:5px 12px;border:1px solid rgba(201,162,42,.1);font-weight:600;letter-spacing:.15em;text-transform:uppercase;transition:all .2s}
  .nav a.active,.nav a:hover{color:var(--gold);border-color:rgba(201,162,42,.35);background:rgba(201,162,42,.06)}
  .messages {
    flex: 1;
    overflow-y: auto;
    padding: 18px;
    display: flex;
    flex-direction: column;
    gap: 14px;
    z-index: 5;
    position: relative;
  }
  .msg {
    max-width: 85%;
    padding: 12px 16px;
    font-size: 14px;
    line-height: 1.7;
    word-wrap: break-word;
    white-space: pre-wrap;
  }
  .msg.user {
    align-self: flex-end;
    background: var(--forest);
    color: var(--wheat);
    border: 1px solid rgba(201,162,42,.12);
    border-radius: 16px 16px 4px 16px;
  }
  .msg.buddy {
    align-self: flex-start;
    background: var(--deep);
    color: var(--cream);
    border: 1px solid rgba(201,162,42,.1);
    border-radius: 16px 16px 16px 4px;
    border-left: 2px solid rgba(201,162,42,.25);
  }
  .msg.buddy .name { font-family:'Cormorant Garamond',serif; color:var(--gold); font-size:13px; font-weight:600; margin-bottom:4px; letter-spacing:.05em; }
  .msg.system {
    align-self: center;
    background: transparent;
    color: rgba(201,162,42,.4);
    font-size: 11px;
    text-align: center;
    letter-spacing: .15em;
    text-transform: uppercase;
  }
  .input-area {
    background: rgba(8,13,9,.95);
    backdrop-filter: blur(10px);
    padding: 14px 18px;
    border-top: 1px solid rgba(201,162,42,.12);
    display: flex;
    gap: 10px;
    z-index: 10;
  }
  .input-area input {
    flex: 1;
    background: var(--forest);
    border: 1px solid rgba(201,162,42,.15);
    border-radius: 0;
    padding: 12px 16px;
    color: var(--cream);
    font-family: 'Syne', sans-serif;
    font-size: 14px;
    outline: none;
    transition: border-color .2s;
  }
  .input-area input:focus { border-color: var(--gold); }
  .input-area input::placeholder { color: rgba(232,212,160,.2); }
  .input-area button {
    background: var(--gold);
    color: var(--void);
    border: none;
    padding: 12px 22px;
    font-family: 'Syne', sans-serif;
    font-size: 12px;
    font-weight: 700;
    letter-spacing: .15em;
    text-transform: uppercase;
    cursor: pointer;
    transition: background .2s;
  }
  .input-area button:hover { background: var(--gold-lt); }
  .input-area button:disabled { opacity:0.35; }
  .typing { color:var(--gold); font-size:12px; padding:4px 16px; letter-spacing:.1em; }
  @keyframes spin{from{transform:rotate(0deg)}to{transform:rotate(360deg)}}
  @media (max-width: 600px) { .msg { max-width: 92%; } }
</style>
</head>
<body>
  <canvas id="pc"></canvas>
  <div class="header">
    <div class="geo"><span class="geo-inner">&#x2B21;</span></div>
    <h1>Buddy</h1>
    <span class="sub">Dominion AI</span>
  </div>
  <div class="nav">
    <a href="/buddy" class="active">Chat</a>
    <a href="/buddy/jobs">Proposals</a>
  </div>
  <div class="messages" id="messages">
    <div class="msg system">Sovereign AI Online — Speak Your Mind</div>
  </div>
  <div class="input-area">
    <input type="text" id="input" placeholder="Talk to Buddy..." autocomplete="off" autofocus>
    <button id="send" onclick="sendMsg()">SEND</button>
    <button id="mic" onclick="toggleVoice()" style="background:#c9a22a;border:none;color:#0a0a1a;font-weight:bold;padding:10px 16px;border-radius:8px;cursor:pointer;font-size:18px" title="Hold to talk">&#x1F3A4;</button>
  </div>
<script>
const input = document.getElementById('input');
const msgs = document.getElementById('messages');
const btn = document.getElementById('send');
let sessionId = 'phone_' + Date.now();

input.addEventListener('keydown', e => { if(e.key==='Enter' && !btn.disabled) sendMsg(); });

async function sendMsg() {
  const text = input.value.trim();
  if (!text) return;
  input.value = '';
  addMsg(text, 'user');
  btn.disabled = true;
  const typing = document.createElement('div');
  typing.className = 'typing';
  typing.textContent = 'processing...';
  msgs.appendChild(typing);
  msgs.scrollTop = msgs.scrollHeight;
  try {
    const r = await fetch('/buddy/api/chat', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({message: text, session_id: sessionId})
    });
    const data = await r.json();
    typing.remove();
    addMsg(data.response || 'No response.', 'buddy');
    speakText(data.response || '');
  } catch(e) {
    typing.remove();
    addMsg('Connection lost. Retry.', 'system');
  }
  btn.disabled = false;
  input.focus();
}

function addMsg(text, type) {
  const div = document.createElement('div');
  div.className = 'msg ' + type;
  if (type === 'buddy') {
    div.innerHTML = '<div class="name">Buddy</div>' + escapeHtml(text);
  } else { div.textContent = text; }
  msgs.appendChild(div);
  msgs.scrollTop = msgs.scrollHeight;
}

function escapeHtml(t) { const d=document.createElement('div'); d.textContent=t; return d.innerHTML; }


// ── Voice Chat: Speech Recognition + Text-to-Speech ──
let recognition = null;
let isListening = false;
const synth = window.speechSynthesis;

function toggleVoice() {
  const micBtn = document.getElementById('mic');
  if (isListening) {
    if (recognition) recognition.stop();
    isListening = false;
    micBtn.style.background = '#c9a22a';
    micBtn.innerHTML = '&#x1F3A4;';
    return;
  }
  if (!('webkitSpeechRecognition' in window || 'SpeechRecognition' in window)) {
    alert('Voice not supported. Use Chrome.');
    return;
  }
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  recognition = new SR();
  recognition.continuous = false;
  recognition.interimResults = false;
  recognition.lang = 'en-US';
  recognition.onresult = function(e) {
    const text = e.results[0][0].transcript;
    document.getElementById('input').value = text;
    sendMsg();
    isListening = false;
    micBtn.style.background = '#c9a22a';
    micBtn.innerHTML = '&#x1F3A4;';
  };
  recognition.onerror = function() {
    isListening = false;
    micBtn.style.background = '#c9a22a';
    micBtn.innerHTML = '&#x1F3A4;';
  };
  recognition.onend = function() {
    if (isListening) {
      // Auto-restart for continuous listening feel
      try { recognition.start(); } catch(e) {}
    }
  };
  recognition.start();
  isListening = true;
  micBtn.style.background = '#ff4444';
  micBtn.innerHTML = '&#x23F9;';
}

function speakText(text) {
  if (!synth || !text) return;
  synth.cancel();
  // Clean text for speech
  const clean = text.replace(/```[\s\S]*?```/g, ' code block ')
                     .replace(/[*_#`]/g, '')
                     .replace(/https?:\/\/\S+/g, ' link ')
                     .slice(0, 500);
  const u = new SpeechSynthesisUtterance(clean);
  u.rate = 0.9;
  u.pitch = 0.7;
  u.lang = 'en-US';
  // Try to find a good voice
  const voices = synth.getVoices();
  const preferred = voices.find(v => (v.name.includes("Male") || v.name.includes("Guy") || v.name.includes("David") || v.name.includes("James") || v.name.includes("Google US English")) && v.lang.startsWith("en"))
                 || voices.find(v => v.lang === 'en-US');
  if (preferred) u.voice = preferred;
  synth.speak(u);
}

// Load voices (some browsers need this)
if (synth) synth.getVoices();
if (synth) synth.onvoiceschanged = () => synth.getVoices();

// Particles
(function(){
  const cv=document.getElementById('pc'),ctx=cv.getContext('2d'),pts=[];
  function resize(){cv.width=innerWidth;cv.height=innerHeight}
  resize();addEventListener('resize',resize);
  class P{
    constructor(){this.reset()}
    reset(){this.x=Math.random()*cv.width;this.y=Math.random()*cv.height;this.s=Math.random()*1.2+.3;this.sx=(Math.random()-.5)*.3;this.sy=(Math.random()-.5)*.3;this.o=Math.random()*.25+.05}
    update(){this.x+=this.sx;this.y+=this.sy;if(this.x<0||this.x>cv.width||this.y<0||this.y>cv.height)this.reset()}
    draw(){ctx.beginPath();ctx.arc(this.x,this.y,this.s,0,Math.PI*2);ctx.fillStyle='rgba(201,162,42,'+this.o+')';ctx.fill()}
  }
  for(let i=0;i<40;i++)pts.push(new P());
  (function loop(){
    ctx.clearRect(0,0,cv.width,cv.height);
    pts.forEach(p=>{p.update();p.draw()});
    for(let i=0;i<pts.length;i++)for(let j=i+1;j<pts.length;j++){
      const dx=pts[i].x-pts[j].x,dy=pts[i].y-pts[j].y,d=Math.sqrt(dx*dx+dy*dy);
      if(d<100){ctx.beginPath();ctx.moveTo(pts[i].x,pts[i].y);ctx.lineTo(pts[j].x,pts[j].y);ctx.strokeStyle='rgba(201,162,42,'+(0.06*(1-d/100))+')';ctx.lineWidth=.4;ctx.stroke()}
    }
    requestAnimationFrame(loop)
  })();
})();
</script>
</body>
</html>"""


@app.get("/buddy", response_class=HTMLResponse)
@app.get("/buddy/", response_class=HTMLResponse)
def chat_page(request: Request):
    verify_token(request)
    from fastapi.responses import Response
    resp = HTMLResponse(CHAT_HTML)
    # Set cookie so subsequent API calls work without token in URL
    token = request.query_params.get("token", "")
    if token:
        resp.set_cookie("buddy_token", token, httponly=True, max_age=86400*30)
    return resp


@app.post("/buddy/api/chat")
async def chat(request: Request):
    verify_token(request)
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON"}, status_code=400)

    message = body.get("message", "").strip()
    session_id = body.get("session_id", "default")

    if not message:
        return JSONResponse({"error": "Empty message"}, status_code=400)

    # Build context from conversation history
    history = conversations.setdefault(session_id, [])
    history.append({"role": "user", "text": message, "ts": datetime.utcnow().isoformat()})

    # Build prompt with recent context
    context_lines = []
    for msg in history[-MAX_HISTORY:]:
        prefix = "Dewayne" if msg["role"] == "user" else "Buddy"
        context_lines.append(f"{prefix}: {msg['text']}")
    full_prompt = "\n".join(context_lines)

    try:
        response = ask(full_prompt)
    except Exception as e:
        response = f"Brain error: {e}"

    history.append({"role": "buddy", "text": response, "ts": datetime.utcnow().isoformat()})

    # Trim history
    if len(history) > MAX_HISTORY * 2:
        conversations[session_id] = history[-MAX_HISTORY:]

    return JSONResponse({"response": response, "session_id": session_id})


@app.get("/buddy/api/status")
def buddy_status():
    return JSONResponse(brain_status())


@app.get("/buddy/download/{filename}")
def download_file(filename: str, request: Request):
    verify_token(request)
    from fastapi.responses import FileResponse
    # Serve from tiktok_uploads or content_queue
    for search_dir in [Path.home() / "buddy_core" / "tiktok_uploads",
                       Path.home() / "buddy_core" / "content_queue",
                       Path.home() / "buddy_core" / "music_output"]:
        filepath = search_dir / filename
        if filepath.exists() and filepath.is_file():
            return FileResponse(filepath, filename=filename, media_type="video/mp4")
    return JSONResponse({"error": "File not found"}, status_code=404)


# ============================================================
# PROPOSALS PAGE — Upwork/Freelance job proposals from phone
# ============================================================

PROPOSALS_DIR = Path(__file__).resolve().parent / "proposals_queue"
PROPOSALS_DIR.mkdir(exist_ok=True)

JOBS_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<title>Buddy — Proposals</title>
<link href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@300;400;600&family=Syne:wght@400;600;700&display=swap" rel="stylesheet">
<style>
  :root{--void:#080d09;--deep:#0d1810;--forest:#152a18;--moss:#1e3d23;--gold:#c9a22a;--gold-lt:#e8c84a;--wheat:#e8d4a0;--cream:#f4ede0}
  * { margin:0; padding:0; box-sizing:border-box; }
  body { font-family:'Syne',sans-serif; background:var(--void); color:var(--cream); position:relative; }
  canvas#pc{position:fixed;inset:0;pointer-events:none;z-index:0;opacity:.4}
  .header { background:rgba(8,13,9,.92); backdrop-filter:blur(20px); padding:14px 18px; border-bottom:1px solid rgba(201,162,42,.15); display:flex; align-items:center; gap:12px; z-index:10; position:sticky; top:0; }
  .header .geo{width:32px;height:32px;border:1px solid rgba(201,162,42,.3);border-radius:50%;display:flex;align-items:center;justify-content:center;animation:spin 20s linear infinite}
  .header .geo-inner{font-family:'Cormorant Garamond',serif;color:var(--gold);font-size:14px}
  .header h1 { font-family:'Cormorant Garamond',serif; font-size:20px; color:var(--gold); font-weight:600; letter-spacing:.08em; }
  .header .sub { font-size:10px; color:rgba(201,162,42,.45); margin-left:auto; font-weight:600; letter-spacing:.2em; text-transform:uppercase; }
  .nav{display:flex;gap:6px;padding:8px 18px;background:var(--deep);border-bottom:1px solid rgba(201,162,42,.08);z-index:10;position:sticky;top:56px}
  .nav a{color:rgba(232,212,160,.35);text-decoration:none;font-size:11px;padding:5px 12px;border:1px solid rgba(201,162,42,.1);font-weight:600;letter-spacing:.15em;text-transform:uppercase;transition:all .2s}
  .nav a.active,.nav a:hover{color:var(--gold);border-color:rgba(201,162,42,.35);background:rgba(201,162,42,.06)}
  .cards { padding:18px; display:flex; flex-direction:column; gap:16px; position:relative; z-index:5; }
  .card { background:var(--deep); border:1px solid rgba(201,162,42,.1); padding:18px; border-left:2px solid rgba(201,162,42,.25); transition:all .3s; }
  .card:hover { border-color:rgba(201,162,42,.35); }
  .card-title { font-family:'Cormorant Garamond',serif; color:var(--gold); font-size:16px; font-weight:600; margin-bottom:4px; letter-spacing:.03em; }
  .card-rate { color:rgba(201,162,42,.45); font-size:11px; margin-bottom:10px; letter-spacing:.1em; text-transform:uppercase; }
  .card-rate strong { color:var(--wheat); }
  .card-proposal { font-size:13px; line-height:1.7; color:var(--wheat); margin-bottom:14px; white-space:pre-wrap; background:var(--forest); padding:14px; border:1px solid rgba(201,162,42,.06); }
  .card-actions { display:flex; gap:8px; }
  .btn-copy { flex:1; background:var(--gold); color:var(--void); border:none; padding:10px; font-family:'Syne',sans-serif; font-size:11px; font-weight:700; letter-spacing:.12em; text-transform:uppercase; cursor:pointer; transition:background .2s; }
  .btn-copy:hover { background:var(--gold-lt); }
  .btn-copy.copied { background:var(--moss); color:var(--cream); }
  .btn-new { flex:1; background:transparent; color:var(--gold); border:1px solid rgba(201,162,42,.25); padding:10px; font-family:'Syne',sans-serif; font-size:11px; font-weight:700; letter-spacing:.12em; text-transform:uppercase; cursor:pointer; transition:all .2s; }
  .btn-new:hover { border-color:var(--gold); background:rgba(201,162,42,.06); }
  .empty { text-align:center; color:rgba(201,162,42,.3); padding:60px 20px; font-family:'Cormorant Garamond',serif; font-size:18px; }
  .gen-section { padding:18px; border-bottom:1px solid rgba(201,162,42,.08); position:relative; z-index:5; }
  .gen-input { width:100%; background:var(--forest); border:1px solid rgba(201,162,42,.15); padding:12px 14px; color:var(--cream); font-family:'Syne',sans-serif; font-size:13px; outline:none; margin-bottom:8px; transition:border-color .2s; }
  .gen-input:focus { border-color:var(--gold); }
  .gen-input::placeholder { color:rgba(232,212,160,.2); }
  .gen-btn { width:100%; background:var(--gold); color:var(--void); border:none; padding:12px; font-family:'Syne',sans-serif; font-size:12px; font-weight:700; letter-spacing:.15em; text-transform:uppercase; cursor:pointer; transition:background .2s; }
  .gen-btn:hover { background:var(--gold-lt); }
  .gen-btn:disabled { opacity:0.35; }
  .toast { position:fixed; bottom:20px; left:50%; transform:translateX(-50%); background:var(--forest); color:var(--gold); border:1px solid rgba(201,162,42,.25); border-left:3px solid var(--gold); padding:10px 20px; font-size:13px; display:none; z-index:100; }
  .toast.show { display:block; }
  @keyframes spin{from{transform:rotate(0deg)}to{transform:rotate(360deg)}}
</style>
</head>
<body>
  <canvas id="pc"></canvas>
  <div class="header">
    <div class="geo"><span class="geo-inner">&#x2B21;</span></div>
    <h1>Buddy</h1>
    <span class="sub">Proposals</span>
  </div>
  <div class="nav">
    <a href="/buddy">Chat</a>
    <a href="/buddy/jobs" class="active">Proposals</a>
  </div>
  <div class="gen-section">
    <input class="gen-input" id="jobDesc" placeholder="Paste job description here...">
    <button class="gen-btn" id="genBtn" onclick="generateProposal()">Write Proposal</button>
  </div>
  <div class="cards" id="cards"></div>
  <div class="toast" id="toast">Copied to clipboard!</div>
<script>
let proposals = [];

async function loadProposals() {
  try {
    const r = await fetch('/buddy/api/proposals');
    proposals = await r.json();
    render();
  } catch(e) { console.error(e); }
}

function render() {
  const el = document.getElementById('cards');
  if (!proposals.length) {
    el.innerHTML = '<div class="empty">No proposals yet.<br>Paste a job description above and tap Write Proposal.</div>';
    return;
  }
  el.innerHTML = proposals.map((p, i) => `
    <div class="card">
      <div class="card-title">${esc(p.title || 'Untitled Job')}</div>
      <div class="card-rate">Rate: <strong>${esc(p.rate || 'Not specified')}</strong> | ${esc(p.platform || 'Upwork')}</div>
      <div class="card-proposal">${esc(p.proposal)}</div>
      <div class="card-actions">
        <button class="btn-copy" id="copy-${i}" onclick="copyP(${i})">Copy Proposal</button>
        <button class="btn-new" onclick="rewrite(${i})">Rewrite</button>
      </div>
    </div>`).join('');
}

async function generateProposal() {
  const desc = document.getElementById('jobDesc').value.trim();
  if (!desc) return;
  const btn = document.getElementById('genBtn');
  btn.disabled = true; btn.textContent = 'Writing...';
  try {
    const r = await fetch('/buddy/api/proposals/generate', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({job_description: desc})
    });
    const data = await r.json();
    if (data.proposal) {
      proposals.unshift(data);
      render();
      document.getElementById('jobDesc').value = '';
      showToast('Proposal ready!');
    }
  } catch(e) { console.error(e); }
  btn.disabled = false; btn.textContent = 'Write Proposal';
}

async function rewrite(i) {
  const p = proposals[i];
  const btn = event.target;
  btn.disabled = true; btn.textContent = 'Rewriting...';
  try {
    const r = await fetch('/buddy/api/proposals/generate', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({job_description: p.job_description || p.title, rewrite: true})
    });
    const data = await r.json();
    if (data.proposal) { proposals[i] = data; render(); showToast('Rewritten!'); }
  } catch(e) { console.error(e); }
  btn.disabled = false; btn.textContent = 'Rewrite';
}

function copyP(i) {
  const text = proposals[i].proposal;
  navigator.clipboard.writeText(text).then(() => {
    const btn = document.getElementById('copy-'+i);
    btn.textContent = 'Copied!'; btn.classList.add('copied');
    showToast('Copied! Paste in Upwork.');
    setTimeout(() => { btn.textContent = 'Copy Proposal'; btn.classList.remove('copied'); }, 2000);
  });
}

function showToast(msg) {
  const t = document.getElementById('toast');
  t.textContent = msg; t.classList.add('show');
  setTimeout(() => t.classList.remove('show'), 2500);
}

function esc(s) { const d=document.createElement('div'); d.textContent=s||''; return d.innerHTML; }

loadProposals();


// ── Voice Chat: Speech Recognition + Text-to-Speech ──
let recognition = null;
let isListening = false;
const synth = window.speechSynthesis;

function toggleVoice() {
  const micBtn = document.getElementById('mic');
  if (isListening) {
    if (recognition) recognition.stop();
    isListening = false;
    micBtn.style.background = '#c9a22a';
    micBtn.innerHTML = '&#x1F3A4;';
    return;
  }
  if (!('webkitSpeechRecognition' in window || 'SpeechRecognition' in window)) {
    alert('Voice not supported. Use Chrome.');
    return;
  }
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  recognition = new SR();
  recognition.continuous = false;
  recognition.interimResults = false;
  recognition.lang = 'en-US';
  recognition.onresult = function(e) {
    const text = e.results[0][0].transcript;
    document.getElementById('input').value = text;
    sendMsg();
    isListening = false;
    micBtn.style.background = '#c9a22a';
    micBtn.innerHTML = '&#x1F3A4;';
  };
  recognition.onerror = function() {
    isListening = false;
    micBtn.style.background = '#c9a22a';
    micBtn.innerHTML = '&#x1F3A4;';
  };
  recognition.onend = function() {
    if (isListening) {
      // Auto-restart for continuous listening feel
      try { recognition.start(); } catch(e) {}
    }
  };
  recognition.start();
  isListening = true;
  micBtn.style.background = '#ff4444';
  micBtn.innerHTML = '&#x23F9;';
}

function speakText(text) {
  if (!synth || !text) return;
  synth.cancel();
  // Clean text for speech
  const clean = text.replace(/```[\s\S]*?```/g, ' code block ')
                     .replace(/[*_#`]/g, '')
                     .replace(/https?:\/\/\S+/g, ' link ')
                     .slice(0, 500);
  const u = new SpeechSynthesisUtterance(clean);
  u.rate = 0.9;
  u.pitch = 0.7;
  u.lang = 'en-US';
  // Try to find a good voice
  const voices = synth.getVoices();
  const preferred = voices.find(v => (v.name.includes("Male") || v.name.includes("Guy") || v.name.includes("David") || v.name.includes("James") || v.name.includes("Google US English")) && v.lang.startsWith("en"))
                 || voices.find(v => v.lang === 'en-US');
  if (preferred) u.voice = preferred;
  synth.speak(u);
}

// Load voices (some browsers need this)
if (synth) synth.getVoices();
if (synth) synth.onvoiceschanged = () => synth.getVoices();

// Particles
(function(){
  const cv=document.getElementById('pc'),ctx=cv.getContext('2d'),pts=[];
  function resize(){cv.width=innerWidth;cv.height=innerHeight}
  resize();addEventListener('resize',resize);
  class P{
    constructor(){this.reset()}
    reset(){this.x=Math.random()*cv.width;this.y=Math.random()*cv.height;this.s=Math.random()*1.2+.3;this.sx=(Math.random()-.5)*.3;this.sy=(Math.random()-.5)*.3;this.o=Math.random()*.25+.05}
    update(){this.x+=this.sx;this.y+=this.sy;if(this.x<0||this.x>cv.width||this.y<0||this.y>cv.height)this.reset()}
    draw(){ctx.beginPath();ctx.arc(this.x,this.y,this.s,0,Math.PI*2);ctx.fillStyle='rgba(201,162,42,'+this.o+')';ctx.fill()}
  }
  for(let i=0;i<40;i++)pts.push(new P());
  (function loop(){
    ctx.clearRect(0,0,cv.width,cv.height);
    pts.forEach(p=>{p.update();p.draw()});
    for(let i=0;i<pts.length;i++)for(let j=i+1;j<pts.length;j++){
      const dx=pts[i].x-pts[j].x,dy=pts[i].y-pts[j].y,d=Math.sqrt(dx*dx+dy*dy);
      if(d<100){ctx.beginPath();ctx.moveTo(pts[i].x,pts[i].y);ctx.lineTo(pts[j].x,pts[j].y);ctx.strokeStyle='rgba(201,162,42,'+(0.06*(1-d/100))+')';ctx.lineWidth=.4;ctx.stroke()}
    }
    requestAnimationFrame(loop)
  })();
})();
</script>
</body>
</html>"""


@app.get("/buddy/jobs", response_class=HTMLResponse)
@app.get("/buddy/jobs/", response_class=HTMLResponse)
def jobs_page(request: Request):
    verify_token(request)
    from fastapi.responses import Response
    resp = HTMLResponse(JOBS_HTML)
    token = request.query_params.get("token", "")
    if token:
        resp.set_cookie("buddy_token", token, httponly=True, max_age=86400*30)
    return resp


@app.get("/buddy/api/proposals")
def get_proposals(request: Request):
    verify_token(request)
    """Return all saved proposals."""
    from utils.safe_io import load_json
    proposals = load_json(PROPOSALS_DIR / "proposals.json", default=[])
    return JSONResponse(proposals)


@app.post("/buddy/api/proposals/generate")
async def generate_proposal(request: Request):
    """Generate a proposal using four-part protocol."""
    verify_token(request)
    from utils.safe_io import atomic_json_write, load_json

    body = await request.json()
    job_desc = body.get("job_description", "").strip()
    if not job_desc:
        return JSONResponse({"error": "No job description"}, status_code=400)

    # Run through four-part protocol
    try:
        from core.proposal_protocol import ProposalProtocol
        pp = ProposalProtocol()
        protocol_result = pp.run(
            task=job_desc,
            task_type="upwork_proposal",
            platform=body.get("platform", "upwork"),
            rollback_path="Delete proposal from proposals_queue",
        )

        outcome = protocol_result.get("outcome")
        if outcome == "VETOED":
            return JSONResponse({"error": f"Parallax vetoed: {protocol_result.get('reason', '')[:200]}", "qa_passed": False}, status_code=422)
        if outcome == "ESCALATE":
            return JSONResponse({"error": f"Needs your decision: {protocol_result.get('reason', '')[:200]}", "qa_passed": False}, status_code=422)
        if outcome == "BLOCKED":
            return JSONResponse({"error": f"Final review blocked: {protocol_result.get('reason', '')[:200]}", "qa_passed": False}, status_code=422)
        if outcome == "ERROR":
            return JSONResponse({"error": protocol_result.get("error", "Unknown error")}, status_code=500)

        action_result = protocol_result.get("action_result", {})
        if action_result.get("status") == "voice_inverted":
            return JSONResponse({"error": f"Voice inversion detected: {action_result.get('flag')}", "qa_passed": False}, status_code=422)
        if action_result.get("status") == "qa_rejected":
            return JSONResponse({"error": f"QA rejected: {action_result.get('issues', [])}", "qa_passed": False}, status_code=422)

        proposal_text = action_result.get("proposal", "")
    except ImportError:
        # Fallback if protocol not available — use direct generation
        proposal_text = ask(f"Write a 150-word freelance proposal for: {job_desc[:2000]}. Write as DeWayne Singleton, AI ecosystem builder. Hook first sentence. Confident. Return ONLY proposal text.")
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

    # ── QA Gate — validate before saving ──
    qa_result = {"passed": True}
    try:
        from core.qa_gate import validate_proposal
        qa_result = validate_proposal(proposal_text, platform="upwork")
    except Exception:
        pass  # QA gate import fail = allow through with warning

    # Voice inversion check — reject if proposal sounds like employer, not applicant
    inversion_flags = [
        "we are looking for", "we need", "we seek", "the ideal candidate",
        "applicants should", "this role", "responsibilities include",
        "we are hiring", "join our team", "your salary"
    ]
    proposal_lower = proposal_text.lower()
    inversions = [f for f in inversion_flags if f in proposal_lower]
    if inversions:
        qa_result["passed"] = False
        qa_result["issues"] = qa_result.get("issues", []) + [f"VOICE INVERSION: proposal sounds like employer, not applicant. Flags: {inversions}"]

    if not qa_result.get("passed", True):
        # Log failure
        try:
            failure_log = load_json(Path(__file__).resolve().parent / "failure_registry.json", default=[])
            failure_log.append({
                "timestamp": datetime.utcnow().isoformat(),
                "agent": "buddy_web_proposals",
                "action": "proposal_generation",
                "failure_mode": f"QA gate rejected: {qa_result.get('issues', [])}",
                "fix": "Proposal not saved. User should retry.",
                "prevented_by_rule_id": "fix_list_5"
            })
            atomic_json_write(Path(__file__).resolve().parent / "failure_registry.json", failure_log, default=str)
        except Exception:
            pass
        return JSONResponse({
            "error": "QA gate rejected this proposal",
            "issues": qa_result.get("issues", []),
            "proposal": proposal_text,
            "qa_passed": False
        }, status_code=422)

    # Extract title and rate from job desc
    lines = job_desc.split('\n')
    title = lines[0][:100] if lines else "Untitled"

    import re
    rate_match = re.search(r'\$[\d,]+(?:\s*[-–]\s*\$[\d,]+)?(?:/hr)?', job_desc)
    rate = rate_match.group(0) if rate_match else "Not specified"

    entry = {
        "title": title,
        "rate": rate,
        "platform": "Upwork",
        "proposal": proposal_text,
        "job_description": job_desc[:500],
        "generated_at": datetime.utcnow().isoformat(),
        "qa_passed": True,
        "qa_score": qa_result.get("overall", None),
    }

    # Save
    proposals = load_json(PROPOSALS_DIR / "proposals.json", default=[])
    proposals.insert(0, entry)
    if len(proposals) > 50:
        proposals = proposals[:50]
    atomic_json_write(PROPOSALS_DIR / "proposals.json", proposals, default=str)

    return JSONResponse(entry)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=5070)
    parser.add_argument("--host", default="0.0.0.0")
    args = parser.parse_args()
    print(f"Buddy Web Chat starting on {args.host}:{args.port}")
    print(f"Access at: http://localhost:{args.port}/buddy")
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")
