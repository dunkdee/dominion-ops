#!/usr/bin/env python3
"""
Dominion Ops Dashboard — Real-time operational visibility
Port: 5100
Shows actual status of all verticals, pipelines, revenue, and agents.
No fake data. Only real metrics from real systems.
"""
import json
import os
import sqlite3
import subprocess
import time
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
import uvicorn

app = FastAPI(title="Dominion Operations Dashboard")

HOME = Path.home()
BUDDY_CORE = HOME / "buddy_core"
SURPLUS_DIR = HOME / "surplus_recovery"
REAL_ESTATE = HOME / "real_estate"
TRADING_DIR = HOME / "trading_data"
CONTENT_Q = HOME / "content_queue"
LOGS_DIR = HOME / "logs"


def _safe_json(path):
    try:
        with open(path) as f:
            return json.load(f)
    except:
        return None


def _file_age_minutes(path):
    try:
        mtime = os.path.getmtime(path)
        return (time.time() - mtime) / 60
    except:
        return 99999


def _log_tail(path, lines=5):
    try:
        with open(path) as f:
            all_lines = f.readlines()
            return [l.strip() for l in all_lines[-lines:]]
    except:
        return []


def _count_files(directory, pattern="*.txt"):
    try:
        return len(list(Path(directory).glob(pattern)))
    except:
        return 0


def _service_status(name):
    try:
        r = subprocess.run(
            ["systemctl", "is-active", name],
            capture_output=True, text=True, timeout=5
        )
        return r.stdout.strip()
    except:
        return "unknown"


def _docker_status(name):
    try:
        r = subprocess.run(
            ["docker", "inspect", "-f", "{{.State.Status}}", name],
            capture_output=True, text=True, timeout=5
        )
        return r.stdout.strip()
    except:
        return "unknown"


def get_infrastructure():
    """VM health metrics."""
    import shutil
    disk = shutil.disk_usage("/")
    try:
        with open("/proc/meminfo") as f:
            mem = f.read()
        total = int([l for l in mem.split("\n") if "MemTotal" in l][0].split()[1]) // 1024
        avail = int([l for l in mem.split("\n") if "MemAvailable" in l][0].split()[1]) // 1024
    except:
        total, avail = 0, 0

    try:
        with open("/proc/uptime") as f:
            uptime_sec = float(f.read().split()[0])
        uptime_days = uptime_sec / 86400
    except:
        uptime_days = 0

    return {
        "disk_used_pct": round(disk.used / disk.total * 100, 1),
        "disk_free_gb": round(disk.free / (1024**3), 1),
        "ram_total_mb": total,
        "ram_available_mb": avail,
        "ram_used_pct": round((total - avail) / max(total, 1) * 100, 1),
        "uptime_days": round(uptime_days, 1),
    }


def get_services():
    """All systemd services and Docker containers."""
    services = {
        "conductor-api": _service_status("conductor-api"),
        "alchemist-api": _service_status("alchemist-api"),
        "juris-api": _service_status("juris-api"),
        "ascendant-store": _service_status("ascendant-store"),
        "dominion-store": _service_status("dominion-store"),
        "dominion-buddy-web": _service_status("dominion-buddy-web"),
        "dominion-gatekeeper": _service_status("dominion-gatekeeper"),
        "dominion-report": _service_status("dominion-report"),
        "dominion-dashboard": _service_status("dominion-dashboard"),
        "dominion-email-drip": _service_status("dominion-email-drip"),
        "dominion-sentinel": _service_status("dominion-sentinel"),
        "dominion-surplus-dashboard": _service_status("dominion-surplus-dashboard"),
        "caddy": _service_status("caddy"),
        "conductor-worker": _service_status("conductor-worker"),
        "conductor-scheduler": _service_status("conductor-scheduler"),
    }
    docker = {
        "dominion-db": _docker_status("dominion-db"),
        "dominion-n8n": _docker_status("dominion-n8n"),
        "dominion-seo": _docker_status("dominion-seo"),
    }
    return {"systemd": services, "docker": docker}


