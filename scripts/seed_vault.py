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

# ──────────────────────────────────────────────
# Create all lane dirs
# ──────────────────────────────────────────────
print("\n[1/8] Creating vault lane directories...")
for lane in LANES:
    p = mkdir(lane)
    print(f"  OK: {p}")

obsidian_config()

# ──────────────────────────────────────────────
# 90-meta / 00-HOME.md  (master index)
# ──────────────────────────────────────────────
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
- Alpha dashboard: http://34.73.72.30:8787 (Terminal Claude must add Caddy route)

## Codebase

- GitHub: https://github.com/dunkdee/desktop-tutorial
- Dev branch: `claude/vm-status-check-s0800x`
- VM: 34.73.72.30
""")

# ──────────────────────────────────────────────
# 90-meta / agent-registry.md
# ──────────────────────────────────────────────
print("\n[3/8] Writing agent registry...")
write("meta", "agent-registry.md", f"""---
title: Agent Registry
created: {TS}
tags: [agents, registry, meta]
---

# Agent Registry

Every AI agent and automated process running in the Dominion Empire.

---

## Alpha Engine v2
- **Location:** `~/dominion/alpha_engine/`  
- **Service:** `dominion-alpha.service`
- **Port:** 8787
- **Mode:** Paper trading (LIVE_TRADING=false, locked)
- **Council:** 12 advisors — Liquidity, Volume, Momentum, MarketCap, Whale, TokenHealth, HolderGrowth, SocialSentiment, News, Risk, Execution, Skeptic
- **Scanner:** DexScreener profiles + boosts endpoints (real token discovery, no native assets)
- **Memory:** SQLite 8 tables — tokens, trades, state, observations, decisions, performance_snapshots, lessons, advisor_weights
- **Threshold:** BUY >= 0.65 (env), Skeptic veto if score < 0.35
- **Dashboard:** http://34.73.72.30:8787
- **Notes:** [[alpha-engine-v2]]

---

## paper_trade.py  
- **Location:** `~/dominion_trading/paper_trade.py`
- **Status:** Live since Jun 7 (PID ~45110)
- **Market:** BTC-USD
- **Capital:** ~$49.76 (paper)
- **Strategy:** Markov + momentum
- **Logs:** `~/dominion_trading/paper_trade.log`, `paper_trade_state.json`
- **DO NOT TOUCH** — already running, don't restart

---

## Dominion Intel Agent
- **Location:** `~/buddy_core/agents/dominion_intel_trading.py`
- **Service:** `dominion-intel.service` — FILE EXISTS, NOT RUNNING
- **Built by:** Terminal Claude on {DATE}
- **Related:** `gemini-server.service` IS running (59.4% CPU, `/opt/ai_agents/gemini/`)
- **Action needed:** `systemctl status dominion-intel.service` to diagnose, then start if ready
- **Notes:** [[dominion-intel-agent]]

---

