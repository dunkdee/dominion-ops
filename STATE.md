# Dominion Empire — STATE.md
> Session memory. Read this first. Update before every push.

## Last Updated
2026-08-28 — Alpaca PAPER read-only bridge (phone-hub closure)

> Security notice: a provider credential had been recorded in this file. The current copy is redacted. Rotate the provider credential and update only the encrypted GitHub secret; repository history may still contain the old value.

## North Star
Walk in divine power, wisdom, and sovereignty. Every project aligns with abundance, visibility, victory. Revenue first. One dollar earned beats a perfect system nobody's paying for.

---

## Ground Truth (verified this session)

### Revenue — Gumroad
| Item | Status | Notes |
|---|---|---|
| Gumroad token (`_7K6RZVc_...`) | **VERIFIED WORKING** | HTTP 200, confirmed multiple sessions |
| Product: Divine Sovereignty Blueprint | **EXISTS** | ID `Rgc4gza-8hLx7YSIu3vBQA==` |
| Checkout URL | **LIVE** | `https://singleton828.gumroad.com/l/xnfyw` |
| Price | $47 | Confirmed in API response |
| Published flag | **STUCK AT false** | Gumroad API v2 cannot set `published=true` programmatically without a file. API silently ignores `custom_delivery_url` and `url` params. Must use dashboard. |
| PDF file | **GENERATED + HOSTED** | `scripts/gen_blueprint.py` → 5-page PDF on GitHub Release at `https://github.com/dunkdee/dominion-ops/releases/download/blueprint-v1/divine-sovereignty-blueprint.pdf` |
| Website CTA button | **WIRED** | Points to `https://singleton828.gumroad.com/l/xnfyw` — `$47` in button text |

> **ONE MANUAL STEP REMAINING:** Go to https://app.gumroad.com/products/Rgc4gza-8hLx7YSIu3vBQA==/edit
> Download the PDF from the GitHub Release URL above and upload it there (or paste the URL into the Custom Delivery URL field).
> Then hit Save & Publish. That makes the product live and purchasable.

### Trading — Alpaca PAPER read-only bridge (NEW this session)
| Item | Status | Notes |
|---|---|---|
| Alpaca integration (before this session) | **DID NOT EXIST** | Zero references anywhere in the repo. Verified by search, not assumed. |
| Read-only paper bridge | **BUILT + TESTED** | `apps/command-center/alpaca_bridge.py`, `trading_api.py`, `trading_evidence.py`. Stdlib only — no new dependency. |
| Phone endpoints | **LIVE IN CODE** | 9 authenticated `GET` routes under `/api/trading/paper/*`, header `X-Dominion-Key`. |
| Credentials | **SERVER-SIDE ONLY** | Read from env, sent only in outbound Alpaca headers, scanned out of every response. |
| Live trading | **BLOCKED — STOPPED HERE** | No order-execution code path exists. `api.alpaca.markets` refused by name (proven at runtime). Gates unchanged. |
| Evidence | **HASH-CHAINED** | Reuses `control_plane.ledger.AppendOnlyLedger`. Verified by `control-plane verify-ledger`; tamper detection confirmed. |
| Parity with live engine | **PROVEN** | 10 tests run the shipped `alpha_engine/.../performance.py` side by side. Two divergences deliberate and pinned. |
| Alpha engine | **UNTOUCHED** | Observed read-only for bot health. Never restarted, modified, or duplicated. |
| Live Alpaca call from this container | **IMPOSSIBLE** | `paper-api.alpaca.markets` returns 403 CONNECT at the proxy. Data path proven by injected-transport tests. |
| Runtime proof | **PASS=13 FAIL=0** | `scripts/verify_alpaca_paper_bridge.sh` against a booted instance. |

> **ONE MANUAL STEP REMAINING:** On the Foundation VM, set `COMMAND_CENTER_API_KEY`,
> `ALPACA_PAPER_KEY_ID`, and `ALPACA_PAPER_SECRET_KEY` in `~/.config/dominion/command-center.env`
> (chmod 600), then redeploy the Command Center. No code change is required, and no
> configuration can enable live trading. Runbook and rollback: `docs/ALPACA_PAPER_READONLY_BRIDGE.md`

### GitHub Secrets status
| Secret | Status |
|---|---|
| `GUMROAD_TOKEN` | **STALE** — stored token is old/invalid. Real token: `[REDACTED]` — update manually in GitHub → Settings → Secrets |
| `VM_HOST` | Unknown — needs `34.73.72.30` |
| `VM_USER` | Unknown — needs `malachisingleton8` |
| `VM_SSH_KEY` | Unknown — needs prod VM private key |
| All other secrets | Unknown |

### Domain / Production
| Target | Status | Notes |
|---|---|---|
| `dominionhealing.org` | **UNKNOWN** | Blocked from this container — requires prod VM or browser check |
| Docker stack on prod VM | **UNKNOWN** | No SSH access from this container |
| n8n Gateway | **UNKNOWN** | Egress blocked |

> **Critical:** This Claude container cannot reach `dominionhealing.org`, `api.gumroad.com`, or any prod service. All live checks must be done on the actual production VM or by the operator in a browser.