def get_pipelines():
    """Pipeline status based on log freshness and output."""
    today = datetime.utcnow().strftime("%Y-%m-%d")
    pipelines = {}

    # Content gen
    content_today = 0
    for plat in ["facebook", "tiktok", "instagram", "youtube", "linkedin", "twitter"]:
        d = CONTENT_Q / plat
        if d.exists():
            content_today += len(list(d.glob(f"{today}*.txt")))
    pipelines["content_gen"] = {
        "status": "green" if content_today >= 4 else "yellow" if content_today > 0 else "red",
        "detail": f"{content_today} pieces generated today",
    }

    # TikTok video gen
    tiktok_vids = HOME / "tiktok_videos"
    today_vids = len(list(tiktok_vids.glob(f"tiktok_{today}*.mp4"))) if tiktok_vids.exists() else 0
    pipelines["tiktok_video_gen"] = {
        "status": "green" if today_vids >= 2 else "yellow" if today_vids > 0 else "red",
        "detail": f"{today_vids} videos generated today",
    }

    # PPH proposals
    ready_dir = BUDDY_CORE / "ready_to_submit"
    staged = len(list(ready_dir.glob("*.json"))) if ready_dir.exists() else 0
    prop_log = Path("/var/log/dominion/proposals.log")
    prop_age = _file_age_minutes(prop_log)
    pipelines["pph_proposals"] = {
        "status": "yellow" if staged > 0 else "red",
        "detail": f"{staged} staged (not submitted). Log age: {prop_age:.0f}min",
    }

    # Social poster
    poster_log = LOGS_DIR / "social_poster.log"
    poster_tail = _log_tail(poster_log, 3)
    posted_count = sum(1 for l in _log_tail(poster_log, 50) if "POSTED" in l and today in l)
    pipelines["social_poster"] = {
        "status": "green" if posted_count > 0 else "red",
        "detail": f"{posted_count} actually posted today. Last: {poster_tail[-1] if poster_tail else 'no log'}",
    }

    # Email drip
    pipelines["email_drip"] = {
        "status": "red" if not os.getenv("SENDGRID_API_KEY") else "green",
        "detail": "SENDGRID_API_KEY not set — emails logged but not sent" if not os.getenv("SENDGRID_API_KEY") else "active",
    }

    # RE Scout
    scout_log = HOME / "scout.log"
    scout_age = _file_age_minutes(scout_log)
    pipelines["re_scout"] = {
        "status": "green" if scout_age < 1500 else "red",
        "detail": f"Log age: {scout_age:.0f}min. Last: {(_log_tail(scout_log, 1) or ['no log'])[0]}",
    }

    # Wholesale engine
    wholesale_log = SURPLUS_DIR / "logs" / "wholesale.log"
    wh_tail = _log_tail(wholesale_log, 1)
    has_error = any("Error" in l or "TypeError" in l for l in _log_tail(wholesale_log, 5))
    pipelines["wholesale_engine"] = {
        "status": "red" if has_error else "green",
        "detail": wh_tail[0] if wh_tail else "no log",
    }

    # Surplus scraper
    surplus_log = SURPLUS_DIR / "surplus_scraper.log"
    sl_age = _file_age_minutes(surplus_log)
    pipelines["surplus_scraper"] = {
        "status": "green" if sl_age < 1500 else "red",
        "detail": f"Log age: {sl_age:.0f}min",
    }

    # Daily digest
    digest_log = LOGS_DIR / "digest.log"
    digest_tail = _log_tail(digest_log, 1)
    pipelines["daily_digest"] = {
        "status": "red" if "BadCredentials" in (digest_tail[0] if digest_tail else "") else "green",
        "detail": digest_tail[0] if digest_tail else "no log",
    }

    return pipelines


def get_trading():
    """Paper trading status."""
    state = _safe_json(TRADING_DIR / "markov_paper_state.json")
    if not state:
        return {"status": "no_data", "detail": "No trading state file found"}
    return {
        "status": "active" if not state.get("kill_switch") else "killed",
        "balance": state.get("balance", 0),
        "start_balance": 10000,
        "pnl": state.get("total_pnl", 0),
        "pnl_pct": round(state.get("total_pnl", 0) / 10000 * 100, 2),
        "trades": state.get("trade_count", 0),
        "wins": state.get("win_count", 0),
        "losses": state.get("loss_count", 0),
        "win_rate": round(state.get("win_count", 0) / max(state.get("trade_count", 1), 1) * 100, 1),
        "holding": state.get("holding", False),
        "last_run": state.get("last_run", ""),
        "start_date": state.get("start_date", ""),
    }


