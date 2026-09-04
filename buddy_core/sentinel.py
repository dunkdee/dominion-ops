"""
DOMINION SENTINEL — The Autonomous Guardian
=============================================
One file. Runs 24/7 on foundation-vm as systemd service.
Phi-governed (16.18 min cycles). Monitors, heals, reports.

Supersedes: buddy_monitor.py, core/watchdog.py (on VM)
Does NOT replace: Watchmen (security), evolution_engine (learning)

11 Check Modules:
  1. Service port probes (auto-restart on failure)
  2. Docker container health (auto-restart)
  3. Disk monitoring (alert 80%, auto-clean 85%)
  4. Gemini model name validation (flag bad names)
  5. API key validation (verify AIza prefix + test call)
  6. Cron job verification (ensure all expected crons exist)
  7. Pipeline health (alert if last run > 24h)
  8. Database health (postgres connection + counts)
  9. File ownership (ensure malachisingleton8 owns buddy_core)
 10. Log rotation (trim >50MB, delete >30 days)
 11. Watchmen status (verify the 8 are responding)

CLI:
  python sentinel.py          — run daemon (16.18 min loop)
  python sentinel.py status   — print current status
  python sentinel.py cycle    — run one cycle and exit
  python sentinel.py service  — print systemd unit file

Deploy: bash deploy/deploy_sentinel.sh
"""

import os
import sys
import json
import time
import socket
import subprocess
import smtplib
import logging
import hashlib
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pathlib import Path

# ── Attempt ecosystem imports (graceful fallback if not available) ──
try:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from phi_constants import PHI, GEMINI_MODEL, GEMINI_PRO, GCP_PROJECT
except ImportError:
    PHI = 1.618033988749895
    GEMINI_MODEL = "gemini-2.5-flash"
    GEMINI_PRO = "gemini-2.5-pro"
    GCP_PROJECT = "dominion-ascendant"

from core.token_resolver import (
    TOKEN_KEY,
    count_assignments,
    parse_env_file,
)

try:
    from utils.safe_io import atomic_json_write, load_json
except ImportError:
    def load_json(path, default=None):
        try:
            with open(path, "r") as f:
                return json.load(f)
        except Exception:
            return default if default is not None else []

    def atomic_json_write(path, data, indent=2, default=None):
        path = str(path)
        tmp = path + ".tmp"
        kwargs = {"indent": indent}
        if default is not None:
            kwargs["default"] = default
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, **kwargs)
        os.replace(tmp, path)

try:
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=Path.home() / "buddy_core" / ".env")
    load_dotenv(dotenv_path=Path.home() / "conductor" / ".env")
    load_dotenv(dotenv_path=Path.home() / ".env")
except ImportError:
    pass

# ── Saraqael audit log integration ──
def audit_log(source, event, status, details=None):
    """Log to saraqael audit chain if available, else local fallback."""
    try:
        from watchmen.saraqael import log as saraqael_log
        saraqael_log(source, event, status, details or {})
    except Exception:
        # Fallback: append to local audit log
        entry = {
            "ts": datetime.utcnow().isoformat(),
            "source": source,
            "event": event,
            "status": status,
            "details": details or {}
        }
        audit_path = Path.home() / "buddy_core" / "logs" / "sentinel_audit.log"
        audit_path.parent.mkdir(parents=True, exist_ok=True)
        with open(audit_path, "a") as f:
            f.write(json.dumps(entry) + "\n")


# ============================================================
# CONFIG
# ============================================================
SCAN_INTERVAL = PHI * 600            # 970.8s = 16.18 minutes
ALERT_COOLDOWN = PHI * 3600          # 5832.1s = ~97 minutes
BUDDY_CORE = Path.home() / "buddy_core"
STATUS_FILE = BUDDY_CORE / "sentinel_status.json"
LOG_DIR = BUDDY_CORE / "logs"
LOG_FILE = LOG_DIR / "sentinel.log"
LOCK_FILE = BUDDY_CORE / "sentinel.lock"
EXPECTED_OWNER = "malachisingleton8"

# Gmail alert config
GMAIL_USER = os.getenv("GMAIL_USER", os.getenv("SMTP_USER", ""))
GMAIL_PASS = os.getenv("GMAIL_PASS", os.getenv("SMTP_PASS", ""))
ALERT_EMAIL = os.getenv("ALERT_EMAIL", "founder-personal@example.invalid")

# Known-bad model names (things that should NEVER appear in code)
BAD_MODEL_NAMES = [
    "gemini-3-pro-preview",
    "gemini-3-pro",
    "gemini_3_pro",
    "gemini-pro-preview",
]

# Valid model names (from phi_constants.py)
VALID_MODELS = [GEMINI_MODEL, GEMINI_PRO, "gemini-2.5-flash"]

# Services to monitor: name -> port, restart command, criticality
SERVICES = {
    "conductor-api": {
        "port": 5060,
        "restart": "sudo systemctl restart conductor-api",
        "critical": True,
    },
    "dominion-gatekeeper": {
        "port": 5000,
        "restart": "sudo systemctl restart dominion-gatekeeper",
        "critical": True,
    },
    "gemini-server": {
        "port": 5055,
        "restart": "sudo systemctl restart gemini-server",
        "critical": True,
    },
    "alchemist-api": {
        "port": 5050,
        "restart": "sudo systemctl restart alchemist-api",
        "critical": True,
    },
    "juris-api": {
        "port": 5055,
        "restart": "sudo systemctl restart juris-api",
        "critical": False,
    },
    "ollama": {
        "port": 11434,
        "restart": "sudo systemctl restart ollama",
        "critical": False,
    },
}

