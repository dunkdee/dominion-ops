"""
Dominion Healing -- KDP Email Drip Sequence Engine
===================================================
FastAPI service that captures leads and runs a 5-email drip sequence
for each of the three KDP books.

Endpoints:
    POST /api/email-capture   -- capture a new lead
    GET  /api/drip-status      -- dashboard stats
    POST /api/run-drip         -- manually trigger drip scheduler

Deploy: systemd service on foundation-vm  |  SendGrid for delivery
"""

import os
import json
import time
import logging
import threading
import base64
import hmac
import html as html_lib
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional
from filelock import FileLock, Timeout

from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel, EmailStr
import uvicorn

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

DATA_DIR = Path(__file__).parent
LEADS_FILE = DATA_DIR / "leads_drip.json"
SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY", "")
SMTP_HOST     = os.getenv("SMTP_HOST", "mail.privateemail.com")
SMTP_PORT     = int(os.getenv("SMTP_PORT", "587"))
GMAIL_ADDRESS = os.getenv("SMTP_EMAIL", os.getenv("EMAIL_ADDRESS", ""))
GMAIL_PASSWORD = os.getenv("SMTP_PASSWORD", os.getenv("EMAIL_PASSWORD", ""))
FROM_EMAIL = os.getenv("DRIP_FROM_EMAIL", "dewayne@dominionhealing.org")
FROM_NAME = os.getenv("DRIP_FROM_NAME", "Dewayne | Dominion Healing")
DRIP_CHECK_INTERVAL = int(os.getenv("DRIP_CHECK_INTERVAL", "3600"))  # seconds
DRIP_SEND_MODE = os.getenv("DRIP_SEND_MODE", "hold").strip().lower()
LEADS_FILE = Path(os.getenv("DRIP_LEADS_FILE", str(LEADS_FILE)))
SUPPRESSION_FILE = Path(os.getenv(
    "DRIP_SUPPRESSION_FILE",
    "/home/malachisingleton8/buddy_core/email_suppression.json",
))
UNSUBSCRIBE_BASE_URL = os.getenv(
    "UNSUBSCRIBE_BASE_URL",
    "https://dominionhealing.org/api/unsubscribe",
)
SECRET_PATH = Path("/home/malachisingleton8/buddy_core/core/webhook_secret.key")
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
# SendGrid delivery (graceful fallback)
# ---------------------------------------------------------------------------



def _send_email(to_email: str, to_name: str, subject: str, html_body: str) -> bool:
    """Send only when DRIP_SEND_MODE=live. HOLD touches no transport or outbox."""
    if DRIP_SEND_MODE != "live":
        log.info("DRIP HOLD: transport blocked for %s (mode=%s)", to_email, DRIP_SEND_MODE)
        return False

    if GMAIL_ADDRESS and GMAIL_PASSWORD:
        try:
            import smtplib
            from email.mime.text import MIMEText
            from email.mime.multipart import MIMEMultipart
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = f"{FROM_NAME} <{FROM_EMAIL}>"
            msg["To"] = to_email
            msg["Reply-To"] = FROM_EMAIL
            msg.attach(MIMEText(html_body, "html"))
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as srv:
                srv.starttls()
                srv.login(GMAIL_ADDRESS, GMAIL_PASSWORD)
                srv.send_message(msg)
            log.info("SMTP sent to %s: %s", to_email, subject)
            return True
        except Exception as smtp_err:
            log.error("SMTP failed for %s: %s -- trying SendGrid", to_email, smtp_err)

    if SENDGRID_API_KEY:
        try:
            import sendgrid
            from sendgrid.helpers.mail import Mail, Email, To, Content
            sg = sendgrid.SendGridAPIClient(api_key=SENDGRID_API_KEY)
            message = Mail(
                from_email=Email(FROM_EMAIL, FROM_NAME),
                to_emails=To(to_email, to_name),
                subject=subject,
                html_content=Content("text/html", html_body),
            )
            response = sg.send(message)
            log.info("SendGrid sent to %s | status=%s", to_email, response.status_code)
            return 200 <= response.status_code < 300
        except Exception as exc:
            log.error("SendGrid error for %s: %s", to_email, exc)

    from pathlib import Path as _Path
    import json as _json
    _outbox = _Path.home() / "email_outbox"
    _outbox.mkdir(exist_ok=True)
    _ts = __import__("datetime").datetime.now().strftime("%Y%m%d_%H%M%S")
    _efile = _outbox / f"{_ts}_{to_email.replace('@', '_at_')}.json"
    _tmp = _efile.parent / f".{_efile.name}.{os.getpid()}.tmp"
    with _tmp.open("w", encoding="utf-8") as _handle:
        _json.dump({
            "to": to_email,
            "name": to_name,
            "subject": subject,
            "body": html_body,
            "queued_at": _ts,
        }, _handle)
        _handle.flush()
        os.fsync(_handle.fileno())
    os.replace(_tmp, _efile)
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
    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1.0"></head>
