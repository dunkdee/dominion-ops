#!/usr/bin/env python3
"""Seed the Obsidian vault with notes about the entire Dominion Empire system."""
import os
from datetime import datetime, timezone

VAULT = os.path.expanduser(os.environ.get("VAULT_PATH", "~/vault"))
NOW = datetime.now(timezone.utc)
DATE = NOW.strftime("%Y-%m-%d")
TS = NOW.strftime("%Y-%m-%dT%H:%M:%SZ")

LANES = {
    "inbox":    "00-inbox",
    "research": "10-research",
    "deals":    "20-deals",
    "surplus":  "30-surplus-cases",
    "manual":   "40-manual",
    "meta":     "90-meta",
    "health":   "_health",
}

def mkdir(lane):
    path = os.path.join(VAULT, LANES.get(lane, lane))
    os.makedirs(path, exist_ok=True)
    return path

def write(lane, filename, content):
    lane_dir = mkdir(lane)
    path = os.path.join(lane_dir, filename)
    if os.path.exists(path):
        print(f"  SKIP (exists): {path}")
        return path
    with open(path, "w") as f:
        f.write(content)
    print(f"  WROTE: {path}")
    return path

def obsidian_config():
    obs_dir = os.path.join(VAULT, ".obsidian")
    os.makedirs(obs_dir, exist_ok=True)
    app_json = os.path.join(obs_dir, "app.json")
    if not os.path.exists(app_json):
        with open(app_json, "w") as f:
            f.write('{"defaultViewMode":"preview","livePreview":true}\n')
        print(f"  WROTE: {app_json}")

print("\n[1/8] Creating vault lane directories...")
for lane in LANES:
    p = mkdir(lane)
    print(f"  OK: {p}")
obsidian_config()

print("\n[2/8] Writing HOME index...")
write("meta", "00-HOME.md", f"""---
title: Dominion Empire — HOME
created: {TS}
tags: [home, index, meta]
---

# Dominion Empire — Master Index

> The true home and nervous system of the entire operation.
> Last seeded: {DATE}

## Live Systems

| System | Port | Status | Notes |
|--------|------|--------|-------|
| Alpha Engine v2 | 8787 | RUNNING | Paper trading, 12-advisor council |
| Baby API | 8080 | RUNNING | Vault, YouTube, Gumroad, AI endpoints |
| Dominion Web | 8090 | RUNNING | Empire landing page |
| n8n | 5678 | RUNNING | Automation workflows |
| Gemini Server | — | RUNNING | AI agent infrastructure |
| paper_trade.py | — | RUNNING | BTC-USD paper trader (PID ~45110) |
| Dominion Intel Agent | — | FILE EXISTS, not started | See [[dominion-intel-agent]] |

## Vault Lanes

- [[00-inbox/]] — Incoming items to process
- [[10-research/]] — Deep research and analysis
- [[20-deals/]] — Revenue deals and sales
- [[30-surplus-cases/]] — Surplus case management
- [[40-manual/]] — Manual notes and guides
- [[90-meta/]] — System meta, this HOME note

## Key Research Notes

- [[alpha-engine-v2]] — Trading engine architecture
- [[dominion-intel-agent]] — AI intel agent status
- [[system-architecture]] — Full VM layout
- [[revenue-pipeline]] — Revenue flow from product to cash

## Empire Domain

- Main site: https://dominionhealing.org
- Empire hub: https://empire.dominionhealing.org
- n8n: https://n8n.dominionhealing.org
- Alpha dashboard: http://34.73.72.30:8787

## Codebase

- GitHub: https://github.com/dunkdee/dominion-ops
- VM: 34.73.72.30
""")

print("\n[3/8] Writing agent registry...")
write("meta", "agent-registry.md", f"""---
title: Agent Registry
created: {TS}
tags: [agents, registry, meta]
---

# Agent Registry

## Alpha Engine v2
- **Service:** dominion-alpha.service | **Port:** 8787 | **Mode:** Paper (LIVE_TRADING=false)
- **Council:** 12 advisors (Liquidity, Volume, Momentum, MarketCap, Whale, TokenHealth,
  HolderGrowth, SocialSentiment, News, Risk, Execution, Skeptic)
- **Scanner:** DexScreener profiles+boosts (real discovery, filters native assets)
- **Threshold:** BUY >= 0.65 (env) | Skeptic veto < 0.35
- **Dashboard:** http://34.73.72.30:8787

## paper_trade.py
- **Location:** ~/dominion_trading/paper_trade.py | **PID:** ~45110
- **Market:** BTC-USD | **Capital:** ~$49.76 paper | **Running since:** Jun 7
- DO NOT TOUCH

## Dominion Intel Agent
- **Location:** ~/buddy_core/agents/dominion_intel_trading.py
- **Service:** dominion-intel.service — FILE EXISTS, NOT RUNNING
- **Related:** gemini-server.service IS running (/opt/ai_agents/gemini/)
- **Action:** Terminal Claude must start the service

## Baby API
- **Container:** dominion-ops-baby-api-1 | **Port:** 8080
- **Vault:** mounts ~/vault → /vault inside container

## Gemini Server
- **Location:** /opt/ai_agents/gemini/server.py | **Service:** gemini-server.service RUNNING

## Browser Agents
- **Container:** browser-agents | **Port:** 8081 | Social posting + PPH proposals

## Web Claude (GitHub-only)
- Branch: claude/vm-status-check-s0800x
- NEVER: touch Caddyfile, touch ~/dominion/ services

## Terminal Claude (VM-only)
- Owns: sudo, Caddy, systemd, direct file edits
""")

