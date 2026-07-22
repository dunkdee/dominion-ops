# Dominion Production Runtime Alignment

**Initial snapshot:** 2026-07-21 19:32 UTC  
**Initial source:** `Production Ecosystem Audit` run `29861920503`  
**Stage-1 verification:** run `29862504700`  
**Stage-2 ownership map:** run `29863614231`  
**Stage-2A verification:** run `29864120927`  
**Stage-2B reconciliation map:** run `29864574740`  
**Stage-2C preparation:** run `29866812526`  
**Stage-2D preflight veto:** run `29867278124`  
**Stage-2D-R trace:** runs `29868756275`, `29869539712`  
**Stage-2D-R3 persistent retirement:** run `29874133137`  
**Stage-2D-R4 final preflight:** run `29879295855`  
**Stage-2E exact cutover map:** run `29880455592`  
**Stage-2F failed cutover:** run `29883264403`  
**Operating order:** Cash flow → Systems → Scale

## Executive determination

The systemd control plane remains stable and governed. Retired Alchemist, Conductor, and Juris API units and the obsolete port healer remain persistently masked. Approval-gated publishing timers remain disabled, and canonical systemd services recorded zero restart deltas during the Stage-2F attempt.

Stage 2F failed closed when the new Wix Agent did not pass `/ready`. The workflow removed the new Baby API, Dominion Web, and Wix containers and restored the original Wix data snapshot. Dominion Web, Wix, n8n, Alpha Engine, and Conductor recovered successfully. The original Baby API did not recover and is currently restart-looping with port 8080 unavailable.

The failed full-cutover workflow has been removed from `main`. No further broad migration is authorized until Baby API service is restored and the Wix failure is diagnosed separately.

## Current production status

| Component | Current evidence | Mode |
|---|---|---|
| Baby API | **Unavailable on port 8080; original container restarting** | Emergency recovery active |
| Wix Agent | HTTP 200 on `127.0.0.1:8082/ready` | Record-only |
| Dominion Web | HTTP 200 on `127.0.0.1:8090/` | Production |
| n8n | HTTP 200 on `127.0.0.1:5678/healthz` | Approved automation only |
| Alpha Engine | HTTP 200 on `127.0.0.1:8787/health` | Paper-only |
| Conductor | HTTP 200 on `127.0.0.1:5060/health` | Observe and route |
| Caddy, Gatekeeper, Store, Guardian, Sentinel, Juris, Alchemist, Gemini | Active under existing controls | Protected |

## Durable containment

- `alchemist-api.service`, `conductor-api.service`, `juris-api.service`, and `dominion-port-healer.service` remain persistently masked and inactive.
- Root-only unit recovery copies remain at `/var/lib/dominion/unit-retirement/stage2d-r3-29874133137`.
- Approval-gated publisher timers remain inactive and disabled.
- The surplus scraper remains quarantined.
- Browser Agents and Obsidian remain inactive.

## Canonical release and recovery assets

- Approved source: `10646094aa3a5a1e0d4d18dc5508a33d2f5ec2a3`.
- Release root: `/home/malachisingleton8/dominion-releases/dominion-ops-10646094aa3a`.
- Compose SHA-256: `42e2e90c41e9c154bf96f3ba2dc277811f873626af41b747474fcea6a494c8eb`.
- Release `.env` remains local with mode `0600`; values were not uploaded or reported.
- Stage-2C recovery root: `/home/malachisingleton8/.dominion-recovery/stage2c-29866812526`.
- Stage-2F local cutover root: `/var/lib/dominion/cutovers/stage2f-29883264403-1`.
- Quiescent Wix data and log archives exist locally with mode `0600`.
- Wix data was restored during rollback.

## Stage-2F failure evidence

- New Baby API and Dominion Web passed service-level migration checks before Wix migration.
- New Wix Agent failed its `/ready` health gate.
- New Baby API, Dominion Web, and Wix containers were removed.
- Original Dominion Web and Wix Agent returned HTTP 200 after rollback.
- Original Baby API returned no HTTP response and entered a restart loop.
- Rollback result recorded `rollback_health_failed:baby-api` and `rollback_protected_http_failed`.
- Unaffected container identities remained unchanged.
- No databases, DNS, network definitions, volume definitions, repository checkout, secret values, or customer data were changed or collected.

## Current recovery action

### Stage 2F-R1 — Baby API only

The emergency recovery will:

1. Require exact authorization `RECOVER_BABY_STAGE_2F`.
2. Verify the old container ID, old and approved image IDs, release hashes, network ID, retired masks, and publishing timers.
3. Classify recent Baby API failure signals without including raw logs in the report.
4. Preserve the failing original Baby API container under a unique stopped name.
5. Start only the already-tested canonical Baby API image through Compose project `dominion-ops`.
6. Reuse the existing production network, canonical release bind mount, and vault mount.
7. Verify the exact image, Compose ownership, network, mounts, public port 8080, HTTP 200, and 60-second stability.
8. Verify Wix, Dominion Web, n8n, Alpha, and Conductor remain healthy and unrelated container identities remain unchanged.

## Blocked operations

Until Baby API recovery passes:

- No full-stack cutover retry.
- No deletion of failed, rollback, or recovery containers and archives.
- No reset or deletion of the old VM checkout.
- No Browser Agents or Obsidian activation.
- No n8n, PostgreSQL, SEO, or Movie Generator migration.
- No production publishing, live trading, or surplus claimant contact.

## Stage sequence

### Stage 1 — Stabilize — COMPLETE

### Stage 2 — Unify control — ACTIVE

- Supervisor containment — complete.
- Approval-timer enforcement — complete.
- Boot persistence — complete.
- Deployment reconciliation map — complete.
- Parallel immutable release preparation — complete.
- Persistent retirement — complete.
- Independent gate and isolated-build preflight — complete.
- Exact cutover and rollback map — complete.
- Guarded full cutover — failed closed.
- Baby API emergency recovery — active.

### Stage 3 — Prove vertical duties

Blocked until Stage 2 returns to a stable, verified state.

### Stage 4 — Scale

Scale remains prohibited until relevant Stage-3 exit gates are evidenced and recorded.