<body style="font-family:Georgia,serif;max-width:600px;margin:0 auto;padding:20px;color:#2d2d2d;line-height:1.7;">
{body}
<hr style="border:none;border-top:1px solid #e0d6c8;margin-top:30px;">
<p style="font-size:12px;color:#999;">You received this because you signed up at Dominion Healing.<br>
<a href="mailto:{FROM_EMAIL}?subject=Unsubscribe">Unsubscribe</a></p>
</body></html>"""


# ===== GOLDEN YEARS WORD SEARCH =====

EMAILS_GOLDEN_YEARS = {
    "welcome": {
        "subject": "Your brain just thanked you (here's a free puzzle)",
        "body": _wrap_html("""
<h2 style="color:#5b4a3f;">Welcome, {{name}}!</h2>
<p>Thank you for joining the Dominion Healing community. You just took a real step toward keeping your mind sharp and active.</p>
<p>Here is something most people do not realize: <strong>word search puzzles activate the same neural pathways used in memory recall and pattern recognition.</strong> Neurologists at Johns Hopkins confirmed that adults who engage in daily word puzzles show measurably slower cognitive decline.</p>
<p>To get you started, try this quick exercise right now:</p>
<p style="background:#faf6f0;padding:15px;border-left:4px solid #c9a96e;">
<strong>60-Second Brain Boost:</strong> Write down 10 words related to "garden" as fast as you can. Time yourself. Tomorrow, try to beat your time. This simple drill strengthens the same retrieval circuits our puzzles target.</p>
<p>Our <em>Golden Years Word Search</em> book has 90+ large-print puzzles built around themes that matter to you -- health, nature, family, travel, and more.</p>
<p>Keep an eye on your inbox. In two days, I am sending you three brain-health tips that pair perfectly with your puzzle practice.</p>
<p>Stay sharp,<br><strong>Dominion Healing Press</strong></p>
"""),
    },
    "value": {
        "subject": "3 brain-health habits backed by science",
        "body": _wrap_html("""
<h2 style="color:#5b4a3f;">3 Daily Habits That Protect Your Memory</h2>
<p>Hi {{name}},</p>
<p>Puzzles are powerful, but they work best alongside these three research-backed habits:</p>
<ol>
<li><strong>Morning hydration.</strong> Your brain is 75% water. Even mild dehydration reduces concentration by up to 13%. Drink a full glass before breakfast.</li>
<li><strong>The 20-minute walk.</strong> A University of British Columbia study showed that regular aerobic exercise actually increases the size of the hippocampus -- the brain region tied to verbal memory and learning.</li>
<li><strong>Novel challenges.</strong> Routine numbs your neurons. Word searches work because each puzzle forces your brain to scan, compare, and decide -- activities that build new synaptic connections at any age.</li>
</ol>
<p>Pair these habits with a daily puzzle session from <em>Golden Years Word Search</em> and you are giving your brain a full workout -- no gym membership required.</p>
<p>More coming in a few days.</p>
<p>To your clarity,<br><strong>Dominion Healing Press</strong></p>
"""),
    },
    "social_proof": {
        "subject": "\"My mother does a puzzle every morning now\"",
        "body": _wrap_html("""
<h2 style="color:#5b4a3f;">Real People, Real Results</h2>
<p>Hi {{name}},</p>
<p>We asked readers what changed after they started doing daily word searches. Here is what they told us:</p>
<blockquote style="border-left:4px solid #c9a96e;padding:10px 15px;background:#faf6f0;margin:15px 0;">
"I bought this for my mother after her doctor suggested brain exercises. She does one puzzle every morning with her coffee. Her focus and mood have both improved noticeably." -- <em>R. Thompson</em>
</blockquote>
<blockquote style="border-left:4px solid #c9a96e;padding:10px 15px;background:#faf6f0;margin:15px 0;">
"The large print is a game-changer. I tried other puzzle books and could not read them without my magnifying glass. This one I can do anywhere." -- <em>M. Dawson</em>
</blockquote>
<p>What these readers have in common is simple: they committed to a small daily habit and their brains responded. Cognitive fitness is not about grand gestures. It is about consistent, enjoyable practice.</p>
<p>If you have been thinking about starting, now is the perfect time.</p>
<p>Warmly,<br><strong>Dominion Healing Press</strong></p>
"""),
    },
    "soft_sell": {
        "subject": "90+ puzzles designed for sharper days ahead",
        "body": _wrap_html(f"""