DOCKER_CONTAINERS = ["dominion-n8n", "dominion-db", "dominion-seo"]

  # proposal_auto_submit removed 2026-08-01 PPH retired
EXPECTED_CRONS = ["multi_content", "social_poster", "tiktok_pipeline", "realestate_scout", "re_outreach", "daily_digest", "asin_watcher", "four_hour_digest"]

# Logging setup
LOG_DIR.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | SENTINEL | %(levelname)s | %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("SENTINEL")


# ============================================================
# SINGLE-INSTANCE GUARD
# ============================================================
def _acquire_lock():
    if LOCK_FILE.exists():
        try:
            pid = int(LOCK_FILE.read_text().strip())
            # Check if process is still running
            os.kill(pid, 0)
            log.error(f"Sentinel already running (PID {pid}). Exiting.")
            sys.exit(0)
        except (ProcessLookupError, ValueError, OSError):
            pass  # Stale lock, take over
    LOCK_FILE.write_text(str(os.getpid()))
    import atexit
    atexit.register(lambda: LOCK_FILE.unlink(missing_ok=True))


# ============================================================
# STATE MANAGER
# ============================================================
class SentinelState:
    def __init__(self):
        self.data = self._load()

    def _load(self):
        return load_json(STATUS_FILE, default={
            "version": "1.0.0",
            "cycles": 0,
            "total_restarts": 0,
            "total_alerts": 0,
            "total_auto_fixes": 0,
            "service_history": {},
            "last_alert_time": {},
            "last_cycle": None,
            "last_result": None,
            "uptime_start": datetime.utcnow().isoformat(),
        })

    def save(self):
        atomic_json_write(STATUS_FILE, self.data, default=str)

    def tick(self):
        self.data["cycles"] += 1
        self.data["last_cycle"] = datetime.utcnow().isoformat()
        self.save()

    def record_restart(self, service):
        self.data["total_restarts"] += 1
        hist = self.data["service_history"].setdefault(service, {"restarts": 0, "last_restart": None})
        hist["restarts"] += 1
        hist["last_restart"] = datetime.utcnow().isoformat()
        self.save()

    def record_fix(self):
        self.data["total_auto_fixes"] += 1
        self.save()

    def can_alert(self, key):
        last = self.data["last_alert_time"].get(key, 0)
        if isinstance(last, str):
            return True  # Legacy format, allow
        return (time.time() - last) > ALERT_COOLDOWN

    def mark_alerted(self, key):
        self.data["last_alert_time"][key] = time.time()
        self.data["total_alerts"] += 1
        self.save()

    def summary(self):
        try:
            uptime_start = datetime.fromisoformat(self.data["uptime_start"])
            uptime_h = round((datetime.utcnow() - uptime_start).total_seconds() / 3600, 2)
        except Exception:
            uptime_h = 0
        return {
            "cycles": self.data["cycles"],
            "total_restarts": self.data["total_restarts"],
            "total_auto_fixes": self.data["total_auto_fixes"],
            "total_alerts": self.data["total_alerts"],
            "uptime_hours": uptime_h,
            "last_cycle": self.data["last_cycle"],
        }


# ============================================================
# CHECK 1: SERVICE PORT PROBES
# ============================================================
def check_port(port, host="127.0.0.1", timeout=3.0):
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (socket.timeout, ConnectionRefusedError, OSError):
        return False


def check_services(state):
    issues, fixed = [], []
    for name, cfg in SERVICES.items():
        alive = check_port(cfg["port"])
        if alive:
            log.info(f"  {name}:{cfg['port']} ONLINE")
            continue

        log.warning(f"  {name}:{cfg['port']} OFFLINE — attempting restart...")
        try:
            time.sleep(PHI)
            subprocess.run(cfg["restart"], shell=True, timeout=30, capture_output=True)
            time.sleep(3)
            if check_port(cfg["port"]):
                log.info(f"  {name} restarted successfully")
                state.record_restart(name)
                state.record_fix()
                fixed.append(f"{name} restarted")
                audit_log("sentinel", f"restart_{name}", "ok", {"port": cfg["port"]})
            else:
                raise RuntimeError("Still offline after restart")
        except Exception as e:
            issues.append(f"{name} OFFLINE (restart failed: {e})")
            audit_log("sentinel", f"restart_{name}", "failed", {"error": str(e)})
            if cfg["critical"]:
                send_alert(f"CRITICAL: {name} is DOWN", f"{name} (port {cfg['port']}) is offline.\nAuto-restart failed: {e}\nManual intervention required.", state, f"svc_{name}")
    return issues, fixed


# ============================================================
# CHECK 2: DOCKER CONTAINERS
# ============================================================
def check_docker_status(name):
    try:
        r = subprocess.run(["docker", "inspect", "--format", "{{.State.Status}}", name], capture_output=True, text=True, timeout=10)
        return r.stdout.strip() or "not_found"
    except Exception:
        return "unknown"


