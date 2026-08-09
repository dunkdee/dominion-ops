"""
Dominion Healing -- KDP Email Drip Sequence Engine
===================================================
FastAPI service that captures leads and runs a 5-email drip sequence
for each of the three KDP books.

Endpoints:
    POST /api/email-capture   -- capture a new lead
    GET  /api/drip-status      -- dashboard stats
    POST /api/run-drip         -- manually trigger drip scheduler

Deploy: systemd service on foundation-vm  |  PrivateEmail SMTP for controlled delivery
"""

import os
import json
import time
import logging
import threading
import base64
import hmac
import hashlib
import html as html_lib
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional
from filelock import FileLock, Timeout

from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel
import uvicorn

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

DATA_DIR = Path(__file__).parent
LEADS_FILE = DATA_DIR / "leads_drip.json"
SMTP_HOST     = os.getenv("SMTP_HOST", "mail.privateemail.com")
SMTP_PORT     = int(os.getenv("SMTP_PORT", "587"))
GMAIL_ADDRESS = os.getenv("SMTP_EMAIL", os.getenv("EMAIL_ADDRESS", ""))
GMAIL_PASSWORD = os.getenv("SMTP_PASSWORD", os.getenv("EMAIL_PASSWORD", ""))
FROM_EMAIL = os.getenv("DRIP_FROM_EMAIL", "dewayne@dominionhealing.org")
FROM_NAME = os.getenv("DRIP_FROM_NAME", "Dewayne | Dominion Healing")
DRIP_CHECK_INTERVAL = int(os.getenv("DRIP_CHECK_INTERVAL", "3600"))  # seconds
DRIP_SEND_MODE = os.getenv("DRIP_SEND_MODE", "hold").strip().lower()
if DRIP_SEND_MODE not in {"hold", "live"}:
    raise RuntimeError("DRIP_SEND_MODE must be hold or live")
LEADS_FILE = Path(os.getenv("DRIP_LEADS_FILE", str(LEADS_FILE)))
SUPPRESSION_FILE = Path(os.getenv(
    "DRIP_SUPPRESSION_FILE",
    "/home/malachisingleton8/buddy_core/email_suppression.json",
))
UNSUBSCRIBE_BASE_URL = os.getenv(
    "UNSUBSCRIBE_BASE_URL",
    "https://dominionhealing.org/api/unsubscribe",
)
SECRET_PATH = Path(os.getenv("DRIP_WEBHOOK_SECRET_PATH", "/home/malachisingleton8/buddy_core/core/webhook_secret.key"))
WEBHOOK_SECRET = SECRET_PATH.read_text(encoding="utf-8").strip()
if not WEBHOOK_SECRET:
    raise RuntimeError("Dominion webhook secret is empty; refusing to start email drip")
LEADS_LOCK = FileLock(str(LEADS_FILE) + ".lock", timeout=5)
SUPPRESSION_LOCK = FileLock(str(SUPPRESSION_FILE) + ".lock", timeout=5)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("email_drip")

app = FastAPI(title="KDP Email Drip Engine", version="1.0.0")

# ---------------------------------------------------------------------------
# Data helpers
# ---------------------------------------------------------------------------


def _load_leads() -> dict:
    if LEADS_FILE.exists():
        with open(LEADS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"leads": [], "stats": {"total_captured": 0, "emails_sent": 0}}



