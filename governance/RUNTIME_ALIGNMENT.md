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
**Operating order:** Cash flow → Systems → Scale

## Executive determination

The production VM is operational and the protected revenue core is stable. Duplicate restart loops are durably contained: the retired Alchemist, Conductor, and Juris API units and the obsolete port healer are persistently masked after root-only local backups were created.

A clean immutable release from approved GitHub source exists beside the live system. Its Compose manifest validates, the local secret-bearing `.env` is preserved with mode `0600`, rollback copies exist, and approved isolated images exist for Baby API, Dominion Web, and Wix Agent.

Stage 2E mapped the exact live ownership boundary. Baby API, Baby Logger, and Dominion Web remain attached to the orphaned `desktop-tutorial` Compose project; Wix Agent is manually managed on the same Docker network. Stage 2F is prepared to move those four services into the canonical `dominion-ops` project under a guarded, automatically reversible procedure.

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
| Guardian | `active/running`, boot-enabled | Observe and report |
| Sentinel | `active/running`, boot-enabled | Independent verification |
| Juris | `active/running`, boot-enabled | Governance intelligence |

## Stabilization and durable containment

- Canonical Alchemist, Conductor, and Juris services are preserved.
- `alchemist-api.service`, `conductor-api.service`, `juris-api.service`, and `dominion-port-healer.service` are persistently masked and inactive.
- Root-only recovery copies are stored at `/var/lib/dominion/unit-retirement/stage2d-r3-29874133137`.
- The surplus scraper remains quarantined; the dashboard and review queue remain available.
- Approval-gated publishers and their timers remain inactive.
- Caddy, canonical Conductor, and Gemini are boot-enabled.
- All protected canonical units recorded zero restart deltas during R3 and R4 verification.
- No rollback was required.

## Stage-2B deployment findings

- The live Docker Compose project is named `desktop-tutorial`.
- Docker records its manifest as `/home/malachisingleton8/desktop-tutorial/docker-compose.yml`, but that path no longer exists.
- `/home/malachisingleton8/dominion-ops` is an orphaned local feature-branch checkout with dirty entries.
- Its untracked `.env` contains private-key risk indicators and must remain local and private.
- The correct Conductor health endpoint is `/health`; `/healthz` returns 404.

## Stage-2C canonical preparation

- Approved source commit: `10646094aa3a5a1e0d4d18dc5508a33d2f5ec2a3`.
- Immutable release root: `/home/malachisingleton8/dominion-releases/dominion-ops-10646094aa3a`.
- Release Compose SHA-256: `42e2e90c41e9c154bf96f3ba2dc277811f873626af41b747474fcea6a494c8eb`.
- Local `.env` copied to the release with mode `0600`; no value was printed, uploaded, or committed.
- Recovery root: `/home/malachisingleton8/.dominion-recovery/stage2c-29866812526`.
- Compose validation passed for six declared services.
- Production containers and the old checkout were not changed.

## Stage-2D governance veto and remediation

The first Stage-2D preflight correctly failed closed because the retired APIs had reactivated. Runtime, secrets, deployment, rollback, Watchmen, and agent-runtime evidence passed, but the governance gate vetoed and isolated builds were skipped.

Read-only traces established that scheduler and worker references were only ordering directives, the healer references were stale comments, no matching user cron entry existed, and the installed retired units' `Restart=always` policies sustained their loops after activation.

Stage-2D-R3 replaced weak runtime containment with persistent, backed-up `/dev/null` masks. All protected services and HTTP checks remained healthy, every canonical restart delta was zero, and production containers were unchanged.

## Stage-2D-R4 verified preflight

- Runtime, secrets, deployment, rollback, governance, agent-runtime, build, and post-build-stability gates passed.
- The deterministic Five Council recorded five passes.
- Conductor, Guardian, Sentinel, and Juris remained active/running; Watchmen status returned HTTP 200.
- Approved isolated images:
  - `dominion-stage2d-r4-baby-api:latest`
  - `dominion-stage2d-r4-dominion-web:latest`
  - `dominion/wix-agent:stage2d-r4-10646094aa3a`