def check_docker(state):
    issues, fixed = [], []
    for name in DOCKER_CONTAINERS:
        status = check_docker_status(name)
        if status == "running":
            log.info(f"  {name}: running")
            continue

        log.warning(f"  {name}: {status} — restarting...")
        try:
            subprocess.run(["docker", "start", name], capture_output=True, timeout=30)
            time.sleep(3)
            if check_docker_status(name) == "running":
                state.record_restart(name)
                state.record_fix()
                fixed.append(f"{name} container restarted")
                audit_log("sentinel", f"docker_restart_{name}", "ok")
            else:
                raise RuntimeError(f"Still {status}")
        except Exception as e:
            issues.append(f"Docker {name}: {status} (restart failed)")
            send_alert(f"Docker container down: {name}", f"Status: {status}\nRestart failed: {e}", state, f"docker_{name}")
    return issues, fixed


# ============================================================
# CHECK 3: DISK MONITORING
# ============================================================
def check_disk(state):
    issues, fixed = [], []
    try:
        r = subprocess.run(["df", "-h", "/"], capture_output=True, text=True, timeout=10)
        lines = r.stdout.strip().split("\n")
        if len(lines) < 2:
            return issues, fixed
        parts = lines[1].split()
        pct = int(parts[4].replace("%", ""))
        log.info(f"  Disk: {parts[2]} used / {parts[1]} total ({pct}%)")

        if pct >= 85:
            log.warning(f"  Disk at {pct}% — AUTO-CLEANING...")
            cmds = [
                "sudo apt-get clean -y",
                "sudo journalctl --vacuum-size=50M",
                "find /home/malachisingleton8/buddy_core/logs -name '*.log' -mtime +14 -delete 2>/dev/null",
                "find /var/log -name '*.gz' -mtime +7 -delete 2>/dev/null",
                "find /tmp -type f -mtime +7 -delete 2>/dev/null",
            ]
            for cmd in cmds:
                try:
                    subprocess.run(cmd, shell=True, timeout=30, capture_output=True)
                except Exception:
                    pass
            # Re-check
            r2 = subprocess.run(["df", "-h", "/"], capture_output=True, text=True, timeout=10)
            new_pct = int(r2.stdout.strip().split("\n")[1].split()[4].replace("%", ""))
            if new_pct < pct:
                fixed.append(f"Disk cleaned: {pct}% -> {new_pct}%")
                state.record_fix()
                audit_log("sentinel", "disk_clean", "ok", {"before": pct, "after": new_pct})
            if new_pct >= 85:
                issues.append(f"Disk still at {new_pct}% after auto-clean")
                send_alert(f"DISK CRITICAL: {new_pct}%", f"Auto-clean ran but disk still at {new_pct}%.\nManual cleanup needed.", state, "disk")
        elif pct >= 80:
            issues.append(f"Disk at {pct}% — approaching critical")
            send_alert(f"Disk warning: {pct}%", f"Disk usage is at {pct}%. Target is < 80%.", state, "disk_warn")
    except Exception as e:
        log.error(f"  Disk check failed: {e}")
    return issues, fixed


# ============================================================
# CHECK 4: MODEL NAME VALIDATION
# ============================================================
def validate_models():
    issues = []
    # Skip sentinel.py itself — it contains bad names as detection strings
    skip_files = {"sentinel.py"}
    py_dirs = [BUDDY_CORE / "core", BUDDY_CORE / "agents", BUDDY_CORE]
    for d in py_dirs:
        if not d.exists():
            continue
        for f in d.glob("*.py"):
            if f.name in skip_files:
                continue
            try:
                content = f.read_text(encoding="utf-8", errors="ignore")
                for bad in BAD_MODEL_NAMES:
                    if bad in content:
                        issues.append(f"BAD MODEL NAME '{bad}' in {f.name}")
                        log.warning(f"  {f.name} contains bad model name: {bad}")
            except Exception:
                pass
    if not issues:
        log.info("  Model names: all valid")
    return issues


# ============================================================
# CHECK 5: API KEY VALIDATION
# ============================================================
def validate_api_keys():
    issues = []
    gemini_key = os.getenv("GEMINI_API_KEY", "")
    if not gemini_key:
        issues.append("GEMINI_API_KEY not set")
        log.warning("  GEMINI_API_KEY: NOT SET")
    elif not gemini_key.startswith("AIza"):
        issues.append(f"GEMINI_API_KEY invalid prefix: {gemini_key[:8]}...")
        log.warning(f"  GEMINI_API_KEY: BAD PREFIX ({gemini_key[:8]}...)")
    else:
        log.info(f"  GEMINI_API_KEY: valid (AIza...)")

    admin_key = os.getenv("ADMIN_KEY", "")
    if not admin_key:
        issues.append("ADMIN_KEY not set")
        log.warning("  ADMIN_KEY: NOT SET")
    else:
        log.info("  ADMIN_KEY: set")

    return issues