def _save_leads(data: dict) -> None:
    if not LEADS_FILE.parent.exists():
        raise OSError(f"Lead directory missing: {LEADS_FILE.parent}")
    if LEADS_FILE.exists():
        st = LEADS_FILE.stat()
        uid = st.st_uid
        gid = st.st_gid
        mode = st.st_mode & 0o777
    else:
        uid = os.getuid()
        gid = os.getgid()
        mode = 0o600
    tmp = LEADS_FILE.parent / f".{LEADS_FILE.name}.{os.getpid()}.{threading.get_ident()}.tmp"
    try:
        with tmp.open("w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2, default=str)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(tmp, mode)
        os.chown(tmp, uid, gid)
        os.replace(tmp, LEADS_FILE)
        try:
            fd = os.open(str(LEADS_FILE.parent), os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
        except OSError:
            pass
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass



# ---------------------------------------------------------------------------
# Controlled PrivateEmail SMTP delivery (no provider fallback)
# ---------------------------------------------------------------------------



def _normalize_email(value: str) -> str:
    """Normalize a conservative Internet email shape without adding a runtime dependency."""
    email = str(value or "").strip().lower()
    if not email or len(email) > 254 or email.count("@") != 1 or any(ch.isspace() for ch in email):
        return ""
    local, domain = email.rsplit("@", 1)
    if not local or len(local) > 64 or not domain or "." not in domain:
        return ""
    if local.startswith(".") or local.endswith(".") or ".." in local:
        return ""
    labels = domain.split(".")
    if len(labels[-1]) < 2:
        return ""
    for label in labels:
        if (
            not label
            or len(label) > 63
            or label.startswith("-")
            or label.endswith("-")
            or not all(ch.isalnum() or ch == "-" for ch in label)
        ):
            return ""
    return email


def _lead_ref(email: str) -> str:
    """Return a stable non-PII reference for operational logs."""
    normalized = (email or "").strip().lower()
    if not normalized:
        return "missing"
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:12]

def _send_email(to_email: str, to_name: str, subject: str, html_body: str) -> bool:
    """Send through approved PrivateEmail SMTP only; fail closed on any error."""
    lead_ref = _lead_ref(to_email)
    if DRIP_SEND_MODE != "live":
        log.info("DRIP HOLD: transport blocked lead_ref=%s mode=%s", lead_ref, DRIP_SEND_MODE)
        return False
    if not GMAIL_ADDRESS or not GMAIL_PASSWORD:
        log.error("SMTP blocked: credentials unavailable lead_ref=%s", lead_ref)
        return False
    try:
        import smtplib
        from email.mime.multipart import MIMEMultipart
        from email.mime.text import MIMEText

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"{FROM_NAME} <{FROM_EMAIL}>"
        msg["To"] = to_email
        msg["Reply-To"] = FROM_EMAIL
        msg.attach(MIMEText(html_body, "html"))
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20) as srv:
            srv.starttls()
            srv.login(GMAIL_ADDRESS, GMAIL_PASSWORD)
            srv.send_message(msg)
        log.info("SMTP sent lead_ref=%s subject=%s", lead_ref, subject)
        return True
    except Exception as exc:  # noqa: BLE001
        log.error(
            "SMTP failed lead_ref=%s error_type=%s; provider fallback disabled",
            lead_ref,
            type(exc).__name__,
        )
        return False

# ---------------------------------------------------------------------------
# Email content -- 5 emails x 3 books = 15 total
# ---------------------------------------------------------------------------

DRIP_SCHEDULE = [
    {"day": 0, "key": "welcome"},
    {"day": 2, "key": "value"},
    {"day": 5, "key": "social_proof"},
    {"day": 7, "key": "soft_sell"},
    {"day": 14, "key": "last_chance"},
]

AMAZON_LINKS = {
    "golden_years": "https://www.amazon.com/dp/B0F1YFP8QP",
    "sovereign_mind": "https://www.amazon.com/dp/B0F55B6ZKW",
    "debt_freedom": "https://www.amazon.com/dp/B0F4ZZ7YQ7",
}

BUNDLE_LINK = "https://www.amazon.com/s?k=Dominion+Healing+Press"


def _wrap_html(body: str) -> str:
    """Wrap message content; scheduler appends the one canonical signed unsubscribe link."""
    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1.0"></head>
<body style="font-family:Georgia,serif;max-width:600px;margin:0 auto;padding:20px;color:#2d2d2d;line-height:1.7;">
{body}
</body></html>"""

# ===== GOLDEN YEARS WORD SEARCH =====

EMAILS_GOLDEN_YEARS = {
    "welcome": {
        "subject": "A simple puzzle habit to start today",
        "body": _wrap_html("""
<h2 style="color:#5b4a3f;">Welcome, {{name}}!</h2>
<p>Thank you for joining the Dominion Healing community.</p>
<p>Word searches are recreational puzzles that practice attention, scanning, and pattern recognition. They can be an enjoyable part of a mentally active routine, but they are not a treatment or a guarantee against cognitive decline.</p>
<p style="background:#faf6f0;padding:15px;border-left:4px solid #c9a96e;"><strong>60-Second Word Challenge:</strong> Write down 10 words related to "garden" as fast as you can. Tomorrow, try a different theme. Use it for variety, not as a medical test.</p>
<p><em>Golden Years Word Search</em> includes 90+ large-print puzzles across themes such as nature, family, travel, and everyday life.</p>
<p>In two days, I will send three simple ideas for making a puzzle routine easier to enjoy.</p>
<p>Stay curious,<br><strong>Dominion Healing Press</strong></p>
"""),
    },
    "value": {
        "subject": "3 simple habits for a more intentional day",
        "body": _wrap_html("""
<h2 style="color:#5b4a3f;">Three Simple Routine Ideas</h2>
<p>Hi {{name}},</p>
<ol>
<li><strong>Hydration.</strong> Keep water available and follow any guidance your clinician has given you about fluid intake.</li>
<li><strong>Movement.</strong> If it is appropriate for you, walking or another activity you enjoy can be part of a balanced routine.</li>
<li><strong>Variety.</strong> Rotate between puzzles, reading, conversation, hobbies, and other activities you enjoy.</li>
</ol>
<p>If you enjoy word searches, a short puzzle session can be one pleasant, screen-free part of your day.</p>
<p>To your routine,<br><strong>Dominion Healing Press</strong></p>
"""),
    },
    "social_proof": {
        "subject": "What makes a puzzle habit easier to keep",
        "body": _wrap_html("""
