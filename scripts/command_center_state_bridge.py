#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def run(args: list[str]) -> tuple[int, str]:
    try:
        cp = subprocess.run(args, check=False, capture_output=True, text=True, timeout=10)
        return cp.returncode, cp.stdout.strip()
    except Exception:
        return 99, ""


def systemd_unit(name: str) -> dict[str, Any]:
    _, active = run(["systemctl", "is-active", name])
    _, enabled = run(["systemctl", "is-enabled", name])
    return {
        "active": active == "active",
        "active_state": active or "unknown",
        "enabled": enabled == "enabled",
        "enabled_state": enabled or "unknown",
    }


def http_health(url: str) -> dict[str, Any]:
    rc, code = run(["curl", "-sS", "-o", "/dev/null", "-w", "%{http_code}", "--connect-timeout", "2", "--max-time", "5", url])
    return {"ok": rc == 0 and code == "200", "status": int(code) if code.isdigit() else None}


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def atomic_write(path: Path, text: str, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(tmp_name, mode)
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def lane_snapshot(policy_path: Path) -> dict[str, Any]:
    policy = load_json(policy_path)
    if not isinstance(policy, dict):
        return {"connected": False, "registered": 0, "open": 0, "all_open": False, "items": []}
    lane_map = policy.get("lanes", {})
    if not isinstance(lane_map, dict):
        lane_map = {}
    items = []
    for slug, state in lane_map.items():
        state = state if isinstance(state, dict) else {}
        items.append({
            "slug": slug,
            "name": slug.replace("_", " ").title(),
            "internal_work_open": bool(state.get("internal_work_open")),
            "scheduler_eligible": bool(state.get("scheduler_eligible")),
            "external_readiness": state.get("external_readiness", "separate_gate"),
        })
    open_count = sum(1 for item in items if item["internal_work_open"] and item["scheduler_eligible"])
    return {
        "connected": True,
        "governing_name": policy.get("governing_name", "RADAH MEMSHALAH — רָדָה מֶמְשָׁלָה"),
        "registered": len(items),
        "open": open_count,
        "all_open": bool(items) and open_count == len(items),
        "items": items,
    }


def revenue_snapshot(db_path: Path) -> dict[str, Any]:
    base = {
        "connected": False,
        "constraint": "REVENUE_RUNTIME_UNAVAILABLE",
        "active_experiment_count": 0,
        "experiments": [],
        "totals": {"visitors": None, "clicks": None, "purchases": None, "revenue_cents": None},
    }
    if not db_path.is_file():
        return base
    try:
        db = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=5)
        db.row_factory = sqlite3.Row
        experiments = db.execute(
            """SELECT id,name,product_id,target_url,status,winner,activated_at,decided_at
               FROM experiments
               WHERE status IN ('active','winner_ready','promoted','rolled_back')
               ORDER BY COALESCE(activated_at,created_at) DESC"""
        ).fetchall()
        output = []
        total_visitors = total_clicks = total_purchases = total_revenue = 0
        for exp in experiments:
            exp_id = exp["id"]
            variants: dict[str, Any] = {}
            for variant in ("control", "treatment"):
                visitors = int(db.execute(
                    "SELECT COUNT(DISTINCT visitor_id) FROM events WHERE experiment_id=? AND variant=? AND event_type='impression'",
                    (exp_id, variant),
                ).fetchone()[0] or 0)
                clicks = int(db.execute(
                    "SELECT COUNT(DISTINCT visitor_id) FROM events WHERE experiment_id=? AND variant=? AND event_type='click'",
                    (exp_id, variant),
                ).fetchone()[0] or 0)
                purchases = int(db.execute(
                    "SELECT COUNT(DISTINCT visitor_id) FROM events WHERE experiment_id=? AND variant=? AND event_type='purchase'",
                    (exp_id, variant),
                ).fetchone()[0] or 0)
                revenue_cents = int(db.execute(
                    "SELECT COALESCE(SUM(revenue_cents),0) FROM events WHERE experiment_id=? AND variant=? AND event_type='purchase'",
                    (exp_id, variant),
                ).fetchone()[0] or 0)
                variants[variant] = {
                    "visitors": visitors,
                    "clicks": clicks,
                    "purchases": purchases,
                    "revenue_cents": revenue_cents,
                }
                total_visitors += visitors
                total_clicks += clicks
                total_purchases += purchases
                total_revenue += revenue_cents
            output.append({
                "id": exp_id,
                "name": exp["name"],
                "product_id": exp["product_id"],
                "target_url": exp["target_url"],
                "status": exp["status"],
                "winner": exp["winner"],
                "activated_at": exp["activated_at"],
                "decided_at": exp["decided_at"],
                "variants": variants,
            })
        db.close()
    except Exception as exc:
        base["error"] = type(exc).__name__
        return base

    active = [e for e in output if e["status"] == "active"]
    if not active:
        constraint = "NO_ACTIVE_EXPERIMENT"
    elif total_visitors == 0:
        constraint = "QUALIFIED_TRAFFIC"
    elif total_clicks == 0:
        constraint = "OFFER_ENGAGEMENT"
    elif total_purchases == 0:
        constraint = "PURCHASE_CONVERSION"
    else:
        constraint = "STATISTICAL_EVIDENCE"
        if any(e["status"] == "promoted" for e in output):
            constraint = "COMPOUND_WINNER"

    return {
        "connected": True,
        "constraint": constraint,
        "active_experiment_count": len(active),
        "experiments": output,
        "totals": {
            "visitors": total_visitors,
            "clicks": total_clicks,
            "purchases": total_purchases,
            "revenue_cents": total_revenue,
        },
    }