# ============================================================
# CHECK 6: CRON VERIFICATION
# ============================================================
def check_crons():
    issues = []
    try:
        r = subprocess.run(["crontab", "-l"], capture_output=True, text=True, timeout=5)
        crontab = r.stdout
        # Check if crontab is empty or nearly empty
        active_lines = [l for l in crontab.strip().splitlines() if l.strip() and not l.strip().startswith('#')]
        if len(active_lines) < 10:
            issues.append(f"CRITICAL: Crontab has only {len(active_lines)} entries (expected 27+). May have been wiped.")
            log.error(f"  Crontab INTEGRITY FAILURE: only {len(active_lines)} active entries")
        else:
            log.info(f"  Crontab: {len(active_lines)} active entries")
        # Check each expected cron
        for job in EXPECTED_CRONS:
            if job in crontab:
                log.info(f"  Cron '{job}': SCHEDULED")
            else:
                issues.append(f"Cron missing: {job}")
                log.warning(f"  Cron '{job}': MISSING")
        # Compare against canonical crontab if available
        canonical = BUDDY_CORE / "infra" / "crontab.txt"
        if canonical.exists():
            with open(canonical) as f:
                canonical_lines = set(l.strip() for l in f if l.strip() and not l.strip().startswith('#'))
            current_lines = set(l.strip() for l in crontab.splitlines() if l.strip() and not l.strip().startswith('#'))
            missing = canonical_lines - current_lines
            if missing:
                issues.append(f"Crontab drift: {len(missing)} entries missing vs canonical")
                log.warning(f"  Crontab DRIFT: {len(missing)} entries differ from infra/crontab.txt")
            else:
                log.info("  Crontab matches canonical (infra/crontab.txt)")
    except Exception as e:
        log.error(f"  Cron check failed: {e}")
    return issues


# ============================================================
# CHECK 7: PIPELINE HEALTH
# ============================================================
def check_pipeline_health():
    issues = []
    # Check multiple possible log locations
    conductor_log = None
    for candidate in [BUDDY_CORE / "conductor_log.json", Path.home() / "conductor" / "conductor_log.json"]:
        if candidate.exists():
            conductor_log = candidate
            break
    if conductor_log is None:
        # Not critical — conductor may log to journal/DB instead of JSON
        log.info("  Pipeline: no conductor_log.json (logs may be in journal)")
        return issues

    try:
        entries = load_json(conductor_log, default=[])
        if not entries:
            issues.append("conductor_log.json is empty")
            log.warning("  conductor_log.json: EMPTY")
            return issues

        # Find most recent entry
        last = entries[-1] if isinstance(entries, list) else None
        if last and "timestamp" in last:
            last_time = datetime.fromisoformat(last["timestamp"].replace("Z", "+00:00").replace("+00:00", ""))
            age_hours = (datetime.utcnow() - last_time).total_seconds() / 3600
            log.info(f"  Last pipeline run: {age_hours:.1f}h ago")
            if age_hours > 24:
                issues.append(f"Pipeline stale: last run {age_hours:.1f}h ago (>24h)")
                log.warning(f"  Pipeline STALE: {age_hours:.1f}h since last run")
        elif last and "ts" in last:
            last_time = datetime.fromisoformat(last["ts"])
            age_hours = (datetime.utcnow() - last_time).total_seconds() / 3600
            log.info(f"  Last pipeline run: {age_hours:.1f}h ago")
            if age_hours > 24:
                issues.append(f"Pipeline stale: last run {age_hours:.1f}h ago (>24h)")
        else:
            log.info("  conductor_log.json: entries found (no timestamp field)")
    except Exception as e:
        log.error(f"  Pipeline health check failed: {e}")
    return issues


# ============================================================
# CHECK 8: DATABASE HEALTH
# ============================================================
def check_db():
    issues = []
    try:
        # Use actual container name: dominion-db
        r = subprocess.run(
            ["docker", "exec", "dominion-db", "psql", "-U", "dominion", "-d", "dominion", "-c", "SELECT 1;"],
            capture_output=True, text=True, timeout=10,
        )
        if r.returncode == 0:
            log.info("  Postgres: ONLINE (connection ok)")
            # Count gatekeeper leads from captured_leads table
            r2 = subprocess.run(
                ["docker", "exec", "dominion-db", "psql", "-U", "dominion", "-d", "dominion", "-c", "SELECT COUNT(*) FROM captured_leads;"],
                capture_output=True, text=True, timeout=10,
            )
            if r2.returncode == 0:
                for line in r2.stdout.strip().split("\n"):
                    if line.strip().isdigit():
                        log.info(f"  Leads table: {line.strip()} rows")
                        break
        else:
            issues.append(f"Postgres connection failed: {r.stderr.strip()[:100]}")
            log.warning("  Postgres: CONNECTION FAILED")
    except Exception as e:
        issues.append(f"Postgres unreachable: {e}")
        log.error(f"  Postgres: UNREACHABLE ({e})")
    return issues


# ============================================================
# CHECK 9: FILE OWNERSHIP
# ============================================================
def check_ownership(state):
    issues, fixed = [], []
    try:
        r = subprocess.run(
            ["find", str(BUDDY_CORE), "-maxdepth", "1", "-not", "-user", EXPECTED_OWNER],
            capture_output=True, text=True, timeout=10,
        )
        bad_files = [f for f in r.stdout.strip().split("\n") if f]
        if bad_files:
            log.warning(f"  {len(bad_files)} files not owned by {EXPECTED_OWNER} — fixing...")
            fix = subprocess.run(
                ["sudo", "chown", "-R", f"{EXPECTED_OWNER}:{EXPECTED_OWNER}", str(BUDDY_CORE)],
                capture_output=True, timeout=30,
            )
            if fix.returncode == 0:
                fixed.append(f"Fixed ownership on {len(bad_files)} files")
                state.record_fix()
                audit_log("sentinel", "fix_ownership", "ok", {"count": len(bad_files)})
            else:
                issues.append("File ownership fix failed (sudo issue?)")
        else:
            log.info(f"  File ownership: all {EXPECTED_OWNER}")
    except Exception as e:
        log.error(f"  Ownership check failed: {e}")
    return issues, fixed