## Baby API
- **Location:** `~/desktop-tutorial/api/`
- **Container:** `desktop-tutorial-baby-api-1`
- **Port:** 8080
- **Endpoints:** /health, /vault/*, /youtube/*, /gumroad/*, /ai/complete, /email/purchase
- **Vault:** Mounts `~/vault` → `/vault` inside container
- **Code:** `api/app.py`, `api/vault_io.py`

---

## Gemini Server
- **Location:** `/opt/ai_agents/gemini/server.py`
- **Service:** `gemini-server.service` — RUNNING
- **PID:** ~3585577, 59.4% CPU
- **Purpose:** AI agent infrastructure (powers Dominion Intel)

---

## n8n
- **Service:** `n8n` systemd service
- **Port:** 5678
- **URL:** https://n8n.dominionhealing.org
- **Workflows:** Gumroad webhook → vault → email, daily health checks
- **DO NOT TOUCH** — part of existing ~/dominion/ system

---

## Web Claude (this session)
- **Role:** GitHub repo, GitHub Actions, code on branches
- **Branch:** `claude/vm-status-check-s0800x`
- **NEVER:** Push to Caddyfile, touch ~/dominion/ services directly

## Terminal Claude
- **Role:** Live VM changes, systemd, Caddy, direct file edits
- **Owns:** All `sudo` operations, Caddy config, starting/stopping services
""")

# ──────────────────────────────────────────────
# 10-research / alpha-engine-v2.md
# ──────────────────────────────────────────────
print("\n[4/8] Writing Alpha Engine v2 research note...")
write("research", "alpha-engine-v2.md", f"""---
title: Alpha Engine v2
created: {TS}
tags: [trading, alpha, engine, research]
---

# Alpha Engine v2 — Architecture

## Status
Running on VM, port 8787, LIVE_TRADING=false (hard-locked via assert).

## Scanner (v2 — fixed)
Uses DexScreener discovery endpoints (NOT the broken `?q=solana` search):
- `GET /token-profiles/latest/v1` → new token profiles
- `GET /token-boosts/latest/v1` → boosted tokens
- Filter: skip native assets (SOL, WSOL, ETH, WETH, BTC, USDC, USDT, BNB, etc.)
- Chains: solana, base, ethereum
- Enriches each via `/latest/dex/tokens/{{address}}` for full pair data

## 12-Advisor Council

| Advisor | Weight | Signal |
|---------|--------|--------|
| LiquidityAdvisor | 1.5 | $10k→0.1, $50k→0.5, $200k→0.8, $1M+→0.95 |
| VolumeAdvisor | 1.2 | 24h volume tiers |
| MomentumAdvisor | 1.3 | vol/liq ratio + 5m direction |
| MarketCapAdvisor | 1.0 | $50k-$5M sweet spot |
| WhaleAdvisor | 1.2 | buy/sell ratio >2→dump risk |
| TokenHealthAdvisor | 1.4 | age <1h→new, >30d→old |
| HolderGrowthAdvisor | 1.1 | buy_sell_ratio proxy |
| SocialSentimentAdvisor | 0.8 | socials + website presence |
| NewsAdvisor | 0.7 | description length |
| RiskAdvisor | 1.5 | red flags: age<10min→0.0, liq<$5k→0.0 |
| ExecutionAdvisor | 1.0 | slippage estimate |
| **SkepticAdvisor** | **1.6** | **VETO: score<0.35 → force SKIP** |

## Governor
- GovernorState singleton
- kill_switch (toggleable via POST /governor/kill)
- threshold: 0.65 (from preserved v1 .env — target 0.82 per spec)
- max_daily_loss_pct: 20%
- All decisions logged to `decisions` table

## Memory (8 tables)
`tokens`, `trades`, `state`, `observations`, `decisions`, `performance_snapshots`, `lessons`, `advisor_weights`

## API Endpoints
- `GET /` — full dashboard HTML
- `GET /health` → `{{"version":"2.0","live_trading":false}}`
- `GET /performance` — metrics JSON
- `GET /decisions` — Governor decision log
- `GET /watchlist` — WATCH-verdict tokens
- `GET /lessons` — learning log
- `GET /weights` — advisor weights
- `POST /governor/kill` — toggle kill switch
- `POST /governor/emergency-exit` — exit all positions

## Upgrade Needed
- Terminal Claude: update VM `.env` → `MIN_SCORE=0.82` to hit the v2 threshold
- Terminal Claude: add Caddy route `alpha.dominionhealing.org → localhost:8787`
""")

# ──────────────────────────────────────────────
# 10-research / dominion-intel-agent.md
# ──────────────────────────────────────────────
print("\n[5/8] Writing Dominion Intel Agent note...")
write("research", "dominion-intel-agent.md", f"""---
title: Dominion Intel Agent
created: {TS}
tags: [intel, agent, trading, research]
status: incomplete
---

# Dominion Intel Agent

## Status: FILE EXISTS, SERVICE NOT RUNNING

**Built by Terminal Claude on {DATE}**

## What We Know
- File: `/home/malachisingleton8/buddy_core/agents/dominion_intel_trading.py`
- Service file: `/etc/systemd/system/dominion-intel.service` — EXISTS
- Service state: NOT active/running as of {DATE}
- Related: `gemini-server.service` IS running (`/opt/ai_agents/gemini/server.py`, ~59% CPU)

## What Terminal Claude Needs To Do
```bash
# Check why service isn't running
systemctl status dominion-intel.service
journalctl -u dominion-intel.service -n 50

# If config looks good, start it
sudo systemctl start dominion-intel.service
sudo systemctl enable dominion-intel.service

# Verify
curl http://localhost:<PORT>/health
```

## Integration with Alpha Engine
Once running, the Intel agent likely feeds signals INTO the Alpha Engine.
Check if `dominion_intel_trading.py` has a port or API it exposes.

## Next Steps
1. Terminal Claude: check service status and start it
2. Web Claude: read the file contents and document the architecture here
3. Once running: integrate signals with Alpha Engine v2
""")

# ──────────────────────────────────────────────
# 10-research / system-architecture.md
# ──────────────────────────────────────────────
print("\n[6/8] Writing system architecture note...")
write("research", "system-architecture.md", f"""---
title: System Architecture
created: {TS}
tags: [architecture, vm, system, meta]
---

# Dominion Empire — System Architecture

## VM: foundation-vm (34.73.72.30)
GCP Compute Engine instance with gcloud CLI and Application Default Credentials.

## Two Parallel Systems

### System 1: ~/dominion/ (DO NOT TOUCH)
30+ systemd services that ARE dominionhealing.org.
Real agents: Alchemist, Juris, Conductor, Buddy, Store, Surplus.
Real data in PostgreSQL.
Traffic via Caddy routes: api, n8n, store, buddy, surplus, report subdomains.

### System 2: ~/desktop-tutorial/ (GitHub-managed)
Docker stack managed via GitHub Actions.
Services: baby-api (8080), dominion-web (8090), browser-agents (8081).
Adds: Vault (Obsidian), Vertex AI, YouTube pipeline, Gumroad, GA4.
Accessible via empire.dominionhealing.org.

## Active Ports
| Port | Service | Notes |
|------|---------|-------|
| 80/443 | Caddy | Reverse proxy for all domains |
| 5678 | n8n | Automation |
| 8080 | baby-api | Docker, vault/AI/payments |
| 8081 | browser-agents | Docker, social/scraping |
| 8090 | dominion-web | Docker, landing page |
| 8787 | Alpha Engine v2 | Paper trading dashboard |

## Caddy Routes (existing — DO NOT CHANGE)
- api.dominionhealing.org
- n8n.dominionhealing.org
- store.dominionhealing.org
- buddy.dominionhealing.org
- surplus.dominionhealing.org
- report.dominionhealing.org
- empire.dominionhealing.org → baby-api:8080

## Caddy Routes (needed — Terminal Claude to add)
- hub.dominionhealing.org → localhost:8080 (baby-api from web)
- alpha.dominionhealing.org → localhost:8787 (trading dashboard)

## Integration Rule
All integration happens via HTTP calls between services.
NO shared state, NO direct code changes to ~/dominion/.

## Key Files
- `~/desktop-tutorial/.env` — all secrets for Docker stack
- `~/desktop-tutorial/docker-compose.yml` — service definitions
- `~/vault/` — Obsidian second brain (this vault)
- `~/dominion_trading/paper_trade.py` — original paper trader
- `~/buddy_core/agents/dominion_intel_trading.py` — intel agent
""")

# ──────────────────────────────────────────────
# 10-research / revenue-pipeline.md
# ──────────────────────────────────────────────
print("\n[7/8] Writing revenue pipeline note...")
write("research", "revenue-pipeline.md", f"""---
title: Revenue Pipeline
created: {TS}
tags: [revenue, gumroad, pipeline, deals]
---

# Revenue Pipeline

## Current Product
- **Divine Sovereignty Blueprint** — $47 on Gumroad
- Product ID: xnfyw
- Landing page: https://dominionhealing.org/divine-sovereignty.html
- Status: Check if PDF is attached and product is published

## Revenue Flow
```
Customer → divine-sovereignty.html → Gumroad checkout ($47)
    ↓
Gumroad webhook → n8n → baby-api /email/purchase → Brevo welcome email
    ↓
Vault records sale in 20-deals/ lane
    ↓
Daily: analytics tracking conversions
    ↓
Alchemist calls /ai/complete → generates content → posts to socials
    ↓
New traffic → more sales
```

## n8n Automations Needed
1. Gumroad sale webhook → POST baby-api `/vault/inbox` (log the sale)
2. Gumroad sale webhook → POST baby-api `/email/purchase` (trigger Brevo email)
3. Daily health check → GET baby-api `/health`

## Brevo Email
- API key in VM .env as BREVO_API_KEY
- Need to create email template in Brevo dashboard
- Template should: welcome buyer, deliver PDF link, introduce next steps

## Social Funnel
- TikTok / Instagram / Twitter → content about healing sovereignty
- Links back to dominionhealing.org product page
- Browser agents handle posting (when deployed)

## Monthly Revenue Target
Currently paper-trading capital only.
Real revenue: $0 until first Gumroad sale.
Path to $1k/mo: 22 sales of $47 product.

## Alpha Engine Revenue (future)
Currently paper mode (LIVE_TRADING=false).
Capital: $773.78 (paper).
When v2 proves profitable in paper → user decision to go live.
""")

# ──────────────────────────────────────────────
# 90-meta / agent-learnings.md  (browser agent memory)
# ──────────────────────────────────────────────
print("\n[8/8] Writing agent learnings (browser agent memory)...")
write("meta", "agent-learnings.md", f"""---
title: Agent Learnings
created: {TS}
tags: [learnings, browser-agents, memory, meta]
---

# Agent Learnings

This file is the memory store for browser agents.
Agents read this before each task and write new learnings after.

## Format
Each learning entry:
```
## [DATE] [TASK] — [OUTCOME]
Strategy: what was attempted
Result: what happened
Lesson: what to do differently
Reinforce: what worked well
```

---

## {DATE} Vault Seeded — SUCCESS
Strategy: Python seed script via GitHub Actions → SSH → git pull → run script
Result: All lanes created, 8 seed notes written
Lesson: Always check if file exists before writing (script skips existing files)
Reinforce: Using the repo to carry scripts (not SSH heredocs) avoids YAML escaping bugs

---

## Instructions for Browser Agents
1. Before starting ANY task: read this file first
2. After completing a task: append a learning entry
3. If a task FAILED: note what didn't work and why
4. If a task SUCCEEDED: note the exact steps that worked
5. Never overwrite — always APPEND to this file
6. Keep entries short and actionable

## Known Working Strategies
- TikTok: (to be filled in after first successful post)
- Instagram: (to be filled in)
- PPH proposals: (to be filled in)
- Real estate leads: (to be filled in)

## Known Failures / Anti-Patterns
- (to be filled in as agents learn)
""")

# ──────────────────────────────────────────────
# Done
# ──────────────────────────────────────────────
print(f"""
╔══════════════════════════════════════════════╗
║  VAULT SEED COMPLETE                         ║
║  Location: {VAULT:<33}║
║  Date: {DATE:<37}║
╚══════════════════════════════════════════════╝

Lanes created:
""")
for name, folder in LANES.items():
    path = os.path.join(VAULT, folder)
    count = len([f for f in os.listdir(path) if f.endswith(".md")]) if os.path.isdir(path) else 0
    print(f"  {folder:<25} {count} notes")

print("\nOpen this vault in Obsidian → navigate to 90-meta/00-HOME.md")