def latest_receipts(root: Path, limit: int = 6) -> list[dict[str, Any]]:
    files = []
    for child in (root / "autopilot" / "receipts", root / "revenue-runtime" / "receipts"):
        if child.is_dir():
            try:
                files.extend(p for p in child.glob("*.json") if p.is_file())
            except OSError:
                pass
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    receipts = []
    for path in files[:limit]:
        payload = load_json(path)
        receipts.append({
            "source": "autopilot" if "autopilot" in path.parts else "revenue-runtime",
            "name": path.name,
            "data": payload if isinstance(payload, dict) else None,
        })
    return receipts


def autopilot_snapshot(root: Path) -> dict[str, Any]:
    state_path = root / "autopilot" / "state.json"
    state = load_json(state_path)
    if not isinstance(state, dict):
        return {"connected": False, "timer": systemd_unit("dominion-radah-autopilot.timer")}
    lanes = state.get("lanes", {}) if isinstance(state.get("lanes"), dict) else {}
    progressed = sum(1 for item in lanes.values() if isinstance(item, dict) and item.get("last_progress_at"))
    return {
        "connected": True,
        "timer": systemd_unit("dominion-radah-autopilot.timer"),
        "cycles": int(state.get("cycles", 0) or 0),
        "lanes_touched": len(lanes),
        "lanes_progressed": progressed,
        "lane_state": lanes,
    }


def founder_holds(repo: Path) -> list[str]:
    holds = set()
    revenue = load_json(repo / "governance" / "revenue_execution_policy.json")
    if isinstance(revenue, dict):
        actions = revenue.get("automatic_external_actions", {})
        if isinstance(actions, dict):
            for key, enabled in actions.items():
                if enabled is False:
                    holds.add(key)
    autopilot = load_json(repo / "governance" / "radah_memshalah_autopilot_policy.json")
    if isinstance(autopilot, dict):
        boundaries = autopilot.get("authority", {})
        if isinstance(boundaries, dict):
            for key in boundaries.get("founder_held_prefixes", []) or []:
                holds.add(str(key))
    return sorted(holds)


