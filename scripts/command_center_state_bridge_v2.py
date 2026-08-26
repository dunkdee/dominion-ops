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


def run(args: list[str], timeout: int = 10) -> tuple[int, str]:
    try:
        cp = subprocess.run(args, check=False, capture_output=True, text=True, timeout=timeout)
        return cp.returncode, cp.stdout.strip()
    except Exception:
        return 99, ""


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def atomic_write(path: Path, text: str, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def unit(name: str) -> dict[str, Any]:
    _, active = run(["systemctl", "is-active", name])
    _, enabled = run(["systemctl", "is-enabled", name])
    return {
        "active": active == "active",
        "active_state": active or "unknown",
        "enabled": enabled == "enabled",
        "enabled_state": enabled or "unknown",
    }


def http(url: str, expected: set[str] | None = None) -> dict[str, Any]:
    expected = expected or {"200"}
    rc, code = run(["curl", "-sS", "-o", "/dev/null", "-w", "%{http_code}", "--connect-timeout", "2", "--max-time", "5", url])
    return {"ok": rc == 0 and code in expected, "status": int(code) if code.isdigit() else None}


def container(name: str) -> dict[str, Any]:
    rc, state = run(["docker", "inspect", "--format", "{{.State.Status}}", name])
    return {"active": rc == 0 and state == "running", "active_state": state or "unavailable"}


def lane_state(repo: Path) -> tuple[dict[str, Any], list[str]]:
    policy = load_json(repo / "governance/lane_access_policy.json")
    if not isinstance(policy, dict):
        return ({"connected": False, "registered": 0, "open": 0, "all_open": False, "items": []}, [])
    lane_map = policy.get("lanes", {}) if isinstance(policy.get("lanes"), dict) else {}
    items = []
    for slug, state in lane_map.items():
        state = state if isinstance(state, dict) else {}
        items.append({
            "slug": slug,
            "name": slug.replace("_", " ").title(),
            "internal_work_open": bool(state.get("internal_work_open")),
            "scheduler_eligible": bool(state.get("scheduler_eligible")),
            "external_readiness": "separate_founder_gate",
        })
    opened = sum(1 for item in items if item["internal_work_open"] and item["scheduler_eligible"])
    holds = [str(x) for x in policy.get("founder_held_external_classes", []) if str(x).strip()]
    return ({
        "connected": True,
        "governing_name": policy.get("governing_name", "RADAH MEMSHALAH — רָדָה מֶמְשָׁלָה"),
        "registered": len(items),
        "open": opened,
        "all_open": bool(items) and opened == len(items),
        "items": items,
    }, holds)


def revenue_state(db_path: Path) -> dict[str, Any]:
    empty = {
        "connected": False,
        "constraint": "REVENUE_RUNTIME_UNAVAILABLE",
        "active_experiment_count": 0,
        "experiments": [],
        "totals": {"visitors": None, "clicks": None, "purchases": None, "revenue_cents": None},
    }
    if not db_path.is_file():
        return empty
    try:
        db = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=5)
        db.row_factory = sqlite3.Row
        rows = db.execute(
            """SELECT id,name,product_id,target_url,status,winner,activated_at,decided_at,created_at
               FROM experiments
               ORDER BY COALESCE(activated_at,created_at) DESC"""
        ).fetchall()
        experiments = []
        totals = {"visitors": 0, "clicks": 0, "purchases": 0, "revenue_cents": 0}
        for row in rows:
            variants: dict[str, Any] = {}
            for variant in ("control", "treatment"):
                visitors = int(db.execute(
                    "SELECT COUNT(DISTINCT visitor_id) FROM events WHERE experiment_id=? AND variant=? AND event_type='impression'",
                    (row["id"], variant),
                ).fetchone()[0] or 0)
                clicks = int(db.execute(
                    "SELECT COUNT(DISTINCT visitor_id) FROM events WHERE experiment_id=? AND variant=? AND event_type='click'",
                    (row["id"], variant),
                ).fetchone()[0] or 0)
                purchases = int(db.execute(
                    "SELECT COUNT(DISTINCT visitor_id) FROM events WHERE experiment_id=? AND variant=? AND event_type='purchase'",
                    (row["id"], variant),
                ).fetchone()[0] or 0)
                revenue_cents = int(db.execute(
                    "SELECT COALESCE(SUM(revenue_cents),0) FROM events WHERE experiment_id=? AND variant=? AND event_type='purchase'",
                    (row["id"], variant),
                ).fetchone()[0] or 0)
                variants[variant] = {"visitors": visitors, "clicks": clicks, "purchases": purchases, "revenue_cents": revenue_cents}
                totals["visitors"] += visitors
                totals["clicks"] += clicks
                totals["purchases"] += purchases
                totals["revenue_cents"] += revenue_cents
            experiments.append({
                "id": row["id"], "name": row["name"], "product_id": row["product_id"], "target_url": row["target_url"],
                "status": row["status"], "winner": row["winner"], "activated_at": row["activated_at"],
                "decided_at": row["decided_at"], "variants": variants,
            })
        db.close()
    except Exception as exc:
        return {**empty, "error": type(exc).__name__}

    active = [item for item in experiments if item["status"] == "active"]
    if not active:
        constraint = "NO_ACTIVE_EXPERIMENT"
    elif totals["visitors"] == 0:
        constraint = "QUALIFIED_TRAFFIC"
    elif totals["clicks"] == 0:
        constraint = "OFFER_ENGAGEMENT"
    elif totals["purchases"] == 0:
        constraint = "PURCHASE_CONVERSION"
    elif any(item["status"] == "promoted" for item in experiments):
        constraint = "COMPOUND_WINNER"
    else:
        constraint = "STATISTICAL_EVIDENCE"
    return {"connected": True, "constraint": constraint, "active_experiment_count": len(active), "experiments": experiments, "totals": totals}


