# Dominion Production Runtime Alignment

**Initial snapshot:** 2026-07-21 19:32 UTC  
**Initial source:** `Production Ecosystem Audit` run `29861920503`  
**Stage-1 verification:** run `29862504700`  
**Stage-2 ownership map:** run `29863614231`  
**Stage-2A verification:** run `29864120927`  
**Stage-2B reconciliation map:** run `29864574740`  
**Stage-2C preparation:** run `29866812526`  
**Operating order:** Cash flow → Systems → Scale

## Executive determination

The production VM is operational, stabilized, and governed. Duplicate restart loops, the reactivation supervisor, approval-gated publisher timers, and the stuck surplus scraper have been removed from active execution without regressing the protected revenue core.

A clean immutable release from current GitHub `main` now exists beside the live system. Its Compose manifest validates, the local secret-bearing `.env` is preserved with mode `0600`, rollback copies exist, and the active container inventory was unchanged during preparation.

The ecosystem is **not yet cut over to unified deployment ownership**. Independent council evidence, isolated image builds, rollback validation, and a guarded cutover plan are still required.

No vertical may be promoted merely because code or a service exists. Promotion requires the exit gate in `governance/verticals.json`.

## Protected revenue core

| Component | Verified production evidence | Governance mode |
|---|---|---|
| Baby API | HTTP 200 on `127.0.0.1:8080/` | Production support |
| Wix Agent | HTTP 200 on `127.0.0.1:8082/ready` | Record-only |
| Dominion Web | HTTP 200 on `127.0.0.1:8090/` | Production |
| n8n | HTTP 200 on `127.0.0.1:5678/healthz` | Approved automation only |
| Alpha Engine | HTTP 200 on `127.0.0.1:8787/health` | Paper-only |
| Caddy | `active/running`, boot-enabled | Production edge |
| Conductor | `active/running`, boot-enabled; health route `/health` | Observe and route |
| Gemini server | `active/running`, boot-enabled | Intelligence service |
| Gatekeeper | `active/running` | Revenue rail |
| Store API | `active/running` | Production payment surface |

## Stabilization and containment

- Canonical Alchemist, Conductor, and Juris services were preserved.
- Legacy `alchemist-api.service`, `conductor-api.service`, and `juris-api.service` were removed from active execution.
- `dominion-port-healer.service` is inactive and disabled.
- The surplus scraper is quarantined; the dashboard and review queue remain available.
- Approval-gated publishers and their timers remain inactive.
- Caddy, canonical Conductor, and Gemini are boot-enabled.
- Protected services recorded zero restart deltas during Stage-2A verification.

## Stage-2B verified deployment findings

- The live Docker Compose project is named `desktop-tutorial`.
- Docker records its manifest as `/home/malachisingleton8/desktop-tutorial/docker-compose.yml`, but that path no longer exists.
- `/home/malachisingleton8/dominion-ops` is an orphaned local feature-branch checkout with dirty entries.
- Its untracked `.env` contains private-key risk indicators and must remain local and private.
- The correct Conductor health endpoint is `/health`; `/healthz` returns 404.

## Stage-2C verified preparation

- Approved source commit: `10646094aa3a5a1e0d4d18dc5508a33d2f5ec2a3`.
- Immutable release root: `/home/malachisingleton8/dominion-releases/dominion-ops-10646094aa3a`.
- Release Compose SHA-256: `42e2e90c41e9c154bf96f3ba2dc277811f873626af41b747474fcea6a494c8eb`.
- Local `.env` copied to the release with mode `0600`; no value was printed, uploaded, or committed.
- Recovery root: `/home/malachisingleton8/.dominion-recovery/stage2c-29866812526`.
- Recovery copies exist for the prior `.env` and modified Compose manifest.
- Compose validation passed for six declared services.
- Production containers were identical before and after preparation.
- Databases, DNS, volumes, networks, production images, and the old checkout were not changed.

## Human-approval gates

TikTok publishing defaults to disabled and requires all of the following:

1. A configured operator token.
2. A matching `X-Operator-Token` header.
3. `X-Human-Approval: APPROVED`.
4. An explicitly configured and verified account.
5. `TIKTOK_PUBLISH_ENABLED=true` set by the human operator.

The surplus vertical remains `research_only`. It may not autonomously contact claimants, collect sensitive identity data, sign, submit, or file documents.

## Remaining Stage-2 reconciliation

- Complete Stage-2D independent council and isolated build preflight.
- Record Conductor, Guardian, Sentinel, and Juris runtime evidence.
- Verify the five deterministic gates: runtime, secrets, deployment, rollback, and governance.
- Build only the protected core images under isolated tags without changing running containers.
- Define a guarded cutover and automatic rollback plan.
- Reconcile unmanaged n8n, database, SEO, and movie-generator containers into declared ownership without disrupting them.
- Add resource limits to currently unlimited production containers.
- Perform a restore test using non-production data.
- Preserve the old checkout until post-cutover verification is complete.
- Keep browser-agents and Obsidian inactive until separately approved.

## Stage sequence

### Stage 1 — Stabilize — COMPLETE

- Removed proven duplicate restart loops.
- Preserved the healthy revenue core.
- Disabled approval-gated autonomous publishers.
- Quarantined the stuck surplus scraper.

### Stage 2 — Unify control — ACTIVE

- Supervisor containment — complete.
- Approval-timer enforcement — complete.
- Boot persistence — complete.
- Deployment reconciliation map — complete.
- Parallel immutable release preparation — complete.
- Independent council and build preflight — pending.
- Guarded cutover and rollback verification — blocked pending preflight.

### Stage 3 — Prove vertical duties

- Digital products: complete controlled checkout and delivery test.
- Commerce: complete one Wix sandbox order with exactly one fulfillment record.
- Services: produce one qualified lead and reviewable proposal without submission.
- Content: complete one private/unlisted approved post.
- Surplus: complete one synthetic, jurisdiction-reviewed case.
- Trading: meet documented paper-performance and failure-recovery thresholds.

### Stage 4 — Scale

Scale remains prohibited until the relevant Stage-3 exit gate is evidenced and recorded.