def render_daily(snapshot: dict[str, Any]) -> str:
    lanes = snapshot["lanes"]
    revenue = snapshot["revenue"]
    autopilot = snapshot["autopilot"]
    totals = revenue["totals"]
    systems = snapshot["systems"]
    lines = [
        "---",
        "cssclasses:",
        "  - dominion-command-center",
        "aliases:",
        "  - Dominion Live Daily State",
        "---",
        "",
        '<div class="dominion-shell">',
        "",
        "# Live Daily State",
        "",
        f"**Observed:** `{snapshot['observed_at']}`  ",
        f"**Release:** `{snapshot.get('release_sha') or 'unavailable'}`  ",
        f"**Lane access:** **{lanes['open']} / {lanes['registered']} OPEN**  ",
        f"**Revenue constraint:** **{revenue['constraint']}**  ",
        "",
        "> Current production state requires timestamped runtime receipts.",
        "",
        "## Revenue Work Plane",
        "",
        f"- Active experiments: **{revenue['active_experiment_count']}**",
        f"- Real visitors: **{totals['visitors'] if totals['visitors'] is not None else 'unavailable'}**",
        f"- Clicks: **{totals['clicks'] if totals['clicks'] is not None else 'unavailable'}**",
        f"- Paid purchases: **{totals['purchases'] if totals['purchases'] is not None else 'unavailable'}**",
        f"- Attributed revenue: **${((totals['revenue_cents'] or 0) / 100):,.2f}**" if totals['revenue_cents'] is not None else "- Attributed revenue: **unavailable**",
        "",
    ]
    for exp in revenue.get("experiments", []):
        lines.extend([
            f"### {exp['name']}",
            f"- Experiment: `{exp['id']}`",
            f"- Status: **{exp['status']}**",
            f"- Product: `{exp['product_id']}`",
            f"- Winner: **{exp.get('winner') or 'not decided'}**",
            "",
        ])
    lines.extend([
        "## RADAH MEMSHALAH Work Plane",
        "",
        f"- Autopilot connected: **{autopilot.get('connected', False)}**",
        f"- Autopilot timer active: **{autopilot.get('timer', {}).get('active', False)}**",
        f"- Cycles recorded: **{autopilot.get('cycles', 0)}**",
        f"- Lanes touched: **{autopilot.get('lanes_touched', 0)}**",
        f"- Lanes with recorded progress: **{autopilot.get('lanes_progressed', 0)}**",
        "",
        "## Core Runtime",
        "",
    ])
    for name, state in systems.items():
        if isinstance(state, dict):
            ok = state.get("active") if "active" in state else state.get("ok")
            lines.append(f"- {name}: **{'ONLINE' if ok else 'NOT VERIFIED'}**")
    lines.extend([
        "",
        "## Founder-Held External Effects",
        "",
    ])
    for hold in snapshot.get("founder_holds", []):
        lines.append(f"- `{hold}`")
    lines.extend([
        "",
        "## Latest Receipts",
        "",
    ])
    for receipt in snapshot.get("latest_receipts", []):
        lines.append(f"- `{receipt['source']}` · `{receipt['name']}`")
    lines.extend(["", "</div>", ""])
    return "\n".join(lines)


def build_snapshot(repo: Path, dominion_root: Path) -> dict[str, Any]:
    rc, release_sha = run(["git", "-C", str(repo), "rev-parse", "HEAD"])
    release_sha = release_sha if rc == 0 else None
    lanes = lane_snapshot(repo / "governance" / "lane_access_policy.json")
    revenue = revenue_snapshot(dominion_root / "revenue-runtime" / "revenue.db")
    systems = {
        "command_center": http_health("http://127.0.0.1:8091/health"),
        "revenue_runtime": systemd_unit("dominion-revenue-runtime.service"),
        "revenue_evaluator": systemd_unit("dominion-revenue-evaluator.timer"),
        "radah_autopilot": systemd_unit("dominion-radah-autopilot.timer"),
        "buddy": http_health("http://127.0.0.1:5070/health"),
        "n8n": http_health("http://127.0.0.1:5678/healthz"),
        "conductor": http_health("http://127.0.0.1:5060/health"),
        "wix_agent": http_health("http://127.0.0.1:8082/ready"),
    }
    return {
        "schema": "dominion-command-center-runtime-state-v1",
        "observed_at": now_iso(),
        "release_sha": release_sha,
        "systems": systems,
        "lanes": lanes,
        "autopilot": autopilot_snapshot(dominion_root),
        "revenue": revenue,
        "founder_holds": founder_holds(repo),
        "latest_receipts": latest_receipts(dominion_root),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default=str(Path.home() / "dominion-ops"))
    parser.add_argument("--dominion-root", default=str(Path.home() / ".dominion"))
    parser.add_argument("--output", default=str(Path.home() / ".dominion/command-center/runtime-state.json"))
    parser.add_argument("--daily-state", default="")
    args = parser.parse_args()

    snapshot = build_snapshot(Path(args.repo), Path(args.dominion_root))
    output = Path(args.output)
    atomic_write(output, json.dumps(snapshot, indent=2, ensure_ascii=False, sort_keys=True) + "\n")
    if args.daily_state:
        atomic_write(Path(args.daily_state), render_daily(snapshot), 0o600)
    lanes = snapshot["lanes"]
    revenue = snapshot["revenue"]
    print(
        "COMMAND_CENTER_STATE=PASS "
        f"lanes={lanes['open']}/{lanes['registered']} "
        f"revenue_connected={str(revenue['connected']).lower()} "
        f"constraint={revenue['constraint']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