<h2 style="color:#5b4a3f;">Make the Habit Easy to Return To</h2>
<p>Hi {{name}},</p>
<p>A puzzle routine is easier to keep when the material is readable, the sessions are short enough to enjoy, and you can stop and restart without losing your place.</p>
<p><em>Golden Years Word Search</em> uses large print, themed puzzles, and a full solution key so the activity can stay recreational instead of becoming frustrating.</p>
<p>Consistency does not require perfection. Pick a time that fits your day and use the book when you want a focused activity.</p>
<p>Warmly,<br><strong>Dominion Healing Press</strong></p>
"""),
    },
    "soft_sell": {
        "subject": "90+ large-print puzzles for your routine",
        "body": _wrap_html(f"""
<h2 style="color:#5b4a3f;">Ready to Keep the Puzzle Habit Going?</h2>
<p>Hi {{{{name}}}},</p>
<p><em>Golden Years Word Search</em> includes:</p>
<ul>
<li>90+ large-print puzzles across 12 themes</li>
<li>Progressive difficulty</li>
<li>A full solution key</li>
<li>A format designed for easy, screen-free use</li>
</ul>
<p style="text-align:center;margin:25px 0;"><a href="{AMAZON_LINKS['golden_years']}" style="background:#c9a96e;color:#fff;padding:14px 28px;text-decoration:none;border-radius:6px;font-weight:bold;">Get Your Copy on Amazon</a></p>
<p>If that format fits your routine, the book is there when you want the next puzzle.</p>
<p>Stay well,<br><strong>Dominion Healing Press</strong></p>
"""),
    },
    "last_chance": {
        "subject": "Three different tools for three different routines",
        "body": _wrap_html(f"""
<h2 style="color:#5b4a3f;">One Last Note, {{{{name}}}}</h2>
<p>This is the last email in this series.</p>
<p>Dominion Healing Press currently offers three different kinds of structured practice:</p>
<ol>
<li><strong>Golden Years Word Search</strong> -- recreational puzzle practice</li>
<li><strong>Sovereign Mind Journal</strong> -- guided reflection</li>
<li><strong>Debt Freedom Planner</strong> -- structured debt-payoff planning</li>
</ol>
<p style="text-align:center;margin:25px 0;"><a href="{BUNDLE_LINK}" style="background:#c9a96e;color:#fff;padding:14px 28px;text-decoration:none;border-radius:6px;font-weight:bold;">Browse the Books on Amazon</a></p>
<p>Thank you for spending these two weeks with us.</p>
<p>With gratitude,<br><strong>Dominion Healing Press</strong></p>
"""),
    },
}

# ===== SOVEREIGN MIND JOURNAL =====

EMAILS_SOVEREIGN_MIND = {
    "welcome": {
        "subject": "Turn one intention into a written next step",
        "body": _wrap_html("""
<h2 style="color:#5b4a3f;">Welcome, {{name}}!</h2>
<p>Thank you for joining us.</p>
<p>Writing a goal down can make a vague intention more concrete. Research on goal setting has examined written commitments and accountability, but no writing exercise guarantees an outcome.</p>
<p style="background:#faf6f0;padding:15px;border-left:4px solid #c9a96e;"><strong>The Sovereignty Snapshot:</strong> Write one sentence for each question: (1) What do I want most right now? (2) What is getting in the way? (3) What is one action I can take today?</p>
<p>The <em>Sovereign Mind Journal</em> provides 90 days of guided prompts, gratitude frames, and reflection checkpoints designed to help you examine your own patterns and choices.</p>
<p>In two days, I will send a practical way to make gratitude entries more specific.</p>
<p>Own your next step,<br><strong>Dominion Healing Press</strong></p>
"""),
    },
    "value": {
        "subject": "A more specific way to practice gratitude",
        "body": _wrap_html("""
<h2 style="color:#5b4a3f;">Make Gratitude More Specific</h2>
<p>Hi {{name}},</p>
<p>Research reviews suggest gratitude practices can produce small average improvements in well-being, although effects vary from person to person.</p>
<p>One useful technique is to record a specific moment instead of repeating the same broad phrase every day:</p>
<ul>
<li><strong>Broad:</strong> "I am grateful for my health."</li>
<li><strong>Specific:</strong> "I am grateful I had enough energy to walk to the park this morning."</li>
</ul>
<p>The second entry gives you a concrete event to reflect on later. The journal uses specific prompts to help you build a more detailed record of your own observations.</p>
<p>Intentionally,<br><strong>Dominion Healing Press</strong></p>
"""),
    },
    "social_proof": {
        "subject": "A structured way to notice your own patterns",
        "body": _wrap_html("""
<h2 style="color:#5b4a3f;">Use Prompts to Notice Patterns</h2>
<p>Hi {{name}},</p>
<p>A blank page asks you to invent both the question and the answer. A guided journal removes the first problem by giving you a specific prompt to respond to.</p>
<p>That structure can help you compare what you wrote across days and weeks, notice recurring themes, and decide what you want to do next.</p>
<p>It is a reflection tool, not a substitute for professional mental-health care.</p>
<p>Onward,<br><strong>Dominion Healing Press</strong></p>
"""),
    },
    "soft_sell": {
        "subject": "A 90-day guided reflection structure",
        "body": _wrap_html(f"""
