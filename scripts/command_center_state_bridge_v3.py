#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import json
import sqlite3
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

BASE_PATH = Path(__file__).with_name("command_center_state_bridge_v2.py")
spec = importlib.util.spec_from_file_location("command_center_state_bridge_v2", BASE_PATH)
if not spec or not spec.loader:
    raise RuntimeError("command_center_state_bridge_v2_import_failed")
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)


def _integrity_state(root: Path) -> dict:
    latest = base.load_json(root / "system-integrity/latest.json")
    if not isinstance(latest, dict):
        return {"ok": False, "status": "UNVERIFIED", "observed_at": None, "defect_count": None, "cycle": None}
    observed_at = latest.get("observed_at")
    age = None
    try:
        observed = datetime.fromisoformat(str(observed_at).replace("Z", "+00:00")).astimezone(timezone.utc)
        age = max(0.0, (datetime.now(timezone.utc) - observed).total_seconds())
    except (TypeError, ValueError):
        pass
    fresh = age is not None and age <= 240
    return {
        "ok": latest.get("ok") is True and latest.get("status") == "PASS" and fresh,
        "status": latest.get("status") if fresh else "STALE",
        "observed_at": observed_at,
        "age_seconds": None if age is None else int(age),
        "defect_count": latest.get("defect_count"),
        "cycle": latest.get("cycle"),
        "authority": latest.get("authority"),
    }


def _publisher_health() -> dict:
    """Read only the Publisher's non-secret loopback health contract."""
    try:
        with urllib.request.urlopen("http://127.0.0.1:5112/health", timeout=5) as response:
            status_code = int(response.status)
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, ValueError, TypeError, urllib.error.URLError):
        return {
            "ok": False,
            "status": None,
            "service": "dominion-publisher",
            "operator_gate_configured": False,
            "meta_app_configured": False,
            "meta_token_configured": False,
            "meta_graph_version_configured": False,
            "meta_bound_counts": {"facebook": 0, "instagram": 0},
            "platforms": [],
        }
    if not isinstance(payload, dict):
        return {
            "ok": False,
            "status": status_code,
            "service": "dominion-publisher",
            "operator_gate_configured": False,
            "meta_app_configured": False,
            "meta_token_configured": False,
            "meta_graph_version_configured": False,
            "meta_bound_counts": {"facebook": 0, "instagram": 0},
            "platforms": [],
        }
    counts = payload.get("meta_bound_counts") if isinstance(payload.get("meta_bound_counts"), dict) else {}
    safe_counts = {
        "facebook": int(counts.get("facebook", 0) or 0),
        "instagram": int(counts.get("instagram", 0) or 0),
    }
    return {
        "ok": status_code == 200 and payload.get("status") == "ok" and payload.get("service") == "dominion-publisher",
        "status": status_code,
        "service": "dominion-publisher",
        "operator_gate_configured": payload.get("operator_gate_configured") is True,
        "meta_app_configured": payload.get("meta_app_configured") is True,
        "meta_token_configured": payload.get("meta_token_configured") is True,
        "meta_graph_version_configured": payload.get("meta_graph_version_configured") is True,
        "meta_bound_counts": safe_counts,
        "platforms": sorted(str(x) for x in payload.get("platforms", []) if str(x).strip()),
    }


def _publisher_ledger(root: Path) -> dict:
    """Read queue/receipt counts from the Publisher SQLite ledger without mutation."""
    db_path = root / "publisher/dominion_publisher.db"
    empty = {
        "connected": False,
        "jobs_total": None,
        "queued": None,
        "published": None,
        "failed": None,
        "blocked": None,
        "receipts_total": None,
        "latest_receipt_at": None,
    }
    if not db_path.is_file():
        return empty
    try:
        db = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=5)
        rows = db.execute("SELECT status, COUNT(*) FROM jobs GROUP BY status").fetchall()
        by_status = {str(status).upper(): int(count) for status, count in rows}
        jobs_total = int(db.execute("SELECT COUNT(*) FROM jobs").fetchone()[0] or 0)
        receipts_total = int(db.execute("SELECT COUNT(*) FROM receipts").fetchone()[0] or 0)
        latest = db.execute("SELECT MAX(created_at) FROM receipts").fetchone()[0]
        db.close()
    except (sqlite3.Error, OSError, TypeError, ValueError):
        return empty
    return {
        "connected": True,
        "jobs_total": jobs_total,
        "queued": by_status.get("QUEUED", 0),
        "published": by_status.get("PUBLISHED", 0),
        "failed": by_status.get("FAILED", 0),
        "blocked": by_status.get("BLOCKED", 0),
        "receipts_total": receipts_total,
        "latest_receipt_at": latest,
    }