def autopilot_state(root: Path) -> dict[str, Any]:
    state = load_json(root / "autopilot/state.json")
    timer = unit("dominion-radah-autopilot.timer")
    if not isinstance(state, dict):
        return {"connected": False, "timer": timer, "cycles": None, "lanes_touched": None, "lanes_progressed": None}
    lanes = state.get("lanes", {}) if isinstance(state.get("lanes"), dict) else {}
    progressed = sum(1 for value in lanes.values() if isinstance(value, dict) and value.get("last_progress_at"))
    return {
        "connected": True,
        "timer": timer,
        "cycles": int(state.get("cycles", 0) or 0),
        "lanes_touched": len(lanes),
        "lanes_progressed": progressed,
        "lane_state": lanes,
    }


def receipt_index(root: Path, limit: int = 12) -> list[dict[str, Any]]:
    files: list[Path] = []
    try:
        files = [p for p in root.rglob("*.json") if p.is_file() and "receipts" in p.parts]
    except OSError:
        return []
    safe: list[tuple[float, Path]] = []
    for path in files:
        try:
            safe.append((path.stat().st_mtime, path))
        except OSError:
            continue
    safe.sort(key=lambda pair: pair[0], reverse=True)
    result = []
    for mtime, path in safe[:limit]:
        try:
            rel = path.relative_to(root)
            source = "/".join(rel.parts[:-2]) or rel.parts[0]
        except Exception:
            source = "runtime"
        result.append({
            "source": source,
            "name": path.name,
            "observed_at": datetime.fromtimestamp(mtime, timezone.utc).isoformat(),
        })
    return result


def founder_holds(repo: Path, lane_holds: list[str]) -> list[str]:
    holds = set(lane_holds)
    revenue = load_json(repo / "governance/revenue_execution_policy.json")
    if isinstance(revenue, dict):
        actions = revenue.get("automatic_external_actions", {})
        if isinstance(actions, dict):
            holds.update(str(key) for key, enabled in actions.items() if enabled is False)
    autopilot = load_json(repo / "governance/radah_memshalah_autopilot_policy.json")
    if isinstance(autopilot, dict):
        holds.update(str(x) for x in autopilot.get("held_external_prefixes", []) if str(x).strip())
    return sorted(holds)


def build_state(repo: Path, root: Path) -> dict[str, Any]:
    rc, sha = run(["git", "-C", str(repo), "rev-parse", "HEAD"])
    lanes, lane_holds = lane_state(repo)
    return {
        "schema": "dominion-command-center-runtime-state-v2",
        "observed_at": now_iso(),
        "release_sha": sha if rc == 0 else None,
        "systems": {
            "command_center": http("http://127.0.0.1:8091/health"),
            "obsidian": container("obsidian-remote"),
            "revenue_runtime": unit("dominion-revenue-runtime.service"),
            "revenue_evaluator": unit("dominion-revenue-evaluator.timer"),
            "radah_autopilot": unit("dominion-radah-autopilot.timer"),
            "buddy": unit("dominion-buddy-web.service"),
            "n8n": http("http://127.0.0.1:5678/healthz"),
            "conductor": http("http://127.0.0.1:5060/health"),
            "alpha_engine": http("http://127.0.0.1:8787/health"),
            "dominion_web": http("http://127.0.0.1:8090/"),
            "wix_agent": http("http://127.0.0.1:8082/ready"),
        },
        "lanes": lanes,
        "autopilot": autopilot_state(root),
        "revenue": revenue_state(root / "revenue-runtime/revenue.db"),
        "founder_holds": founder_holds(repo, lane_holds),
        "latest_receipts": receipt_index(root),
    }