<h2 style="color:#5b4a3f;">Your 90-Day Reflection Framework</h2>
<p>Hi {{{{name}}}},</p>
<p><em>Sovereign Mind Journal</em> includes:</p>
<ul>
<li>90 daily guided prompts</li>
<li>Weekly reflection checkpoints</li>
<li>Specific gratitude prompts</li>
<li>Goal-setting and next-action exercises</li>
<li>Morning and evening routine suggestions</li>
</ul>
<p style="text-align:center;margin:25px 0;"><a href="{AMAZON_LINKS['sovereign_mind']}" style="background:#c9a96e;color:#fff;padding:14px 28px;text-decoration:none;border-radius:6px;font-weight:bold;">Get Your Copy on Amazon</a></p>
<p>Ninety days gives you a defined practice window. What you get from it depends on how consistently and thoughtfully you use it.</p>
<p>With conviction,<br><strong>Dominion Healing Press</strong></p>
"""),
    },
    "last_chance": {
        "subject": "Reflection, puzzles, and financial planning",
        "body": _wrap_html(f"""
<h2 style="color:#5b4a3f;">Before I Go, {{{{name}}}}</h2>
<p>This is the final email in this series.</p>
<p>The Dominion Healing Press books serve different purposes:</p>
<ol>
<li><strong>Sovereign Mind Journal</strong> -- guided reflection</li>
<li><strong>Golden Years Word Search</strong> -- recreational puzzle practice</li>
<li><strong>Debt Freedom Planner</strong> -- structured debt-payoff planning</li>
</ol>
<p style="text-align:center;margin:25px 0;"><a href="{BUNDLE_LINK}" style="background:#c9a96e;color:#fff;padding:14px 28px;text-decoration:none;border-radius:6px;font-weight:bold;">See the Books on Amazon</a></p>
<p>Use whichever tool fits the area you want to work on.</p>
<p>With respect,<br><strong>Dominion Healing Press</strong></p>
"""),
    },
}

# ===== DEBT FREEDOM PLANNER =====

EMAILS_DEBT_FREEDOM = {
    "welcome": {
        "subject": "Start with the numbers you can actually see",
        "body": _wrap_html("""
<h2 style="color:#5b4a3f;">Welcome, {{name}}!</h2>
<p>Thank you for signing up. You chose to look at your debt directly and turn it into a set of numbers you can work with.</p>
<p>A repayment plan starts with concrete information: balances, interest rates, minimum payments, fees, and available cash flow.</p>
<p style="background:#faf6f0;padding:15px;border-left:4px solid #c9a96e;"><strong>The Starting Number:</strong> List each debt and record its current balance, rate, and required payment. This is a planning baseline, not a judgment about you.</p>
<p>The <em>Debt Freedom Planner</em> provides worksheets for organizing those numbers and comparing payoff approaches.</p>
<p>In two days, I will break down two common payoff strategies.</p>
<p>To your plan,<br><strong>Dominion Healing Press</strong></p>
"""),
    },
    "value": {
        "subject": "Snowball vs. avalanche -- two common approaches",
        "body": _wrap_html("""
<h2 style="color:#5b4a3f;">Two Ways to Order Extra Payments</h2>
<p>Hi {{name}},</p>
<p><strong>Debt snowball:</strong> Pay required minimums, then direct available extra money to the smallest balance first. When it is paid, roll that amount toward the next balance. Some people prefer the earlier account closures.</p>
<p><strong>Debt avalanche:</strong> Pay required minimums, then direct available extra money to the highest interest rate first. With the same payment amounts and no special constraints, prioritizing higher rates generally reduces interest cost compared with paying lower-rate balances first.</p>
<p>Which approach fits depends on your balances, rates, fees, cash flow, and what you can sustain. The planner includes worksheets for both so you can compare and revise a working timeline.</p>
<p>Strategically,<br><strong>Dominion Healing Press</strong></p>
"""),
    },
    "social_proof": {
        "subject": "Why visible progress matters in a payoff plan",
        "body": _wrap_html("""
<h2 style="color:#5b4a3f;">Make Progress Visible</h2>
<p>Hi {{name}},</p>
<p>A payoff plan is easier to evaluate when balances, rates, required payments, and extra payments are visible in one place.</p>
<p>Tracking each update gives you a record you can compare with your original estimate. If income, expenses, rates, or balances change, revise the plan rather than treating the first timeline as a promise.</p>
<p>The planner is designed to make that record-keeping straightforward.</p>
<p>Warmly,<br><strong>Dominion Healing Press</strong></p>
"""),
    },
    "soft_sell": {
        "subject": "Build a debt-payoff plan you can update",
        "body": _wrap_html(f"""
