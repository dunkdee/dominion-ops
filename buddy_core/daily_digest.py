"""
daily_digest.py — Dominion CEO Daily Digest Email
Runs at 7AM EST (12:00 UTC) via cron.
Compiles all 10 lane metrics and emails to DeWayne.
"""
import os, sys, json, smtplib, subprocess, datetime
from pathlib import Path
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv

load_dotenv(Path.home() / ".env")
load_dotenv(Path.home() / "buddy_core/.env")

TO_EMAIL = "founder-business@example.invalid"
FROM_EMAIL = os.getenv("SMTP_EMAIL", os.getenv("EMAIL_ADDRESS", ""))
EMAIL_PASS = os.getenv("EMAIL_PASSWORD", "")
SMTP_HOST = os.getenv("SMTP_HOST", "mail.privateemail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))


def run(cmd, timeout=10):
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return r.stdout.strip()
    except Exception as e:
        return f"ERROR: {e}"


def safe_json(path):
    p = Path(path)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except Exception:
        return None


def build_digest():
    now = datetime.datetime.utcnow()
    today = now.strftime("%Y-%m-%d")
    home = Path.home()

    # Service health
    services = [
        "dominion-store", "dominion-buddy-web", "dominion-gatekeeper",
        "conductor-api", "alchemist-api", "juris-api", "auric_edge",
        "dominion-tracker", "dominion-sentinel", "ascendant-store",
        "dominion-report", "dominion-dashboard",
    ]
    svc_status = {}
    for s in services:
        status = run(f"systemctl is-active {s}")
        svc_status[s] = status

    active = sum(1 for v in svc_status.values() if v == "active")
    down = [k for k, v in svc_status.items() if v != "active"]

    # Disk
    disk = run("df -h / | tail -1 | awk '{print $5}'")

    # Leads
    leads_data = safe_json(home / "leads_captured.json")
    total_leads = len(leads_data) if leads_data else 0

    # Wholesale
    ws_data = safe_json(home / "buddy_core/wholesale_leads.json")
    total_ws = len(ws_data) if ws_data else 0

    # Email subs
    email_data = safe_json(home / "ascendant_store/email_leads.json")
    email_subs = len(email_data) if email_data else 0

    # Trading bot
    tracker = safe_json(home / "buddy_core/tracker_log.json")
    if tracker:
        bot_balance = tracker.get("account", 0)
        bot_start = tracker.get("start_balance", 50)
        bot_signals = len(tracker.get("signals", []))
        bot_day = (now - datetime.datetime.fromisoformat(tracker.get("start_date", now.isoformat()))).days
    else:
        bot_balance = bot_start = bot_signals = bot_day = 0

    # Outreach
    outreach = safe_json(home / "outreach_log.json")
    outreach_count = len(outreach) if isinstance(outreach, list) else len(outreach.get("leads", [])) if outreach else 0

    # Content logs
    tiktok_log = run("tail -5 /home/malachisingleton8/logs/tiktok_pipeline.log 2>/dev/null")
    social_log = run("tail -3 /home/malachisingleton8/logs/social_poster.log 2>/dev/null")
    proposal_count = run("grep -c 'decision' /var/log/dominion/proposals.log 2>/dev/null")

    # TikTok videos generated
    tiktok_vids = run(f"ls -1 {home}/tiktok_videos/tiktok_{today}* 2>/dev/null | wc -l")

    # Cron health
    cron_jobs = run("crontab -l 2>/dev/null | grep -v '^#' | grep -v '^$' | wc -l")

    # Build HTML
    html = f"""
    <html>
    <body style="font-family: monospace; background: #0a0a0a; color: #e0e0e0; padding: 20px;">
    <div style="max-width: 700px; margin: 0 auto;">

    <h1 style="color: #DAA520; border-bottom: 2px solid #DAA520; padding-bottom: 10px;">
        DOMINION DAILY DIGEST — {today}
    </h1>

    <h2 style="color: #DAA520;">INFRASTRUCTURE</h2>
    <table style="width:100%; border-collapse: collapse;">
        <tr><td>Services</td><td style="color: {'#4ade80' if not down else '#ef4444'}">
            {active}/{len(services)} active{f' — DOWN: {", ".join(down)}' if down else ' — ALL GREEN'}
        </td></tr>
        <tr><td>Disk</td><td>{disk}</td></tr>
        <tr><td>Cron Jobs</td><td>{cron_jobs} active</td></tr>
    </table>

    <h2 style="color: #DAA520;">REVENUE LANES</h2>
    <table style="width:100%; border-collapse: collapse;">
        <tr><td>Stripe Revenue</td><td>Check report.dominionhealing.org</td></tr>
        <tr><td>KDP Books</td><td>2 submitted, 1 pending</td></tr>
        <tr><td>Email Subscribers</td><td>{email_subs}</td></tr>
        <tr><td>Leads Captured</td><td>{total_leads}</td></tr>
        <tr><td>Wholesale Pipeline</td><td>{total_ws} leads</td></tr>
        <tr><td>RE Outreach</td><td>{outreach_count} contacted</td></tr>
        <tr><td>PPH Proposals</td><td>{proposal_count} evaluated</td></tr>
    </table>

    <h2 style="color: #DAA520;">TRADING BOT</h2>
    <table style="width:100%; border-collapse: collapse;">
        <tr><td>Day</td><td>{bot_day}/90</td></tr>
        <tr><td>Balance</td><td>${bot_balance:.2f} (started ${bot_start:.2f})</td></tr>
        <tr><td>Total Signals</td><td>{bot_signals}</td></tr>
    </table>

    <h2 style="color: #DAA520;">CONTENT</h2>
    <table style="width:100%; border-collapse: collapse;">
        <tr><td>TikTok Videos Today</td><td>{tiktok_vids}</td></tr>
        <tr><td>Voice Engine</td><td>Piper TTS (Lessac — natural male)</td></tr>
    </table>

    <h3>Latest TikTok Log:</h3>
    <pre style="background: #111; padding: 10px; font-size: 12px; overflow-x: auto;">{tiktok_log}</pre>

    <h3>Latest Social Log:</h3>
    <pre style="background: #111; padding: 10px; font-size: 12px; overflow-x: auto;">{social_log}</pre>

    <h2 style="color: #DAA520;">ACTION ITEMS</h2>
    <ul>
    {'<li style="color:#ef4444">SERVICES DOWN: ' + ', '.join(down) + '</li>' if down else ''}
    {'<li>Upload 3rd KDP book (Debt Freedom Planner)</li>' if True else ''}
    {'<li>TikTok OAuth: authorize API access for auto-posting</li>'}
    {'<li>Set up affiliate accounts (see affiliate_signup_queue.md)</li>'}
    {'<li>Set up ConvertKit for email sequences (see email_sequences/)</li>'}
    {'<li>Launch Amazon Ads (see kdp_ad_strategy.md)</li>'}
    {'<li>Launch Google Ads (see google_ads_campaigns.md)</li>'}
    </ul>

    <p style="color: #666; margin-top: 30px; border-top: 1px solid #333; padding-top: 10px;">
        Full dashboard: <a href="https://report.dominionhealing.org" style="color: #DAA520;">report.dominionhealing.org</a><br>
        Generated: {now.strftime('%Y-%m-%d %H:%M:%S')} UTC | phi = 1.618
    </p>

    </div>
    </body>
    </html>
    """
    return html


def send_digest():
    html = build_digest()

    if not FROM_EMAIL or not EMAIL_PASS:
        print("[DIGEST] No email credentials — saving digest to file")
        out = Path.home() / "logs" / f"digest_{datetime.date.today()}.html"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(html)
        print(f"[DIGEST] Saved to {out}")
        return

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"DOMINION DAILY DIGEST — {datetime.date.today()}"
    msg["From"] = FROM_EMAIL
    msg["To"] = TO_EMAIL
    msg.attach(MIMEText(html, "html"))

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(FROM_EMAIL, EMAIL_PASS)
            server.send_message(msg)
        print(f"[DIGEST] Sent to {TO_EMAIL}")
    except Exception as e:
        print(f"[DIGEST] Send failed: {e}")
        out = Path.home() / "logs" / f"digest_{datetime.date.today()}.html"
        out.write_text(html)
        print(f"[DIGEST] Saved fallback to {out}")
        # Send SMS notification that digest is ready
        try:
            _sid = os.getenv("TWILIO_SID", "")
            _token = os.getenv("TWILIO_AUTH_TOKEN", "")
            _from = os.getenv("TWILIO_PHONE", "")
            _to = os.getenv("DEWAYNE_PHONE", "")
            if _sid and _token and _from and _to:
                from twilio.rest import Client
                client = Client(_sid, _token)
                client.messages.create(
                    body="DOMINION DIGEST READY - view at http://34.135.158.163:5095",
                    from_=_from, to=_to
                )
                print("[DIGEST] SMS notification sent")
        except Exception as sms_e:
            print(f"[DIGEST] SMS notification failed: {sms_e}")


if __name__ == "__main__":
    send_digest()