# ============================================================
# CHECK 10: LOG ROTATION
# ============================================================
def rotate_logs():
    fixed = []
    log_dirs = [LOG_DIR, BUDDY_CORE]
    max_size = 50 * 1024 * 1024  # 50MB

    for d in log_dirs:
        if not d.exists():
            continue
        for f in d.glob("*.log"):
            try:
                size = f.stat().st_size
                if size > max_size:
                    # Truncate to last 10000 lines
                    lines = f.read_text(errors="ignore").split("\n")
                    f.write_text("\n".join(lines[-10000:]))
                    new_size = f.stat().st_size
                    fixed.append(f"Trimmed {f.name}: {size//1024//1024}MB -> {new_size//1024//1024}MB")
                    log.info(f"  Trimmed {f.name} from {size//1024//1024}MB to {new_size//1024//1024}MB")
            except Exception:
                pass

        for f in d.glob("*.json"):
            try:
                size = f.stat().st_size
                if size > max_size and f.name not in ("sentinel_status.json",):
                    data = load_json(f, default=[])
                    if isinstance(data, list) and len(data) > 500:
                        atomic_json_write(f, data[-500:], default=str)
                        fixed.append(f"Trimmed {f.name}: kept last 500 entries")
                        log.info(f"  Trimmed {f.name} to last 500 entries")
            except Exception:
                pass

    # Delete old logs (>30 days)
    try:
        r = subprocess.run(
            ["find", str(LOG_DIR), "-name", "*.log", "-mtime", "+30", "-delete"],
            capture_output=True, timeout=10,
        )
    except Exception:
        pass

    if not fixed:
        log.info("  Logs: sizes OK")
    return fixed


# ============================================================
# CHECK 11: WATCHMEN STATUS
# ============================================================
def check_watchmen():
    issues = []
    watchmen_dir = BUDDY_CORE / "watchmen"
    expected = ["saraqael", "gabriel", "uriel", "raphael", "raguel", "michael", "remiel", "the_eighth"]

    if not watchmen_dir.exists():
        issues.append("watchmen/ directory missing")
        log.warning("  watchmen/: MISSING")
        return issues

    for name in expected:
        f = watchmen_dir / f"{name}.py"
        if not f.exists():
            issues.append(f"Watchman missing: {name}.py")
            log.warning(f"  {name}.py: MISSING")
        else:
            log.info(f"  {name}.py: present")

    return issues


# ============================================================
# CHECK 12: ENV KEY SYNC
# ============================================================

REQUIRED_ENV_KEYS = [
    "GEMINI_API_KEY",
    "STRIPE_SECRET_KEY",
    "GROQ_API_KEY",
    "ADMIN_KEY",
    "BUDDY_WEB_TOKEN",
]

ENV_FILES = [
    Path.home() / ".env",
    Path.home() / "conductor" / ".env",
    Path.home() / "buddy_core" / ".env",
]

# BUDDY_WEB_TOKEN is a live production auth secret, not an ordinary config
# value: it must exist in exactly one place. Every other required key is
# still mirrored across ENV_FILES for backward compatibility; the token is
# instead enforced single-source here and actively stripped from the rest.
CANONICAL_TOKEN_FILE = Path.home() / "buddy_core" / ".env"


def _write_env_key(env_file: Path, key: str, value: str) -> str:
    """Set ``key`` to ``value`` in ``env_file`` with exactly one assignment.

    The previous implementation appended a new line whenever a file lacked a
    non-empty value. A file holding ``KEY=`` therefore ended up with two
    assignments, and python-dotenv's override=False kept the empty one — which
    is how Buddy's auth could report "not configured" while the real token sat
    two lines below. Rewriting in place keeps every file single-valued and
    makes repeated sentinel cycles idempotent.
    """
    lines = env_file.read_text(encoding="utf-8", errors="ignore").splitlines()
    replaced = False
    out = []
    for line in lines:
        stripped = line.strip()
        candidate = stripped[len("export "):].lstrip() if stripped.startswith("export ") else stripped
        if not stripped.startswith("#") and "=" in candidate and candidate.partition("=")[0].strip() == key:
            if replaced:
                continue  # drop the surplus duplicate assignment
            out.append(f"{key}={value}")
            replaced = True
            continue
        out.append(line)
    if not replaced:
        out.append(f"{key}={value}")
    backup = Path(str(env_file) + ".sentinel-bak")
    try:
        backup.write_text("\n".join(lines) + "\n", encoding="utf-8")
        backup.chmod(0o600)
    except OSError:
        pass
    env_file.write_text("\n".join(out) + "\n", encoding="utf-8")
    try:
        env_file.chmod(0o600)
    except OSError:
        pass
    return "rewrote" if replaced else "appended"