<h2 style="color:#5b4a3f;">Put the Plan in One Place</h2>
<p>Hi {{{{name}}}},</p>
<p><em>Debt Freedom Planner</em> includes:</p>
<ul>
<li>Debt inventory worksheets for balances, rates, and minimums</li>
<li>Snowball and avalanche planning templates</li>
<li>Budget worksheets for identifying possible room for extra payments</li>
<li>Progress tracking pages</li>
<li>Emergency-fund planning prompts</li>
</ul>
<p style="text-align:center;margin:25px 0;"><a href="{AMAZON_LINKS['debt_freedom']}" style="background:#c9a96e;color:#fff;padding:14px 28px;text-decoration:none;border-radius:6px;font-weight:bold;">Get Your Copy on Amazon</a></p>
<p>The planner helps you choose an order, estimate a timeline, and track progress. Results depend on your balances, rates, fees, income, and payment amounts.</p>
<p>To your plan,<br><strong>Dominion Healing Press</strong></p>
"""),
    },
    "last_chance": {
        "subject": "Three practical books, three different uses",
        "body": _wrap_html(f"""
<h2 style="color:#5b4a3f;">The Final Note, {{{{name}}}}</h2>
<p>This is the last email in this series.</p>
<ol>
<li><strong>Debt Freedom Planner</strong> -- structured debt-payoff planning</li>
<li><strong>Sovereign Mind Journal</strong> -- guided reflection</li>
<li><strong>Golden Years Word Search</strong> -- recreational puzzle practice</li>
</ol>
<p style="text-align:center;margin:25px 0;"><a href="{BUNDLE_LINK}" style="background:#c9a96e;color:#fff;padding:14px 28px;text-decoration:none;border-radius:6px;font-weight:bold;">See the Books on Amazon</a></p>
<p>Use the tools that fit your goals and circumstances.</p>
<p>With respect,<br><strong>Dominion Healing Press</strong></p>
"""),
    },
}

# ===== DIVINE SOVEREIGNTY =====

EMAILS_DIVINE_SOVEREIGNTY = {
    "welcome": {
        "subject": "Your sovereignty starts with what you choose to examine",
        "body": _wrap_html("""
<h2 style="color:#5b4a3f;">Welcome, {{name}}.</h2>
<p>Thank you for joining Dominion Healing.</p>
<p><em>Divine Sovereignty</em> presents a spiritual and personal-development framework for examining authority, responsibility, faith, finances, and future choices.</p>
<p style="background:#faf6f0;padding:15px;border-left:4px solid #d4af37;"><strong>Sovereignty is not rebellion.</strong> In the book's framework, it begins with examining what you believe, what you are responsible for, and how those beliefs show up in your decisions.</p>
<p>Over the next two weeks, I will share several themes from the book for you to consider.</p>
<p>Stay sovereign,<br><strong>Dewayne Singleton</strong><br>Dominion Healing</p>
"""),
    },
    "value": {
        "subject": "Five questions for examining inherited beliefs",
        "body": _wrap_html("""
<h2 style="color:#5b4a3f;">Five Practices from the Book</h2>
<p>Hi {{name}},</p>
<ol>
<li><strong>Identify the unquestioned belief.</strong></li>
<li><strong>Trace the source.</strong> Where did it come from?</li>
<li><strong>Test it.</strong> Does it hold up under honest scrutiny?</li>
<li><strong>Choose deliberately.</strong> What belief or principle do you want to act from?</li>
<li><strong>Guard the gates.</strong> Be intentional about what you repeatedly allow to shape your thinking.</li>
</ol>
<p>This is a repeatable practice for examining assumptions and choices within the book's spiritual framework.</p>
<p>In truth,<br><strong>Dewayne Singleton</strong></p>
"""),
    },
    "social_proof": {
        "subject": "Questions Divine Sovereignty asks you to examine",
        "body": _wrap_html("""
<h2 style="color:#5b4a3f;">Questions Worth Examining</h2>
<p>Hi {{name}},</p>
<ul>
<li>Which beliefs did you inherit without examining?</li>
<li>Which values do you want your decisions to reflect?</li>
<li>Where do responsibility, faith, and personal agency meet in your daily life?</li>
</ul>
<p>The book develops these questions through its own spiritual and personal-development framework.</p>
<p>Warmly,<br><strong>Dewayne Singleton</strong></p>
"""),
    },
    "soft_sell": {
        "subject": "Freedom, purpose, and responsibility -- inside one book",
        "body": _wrap_html("""