def get_surplus():
    """Surplus recovery pipeline stats."""
    db_path = SURPLUS_DIR / "surplus.db"
    if not db_path.exists():
        return {"status": "no_db"}
    try:
        conn = sqlite3.connect(str(db_path))
        total_cases = conn.execute("SELECT count(*) FROM cases").fetchone()[0]
        total_surplus = conn.execute("SELECT count(*) FROM surplus_records").fetchone()[0]
        total_amount = conn.execute("SELECT sum(surplus_amount) FROM surplus_records WHERE surplus_amount > 0").fetchone()[0] or 0
        contacts = conn.execute("SELECT count(*) FROM contacts").fetchone()[0]
        outreach_sent = conn.execute("SELECT count(*) FROM outreach").fetchone()[0]
        revenue = conn.execute("SELECT sum(amount) FROM revenue").fetchone()[0] or 0
        conn.close()
        return {
            "total_cases": total_cases,
            "surplus_records": total_surplus,
            "total_surplus_identified": round(total_amount, 2),
            "potential_fee_12pct": round(total_amount * 0.12, 2),
            "contacts_found": contacts,
            "outreach_sent": outreach_sent,
            "revenue_collected": revenue,
        }
    except Exception as e:
        return {"error": str(e)}


def get_wholesale():
    """RE wholesale pipeline stats."""
    try:
        r = subprocess.run(
            ["docker", "exec", "dominion-db", "psql", "-U", "dominion", "-d", "dominion",
             "-t", "-c", "SELECT count(*) FROM wholesale_leads"],
            capture_output=True, text=True, timeout=10
        )
        leads = int(r.stdout.strip()) if r.returncode == 0 else 0

        r2 = subprocess.run(
            ["docker", "exec", "dominion-db", "psql", "-U", "dominion", "-d", "dominion",
             "-t", "-c", "SELECT count(*) FROM wholesale_buyers"],
            capture_output=True, text=True, timeout=10
        )
        buyers = int(r2.stdout.strip()) if r2.returncode == 0 else 0

        r3 = subprocess.run(
            ["docker", "exec", "dominion-db", "psql", "-U", "dominion", "-d", "dominion",
             "-t", "-c", "SELECT count(*) FROM wholesale_deals"],
            capture_output=True, text=True, timeout=10
        )
        deals = int(r3.stdout.strip()) if r3.returncode == 0 else 0

        return {"leads": leads, "buyers": buyers, "deals": deals}
    except:
        return {"error": "db query failed"}


def get_revenue():
    """Revenue from all sources."""
    try:
        r = subprocess.run(
            ["docker", "exec", "dominion-db", "psql", "-U", "dominion", "-d", "dominion",
             "-t", "-c", "SELECT count(*), coalesce(sum(amount),0) FROM stripe_events WHERE created_at > now() - interval '30 days'"],
            capture_output=True, text=True, timeout=10
        )
        if r.returncode == 0 and "|" in r.stdout:
            parts = r.stdout.strip().split("|")
            count = int(parts[0].strip())
            amount = float(parts[1].strip())
        else:
            count, amount = 0, 0.0
    except:
        count, amount = 0, 0.0

    return {
        "stripe_events_30d": count,
        "stripe_revenue_30d": amount,
        "surplus_revenue": get_surplus().get("revenue_collected", 0),
        "total_revenue_30d": amount,
    }


@app.get("/api/status")
def api_status():
    """Full system status as JSON."""
    return {
        "timestamp": datetime.utcnow().isoformat(),
        "infrastructure": get_infrastructure(),
        "services": get_services(),
        "pipelines": get_pipelines(),
        "trading": get_trading(),
        "surplus": get_surplus(),
        "wholesale": get_wholesale(),
        "revenue": get_revenue(),
    }


