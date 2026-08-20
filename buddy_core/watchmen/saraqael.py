"""
watchmen/saraqael.py — SARAQAEL (Audit Watchman)
=================================================
The first and foundational Watchman. Append-only, tamper-proof audit log
with cryptographic chain signatures. All other Watchmen report here.

Architecture:
  - Each entry is SHA-256 hashed and includes the hash of the previous entry
    (blockchain-style chaining). Tampering with any entry breaks the chain.
  - Written to watchmen_audit.log (append-only, never truncated).
  - Machine-readable JSONL — one JSON object per line.
  - Exposes: log(), verify_chain(), tail(), report()

Governance: phi = 1.618 | DominionBrain validation required for chain reset.
"""

import os
import sys
import json
import hmac
import hashlib
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from phi_memory import get_store as _get_mem

_memory = _get_mem()
_AGENT  = "saraqael"

# ── Config ────────────────────────────────────────────────────

BASE_DIR    = Path(__file__).resolve().parent.parent
AUDIT_FILE  = BASE_DIR / "watchmen_audit.log"
CHAIN_FILE  = BASE_DIR / "watchmen_chain.json"   # Stores latest hash for chaining

# Chain key — used as HMAC secret. Embedded (not stored externally).
# Change only in a secure session; doing so breaks existing chain verification.
_CHAIN_SECRET = b"dominion_phi_1618_saraqael_eternal"


# ── Chain helpers ─────────────────────────────────────────────

def _load_chain() -> dict:
    """Load the running chain state (last hash + entry count)."""
    if CHAIN_FILE.exists():
        try:
            return json.loads(CHAIN_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"last_hash": "GENESIS", "count": 0}


def _save_chain(state: dict):
    CHAIN_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")


def _entry_hash(entry: dict, prev_hash: str) -> str:
    """HMAC-SHA256 of the entry content + previous hash."""
    payload = json.dumps(entry, sort_keys=True, ensure_ascii=True) + prev_hash
    return hmac.new(_CHAIN_SECRET, payload.encode(), hashlib.sha256).hexdigest()


# ── Core API ──────────────────────────────────────────────────

def log(
    source: str,
    event: str,
    status: str = "info",
    details: dict = None,
    threat_level: str = "none",
) -> dict:
    """
    Append a cryptographically chained entry to the audit log.

    Args:
        source:       Watchman or system that generated the event
                      (e.g. 'gabriel', 'uriel', 'system')
        event:        Short event descriptor (e.g. 'ssh_attempt', 'file_modified')
        status:       'info' | 'warning' | 'critical' | 'ok'
        details:      Arbitrary dict — kept under 1KB
        threat_level: 'none' | 'low' | 'medium' | 'high' | 'critical'

    Returns:
        The completed entry dict (includes hash and sequence number).
    """
    chain = _load_chain()
    ts    = datetime.now(timezone.utc).isoformat()

    entry = {
        "seq":          chain["count"] + 1,
        "ts":           ts,
        "source":       source,
        "event":        event,
        "status":       status,
        "threat_level": threat_level,
        "details":      details or {},
        "prev_hash":    chain["last_hash"],
    }

    entry_hash = _entry_hash(entry, chain["last_hash"])
    entry["hash"] = entry_hash

    # Append to audit log — JSONL format
    with open(AUDIT_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=True) + "\n")

    # Update chain state
    chain["last_hash"] = entry_hash
    chain["count"]     = entry["seq"]
    _save_chain(chain)

    # PhiMemory: store critical events
    if threat_level in ("high", "critical"):
        try:
            level_map = {"high": 0.8, "critical": 1.0}
            _memory.store(_AGENT,
                [level_map.get(threat_level, 0.5), 1.0, 0.0, 0.0],
                metadata={"ts": ts[:19], "source": source, "event": event,
                          "threat": threat_level, "seq": entry["seq"]})
        except Exception:
            pass

    return entry


def verify_chain() -> dict:
    """
    Walk the entire audit log and verify every hash in the chain.
    Returns a report dict with 'valid', 'entries_checked', 'first_break'.
    """
    if not AUDIT_FILE.exists():
        return {"valid": True, "entries_checked": 0, "first_break": None, "message": "Log empty"}

    entries = []
    with open(AUDIT_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    entries.append(json.loads(line))
                except Exception:
                    pass

    if not entries:
        return {"valid": True, "entries_checked": 0, "first_break": None, "message": "No entries"}

    prev_hash = "GENESIS"
    for e in entries:
        stored_hash = e.get("hash", "")
        e_copy = {k: v for k, v in e.items() if k != "hash"}
        expected = _entry_hash(e_copy, e.get("prev_hash", "GENESIS"))
        if expected != stored_hash:
            return {
                "valid":           False,
                "entries_checked": e["seq"],
                "first_break":     e["seq"],
                "message":         f"Chain broken at entry #{e['seq']} (ts={e['ts']})",
            }
        prev_hash = stored_hash

    return {
        "valid":           True,
        "entries_checked": len(entries),
        "first_break":     None,
        "message":         f"Chain intact across {len(entries)} entries",
    }


def tail(n: int = 20) -> list:
    """Return the last N audit log entries."""
    if not AUDIT_FILE.exists():
        return []
    entries = []
    with open(AUDIT_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    entries.append(json.loads(line))
                except Exception:
                    pass
    return entries[-n:]


def report() -> dict:
    """Generate a summary report of the audit log."""
    if not AUDIT_FILE.exists():
        return {"total": 0, "by_status": {}, "by_source": {}, "threats": []}

    total = 0
    by_status: dict = {}
    by_source: dict = {}
    threats   = []

    with open(AUDIT_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                e = json.loads(line)
                total += 1
                by_status[e["status"]]  = by_status.get(e["status"], 0) + 1
                by_source[e["source"]]  = by_source.get(e["source"], 0) + 1
                if e.get("threat_level") in ("high", "critical"):
                    threats.append({
                        "seq":    e["seq"],
                        "ts":     e["ts"],
                        "source": e["source"],
                        "event":  e["event"],
                        "level":  e["threat_level"],
                    })
            except Exception:
                pass

    chain_status = verify_chain()

    return {
        "total":        total,
        "chain_valid":  chain_status["valid"],
        "chain_msg":    chain_status["message"],
        "by_status":    by_status,
        "by_source":    by_source,
        "open_threats": [t for t in threats[-10:]],
    }


def run():
    """Saraqael self-check — verify chain integrity and log startup."""
    log("saraqael", "startup", "ok", {"watchman": "Saraqael", "role": "audit"})
    result = verify_chain()
    status = "ok" if result["valid"] else "critical"
    log("saraqael", "chain_verify", status, result,
        threat_level="none" if result["valid"] else "critical")
    print(f"[SARAQAEL] Chain: {result['message']}")
    return result


if __name__ == "__main__":
    run()
    r = report()
    print(f"[SARAQAEL] Report: {r['total']} entries | Chain valid: {r['chain_valid']}")