<h2 style="color:#5b4a3f;">Ready to Make It a Daily Habit?</h2>
<p>Hi {{{{name}}}},</p>
<p>Over the past week, you have learned why word puzzles protect your memory, the three daily habits that amplify the effect, and what other readers have experienced.</p>
<p>If any of that resonated, <em>Golden Years Word Search</em> was built for exactly this moment:</p>
<ul>
<li>90+ large-print puzzles across 12 life-enriching themes</li>
<li>Progressive difficulty -- start comfortable, build strength</li>
<li>Full solution key in the back so you never get stuck</li>
<li>Designed for readers 55+ who want substance, not fluff</li>
</ul>
<p style="text-align:center;margin:25px 0;">
<a href="{AMAZON_LINKS['golden_years']}" style="background:#c9a96e;color:#fff;padding:14px 28px;text-decoration:none;border-radius:6px;font-weight:bold;">Get Your Copy on Amazon</a>
</p>
<p>A sharper mind is a daily choice. This book makes that choice easy.</p>
<p>Stay well,<br><strong>Dominion Healing Press</strong></p>
"""),
    },
    "last_chance": {
        "subject": "Complete your brain-health library (all 3 books)",
        "body": _wrap_html(f"""
<h2 style="color:#5b4a3f;">One Last Thing, {{{{name}}}}</h2>
<p>Two weeks ago you took the first step toward a sharper, more engaged mind. That matters.</p>
<p>Today I want to share something we put together for committed readers: <strong>the Dominion Healing complete library.</strong></p>
<p>Three books. Three dimensions of personal growth:</p>
<ol>
<li><strong>Golden Years Word Search</strong> -- cognitive fitness through daily puzzles</li>
<li><strong>Sovereign Mind Journal</strong> -- mindset mastery through guided reflection</li>
<li><strong>Debt Freedom Planner</strong> -- financial clarity through structured action</li>
</ol>
<p>Together they cover mind, purpose, and prosperity. Readers who pick up all three tell us it feels like a personal development system, not just a stack of books.</p>
<p style="text-align:center;margin:25px 0;">
<a href="{BUNDLE_LINK}" style="background:#c9a96e;color:#fff;padding:14px 28px;text-decoration:none;border-radius:6px;font-weight:bold;">Browse All 3 Books on Amazon</a>
</p>
<p>This is my last email in this series. Whatever you decide, thank you for spending these two weeks with us. Your brain is already better for it.</p>
<p>With gratitude,<br><strong>Dominion Healing Press</strong></p>
"""),
    },
}

# ===== SOVEREIGN MIND JOURNAL =====

EMAILS_SOVEREIGN_MIND = {
    "welcome": {
        "subject": "Your mind is sovereign -- here's how to prove it",
        "body": _wrap_html("""
<h2 style="color:#5b4a3f;">Welcome, {{name}}!</h2>
<p>Thank you for joining us. The fact that you are here tells me something important: you are not content to drift. You want direction, clarity, and control over your own thinking.</p>
<p>That instinct is backed by hard science. A 2015 study published in <em>Psychological Science</em> found that people who write about their goals are <strong>42% more likely to achieve them</strong> than those who simply think about them.</p>
<p>Here is a challenge to start right now:</p>
<p style="background:#faf6f0;padding:15px;border-left:4px solid #c9a96e;">
<strong>The Sovereignty Snapshot:</strong> Grab a piece of paper. Write one sentence answering each question: (1) What do I want most right now? (2) What is stopping me? (3) What is one action I can take today? This 3-line exercise is the seed of everything our journal builds on.</p>
<p>The <em>Sovereign Mind Journal</em> gives you 90 days of guided prompts, gratitude frames, and reflection architecture designed to rewire how you think about your own potential.</p>
<p>In two days, I will send you the science behind gratitude journaling -- and why most people do it wrong.</p>
<p>Own your mind,<br><strong>Dominion Healing Press</strong></p>
"""),
    },
    "value": {
        "subject": "Why most gratitude journals fail (and what works instead)",
        "body": _wrap_html("""