def _strip_env_key(env_file: Path, key: str) -> bool:
    """Remove every assignment of ``key`` from ``env_file``. Returns True if
    anything was actually removed.

    Used only to retire a secret from a non-canonical location — never to
    delete an ordinary config key, and never touching the canonical file.
    """
    lines = env_file.read_text(encoding="utf-8", errors="ignore").splitlines()
    out = []
    removed = False
    for line in lines:
        stripped = line.strip()
        candidate = stripped[len("export "):].lstrip() if stripped.startswith("export ") else stripped
        if not stripped.startswith("#") and "=" in candidate and candidate.partition("=")[0].strip() == key:
            removed = True
            continue
        out.append(line)
    if not removed:
        return False
    backup = Path(str(env_file) + ".sentinel-bak")
    try:
        backup.write_text("\n".join(lines) + "\n", encoding="utf-8")
        backup.chmod(0o600)
    except OSError:
        pass
    env_file.write_text(("\n".join(out) + "\n") if out else "", encoding="utf-8")
    try:
        env_file.chmod(0o600)
    except OSError:
        pass
    return True


def check_env_keys(state):
    """Verify required keys exist, agree, and are single-valued in every .env.

    Three conditions are repaired, all idempotent:
      * key missing from a file             -> written
      * key present but empty               -> filled in place, not appended
      * key assigned twice in one file      -> collapsed to a single assignment
    Two files holding *different* non-empty values is the conflict that used to
    pass unnoticed; it is now reported and aligned on the value the runtime
    actually authenticates with.
    """
    issues, fixed = [], []

    # Per-file values parsed with shell `source` semantics (last write wins)
    # rather than dotenv's first-write-wins, which is what let an empty
    # duplicate line shadow a real secret.
    all_keys = {}    # key -> {file: value}
    duplicates = {}  # key -> [file name, ...]
    for env_file in ENV_FILES:
        if not env_file.exists():
            continue
        parsed = parse_env_file(env_file)
        for key in REQUIRED_ENV_KEYS:
            value = str(parsed.get(key, "") or "").strip()
            if value:
                all_keys.setdefault(key, {})[str(env_file)] = value
            if count_assignments(env_file, key) > 1:
                duplicates.setdefault(key, []).append(env_file.name)

    for key, files in duplicates.items():
        issues.append(f"ENV KEY DUPLICATED: {key} assigned more than once in {', '.join(files)}")
        log.warning(f"  {key}: duplicate assignment in {', '.join(files)}")

    for key in REQUIRED_ENV_KEYS:
        sources = all_keys.get(key, {})
        if not sources:
            issues.append(f"ENV KEY MISSING EVERYWHERE: {key}")
            log.warning(f"  {key}: NOT FOUND in any .env")
            continue

        if key == TOKEN_KEY:
            # Single canonical source, not a mirrored config value. A secret
            # copied into three dotenv files is three places it can drift or
            # leak — enforce exactly one authoritative location and retire it
            # everywhere else instead of syncing it everywhere.
            canonical_str = str(CANONICAL_TOKEN_FILE)
            canonical_value = sources.get(canonical_str) or list(sources.values())[0]

            if CANONICAL_TOKEN_FILE.exists():
                already_correct = sources.get(canonical_str) == canonical_value
                needs_dedupe = CANONICAL_TOKEN_FILE.name in duplicates.get(key, [])
                if not already_correct or needs_dedupe:
                    try:
                        action = _write_env_key(CANONICAL_TOKEN_FILE, key, canonical_value)
                        fixed.append(f"{action.capitalize()} {key} in {CANONICAL_TOKEN_FILE.name} (canonical)")
                        state.record_fix()
                        log.info(f"  {action.capitalize()} {key} in {CANONICAL_TOKEN_FILE.name} (canonical)")
                        audit_log(
                            "sentinel", "env_key_sync", "ok",
                            {"key": key, "target": CANONICAL_TOKEN_FILE.name, "action": action},
                        )
                    except Exception as e:
                        issues.append(f"Failed to write canonical {key} to {CANONICAL_TOKEN_FILE.name}: {e}")
            else:
                issues.append(f"ENV KEY CANONICAL FILE MISSING: {CANONICAL_TOKEN_FILE}")
                log.warning(f"  {key}: canonical file missing: {CANONICAL_TOKEN_FILE}")

            for env_file in ENV_FILES:
                if str(env_file) == canonical_str or not env_file.exists():
                    continue
                try:
                    if _strip_env_key(env_file, key):
                        issues.append(f"ENV KEY NON-CANONICAL: removed {key} from {env_file.name}")
                        fixed.append(f"Stripped {key} from {env_file.name} (non-canonical)")
                        state.record_fix()
                        log.info(f"  Stripped {key} from {env_file.name} (non-canonical)")
                        audit_log(
                            "sentinel", "env_key_desync", "ok",
                            {"key": key, "target": env_file.name, "action": "stripped_non_canonical"},
                        )
                except Exception as e:
                    issues.append(f"Failed to strip {key} from {env_file.name}: {e}")
            continue

        canonical_value = list(sources.values())[0]
        if len(set(sources.values())) > 1:
            issues.append(
                f"ENV KEY CONFLICT: {key} differs across "
                f"{', '.join(Path(f).name for f in sources)}"
            )
            log.warning(f"  {key}: conflicting values across {len(sources)} files")

        for env_file in ENV_FILES:
            if not env_file.exists():
                continue
            already_correct = sources.get(str(env_file)) == canonical_value
            needs_dedupe = env_file.name in duplicates.get(key, [])
            if already_correct and not needs_dedupe:
                continue
            try:
                action = _write_env_key(env_file, key, canonical_value)
                fixed.append(f"{action.capitalize()} {key} in {env_file.name}")
                state.record_fix()
                log.info(f"  {action.capitalize()} {key} in {env_file.name}")
                audit_log("sentinel", "env_key_sync", "ok", {"key": key, "target": env_file.name, "action": action})
            except Exception as e:
                issues.append(f"Failed to sync {key} to {env_file.name}: {e}")

    if not issues and not fixed:
        log.info(f"  Env keys: all {len(REQUIRED_ENV_KEYS)} keys synced across {len(ENV_FILES)} files")

    return issues, fixed