<h2 style="color:#5b4a3f;">Ready to Read Divine Sovereignty?</h2>
<p>Hi {{name}},</p>
<p>The book is organized around three parts:</p>
<ul>
<li><strong>Part One: The Foundation</strong> -- awakening, invisible constraints, and divine law</li>
<li><strong>Part Two: The Transformation</strong> -- examining bondage, creator mindset, responsibility, and beliefs about wealth</li>
<li><strong>Part Three: The Ascension</strong> -- faith, purpose, and life beyond self-imposed limitation</li>
</ul>
<p style="text-align:center;margin:25px 0;"><a href="https://buy.stripe.com/9B6cN5ar19NJfbr4k78Zq0b" style="background:linear-gradient(135deg,#d4af37,#a07830);color:#000;padding:14px 28px;text-decoration:none;border-radius:6px;font-weight:bold;">Get Divine Sovereignty -- $19</a></p>
<p>In service,<br><strong>Dewayne Singleton</strong></p>
"""),
    },
    "last_chance": {
        "subject": "One last note about Divine Sovereignty",
        "body": _wrap_html("""
<h2 style="color:#5b4a3f;">The Choice Is Yours</h2>
<p>Hi {{name}},</p>
<p>The book's core theme is that internal authority should show up in your decisions, habits, and responsibilities.</p>
<p style="text-align:center;margin:25px 0;"><a href="https://buy.stripe.com/9B6cN5ar19NJfbr4k78Zq0b" style="background:linear-gradient(135deg,#d4af37,#a07830);color:#000;padding:14px 28px;text-decoration:none;border-radius:6px;font-weight:bold;">Get Divine Sovereignty -- $19</a></p>
<p>The path described in the book is an invitation to examine and choose; the choice remains yours.</p>
<p>With honor,<br><strong>Dewayne Singleton</strong><br>Founder, Dominion Healing</p>
"""),
    },
}

# Map source keywords to book email sets
BOOK_EMAILS = {
    "golden_years": EMAILS_GOLDEN_YEARS,
    "sovereign_mind": EMAILS_SOVEREIGN_MIND,
    "debt_freedom": EMAILS_DEBT_FREEDOM,
    "divine_sovereignty": EMAILS_DIVINE_SOVEREIGNTY,
}

BOOK_EMAILS["free_audit_hold"] = {}

BOOK_DISCLAIMERS = {
    "golden_years": "Recreational and general educational content only; not medical advice or treatment.",
    "sovereign_mind": "Personal reflection and general educational content only; not mental-health treatment.",
    "debt_freedom": "General educational planning content only; not individualized financial, tax, or legal advice.",
    "divine_sovereignty": "Spiritual and personal-development content; not medical, legal, or financial advice.",
    "free_audit_hold": "",
}

# Default if no source match
DEFAULT_BOOK = "sovereign_mind"

SOURCE_TO_BOOK = {
    "free_audit": "free_audit_hold",
    "golden_years": "golden_years",
    "word_search": "golden_years",
    "wordsearch": "golden_years",
    "brain": "golden_years",
    "puzzle": "golden_years",
    "senior": "golden_years",
    "sovereign_mind": "sovereign_mind",
    "journal": "sovereign_mind",
    "mindset": "sovereign_mind",
    "gratitude": "sovereign_mind",
    "debt_freedom": "debt_freedom",
    "debt": "debt_freedom",
    "planner": "debt_freedom",
    "financial": "debt_freedom",
    "money": "debt_freedom",
    "divine_sovereignty": "divine_sovereignty",
    "divine": "divine_sovereignty",
    "sovereignty": "divine_sovereignty",
    "freedom": "divine_sovereignty",
    "awakening": "divine_sovereignty",
}


def _resolve_book(source: str) -> str:
    src = (source or "").lower().replace(" ", "_").replace("-", "_")
    for key, book in SOURCE_TO_BOOK.items():
        if key in src:
            return book
    return DEFAULT_BOOK



def _suppression_state(email: str) -> str:
    try:
        with SUPPRESSION_LOCK:
            if not SUPPRESSION_FILE.exists():
                return "error"
            with SUPPRESSION_FILE.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
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
        WEBHOOK_SECRET.encode("utf-8"),
        normalized.encode("utf-8"),
        "sha256",
    ).hexdigest()[:32]
    encoded = base64.urlsafe_b64encode(normalized.encode("utf-8")).decode("ascii").rstrip("=")
    return f"{UNSUBSCRIBE_BASE_URL}?e={encoded}&t={token}"


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------



class EmailCapture(BaseModel):
    email: str
    name: Optional[str] = None
    source: Optional[str] = ""
    unsubscribe_url: Optional[str] = ""



# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@app.post("/api/email-capture")

def capture_email(payload: EmailCapture):
    email = _normalize_email(payload.email)
    if not email:
        raise HTTPException(status_code=400, detail="invalid_email")

    suppression = _suppression_state(email)
    if suppression == "error":
        raise HTTPException(status_code=503, detail="suppression_check_failed")
    if suppression == "suppressed":
        return {"status": "suppressed", "message": "Email is unsubscribed"}

    name = (payload.name or "Friend").strip() or "Friend"
    source_value = (payload.source or "").strip()
    book = _resolve_book(source_value)
    unsubscribe_url = _unsubscribe_url(email)

    try:
        with LEADS_LOCK:
            data = _load_leads()
            if not isinstance(data, dict) or not isinstance(data.get("leads"), list):
                raise ValueError("invalid lead store schema")
            data.setdefault("stats", {}).setdefault("total_captured", 0)
            data["stats"].setdefault("emails_sent", 0)

            for lead in data["leads"]:
                if _normalize_email(str(lead.get("email", ""))) == email:
                    if book == "free_audit_hold" and lead.get("book") != "free_audit_hold":
                        lead["source"] = source_value
                        lead["book"] = "free_audit_hold"
                        lead["unsubscribe_url"] = unsubscribe_url
                        _save_leads(data)
                    return {
                        "status": "exists",
                        "message": "Email already registered",
                        "book": "free_audit_hold" if book == "free_audit_hold" else lead.get("book", book),
                    }

            lead = {
                "email": email,
                "name": name,
                "source": source_value,
                "book": book,
                "captured_at": datetime.now(timezone.utc).isoformat(),
                "emails_sent": [],
                "last_sent_at": None,
                "unsubscribe_url": unsubscribe_url,
            }
            data["leads"].append(lead)
            data["stats"]["total_captured"] += 1
            _save_leads(data)
    except (RuntimeError, json.JSONDecodeError, OSError, Timeout, TypeError, ValueError) as exc:
        log.error("Lead store failure: %s", type(exc).__name__)
        raise HTTPException(status_code=503, detail="lead_store_unavailable")

    log.info("Captured lead_ref=%s for book=%s", _lead_ref(email), book)
    return {"status": "ok", "message": f"Lead captured for {book}", "book": book}



@app.get("/api/drip-status")
def drip_status():
    data = _load_leads()
    total = len(data["leads"])
    by_book = {}
    fully_dripped = 0
    for lead in data["leads"]:
        b = lead.get("book", "unknown")
        by_book[b] = by_book.get(b, 0) + 1
        sent_steps = lead.get("emails_sent", [])
        if isinstance(sent_steps, list) and len(sent_steps) >= 5:
            fully_dripped += 1

    return {
        "total_leads": total,
        "leads_by_book": by_book,
        "total_emails_sent": data["stats"].get("emails_sent", 0),
        "fully_completed_sequences": fully_dripped,
        "sendgrid_configured": False,
        "smtp_configured": bool(GMAIL_ADDRESS and GMAIL_PASSWORD),
        "transport": "smtp",
        "from_email": FROM_EMAIL,
        "drip_check_interval_seconds": DRIP_CHECK_INTERVAL,
    }


@app.post("/api/run-drip")
def run_drip_manual():
    sent = _run_drip_cycle()
    return {"status": "ok", "emails_sent_this_cycle": sent}


@app.get("/health")

def health():
    return {
        "status": "ok",
        "service": "email_drip",
        "version": "1.0.0",
        "send_mode": DRIP_SEND_MODE,
    }



# ---------------------------------------------------------------------------
# Drip scheduler logic
# ---------------------------------------------------------------------------


def _plan_due_message(lead: dict, now: datetime) -> dict:
    """Return one scheduler-faithful candidate or a non-send status; never mutate state."""
    raw_email = str(lead.get("email", ""))
    email = _normalize_email(raw_email)
    captured_raw = str(lead.get("captured_at", "")).strip()
    if not email or not captured_raw:
        return {"status": "ghost_or_invalid", "lead_ref": _lead_ref(raw_email)}

    suppression = _suppression_state(email)
    if suppression == "error":
        return {"status": "suppression_error", "lead_ref": _lead_ref(email)}
    if suppression == "suppressed":
        return {"status": "suppressed", "lead_ref": _lead_ref(email)}

    try:
        captured = datetime.fromisoformat(captured_raw.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return {"status": "invalid_captured_at", "lead_ref": _lead_ref(email)}
    if captured.tzinfo is None:
        return {"status": "invalid_captured_at", "lead_ref": _lead_ref(email)}

    days_since = (now - captured).days
    sent_raw = lead.get("emails_sent", [])
    if not isinstance(sent_raw, list):
        return {"status": "invalid_emails_sent", "lead_ref": _lead_ref(email)}
    already_sent = {str(value) for value in sent_raw}
    resolved_from_source = _resolve_book(str(lead.get("source", "")))
    stored_book = str(lead.get("book", "")).strip()
    book = "free_audit_hold" if resolved_from_source == "free_audit_hold" else (stored_book or resolved_from_source)
    if book not in BOOK_EMAILS:
        return {"status": "invalid_book", "book": book, "lead_ref": _lead_ref(email)}
    emails = BOOK_EMAILS[book]
    if not emails:
        return {"status": "no_email_content", "book": book, "lead_ref": _lead_ref(email)}

    for step in DRIP_SCHEDULE:
        if step["key"] in already_sent or days_since < step["day"]:
            continue
        content = emails.get(step["key"])
        if not content:
            continue
        unsubscribe_url = _unsubscribe_url(email)
        return {
            "status": "candidate",
            "email": email,
            "lead_ref": _lead_ref(email),
            "name": lead.get("name") or "Friend",
            "book": book,
            "step": step["key"],
            "subject": content["subject"],
            "body": content["body"],
            "unsubscribe_url": unsubscribe_url,
        }
    return {"status": "no_due_email", "book": book, "lead_ref": _lead_ref(email)}


def _build_preflight_report(data: Optional[dict] = None, now: Optional[datetime] = None) -> dict:
    """Report blast radius through the exact scheduler planner; invoke no transport and mutate no state."""
    snapshot = _load_leads() if data is None else data
    if not isinstance(snapshot, dict) or not isinstance(snapshot.get("leads"), list):
        raise ValueError("invalid lead store schema")
    current = now or datetime.now(timezone.utc)
    status_counts = {}
    candidates = []
    for lead in snapshot["leads"]:
        plan = _plan_due_message(lead, current)
        status = plan["status"]
        status_counts[status] = status_counts.get(status, 0) + 1
        if status == "candidate":
            candidates.append({"book": plan["book"], "step": plan["step"], "subject": plan["subject"]})
    return {
        "total_leads": len(snapshot["leads"]),
        "candidate_count": len(candidates),
        "candidates": candidates,
        "status_counts": status_counts,
        "free_audit_candidate_count": sum(1 for item in candidates if item["book"] == "free_audit_hold"),
        "pii_fields_included": False,
        "transport_invoked": False,
        "state_mutated": False,
    }




def _run_drip_cycle() -> int:
    """Execute one cycle; advance state only after approved SMTP returns success."""
    now = datetime.now(timezone.utc)
    sent_count = 0
    changed = False
    try:
        with LEADS_LOCK:
            data = _load_leads()
            if not isinstance(data, dict) or not isinstance(data.get("leads"), list):
                raise ValueError("invalid lead store schema")
            data.setdefault("stats", {}).setdefault("emails_sent", 0)

            for lead in data["leads"]:
                plan = _plan_due_message(lead, now)
                status = plan["status"]
                if status == "ghost_or_invalid":
                    log.warning("Ghost/invalid drip lead skipped; report-only, no deletion")
                    continue
                if status == "invalid_captured_at":
                    log.warning("Invalid captured_at skipped lead_ref=%s; report-only, no deletion", plan["lead_ref"])
                    continue
                if status == "suppression_error":
                    log.error("Suppression check failed; send blocked lead_ref=%s", plan["lead_ref"])
                    continue
                if status != "candidate":
                    continue
                if DRIP_SEND_MODE != "live":
                    log.info("DRIP HOLD: due email blocked lead_ref=%s book=%s step=%s", plan["lead_ref"], plan["book"], plan["step"])
                    continue

                safe_name = html_lib.escape(str(plan["name"]), quote=True)
                body = plan["body"].replace("{{name}}", safe_name)
                safe_url = html_lib.escape(plan["unsubscribe_url"], quote=True)
                disclaimer = BOOK_DISCLAIMERS.get(plan["book"], "")
                body += '<hr style="margin-top:28px;border:0;border-top:1px solid #ddd;">'
                if disclaimer:
                    body += f'<p style="font-size:12px;color:#777">{html_lib.escape(disclaimer)}</p>'
                body += '<p style="font-size:12px;color:#777">You received this because you signed up at Dominion Healing. ' + f'<a href="{safe_url}">Unsubscribe</a></p>'

                if _send_email(plan["email"], plan["name"], plan["subject"], body):
                    lead.setdefault("emails_sent", []).append(plan["step"])
                    lead["last_sent_at"] = now.isoformat()
                    data["stats"]["emails_sent"] += 1
                    sent_count += 1
                    changed = True

            if changed:
                _save_leads(data)
    except (RuntimeError, json.JSONDecodeError, OSError, Timeout, TypeError, ValueError) as exc:
        log.error("Drip cycle blocked: %s", type(exc).__name__)
        return 0
    log.info("Drip cycle complete: %d emails sent", sent_count)
    return sent_count

def _drip_loop():
    """Background thread that runs the drip cycle on an interval."""
    log.info("Drip scheduler started (interval=%ds)", DRIP_CHECK_INTERVAL)
    while True:
        try:
            _run_drip_cycle()
        except Exception as exc:
            log.error("Drip cycle error_type=%s", type(exc).__name__)
        time.sleep(DRIP_CHECK_INTERVAL)


@app.on_event("startup")
def start_drip_scheduler():
    # Ensure leads file exists
    if not LEADS_FILE.exists():
        _save_leads({"leads": [], "stats": {"total_captured": 0, "emails_sent": 0}})
    thread = threading.Thread(target=_drip_loop, daemon=True)
    thread.start()
    log.info("Email drip engine online | from=%s | transport=smtp | mode=%s", FROM_EMAIL, DRIP_SEND_MODE)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    uvicorn.run(
        "email_drip:app",
        host=os.getenv("DRIP_HOST", "127.0.0.1"),
        port=int(os.getenv("DRIP_PORT", "8099")),
        reload=False,
        log_level="info",
    )