- Retired units remained masked and approval-gated publishing timers remained disabled.
- Every protected canonical unit recorded a zero restart delta after the build.
- All six protected HTTP checks remained 200.
- Production containers, networks, volumes, databases, and DNS were unchanged.

## Stage-2E verified ownership map

- Baby API, Baby Logger, and Dominion Web carry `desktop-tutorial` Compose ownership labels.
- Wix Agent has no Compose ownership labels.
- All four services share network `desktop-tutorial_default`, ID `fce28b58ed4477fc2466285a6a80feb013061e63fece83eaaaea7236712f84e3`.
- Current production ports:
  - Baby API: public port 8080.
  - Dominion Web: public port 8090.
  - Wix Agent: loopback-only `127.0.0.1:8082`.
- Wix data volume: `wix_agent_data_a33ce2044d95-29785123140-1`.
- Wix logs volume: `wix_agent_logs_a33ce2044d95-29785123140-1`.
- Baby API currently bind-mounts the vanished-project source path and the existing vault.
- Wix retains 512 MB memory and 1 CPU limits, PID limit 256, read-only root filesystem, dropped capabilities, and `no-new-privileges`.
- The map captured exact rollback metadata without environment values, logs, customer data, or secret contents.
- Containers, images, networks, volumes, repositories, databases, DNS, and secrets were unchanged.

## Stage-2F guarded cutover controls

Formal plan: `governance/STAGE2F_CUTOVER_PLAN.md`.

The cutover will:

- Require the exact human authorization `CUTOVER_STAGE_2F`.
- Refuse current-container, image, release, network, or volume drift.
- Preserve full original container inspections in a root-only local cutover directory.
- Stop and rename originals instead of deleting them.
- Create quiescent local Wix data and log archives before replacement.
- Disconnect stopped rollback units to prevent alias competition.
- Create replacements through canonical Compose project `dominion-ops`.
- Reuse the current production network and exact Wix volumes.
- Verify ownership, image IDs, ports, mounts, Wix hardening, HTTP health, systemd stability, retired masks, publishing timers, and unrelated containers.
- Automatically restore original names, aliases, restart policies, Wix data, and service health if any gate fails.

## Human-approval gates

TikTok publishing defaults to disabled and requires all of the following:

1. A configured operator token.
2. A matching `X-Operator-Token` header.
3. `X-Human-Approval: APPROVED`.
4. An explicitly configured and verified account.
5. `TIKTOK_PUBLISH_ENABLED=true` set by the human operator.

The surplus vertical remains `research_only`. It may not autonomously contact claimants, collect sensitive identity data, sign, submit, or file documents.

## Remaining Stage-2 reconciliation

- Execute and verify the guarded Stage-2F cutover.
- Preserve old rollback containers and local Wix archives until separately approved cleanup.
- Reconcile unmanaged n8n, PostgreSQL, SEO, and Movie Generator containers without disrupting them.
- Add resource limits to currently unlimited production containers.
- Perform a restore test using non-production data.
- Preserve the old checkout until post-cutover verification is complete.
- Keep Browser Agents and Obsidian inactive until separately approved.

## Stage sequence

### Stage 1 — Stabilize — COMPLETE

- Removed duplicate restart loops.
- Preserved the healthy revenue core.
- Disabled approval-gated autonomous publishers.
- Quarantined the stuck surplus scraper.

### Stage 2 — Unify control — ACTIVE

- Supervisor containment — complete.
- Approval-timer enforcement — complete.
- Boot persistence — complete.
- Deployment reconciliation map — complete.
- Parallel immutable release preparation — complete.
- Persistent retirement of legacy APIs and healer — complete.
- Independent gate and isolated-build preflight — complete.
- Exact cutover and rollback map — complete.
- Guarded canonical cutover — prepared, pending human authorization.

### Stage 3 — Prove vertical duties

- Digital products: complete controlled checkout and delivery test.
- Commerce: complete one Wix sandbox order with exactly one fulfillment record.
- Services: produce one qualified lead and reviewable proposal without submission.
- Content: complete one private/unlisted approved post.
- Surplus: complete one synthetic, jurisdiction-reviewed case.
- Trading: meet documented paper-performance and failure-recovery thresholds.

### Stage 4 — Scale

Scale remains prohibited until the relevant Stage-3 exit gate is evidenced and recorded.