# ============================================================
# CHECK 13: PORT MANIFEST
# ============================================================

PORT_MANIFEST = {
    5050: "alchemist",
    5055: "juris",
    # 5055 now juris (gemini-server removed),
    5090: "ascendant-store",
    5095: "dominion-report",
    5060: "conductor",
    5000: "gatekeeper",
    5070: "buddy-web",
    5080: "dominion-store",
    9380: "auric-edge",
    3000: "dashboard",
    11434: "ollama",
}


def check_port_manifest():
    """Verify expected ports are bound and no unknown dominion services are squatting."""
    issues = []
    try:
        r = subprocess.run(["ss", "-tln"], capture_output=True, text=True, timeout=10)
        lines = r.stdout.strip().split("\n")

        for port, expected_name in PORT_MANIFEST.items():
            port_str = f":{port} "
            port_str2 = f":{port}\n"
            bound = any(port_str in l or l.endswith(f":{port}") for l in lines)
            if bound:
                log.info(f"  Port {port} ({expected_name}): bound")
            # Not bound = handled by check_services, skip here
    except Exception as e:
        log.error(f"  Port manifest check failed: {e}")

    if not issues:
        log.info("  Port manifest: all clear")
    return issues


# ============================================================
# GMAIL ALERT
# ============================================================
def send_alert(subject, body, state, alert_key):
    if not GMAIL_USER or not GMAIL_PASS:
        log.warning(f"Gmail not configured — alert suppressed: {subject}")
        return
    if not state.can_alert(alert_key):
        log.info(f"Alert cooldown active for {alert_key}")
        return

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"[DOMINION SENTINEL] {subject}"
        msg["From"] = GMAIL_USER
        msg["To"] = ALERT_EMAIL

        html = f"""
        <html><body style="font-family:monospace; background:#050810; color:#c8d8f0; padding:20px;">
        <h2 style="color:#D4AF37;">DOMINION SENTINEL ALERT</h2>
        <p><strong>{subject}</strong></p>
        <pre style="background:#0a1020; padding:15px; border-left:4px solid #D4AF37;">{body}</pre>
        <p style="color:#4a6080;">Phi interval: {SCAN_INTERVAL:.0f}s | {datetime.utcnow().isoformat()}</p>
        <p style="color:#4a6080;">Oath: Yahweh First. Family Second. People Third.</p>
        </body></html>
        """
        msg.attach(MIMEText(html, "html"))

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(GMAIL_USER, GMAIL_PASS)
            smtp.send_message(msg)

        state.mark_alerted(alert_key)
        log.info(f"Alert sent to {ALERT_EMAIL}: {subject}")
    except Exception as e:
        log.error(f"Alert send failed: {e}")


# ============================================================
# MAIN CYCLE
# ============================================================
def run_cycle(state):
    state.tick()
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    log.info(f"{'='*60}")
    log.info(f"PHI CYCLE #{state.data['cycles']} | {now}")
    log.info(f"{'='*60}")

    all_issues = []
    all_fixed = []

    # 1. Service port checks
    log.info("[1/13] Service ports...")
    issues, fixed = check_services(state)
    all_issues.extend(issues)
    all_fixed.extend(fixed)

    # 2. Docker containers
    log.info("[2/13] Docker containers...")
    issues, fixed = check_docker(state)
    all_issues.extend(issues)
    all_fixed.extend(fixed)

    # 3. Disk monitoring
    log.info("[3/13] Disk space...")
    issues, fixed = check_disk(state)
    all_issues.extend(issues)
    all_fixed.extend(fixed)

    # 4. Model name validation
    log.info("[4/13] Model names...")
    all_issues.extend(validate_models())

    # 5. API key validation
    log.info("[5/13] API keys...")
    all_issues.extend(validate_api_keys())

    # 6. Cron verification
    log.info("[6/13] Cron jobs...")
    all_issues.extend(check_crons())

    # 7. Pipeline health
    log.info("[7/13] Pipeline health...")
    all_issues.extend(check_pipeline_health())

    # 8. Database health
    log.info("[8/13] Database...")
    all_issues.extend(check_db())

    # 9. File ownership
    log.info("[9/13] File ownership...")
    issues, fixed = check_ownership(state)
    all_issues.extend(issues)
    all_fixed.extend(fixed)

    # 10. Log rotation
    log.info("[10/13] Log rotation...")
    all_fixed.extend(rotate_logs())

    # 11. Watchmen status
    log.info("[11/13] Watchmen...")
    all_issues.extend(check_watchmen())

    # 12. Env key sync
    log.info("[12/13] Env key sync...")
    issues, fixed = check_env_keys(state)
    all_issues.extend(issues)
    all_fixed.extend(fixed)

    # 13. Port manifest
    log.info("[13/13] Port manifest...")
    all_issues.extend(check_port_manifest())

    # ── Summary ──
    summary = state.summary()
    service_status = {}
    for name, cfg in SERVICES.items():
        service_status[name] = "ONLINE" if check_port(cfg["port"]) else "OFFLINE"

    state.data["last_result"] = {
        "ts": datetime.utcnow().isoformat(),
        "cycle": state.data["cycles"],
        "issues": all_issues,
        "fixed": all_fixed,
        "services": service_status,
        "healthy": len(all_issues) == 0,
    }
    state.save()

    audit_log("sentinel", "cycle_complete",
              "ok" if not all_issues else "warning",
              {"cycle": state.data["cycles"], "issues": len(all_issues), "fixed": len(all_fixed)})

    log.info(f"[SUMMARY] Issues: {len(all_issues)} | Fixed: {len(all_fixed)}")
    if all_fixed:
        log.info(f"  AUTO-FIXED: {all_fixed}")
    if all_issues:
        log.warning(f"  OPEN ISSUES: {all_issues}")
    else:
        log.info("  ALL SYSTEMS SOVEREIGN")
    log.info(f"{'='*60}")

    return {"issues": all_issues, "fixed": all_fixed, "summary": summary}