def daily_markdown(state: dict[str, Any]) -> str:
    lanes = state["lanes"]
    revenue = state["revenue"]
    totals = revenue["totals"]
    autopilot = state["autopilot"]
    lines = [
        "---", "cssclasses:", "  - dominion-command-center", "aliases:", "  - Dominion Live Daily State", "---", "",
        '<div class="dominion-shell">', "", "# Live Daily State", "",
        f"**Observed:** `{state['observed_at']}`  ",
        f"**Release:** `{state.get('release_sha') or 'unavailable'}`  ",
        f"**Lane access:** **{lanes['open']} / {lanes['registered']} OPEN**  ",
        f"**Revenue constraint:** **{revenue['constraint']}**  ", "",
        "> Current production state requires timestamped runtime receipts.", "",
        "## Revenue Work Plane", "",
        f"- Active experiments: **{revenue['active_experiment_count']}**",
        f"- Real visitors: **{totals['visitors'] if totals['visitors'] is not None else 'unavailable'}**",
        f"- Clicks: **{totals['clicks'] if totals['clicks'] is not None else 'unavailable'}**",
        f"- Paid purchases: **{totals['purchases'] if totals['purchases'] is not None else 'unavailable'}**",
        (f"- Attributed revenue: **${totals['revenue_cents']/100:,.2f}**" if totals['revenue_cents'] is not None else "- Attributed revenue: **unavailable**"), "",
    ]
    for exp in revenue.get("experiments", []):
        lines += [f"### {exp['name']}", f"- Experiment: `{exp['id']}`", f"- Status: **{exp['status']}**", f"- Product: `{exp['product_id']}`", f"- Winner: **{exp.get('winner') or 'not decided'}**", ""]
    lines += [
        "## RADAH MEMSHALAH Work Plane", "",
        f"- Autopilot connected: **{autopilot.get('connected', False)}**",
        f"- Autopilot timer active: **{autopilot.get('timer', {}).get('active', False)}**",
        f"- Cycles recorded: **{autopilot.get('cycles')}**",
        f"- Lanes touched: **{autopilot.get('lanes_touched')}**",
        f"- Lanes with recorded progress: **{autopilot.get('lanes_progressed')}**", "",
        "## Core Runtime", "",
    ]
    for name, status in state.get("systems", {}).items():
        if isinstance(status, dict):
            ok = status.get("active") if "active" in status else status.get("ok")
            lines.append(f"- {name}: **{'ONLINE' if ok else 'NOT VERIFIED'}**")
    lines += ["", "## Founder-Held External Effects", ""]
    lines += [f"- `{hold}`" for hold in state.get("founder_holds", [])]
    lines += ["", "## Latest Runtime / Build Receipts", ""]
    lines += [f"- `{item['source']}` · `{item['name']}` · `{item['observed_at']}`" for item in state.get("latest_receipts", [])]
    lines += ["", "</div>", ""]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default=str(Path.home() / "dominion-ops"))
    parser.add_argument("--dominion-root", default=str(Path.home() / ".dominion"))
    parser.add_argument("--output", default=str(Path.home() / ".dominion/command-center/runtime-state.json"))
    parser.add_argument("--daily-state", default="")
    args = parser.parse_args()
    repo, root = Path(args.repo), Path(args.dominion_root)
    state = build_state(repo, root)
    atomic_write(Path(args.output), json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    if args.daily_state:
        atomic_write(Path(args.daily_state), daily_markdown(state), 0o600)
    lanes, revenue = state["lanes"], state["revenue"]
    print(f"COMMAND_CENTER_STATE=PASS lanes={lanes['open']}/{lanes['registered']} revenue_connected={str(revenue['connected']).lower()} constraint={revenue['constraint']} receipts={len(state['latest_receipts'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