<h2 style="color:#5b4a3f;">The Gratitude Mistake Almost Everyone Makes</h2>
<p>Hi {{name}},</p>
<p>You have probably heard that gratitude journaling improves happiness. That is true -- but there is a catch most people miss.</p>
<p><strong>Writing "I'm grateful for my family" every day does almost nothing.</strong></p>
<p>Research from UC Davis psychologist Robert Emmons shows that gratitude only rewires your brain when it is <em>specific</em> and <em>novel</em>. Here is the difference:</p>
<ul>
<li><strong>Weak:</strong> "I'm grateful for my health."</li>
<li><strong>Strong:</strong> "I'm grateful that my knee felt good enough to walk to the park this morning and watch the herons."</li>
</ul>
<p>The second version forces your brain to relive the experience. That activates the prefrontal cortex and floods your system with dopamine and serotonin -- the same chemicals targeted by antidepressants, generated naturally.</p>
<p>The <em>Sovereign Mind Journal</em> is structured around this principle. Every prompt pushes you past surface-level answers into the kind of specific reflection that actually changes your neurochemistry.</p>
<p>More in a few days.</p>
<p>Intentionally,<br><strong>Dominion Healing Press</strong></p>
"""),
    },
    "social_proof": {
        "subject": "\"I stopped needing my therapist to tell me what I already knew\"",
        "body": _wrap_html("""
<h2 style="color:#5b4a3f;">What Guided Journaling Unlocks</h2>
<p>Hi {{name}},</p>
<p>We hear from readers regularly. These two messages capture something important:</p>
<blockquote style="border-left:4px solid #c9a96e;padding:10px 15px;background:#faf6f0;margin:15px 0;">
"After 30 days with this journal, I stopped needing my therapist to tell me what I already knew. The prompts helped me see my own patterns clearly for the first time." -- <em>J. Carter</em>
</blockquote>
<blockquote style="border-left:4px solid #c9a96e;padding:10px 15px;background:#faf6f0;margin:15px 0;">
"I have tried five different journals. They all felt generic. This one asks questions that actually make me think. I look forward to it every morning." -- <em>S. Mitchell</em>
</blockquote>
<p>Self-awareness is not a personality trait. It is a skill -- and like any skill, it improves with the right practice and the right structure. That is exactly what guided journaling provides.</p>
<p>The question is not whether journaling works. The question is whether you are using a system designed to work for you.</p>
<p>Onward,<br><strong>Dominion Healing Press</strong></p>
"""),
    },
    "soft_sell": {
        "subject": "90 days to a mind you actually control",
        "body": _wrap_html(f"""
<h2 style="color:#5b4a3f;">Your 90-Day Sovereignty Blueprint</h2>
<p>Hi {{{{name}}}},</p>
<p>Over the past week, you have seen the science, the method, and the results. Here is what the <em>Sovereign Mind Journal</em> puts in your hands:</p>
<ul>
<li>90 daily guided prompts -- no blank-page anxiety, no generic questions</li>
<li>Weekly reflection checkpoints to track your growth</li>
<li>Gratitude architecture built on the specificity principle</li>
<li>Goal-setting frameworks that move beyond wishful thinking</li>
<li>Morning and evening rhythm suggestions for lasting habit formation</li>
</ul>
<p>This is not a diary. It is a cognitive operating system for people who refuse to leave their potential on the table.</p>
<p style="text-align:center;margin:25px 0;">
<a href="{AMAZON_LINKS['sovereign_mind']}" style="background:#c9a96e;color:#fff;padding:14px 28px;text-decoration:none;border-radius:6px;font-weight:bold;">Get Your Copy on Amazon</a>
</p>
<p>Ninety days from now, you will either be the same person or someone who took the time to build a sovereign mind. The journal just makes the process clear.</p>
<p>With conviction,<br><strong>Dominion Healing Press</strong></p>
"""),
    },
    "last_chance": {
        "subject": "Mind, money, and meaning -- the complete system",
        "body": _wrap_html(f"""