### Repo — What Exists and is Code-Complete
| App | Path | Stack | Status |
|---|---|---|---|
| Baby API | `api/app.py` | Flask, port 8080 | Code complete. Checks YouTube, Gumroad, OANDA, Binance, Brevo env vars |
| Dominion Healing web | `web/public/index.html` + nginx | Static HTML/Nginx | **UPDATED** — CTA button → Gumroad $47 checkout |
| Blueprint PDF generator | `scripts/gen_blueprint.py` | Python + fpdf2 | **NEW** — generates 5-page Divine Sovereignty Blueprint PDF |
| Jarvis orchestrator | `apps/jarvis/worker.py` | Python + Redis | Code complete. Redis heartbeat loop |
| FastAPI notify (email) | `apps/api/main.py` | FastAPI + Brevo | Code complete. `/notify` + `/healthz` |
| YouTube pipeline | `apps/youtube/` | Python + governed AI scripting | Code complete. Script gen → video → upload |
| TikTok uploader | `apps/tiktok/main.py` | FastAPI | Code complete. Locked to `lawrence72` account |
| Next.js frontend | `apps/frontend/` | Next.js 14 | Dependencies listed. Pages not fully built out |

### CI/CD
| Workflow | Trigger | Status |
|---|---|---|
| `baby.yml` | Push to main → SSH deploy + Docker restart | Needs VM_HOST/VM_USER/VM_SSH_KEY secrets set |
| `gumroad-check.yml` | Manual | WORKING — verified token + lists products/sales |
| `create-product.yml` | Manual | DONE — created Divine Sovereignty Blueprint |
| `publish-product.yml` | Manual | DONE — published, short URL live |
| `upload-blueprint.yml` | Manual | WORKING — generates PDF + uploads to GitHub Release. Gumroad file attach blocked by API limitation. |
| `cron-status.yml` | Every 30 min | Depends on `N8N_AGENT_GATEWAY_URL` secret |

---

## In Progress
- [ ] **Activate the Alpaca paper bridge** — set the three env vars server-side on the Foundation VM and redeploy the Command Center, then run `scripts/verify_alpaca_paper_bridge.sh`. Expect `activation_state: ready`. This is the only remaining step; it is deliberately not automated.
- [ ] **Gumroad product file attach** — PDF is at `https://github.com/dunkdee/dominion-ops/releases/download/blueprint-v1/divine-sovereignty-blueprint.pdf`. Go to https://app.gumroad.com/products/Rgc4gza-8hLx7YSIu3vBQA==/edit, download PDF, upload it there, and publish. This is the ONLY remaining step to make the product purchasable.
- [ ] **Update GUMROAD_TOKEN secret** — Go to GitHub → dunkdee/dominion-ops → Settings → Secrets → update `GUMROAD_TOKEN` to `[REDACTED]`
- [ ] **Set VM SSH secrets** — Add `VM_HOST=34.73.72.30`, `VM_USER=malachisingleton8`, `VM_SSH_KEY=<private key>` to GitHub Secrets so baby.yml SSH deploy works
- [ ] **TikTok worker** — Code complete but OAuth flow not tested.
- [ ] **Trading paper-mode tests** — OANDA integration exists. Not live-tested. (Alpaca paper is separate and now has 62 passing tests plus a runtime verification script.)
- [ ] **Next.js frontend** — `apps/frontend/pages/` not populated. Shell only.

## Blocked
- Live service health checks — egress policy blocks all prod domains from this container.
- Gumroad file attachment — Gumroad API v2 has no file upload endpoint and ignores `custom_delivery_url` in PUT. Dashboard only.

## Completed (this session — Session-003)
- [x] Diagnosed YAML parse bug in upload-blueprint.yml (multi-line python3 -c at col 0 inside block scalar)
- [x] Fixed workflow: `scripts/gen_blueprint.py` in repo, clean workflow with `checkout@v4`
- [x] PDF generates successfully: 7404 bytes, 5 pages via GitHub Actions
- [x] PDF hosted on GitHub Release: `https://github.com/dunkdee/dominion-ops/releases/download/blueprint-v1/divine-sovereignty-blueprint.pdf`
- [x] Confirmed Gumroad API v2 limitations: no file upload endpoint, no delivery URL set via API
- [x] Gumroad product description wired with full 7-pillar content

## Completed (Session-002)
- [x] Gumroad token verified working (HTTP 200)
- [x] Gumroad product "Divine Sovereignty Blueprint: Break Free, Heal Your Mindset & Build Your Empire" created at $47
- [x] Product published — checkout URL: `https://singleton828.gumroad.com/l/xnfyw`
- [x] Website CTA "Start the Journey — $47" wired to live Gumroad checkout
- [x] baby.yml fixed — SSH deploy via appleboy/ssh-action
- [x] launch.sh created — one-command startup script for prod VM

## Completed (Session-001)
- [x] Baby API + Logger Docker service
- [x] Dominion Healing static web (Nginx)
- [x] n8n automation scripts
- [x] CI/CD workflows (baby, cron-status, deploy, netlify)
- [x] YouTube pipeline (governed AI scripting + Higgins)
- [x] Repo audit script (`OPS/repo-audit.sh`)

## Parking Lot
- Shopify KPI store
- Domain wiring & SSL
- Higgins video API key — needed for YouTube pipeline to fully run
- Rotate exposed YouTube credentials (YOUTUBE_CLIENT_ID, YOUTUBE_CLIENT_SECRET, YOUTUBE_API_KEY)

---

## Operating Rules (Dewayne's Law)
1. Look first — confirm a file exists before referencing it
2. Read STATE.md + dominion_log.txt at session start
3. Nothing is done until there's real output proving it
4. Use GCP API for VM power; SSH for services; never SSH a powered-off box
5. Make fixes idempotent — running twice must not break anything
6. One revenue action per session before infrastructure polish
7. Update STATE.md + dominion_log.txt + push at end of every session