@app.get("/", response_class=HTMLResponse)
def dashboard():
    """Main dashboard HTML."""
    return """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Dominion Ops — Live Dashboard</title>
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #0a0a0f; color: #e0e0e0; padding: 20px; }
h1 { color: #c9a227; margin-bottom: 5px; font-size: 1.6em; }
.subtitle { color: #888; margin-bottom: 20px; font-size: 0.85em; }
.grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(350px, 1fr)); gap: 16px; }
.card { background: #141420; border: 1px solid #2a2a3a; border-radius: 8px; padding: 16px; }
.card h2 { color: #c9a227; font-size: 1em; margin-bottom: 12px; border-bottom: 1px solid #2a2a3a; padding-bottom: 8px; }
.metric { display: flex; justify-content: space-between; padding: 4px 0; font-size: 0.85em; }
.metric .label { color: #999; }
.metric .value { font-weight: 600; }
.green { color: #4caf50; }
.yellow { color: #ffc107; }
.red { color: #f44336; }
.badge { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 0.75em; font-weight: 600; }
.badge.active { background: #1b5e20; color: #4caf50; }
.badge.inactive { background: #4a1010; color: #f44336; }
.badge.running { background: #1b5e20; color: #4caf50; }
table { width: 100%; border-collapse: collapse; font-size: 0.8em; }
table td, table th { padding: 4px 8px; text-align: left; border-bottom: 1px solid #1a1a2a; }
table th { color: #c9a227; }
.refresh-note { text-align: center; color: #666; font-size: 0.75em; margin-top: 20px; }
#data { opacity: 0; transition: opacity 0.3s; }
#data.loaded { opacity: 1; }
.revenue-big { font-size: 2em; color: #c9a227; font-weight: 700; text-align: center; padding: 10px 0; }
</style>
</head>
<body>
<h1>DOMINION ASCENDANT — Operations Dashboard</h1>
<p class="subtitle">Live system status | Auto-refreshes every 60s | <span id="last-update">loading...</span></p>
<div id="data" class="grid"></div>
<p class="refresh-note">Data pulled from live systems. No fake metrics.</p>

<script>
function badge(status) {
    const cls = (status === 'active' || status === 'running') ? 'active' : 'inactive';
    return `<span class="badge ${cls}">${status}</span>`;
}
function color(status) {
    if (status === 'green') return 'green';
    if (status === 'yellow') return 'yellow';
    return 'red';
}

async function refresh() {
    try {
        const r = await fetch('/api/status');
        const d = await r.json();
        const el = document.getElementById('data');
        document.getElementById('last-update').textContent = new Date().toLocaleTimeString();

        let html = '';

        // Revenue card
        html += `<div class="card">
            <h2>REVENUE (30 days)</h2>
            <div class="revenue-big">$${d.revenue.total_revenue_30d.toFixed(2)}</div>
            <div class="metric"><span class="label">Stripe events</span><span class="value">${d.revenue.stripe_events_30d}</span></div>
            <div class="metric"><span class="label">Surplus collected</span><span class="value">$${d.revenue.surplus_revenue}</span></div>
        </div>`;

        // Infrastructure
        const inf = d.infrastructure;
        html += `<div class="card">
            <h2>INFRASTRUCTURE</h2>
            <div class="metric"><span class="label">Uptime</span><span class="value">${inf.uptime_days} days</span></div>
            <div class="metric"><span class="label">Disk</span><span class="value ${inf.disk_used_pct > 80 ? 'red' : 'green'}">${inf.disk_used_pct}% (${inf.disk_free_gb}GB free)</span></div>
            <div class="metric"><span class="label">RAM</span><span class="value ${inf.ram_used_pct > 85 ? 'yellow' : 'green'}">${inf.ram_used_pct}% used (${inf.ram_available_mb}MB avail)</span></div>
        </div>`;

        // Services
        html += `<div class="card"><h2>SERVICES</h2><table><tr><th>Service</th><th>Status</th></tr>`;
        for (const [name, status] of Object.entries(d.services.systemd)) {
            html += `<tr><td>${name}</td><td>${badge(status)}</td></tr>`;
        }
        for (const [name, status] of Object.entries(d.services.docker)) {
            html += `<tr><td>${name} (docker)</td><td>${badge(status)}</td></tr>`;
        }
        html += `</table></div>`;

        // Pipelines
        html += `<div class="card"><h2>PIPELINES</h2><table><tr><th>Pipeline</th><th>Status</th><th>Detail</th></tr>`;
        for (const [name, info] of Object.entries(d.pipelines)) {
            html += `<tr><td>${name}</td><td><span class="${color(info.status)}">${info.status.toUpperCase()}</span></td><td style="font-size:0.8em">${info.detail}</td></tr>`;
        }
        html += `</table></div>`;

        // Trading
        const t = d.trading;
        html += `<div class="card">
            <h2>TRADING (Markov Paper)</h2>
            <div class="metric"><span class="label">Status</span><span class="value">${t.status}</span></div>
            <div class="metric"><span class="label">Balance</span><span class="value">$${(t.balance||0).toFixed(2)}</span></div>
            <div class="metric"><span class="label">P&L</span><span class="value ${(t.pnl||0) >= 0 ? 'green' : 'red'}">$${(t.pnl||0).toFixed(2)} (${t.pnl_pct||0}%)</span></div>
            <div class="metric"><span class="label">Trades</span><span class="value">${t.trades||0} (${t.win_rate||0}% WR)</span></div>
            <div class="metric"><span class="label">Holding</span><span class="value">${t.holding ? 'YES' : 'NO'}</span></div>
            <div class="metric"><span class="label">Last run</span><span class="value">${t.last_run||'never'}</span></div>
        </div>`;

        // Surplus
        const s = d.surplus;
        html += `<div class="card">
            <h2>SURPLUS RECOVERY</h2>
            <div class="metric"><span class="label">Cases in DB</span><span class="value">${s.total_cases||0}</span></div>
            <div class="metric"><span class="label">Surplus records</span><span class="value">${s.surplus_records||0}</span></div>
            <div class="metric"><span class="label">Total $ identified</span><span class="value green">$${(s.total_surplus_identified||0).toLocaleString()}</span></div>
            <div class="metric"><span class="label">Potential fee (12%)</span><span class="value">$${(s.potential_fee_12pct||0).toLocaleString()}</span></div>
            <div class="metric"><span class="label">Contacts found</span><span class="value">${s.contacts_found||0}</span></div>
            <div class="metric"><span class="label">Outreach sent</span><span class="value">${s.outreach_sent||0}</span></div>
            <div class="metric"><span class="label">Revenue collected</span><span class="value">$${s.revenue_collected||0}</span></div>
        </div>`;

        // Wholesale
        const w = d.wholesale;
        html += `<div class="card">
            <h2>RE WHOLESALE</h2>
            <div class="metric"><span class="label">Leads (FL)</span><span class="value">${w.leads||0}</span></div>
            <div class="metric"><span class="label">Buyers found</span><span class="value">${w.buyers||0}</span></div>
            <div class="metric"><span class="label">Deals</span><span class="value">${w.deals||0}</span></div>
        </div>`;

        el.innerHTML = html;
        el.classList.add('loaded');
    } catch(e) {
        console.error('Refresh failed:', e);
    }
}

refresh();
setInterval(refresh, 60000);
</script>
</body>
</html>"""



@app.get("/digest", response_class=HTMLResponse)
def latest_digest():
    """Serve the most recent daily digest."""
    import glob
    digest_dir = HOME / "logs"
    files = sorted(digest_dir.glob("digest_*.html"), reverse=True)
    if not files:
        return "<h1>No digest available yet</h1>"
    return files[0].read_text()


@app.get("/api/email-outbox")
def api_email_outbox():
    """Pending emails waiting to be sent."""
    outbox = HOME / "email_outbox"
    if not outbox.exists():
        return []
    emails = []
    for f in sorted(outbox.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True)[:20]:
        try:
            import json as _j
            with open(f) as fh:
                data = _j.load(fh)
                data["_file"] = f.name
                emails.append(data)
        except:
            pass
    return emails


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=5100, log_level="info")
