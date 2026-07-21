# Dominion Canonical Agent Operations State

**Authority:** Dewayne Singleton — human final decision-maker  
**Operating order:** Cash flow → Systems → Scale  
**Rule:** No agent may claim a duty is complete without recorded evidence.

## Command structure

| Role | Assigned duty | Current permission boundary |
|---|---|---|
| Human Overseer | Final approval, promotion, publishing, live-money authorization | Unrestricted final authority |
| Coordinator | Sequence work, reconcile evidence, prevent conflicting changes | May prepare and verify; may not bypass human approval gates |
| Conductor | Route approved jobs and maintain execution state | No autonomous publishing or irreversible execution |
| Guardian | Detect service drift, regressions, and unhealthy runtime state | Observe and report; may not reactivate retired services |
| Sentinel | Independent runtime and governance verification | Observe, challenge, and report |
| Juris | Legal/compliance review and documentary boundaries | Draft/review only; no signing, filing, or representation |
| Five Council | Cross-check promotion gates and unresolved risks | Advisory evidence review; human retains final decision |

## Evidence rules

1. An agent must cite a workflow run, commit, health result, test result, or approved artifact before declaring completion.
2. Agents must read this file and `governance/RUNTIME_ALIGNMENT.md` before changing production behavior.
3. No agent may restart, enable, publish, trade live, file, sign, contact claimants, or spend money unless the relevant human approval gate is recorded.
4. Duplicate service ownership is prohibited. One production duty must have one canonical owner.
5. A failed or retired unit must not be auto-healed back into service unless its canonical owner is unavailable and the human explicitly approves failover.
6. Secret values, customer data, private keys, and `.env` contents must never be committed to Git or included in reports.
7. Automated council checks must be identified as deterministic evidence checks; they may not be represented as human or model opinions.

## Verified completed work

### Stage 1 — Stabilization

- Protected revenue services remained healthy.
- Legacy Alchemist, Conductor, and Juris restart loops were stopped.
- Stuck surplus scraper was quarantined.
- Approval-gated publisher services were kept inactive.

### Stage 2A — Supervisor containment

- `dominion-port-healer.service` was stopped and disabled after it reactivated retired API units.
- Legacy `alchemist-api.service`, `conductor-api.service`, and `juris-api.service` were stopped and runtime-contained.
- Autonomous publishing timers were stopped and disabled.
- Caddy, canonical Conductor, and Gemini were enabled for boot persistence.
- Protected HTTP checks remained healthy and canonical restart deltas were zero during verification.

### Stage 2B — Deployment reconciliation map

- Live Docker Compose project reports the name `desktop-tutorial`.
- Its recorded manifest path `/home/malachisingleton8/desktop-tutorial/docker-compose.yml` no longer exists.
- The actual VM repository checkout `/home/malachisingleton8/dominion-ops` is on an orphaned local feature branch.
- That checkout contains a modified `docker-compose.yml` and an untracked `.env` containing private-key risk indicators.
- The `.env` remains local and private; it was not uploaded or committed.
- The correct Conductor health endpoint is `/health`, not `/healthz`.

### Stage 2C — Parallel canonical release preparation

Evidence: workflow run `29866812526`.

- Immutable release prepared at `/home/malachisingleton8/dominion-releases/dominion-ops-10646094aa3a` from source commit `10646094aa3a5a1e0d4d18dc5508a33d2f5ec2a3`.
- Source archive SHA-256 matched the expected value.
- The local `.env` was copied into the release with mode `0600`; its hash matched the protected recovery copy.
- Recovery copies were created under `/home/malachisingleton8/.dominion-recovery/stage2c-29866812526`.
- Compose validation passed for `baby-api`, `baby-logger`, `browser-agents`, `dominion-web`, `obsidian-remote`, and `wix-agent`.
- No production container was started, stopped, recreated, or changed.
- The orphaned VM checkout remained untouched.

## Current protected production core

- Baby API — port 8080
- Wix Agent — port 8082, record-only fulfillment mode
- Dominion Web — port 8090
- n8n — port 5678, approved automation only
- Alpha Engine — port 8787, paper-only
- Caddy — production edge
- Gatekeeper — revenue rail
- Store API — payment surface
- Canonical Conductor — orchestration
- Canonical Juris — legal intelligence
- Canonical Alchemist — health intelligence

## Current active work

### Stage 2D — Independent council and build preflight

**Goal:** Obtain independent operational evidence and isolated build proof before any production cutover.

Required evidence:

1. **Runtime gate:** protected HTTP endpoints remain healthy before and after the preflight.
2. **Secrets gate:** release `.env` remains local, untracked, mode `0600`, and is never printed or uploaded.
3. **Deployment gate:** release marker, source SHA, Compose hash, and resolved core services match the approved release.
4. **Rollback gate:** recovery copies exist and match the recorded hashes.
5. **Governance gate:** retired APIs, port healer, and approval-gated publishing timers remain inactive.
6. **Agent status:** canonical Conductor, Guardian, Sentinel, and Juris runtime status is recorded; Conductor Watchmen routes are mapped without irreversible calls.
7. **Build proof:** only the protected core images are built under isolated preflight tags; no production container is started, stopped, or recreated.

## Blocked until Stage 2D evidence exists

- Switching the live Compose project to the canonical release.
- Resetting, deleting, or renaming the old VM checkout.
- Starting browser-agents or Obsidian.
- Replacing production images, volumes, networks, or environment variables.
- Production publishing.
- Live trading.
- Surplus claimant contact or filing.

## Agent reporting format

Every agent report must contain:

- `agent`
- `duty`
- `evidence`
- `result`
- `risks`
- `next_action`
- `human_approval_required`

An agent that cannot provide evidence must report `result: unverified`.
