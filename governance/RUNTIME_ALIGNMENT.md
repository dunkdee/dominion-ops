# Dominion Production Runtime Alignment

**Initial snapshot:** 2026-07-21 19:32 UTC  
**Initial source:** `Production Ecosystem Audit` run `29861920503`  
**Stage-1 verification:** run `29862504700`  
**Stage-2 ownership map:** run `29863614231`  
**Stage-2A verification:** run `29864120927`  
**Operating order:** Cash flow → Systems → Scale

## Executive determination

The production VM is operational and the stabilization and supervisor-containment stages are complete. The protected revenue core remained healthy while duplicate restart loops, the reactivation supervisor, approval-gated publisher timers, and the stuck surplus scraper were removed from active execution.

The ecosystem is **stable and governed, but deployment ownership is not yet unified**. Stage 2 must still reconcile the production Compose root, the local repository branch and dirty working tree, the Conductor health contract, unmanaged runtime ownership, and resource limits before inactive verticals are promoted.

No vertical may be promoted merely because code or a service exists. Promotion requires the exit gate in `governance/verticals.json`.

## Protected revenue core

These components remained healthy through Stage 2A:

| Component | Verified production evidence | Governance mode |
|---|---|---|
| Baby API | HTTP 200 on `127.0.0.1:8080/` | Production support |
| Wix Agent | HTTP 200 on `127.0.0.1:8082/ready` | Record-only |
| Dominion Web | HTTP 200 on `127.0.0.1:8090/` | Production |
| n8n | HTTP 200 on `127.0.0.1:5678/healthz` | Approved automation only |
| Alpha Engine | HTTP 200 on `127.0.0.1:8787/health` | Paper-only |
| Caddy | `active/running`, boot-enabled | Production edge |
| Conductor | `active/running`, boot-enabled | Observe and route |
| Gemini server | `active/running`, boot-enabled | Intelligence service |
| Gatekeeper | `active/running` | Revenue rail |
| Store API | `active/running` | Production payment surface |

No protected service restarted during the Stage-2A 30-second verification window.

## Stage-1 verified actions

The following duplicate units were stopped and disabled only after their canonical replacements were confirmed `active/running`:

| Vertical | Canonical unit preserved | Duplicate removed from execution | Prior accumulated restarts |
|---|---|---:|---:|
| Health / Alchemist | `dominion-alchemist.service` | `alchemist-api.service` | 25,063 |
| Orchestration / Conductor | `dominion-conductor.service` | `conductor-api.service` | 3,372 |
| Governance / Juris | `dominion-juris.service` | `juris-api.service` | 38,097 |

The stuck `dominion-surplus-scraper.service` was quarantined after 2,739 accumulated restarts. The human-facing surplus dashboard and review queue were preserved.

## Stage-2A verified containment

Stage 2A corrected the mechanism that had reactivated the retired duplicate APIs:

- `dominion-port-healer.service` is inactive and disabled.
- `alchemist-api.service`, `conductor-api.service`, and `juris-api.service` are inactive and remained unreactivated during verification.
- `caddy.service`, `dominion-conductor.service`, and `gemini-server.service` are boot-enabled without being restarted.
- Canonical Alchemist, Alpha, Conductor, Gatekeeper, Juris, Store, Gemini, Caddy, and Surplus Review Queue services recorded zero restart deltas during verification.

The following approval-gated services remain inactive and their timers are disabled:

- `conductor-autonomous.service` / `conductor-autonomous.timer`
- `dominion-social-poster.service` / `dominion-social-poster.timer`
- `dominion-publish.service` / `dominion-publish.timer`
- `dominion-youtube.service` / `dominion-youtube.timer`
- `dominion-kdp.service` / `dominion-kdp.timer`

Stage 2A did not alter Compose, databases, DNS, repository working trees, persistent data, or secrets.

## Human-approval gates

TikTok publishing defaults to disabled and requires all of the following:

1. A configured operator token.
2. A matching `X-Operator-Token` header.
3. `X-Human-Approval: APPROVED`.
4. An explicitly configured and verified account.
5. `TIKTOK_PUBLISH_ENABLED=true` set by the human operator.

The surplus vertical remains `research_only`. It may not autonomously contact claimants, collect sensitive identity data, sign, submit, or file documents.

## Remaining Stage-2 reconciliation

- Production Compose runs from `/home/malachisingleton8/desktop-tutorial/docker-compose.yml`, which is not a Git repository.
- The canonical `/home/malachisingleton8/dominion-ops` checkout is on branch `claude/movie-generator-youtube-b50wx2` with three dirty entries; it must be preserved before alignment to `main`.
- Multiple production containers and systemd units exist outside one declared deployment manifest.
- The Conductor port is reachable, but `/healthz` returns 404; the correct route or implementation must be established.
- Browser agents and Obsidian were not reachable on their expected ports and remain non-core.
- The surplus webroot `/var/www/surplus` is absent.
- Docker resource limits are missing for several production containers; the healthy Wix container is the current hardened exception.
- Recent backups exist and `dominion-backup.timer` is enabled, but restore testing and rollback evidence remain outstanding.
- `dominion-juris.service` and `dominion-review-queue.service` have high historical restart counts but showed zero current restart delta; they require restart-budget monitoring rather than immediate disruption.
- Digital-product publication and delivery still require a controlled checkout and delivery proof.

## Stage sequence

### Stage 1 — Stabilize — COMPLETE

- Removed proven duplicate restart loops.
- Preserved the healthy revenue core.
- Disabled approval-gated autonomous publishers.
- Quarantined the stuck surplus scraper.
- Produced a before/after report with zero core regressions.

### Stage 2 — Unify control — ACTIVE

- Supervisor containment and approval-timer enforcement are complete.
- Boot persistence for Caddy, Conductor, and Gemini is complete.
- Declare and migrate to one canonical deployment root without losing local work.
- Map every active service and container to one vertical and one owner.
- Correct the Conductor health contract.
- Add restart budgets, Docker resource limits, restore verification, and rollback tests.
- Reconcile unmanaged Docker containers and systemd units into a runtime manifest.

### Stage 3 — Prove vertical duties

- Digital products: complete controlled checkout and delivery test.
- Commerce: complete one Wix sandbox order with exactly one fulfillment record.
- Services: produce one qualified lead and reviewable proposal without submission.
- Content: complete one private/unlisted approved post.
- Surplus: complete one synthetic, jurisdiction-reviewed case.
- Trading: meet documented paper-performance and failure-recovery thresholds.

### Stage 4 — Scale

Scale remains prohibited until the relevant Stage-3 exit gate is evidenced and recorded.