def _publisher_state(root: Path) -> dict:
    health = _publisher_health()
    ledger = _publisher_ledger(root)
    counts = health["meta_bound_counts"]
    bound_count = int(counts.get("facebook", 0)) + int(counts.get("instagram", 0))
    if not health["ok"]:
        phase = "RUNTIME_UNAVAILABLE"
    elif not health["meta_app_configured"]:
        phase = "AWAITING_META_APP_CONFIGURATION"
    elif bound_count == 0:
        phase = "AWAITING_META_ACCOUNT_BINDING"
    elif not ledger["connected"]:
        phase = "BOUND_LEDGER_UNVERIFIED"
    elif int(ledger.get("published") or 0) == 0:
        phase = "BOUND_AWAITING_CONTROLLED_CANARY"
    else:
        phase = "PUBLISHING_PROVEN"
    return {
        **health,
        "bound_account_count": bound_count,
        "ledger": ledger,
        "phase": phase,
        "canary_proven": bool(ledger["connected"] and int(ledger.get("published") or 0) > 0),
    }


def _publisher_daily_section(publisher: dict) -> list[str]:
    ledger = publisher.get("ledger", {}) if isinstance(publisher.get("ledger"), dict) else {}
    counts = publisher.get("meta_bound_counts", {}) if isinstance(publisher.get("meta_bound_counts"), dict) else {}
    return [
        "## Dominion Publisher",
        "",
        f"- Runtime: **{'ONLINE' if publisher.get('ok') else 'NOT VERIFIED'}**",
        f"- Closure phase: **{publisher.get('phase', 'UNKNOWN')}**",
        f"- Meta app configured: **{bool(publisher.get('meta_app_configured'))}**",
        f"- Facebook accounts bound: **{int(counts.get('facebook', 0) or 0)}**",
        f"- Instagram accounts bound: **{int(counts.get('instagram', 0) or 0)}**",
        f"- Queue ledger connected: **{bool(ledger.get('connected'))}**",
        f"- Jobs: **{ledger.get('jobs_total') if ledger.get('jobs_total') is not None else 'unavailable'}**",
        f"- Published: **{ledger.get('published') if ledger.get('published') is not None else 'unavailable'}**",
        f"- Failed: **{ledger.get('failed') if ledger.get('failed') is not None else 'unavailable'}**",
        f"- Controlled publish proof: **{bool(publisher.get('canary_proven'))}**",
        "",
    ]


def daily_markdown(state: dict) -> str:
    rendered = base.daily_markdown(state)
    marker = "\n</div>\n"
    section = "\n".join(_publisher_daily_section(state.get("publisher", {})))
    if marker in rendered:
        return rendered.replace(marker, f"\n{section}\n</div>\n", 1)
    return rendered + "\n" + section


def build_state(repo: Path, root: Path):
    state = base.build_state(repo, root)
    systems = state.setdefault("systems", {})
    systems["mcp_cli"] = base.http("http://127.0.0.1:8390/health")
    systems["system_integrity"] = _integrity_state(root)
    publisher = _publisher_state(root)
    state["publisher"] = publisher
    systems["dominion_publisher"] = {
        "ok": publisher["ok"],
        "status": publisher["status"],
    }
    systems["publisher_meta_app"] = {
        "ok": publisher["meta_app_configured"],
        "status": 200 if publisher["meta_app_configured"] else None,
    }
    systems["publisher_account_binding"] = {
        "ok": publisher["bound_account_count"] > 0,
        "status": 200 if publisher["bound_account_count"] > 0 else None,
    }
    systems["publisher_queue_ledger"] = {
        "ok": bool(publisher["ledger"].get("connected")),
        "status": 200 if publisher["ledger"].get("connected") else None,
    }
    systems["publisher_controlled_publish"] = {
        "ok": publisher["canary_proven"],
        "status": 200 if publisher["canary_proven"] else None,
    }
    return state


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default=str(Path.home() / "dominion-ops"))
    parser.add_argument("--dominion-root", default=str(Path.home() / ".dominion"))
    parser.add_argument("--output", default=str(Path.home() / ".dominion/command-center/runtime-state.json"))
    parser.add_argument("--daily-state", default="")
    args = parser.parse_args()

    repo = Path(args.repo)
    root = Path(args.dominion_root)
    state = build_state(repo, root)
    base.atomic_write(Path(args.output), json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    if args.daily_state:
        base.atomic_write(Path(args.daily_state), daily_markdown(state), 0o600)

    lanes = state["lanes"]
    revenue = state["revenue"]
    mcp = state.get("systems", {}).get("mcp_cli", {})
    integrity = state.get("systems", {}).get("system_integrity", {})
    publisher = state.get("publisher", {})
    print(
        f"COMMAND_CENTER_STATE=PASS lanes={lanes['open']}/{lanes['registered']} "
        f"revenue_connected={str(revenue['connected']).lower()} constraint={revenue['constraint']} "
        f"mcp_cli={str(bool(mcp.get('ok'))).lower()} "
        f"system_integrity={str(bool(integrity.get('ok'))).lower()} "
        f"publisher={str(bool(publisher.get('ok'))).lower()} "
        f"publisher_phase={publisher.get('phase', 'UNKNOWN')} "
        f"receipts={len(state['latest_receipts'])}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