<h2 style="color:#5b4a3f;">Before I Go, {{{{name}}}}</h2>
<p>This is my final email in this series, and I want to leave you with something bigger than a single book.</p>
<p>Over two weeks, we have explored how structured reflection reshapes your thinking. But mindset is only one pillar. Real sovereignty requires three:</p>
<ol>
<li><strong>Sovereign Mind Journal</strong> -- clarity and purpose through guided daily practice</li>
<li><strong>Golden Years Word Search</strong> -- cognitive sharpness through engaging mental exercise</li>
<li><strong>Debt Freedom Planner</strong> -- financial control through a proven payoff system</li>
</ol>
<p>Readers who combine all three consistently report that the effect is compounding. A clear mind makes better financial decisions. A sharp brain sustains long-term discipline. Financial freedom removes the stress that clouds everything else.</p>
<p style="text-align:center;margin:25px 0;">
<a href="{BUNDLE_LINK}" style="background:#c9a96e;color:#fff;padding:14px 28px;text-decoration:none;border-radius:6px;font-weight:bold;">See All 3 Books on Amazon</a>
</p>
<p>Whatever path you choose, thank you for these two weeks. Your willingness to invest in yourself is rare and valuable.</p>
<p>With respect,<br><strong>Dominion Healing Press</strong></p>
"""),
    },
}

# ===== DEBT FREEDOM PLANNER =====

EMAILS_DEBT_FREEDOM = {
    "welcome": {
        "subject": "The number most people are afraid to calculate",
        "body": _wrap_html("""
<h2 style="color:#5b4a3f;">Welcome, {{name}}!</h2>
<p>Thank you for signing up. You just did something that 78% of Americans avoid: you acknowledged that debt is worth confronting head-on.</p>
<p>Here is the truth nobody tells you: <strong>debt is not a character flaw. It is a math problem.</strong> And math problems have solutions.</p>
<p>Before you do anything else, try this one exercise:</p>
<p style="background:#faf6f0;padding:15px;border-left:4px solid #c9a96e;">
<strong>The Total Truth Number:</strong> Open every account -- credit cards, student loans, car note, medical bills -- and add up every balance. Write that single number down. This is not about shame. This is your starting line. Every finish line needs one.</p>
<p>The <em>Debt Freedom Planner</em> is built around this principle: clarity first, strategy second, momentum always. It walks you through choosing the right payoff method, building a realistic timeline, and tracking every dollar of progress.</p>
<p>In two days, I will break down the two most effective debt payoff strategies -- and help you pick the right one for your situation.</p>
<p>To your freedom,<br><strong>Dominion Healing Press</strong></p>
"""),
    },
    "value": {
        "subject": "Snowball vs. avalanche -- which one wins?",
        "body": _wrap_html("""