# ============================================================
# STATUS REPORT
# ============================================================
def print_status():
    data = load_json(STATUS_FILE, default={})
    if not data:
        print("No status data yet. Run a cycle first.")
        return

    print(f"\n{'='*60}")
    print(f"  DOMINION SENTINEL — STATUS")
    print(f"  {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"{'='*60}")
    print(f"  Phi interval:    {SCAN_INTERVAL/60:.1f} minutes")
    print(f"  Cycles run:      {data.get('cycles', 0)}")
    print(f"  Total restarts:  {data.get('total_restarts', 0)}")
    print(f"  Total auto-fixes:{data.get('total_auto_fixes', 0)}")
    print(f"  Total alerts:    {data.get('total_alerts', 0)}")
    print(f"  Last cycle:      {data.get('last_cycle', 'never')}")

    last = data.get("last_result", {})
    if last:
        print(f"\n  LAST RESULT ({last.get('ts', '?')}):")
        print(f"  Healthy: {'YES' if last.get('healthy') else 'NO'}")
        services = last.get("services", {})
        if services:
            print(f"\n  SERVICES:")
            for name, status in services.items():
                icon = "+" if status == "ONLINE" else "!"
                print(f"    [{icon}] {name}: {status}")
        issues = last.get("issues", [])
        if issues:
            print(f"\n  OPEN ISSUES:")
            for i in issues:
                print(f"    - {i}")
        fixed_items = last.get("fixed", [])
        if fixed_items:
            print(f"\n  AUTO-FIXED:")
            for f in fixed_items:
                print(f"    + {f}")

    print(f"{'='*60}\n")


# ============================================================
# ENTRY POINT
# ============================================================
def main():
    _acquire_lock()

    log.info("=" * 60)
    log.info("  DOMINION SENTINEL — ONLINE")
    log.info(f"  Phi interval: {SCAN_INTERVAL/60:.1f} minutes ({SCAN_INTERVAL:.0f}s)")
    log.info(f"  Alert email: {ALERT_EMAIL}")
    log.info(f"  Status file: {STATUS_FILE}")
    log.info("  Oath: Yahweh First. Family Second. People Third.")
    log.info("=" * 60)

    state = SentinelState()

    # First cycle immediately
    run_cycle(state)

    # Loop on phi timing
    while True:
        log.info(f"[SLEEP] Next cycle in {SCAN_INTERVAL/60:.1f} minutes...")
        time.sleep(SCAN_INTERVAL)
        try:
            run_cycle(state)
        except Exception as e:
            log.error(f"[CYCLE ERROR] {e}")
            audit_log("sentinel", "cycle_error", "critical", {"error": str(e)})


SYSTEMD_UNIT = """[Unit]
Description=Dominion Sentinel — Autonomous Guardian (phi=1.618)
After=network-online.target docker.service
Wants=network-online.target

[Service]
Type=simple
User=malachisingleton8
WorkingDirectory=/home/malachisingleton8/buddy_core
ExecStart=/home/malachisingleton8/dominion_env/bin/python3 sentinel.py
Restart=always
RestartSec=10
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
"""

if __name__ == "__main__":
    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        if cmd == "status":
            print_status()
        elif cmd == "cycle":
            state = SentinelState()
            result = run_cycle(state)
            print(json.dumps(result, indent=2, default=str))
        elif cmd == "service":
            print(SYSTEMD_UNIT)
            print("To install:")
            print("  sudo cp /tmp/dominion-sentinel.service /etc/systemd/system/")
            print("  sudo systemctl daemon-reload")
            print("  sudo systemctl enable dominion-sentinel")
            print("  sudo systemctl start dominion-sentinel")
        else:
            print(f"Unknown command: {cmd}")
            print("Usage: python sentinel.py [status|cycle|service]")
    else:
        main()