print("\n[4/8] Writing Alpha Engine v2 note...")
write("research", "alpha-engine-v2.md", f"""---
title: Alpha Engine v2
created: {TS}
tags: [trading, alpha, engine]
---

# Alpha Engine v2

## Status: RUNNING (port 8787, paper mode)

## Scanner (v2)
DexScreener discovery: /token-profiles/latest/v1 + /token-boosts/latest/v1
Filters native assets. Enriches via /latest/dex/tokens/{{address}}.

## 12-Advisor Council
Liquidity(1.5), Volume(1.2), Momentum(1.3), MarketCap(1.0), Whale(1.2),
TokenHealth(1.4), HolderGrowth(1.1), SocialSentiment(0.8), News(0.7),
Risk(1.5), Execution(1.0), **Skeptic(1.6) — VETO if score<0.35**

## Governor
Threshold: 0.65 (from .env). kill_switch toggle: POST /governor/kill.
All decisions logged to decisions table.

## Memory: 8 SQLite tables
tokens, trades, state, observations, decisions, performance_snapshots, lessons, advisor_weights

## API
/ dashboard | /health | /performance | /decisions | /watchlist | /lessons | /weights
POST /governor/kill | POST /governor/emergency-exit

## Pending
- Terminal Claude: set MIN_SCORE=0.82 in VM .env
- Terminal Claude: add alpha.dominionhealing.org → localhost:8787 in Caddy
""")

print("\n[5/8] Writing Dominion Intel Agent note...")
write("research", "dominion-intel-agent.md", f"""---
title: Dominion Intel Agent
created: {TS}
tags: [intel, agent, trading]
status: incomplete
---

# Dominion Intel Agent

## Status: FILE EXISTS, SERVICE NOT RUNNING

Built by Terminal Claude on {DATE}.

## Known
- File: ~/buddy_core/agents/dominion_intel_trading.py
- Service: /etc/systemd/system/dominion-intel.service (exists but not active)
- gemini-server.service IS running (~59% CPU at /opt/ai_agents/gemini/)

## Terminal Claude Actions
```bash
systemctl status dominion-intel.service
journalctl -u dominion-intel.service -n 50
sudo systemctl start dominion-intel.service
sudo systemctl enable dominion-intel.service
```

## Next
1. Start the service
2. Document the port/API it exposes here
3. Integrate signals with Alpha Engine v2
""")

print("\n[6/8] Writing system architecture note...")
write("research", "system-architecture.md", f"""---
title: System Architecture
created: {TS}
tags: [architecture, vm, system]
---

# System Architecture

## VM: 34.73.72.30 (GCP Compute Engine)

## System 1: ~/dominion/ (DO NOT TOUCH)
30+ systemd services. Agents: Alchemist, Juris, Conductor, Buddy, Store, Surplus.
PostgreSQL. Caddy routes: api, n8n, store, buddy, surplus, report, empire subdomains.

## System 2: ~/dominion-ops/ (GitHub-managed Docker)
baby-api:8080, dominion-web:8090, browser-agents:8081.
Vault at ~/vault mounted into baby-api container.

## All Active Ports
80/443 Caddy | 5678 n8n | 8080 baby-api | 8081 browser-agents
8090 dominion-web | 8787 Alpha Engine v2

## Caddy Routes Needed (Terminal Claude)
- hub.dominionhealing.org → localhost:8080
- alpha.dominionhealing.org → localhost:8787

## Rule: Integration via HTTP only. No shared state. No ~/dominion/ edits.
""")

print("\n[7/8] Writing revenue pipeline note...")
write("research", "revenue-pipeline.md", f"""---
title: Revenue Pipeline
created: {TS}
tags: [revenue, gumroad, deals]
---

# Revenue Pipeline

## Product: Divine Sovereignty Blueprint ($47)
Gumroad ID: xnfyw | Landing: https://dominionhealing.org/divine-sovereignty.html

## Flow
Gumroad sale → n8n webhook → baby-api /email/purchase → Brevo email
              → vault records in 20-deals/

## n8n Automations Needed
1. Gumroad webhook → POST /vault/inbox (log sale)
2. Gumroad webhook → POST /email/purchase (trigger Brevo)
3. Daily → GET /health

## Path to $1k/mo: 22 sales of $47

## Alpha Engine (future)
Paper mode now ($773.78 paper capital). User decides when to go live.
""")

print("\n[8/8] Writing agent learnings...")
write("meta", "agent-learnings.md", f"""---
title: Agent Learnings
created: {TS}
tags: [learnings, browser-agents, memory]
---

# Agent Learnings

Memory store for browser agents. Read before each task. Append after each task.

## Format
```
## [DATE] [TASK] — [OUTCOME]
Strategy: ...
Result: ...
Lesson: ...
Reinforce: ...
```

---

## {DATE} Vault Seeded — SUCCESS
Strategy: Python seed script in repo → SSH checkout → run
Result: All 7 lanes created, 6 research notes + HOME + registry + learnings written
Lesson: Repo-carried scripts avoid YAML/heredoc escaping bugs in GitHub Actions
Reinforce: Script skips existing files — safe to re-run

---

## Instructions
1. Read this file before any task
2. Append a learning entry after completion
3. Never overwrite — append only
4. Keep entries short and actionable

## Known Working
- (fill in after first successful social post)

## Known Failures
- (fill in as agents learn)
""")

print(f"""
╔{('═'*46)}╗
║  VAULT SEED COMPLETE{' '*27}║
║  Location: {VAULT:<37}║
║  Date: {DATE:<41}║
╚{('═'*46)}╝
""")
for name, folder in LANES.items():
    path = os.path.join(VAULT, folder)
    count = len([f for f in os.listdir(path) if f.endswith(".md")]) if os.path.isdir(path) else 0
    print(f"  {folder:<25} {count} notes")
print("\nOpen in Obsidian → 90-meta/00-HOME.md")