<h2 style="color:#5b4a3f;">The Two Strategies That Actually Work</h2>
<p>Hi {{name}},</p>
<p>There are dozens of debt strategies out there, but only two have survived serious academic scrutiny:</p>
<p><strong>The Debt Snowball (Dave Ramsey's method):</strong><br>
Pay minimums on everything. Throw extra money at your <em>smallest</em> balance first. When it is gone, roll that payment into the next smallest. The wins come fast, and the psychological momentum is real. A Northwestern University study found snowball users are 14% more likely to eliminate all debt.</p>
<p><strong>The Debt Avalanche (the math-optimal method):</strong><br>
Pay minimums on everything. Throw extra money at the <em>highest interest rate</em> first. You save more money over time, but the first payoff takes longer. This method suits people who are motivated by efficiency over emotion.</p>
<p><strong>Which one wins?</strong> The one you actually stick with. If you need early victories to stay motivated, choose the snowball. If watching interest charges drop gives you energy, choose the avalanche.</p>
<p>The <em>Debt Freedom Planner</em> includes worksheets for both methods so you can map out your exact timeline either way.</p>
<p>More coming soon.</p>
<p>Strategically,<br><strong>Dominion Healing Press</strong></p>
"""),
    },
    "social_proof": {
        "subject": "\"We paid off $23,000 in 11 months using this planner\"",
        "body": _wrap_html("""
<h2 style="color:#5b4a3f;">From Overwhelmed to Debt-Free</h2>
<p>Hi {{name}},</p>
<p>Numbers on a page are powerful. But real stories are what make people take action:</p>
<blockquote style="border-left:4px solid #c9a96e;padding:10px 15px;background:#faf6f0;margin:15px 0;">
"My wife and I sat down with this planner on a Sunday afternoon. Seeing everything mapped out -- balances, interest rates, the payoff timeline -- changed the conversation. We stopped fighting about money and started working as a team. Eleven months later, $23,000 gone." -- <em>D. and K. Williams</em>
</blockquote>
<blockquote style="border-left:4px solid #c9a96e;padding:10px 15px;background:#faf6f0;margin:15px 0;">
"I tried apps, spreadsheets, everything. Something about writing it down by hand and physically checking off each payment made it stick. I am four months in and already eliminated two credit cards." -- <em>T. Nguyen</em>
</blockquote>
<p>The common thread is not willpower. It is structure. When you can see the path laid out in front of you, the daily discipline gets easier because you know exactly where each dollar is going and exactly when freedom arrives.</p>
<p>Warmly,<br><strong>Dominion Healing Press</strong></p>
"""),
    },
    "soft_sell": {
        "subject": "Your debt-free date is closer than you think",
        "body": _wrap_html(f"""
<h2 style="color:#5b4a3f;">See Your Payoff Date in Black and White</h2>
<p>Hi {{{{name}}}},</p>
<p>You have learned the two strategies. You have seen what structured planning does for real people. Now here is what the <em>Debt Freedom Planner</em> puts in your hands:</p>
<ul>
<li>Complete debt inventory worksheets -- every balance, rate, and minimum in one place</li>
<li>Snowball and avalanche planning templates with month-by-month timelines</li>
<li>Budget frameworks that find extra payoff money you did not know you had</li>
<li>Progress tracking pages with visual milestones</li>
<li>Emergency fund planning so you never go backward</li>
</ul>
<p>This planner does not just tell you to pay off debt. It shows you exactly how, in what order, and by what date.</p>
<p style="text-align:center;margin:25px 0;">
<a href="{AMAZON_LINKS['debt_freedom']}" style="background:#c9a96e;color:#fff;padding:14px 28px;text-decoration:none;border-radius:6px;font-weight:bold;">Get Your Copy on Amazon</a>
</p>
<p>Your debt-free date exists. This planner helps you find it and work toward it every single day.</p>
<p>To your freedom,<br><strong>Dominion Healing Press</strong></p>
"""),
    },
    "last_chance": {
        "subject": "Sharp mind, clear purpose, zero debt -- the full picture",
        "body": _wrap_html(f"""
<h2 style="color:#5b4a3f;">The Final Piece, {{{{name}}}}</h2>
<p>This is my last email in this series, and I want to zoom out for a moment.</p>
<p>Financial freedom is not just about spreadsheets and payment schedules. It is about what happens when money stress stops consuming your mental energy. That is when real growth begins.</p>
<p>We built three books for exactly this reason:</p>
<ol>
<li><strong>Debt Freedom Planner</strong> -- eliminate financial stress with a clear, structured payoff system</li>
<li><strong>Sovereign Mind Journal</strong> -- build the mindset discipline that sustains long-term change</li>
<li><strong>Golden Years Word Search</strong> -- keep your brain sharp and engaged through daily cognitive exercise</li>
</ol>
<p>Money, mind, and mental fitness. When all three are working together, the compounding effect is remarkable. Readers who use the full set consistently report feeling more in control of their lives than they have in years.</p>
<p style="text-align:center;margin:25px 0;">
<a href="{BUNDLE_LINK}" style="background:#c9a96e;color:#fff;padding:14px 28px;text-decoration:none;border-radius:6px;font-weight:bold;">See All 3 Books on Amazon</a>
</p>
<p>Whatever you decide, thank you for these two weeks. Taking control of your finances takes courage, and you have already shown you have it.</p>
<p>With respect,<br><strong>Dominion Healing Press</strong></p>
"""),
    },
}

# ===== DIVINE SOVEREIGNTY =====

EMAILS_DIVINE_SOVEREIGNTY = {
    'welcome': {
        'subject': 'Your sovereignty starts here, {{name}}',
        'body': _wrap_html(chr(10).join([
            '<h2 style="color:#5b4a3f;">Welcome, {{name}}.</h2>',
            '<p>You just took a step most people never take: you chose to question the systems that were never designed for your liberation.</p>',
            '<p>Divine Sovereignty is not a self-help book. It is <strong>spiritual architecture</strong> -- a framework for reclaiming authority over your mind, your finances, your faith, and your future.</p>',
            '<p style="background:#faf6f0;padding:15px;border-left:4px solid #d4af37;">',
            '<strong>Sovereignty is not rebellion. It is alignment with divine authority.</strong> It is the ability to live, think, decide, and build according to the truth placed inside you.</p>',
            '<p>Over the next two weeks, I will share principles from the book that have transformed lives. Real principles. No hype.</p>',
            '<p>Stay sovereign,<br><strong>Dewayne Singleton</strong><br>Dominion Healing</p>',
        ])),
    },
    'value': {
        'subject': 'The Five Pillars most people never learn',
        'body': _wrap_html(chr(10).join([
            '<h2 style="color:#5b4a3f;">The Five Pillars of Mental Sovereignty</h2>',
            '<p>Hi {{name}},</p>',
            '<p>Most people live their entire lives under mental architecture they did not build and never agreed to.</p>',
            '<ol>',
            '<li><strong>Identify the Unquestioned Beliefs</strong> -- drag every assumption into the light</li>',
            '<li><strong>Trace the Source</strong> -- who installed this belief and why?</li>',
            '<li><strong>Test Against Truth</strong> -- does it hold up under honest scrutiny?</li>',
            '<li><strong>Replace with Sovereignty</strong> -- install your own operating system</li>',
            '<li><strong>Guard the Gates</strong> -- protect your mind from re-infection</li>',
            '</ol>',
            '<p>This is not theory. This is a daily practice that changes how you see everything.</p>',
            '<p>In truth,<br><strong>Dewayne Singleton</strong></p>',
        ])),
    },
    'social_proof': {
        'subject': 'What readers say about Divine Sovereignty',
        'body': _wrap_html(chr(10).join([
            '<h2 style="color:#5b4a3f;">This Book Changes People</h2>',
            '<p>Hi {{name}},</p>',
            '<blockquote style="border-left:4px solid #d4af37;padding:10px 15px;background:#faf6f0;margin:15px 0;">"This book does not just inspire -- it rebuilds. A blueprint for those ready to break free."</blockquote>',
            '<blockquote style="border-left:4px solid #d4af37;padding:10px 15px;background:#faf6f0;margin:15px 0;">"Rarely does a book challenge you spiritually, psychologically, and practically all at once."</blockquote>',
            '<blockquote style="border-left:4px solid #d4af37;padding:10px 15px;background:#faf6f0;margin:15px 0;">"If you are tired of surface-level spirituality and want real transformation, this is your manual."</blockquote>',
            '<p>Warmly,<br><strong>Dewayne Singleton</strong></p>',
        ])),
    },
    'soft_sell': {
        'subject': 'Freedom, healing, and wealth -- all in one book',
        'body': _wrap_html(chr(10).join([
            '<h2 style="color:#5b4a3f;">Ready to Reclaim Your Sovereignty?</h2>',
            '<p>Hi {{name}},</p>',
            '<p>Divine Sovereignty covers the full transformation:</p>',
            '<ul>',
            '<li><strong>Part One: The Foundation</strong> -- Awakening, breaking invisible chains, divine law</li>',
            '<li><strong>Part Two: The Transformation</strong> -- Destroying bondage, creator mindset, wealth as divine right</li>',
            '<li><strong>Part Three: The Ascension</strong> -- Real faith, purpose, and the life beyond limitation</li>',
            '</ul>',
            '<p style="text-align:center;margin:25px 0;">',
            '<a href="https://buy.stripe.com/9B6cN5ar19NJfbr4k78Zq0b" style="background:linear-gradient(135deg,#d4af37,#a07830);color:#000;padding:14px 28px;text-decoration:none;border-radius:6px;font-weight:bold;">Get Divine Sovereignty -- $19</a></p>',
            '<p>In service,<br><strong>Dewayne Singleton</strong></p>',
        ])),
    },
    'last_chance': {
        'subject': 'Last call: the path is clear, {{name}}',
        'body': _wrap_html(chr(10).join([
            '<h2 style="color:#5b4a3f;">The Choice Is Yours</h2>',
            '<p>Hi {{name}},</p>',
            '<p>Two weeks ago something brought you here. A feeling. A knowing that you were made for more.</p>',
            '<p style="background:#faf6f0;padding:15px;border-left:4px solid #d4af37;">',
            '<strong>"Sovereignty is internal freedom that produces external impact."</strong><br>-- Divine Sovereignty, Chapter 1</p>',
            '<p style="text-align:center;margin:25px 0;">',
            '<a href="https://buy.stripe.com/9B6cN5ar19NJfbr4k78Zq0b" style="background:linear-gradient(135deg,#d4af37,#a07830);color:#000;padding:14px 28px;text-decoration:none;border-radius:6px;font-weight:bold;">Get Divine Sovereignty -- $19</a></p>',
            '<p>The pillars stand. The path is clear. The choice is yours.</p>',
            '<p>With honor,<br><strong>Dewayne Singleton</strong><br>Founder, Dominion Healing</p>',
        ])),
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
                return "clear"
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
    email = (payload.email or "").strip().lower()
    if not email or "@" not in email:
        raise HTTPException(status_code=400, detail="invalid_email")

    suppression = _suppression_state(email)
    if suppression == "error":
        raise HTTPException(status_code=503, detail="suppression_check_failed")
    if suppression == "suppressed":
        return {"status": "suppressed", "message": "Email is unsubscribed"}

    name = (payload.name or "Friend").strip() or "Friend"
    source_value = (payload.source or "").strip()
    book = _resolve_book(source_value)
    unsubscribe_url = (payload.unsubscribe_url or "").strip() or _unsubscribe_url(email)

    try:
        with LEADS_LOCK:
            data = _load_leads()
            if not isinstance(data, dict) or not isinstance(data.get("leads"), list):
                raise ValueError("invalid lead store schema")
            data.setdefault("stats", {}).setdefault("total_captured", 0)
            data["stats"].setdefault("emails_sent", 0)

            for lead in data["leads"]:
                if str(lead.get("email", "")).lower() == email:
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

    log.info("Captured lead: %s for book=%s source=%s", email, book, source_value)
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
        if len(lead.get("emails_sent", [])) >= 5:
            fully_dripped += 1

    return {
        "total_leads": total,
        "leads_by_book": by_book,
        "total_emails_sent": data["stats"].get("emails_sent", 0),
        "fully_completed_sequences": fully_dripped,
        "sendgrid_configured": bool(SENDGRID_API_KEY),
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



def _run_drip_cycle() -> int:
    """Check all leads; HOLD and suppression failures advance no send state."""
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
                email = str(lead.get("email", "")).strip().lower()
                captured_raw = str(lead.get("captured_at", "")).strip()
                if not email or "@" not in email or not captured_raw:
                    log.warning("Ghost/invalid drip lead skipped; report-only, no deletion")
                    continue

                suppression = _suppression_state(email)
                if suppression == "error":
                    log.error("Suppression check failed; send blocked for %s", email)
                    continue
                if suppression == "suppressed":
                    continue

                try:
                    captured = datetime.fromisoformat(captured_raw)
                except (TypeError, ValueError):
                    log.warning("Invalid captured_at skipped for %s; report-only, no deletion", email)
                    continue

                days_since = (now - captured).days
                already_sent = set(lead.get("emails_sent", []))
                resolved_from_source = _resolve_book(str(lead.get("source", "")))
                book = "free_audit_hold" if resolved_from_source == "free_audit_hold" else lead.get("book", DEFAULT_BOOK)
                emails = BOOK_EMAILS.get(book, BOOK_EMAILS[DEFAULT_BOOK])

                for step in DRIP_SCHEDULE:
                    if step["key"] in already_sent:
                        continue
                    if days_since < step["day"]:
                        continue

                    email_content = emails.get(step["key"])
                    if not email_content:
                        continue

                    if DRIP_SEND_MODE != "live":
                        log.info(
                            "DRIP HOLD: due email blocked for %s book=%s step=%s",
                            email, book, step["key"],
                        )
                        break

                    unsubscribe_url = (lead.get("unsubscribe_url") or "").strip() or _unsubscribe_url(email)
                    if not unsubscribe_url:
                        log.error("LIVE send blocked: unsubscribe URL unavailable")
                        break

                    subject = email_content["subject"]
                    body = email_content["body"].replace("{{name}}", lead.get("name") or "Friend")
                    safe_url = html_lib.escape(unsubscribe_url, quote=True)
                    body += (
                        '<hr style="margin-top:28px;border:0;border-top:1px solid #ddd;">'
                        '<p style="font-size:12px;color:#777">'
                        f'<a href="{safe_url}">Unsubscribe</a>'
                        '</p>'
                    )

                    success = _send_email(email, lead.get("name") or "Friend", subject, body)
                    if success:
                        lead.setdefault("emails_sent", []).append(step["key"])
                        lead["last_sent_at"] = now.isoformat()
                        data["stats"]["emails_sent"] += 1
                        sent_count += 1
                        changed = True
                    break

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
            log.error("Drip cycle error: %s", exc)
        time.sleep(DRIP_CHECK_INTERVAL)


@app.on_event("startup")
def start_drip_scheduler():
    # Ensure leads file exists
    if not LEADS_FILE.exists():
        _save_leads({"leads": [], "stats": {"total_captured": 0, "emails_sent": 0}})
    thread = threading.Thread(target=_drip_loop, daemon=True)
    thread.start()
    log.info("Email drip engine online | from=%s | sendgrid=%s", FROM_EMAIL, bool(SENDGRID_API_KEY))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    uvicorn.run(
        "email_drip:app",
        host="0.0.0.0",
        port=int(os.getenv("DRIP_PORT", "8099")),
        reload=False,
        log_level="info",
    )
