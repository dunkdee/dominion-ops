# Dominion Production Runtime Alignment

**Initial snapshot:** 2026-07-21 19:32 UTC  
**Initial source:** `Production Ecosystem Audit` run `29861920503`  
**Stage-1 verification:** `Production Alignment Stage 1` run `29862504700`  
**Operating order:** Cash flow → Systems → Scale

## Executive determination

The production VM is operational and the first stabilization stage is complete. The protected revenue core remained healthy while proven duplicate restart loops, approval-gated publishers, and the stuck surplus scraper were removed from active execution.

The ecosystem is **stabilized but not yet fully unified**. Stage 2 must establish one canonical runtime inventory, boot-persistent ownership, restart budgets, backup proof, and a deployment-root decision before any inactive vertical is promoted.

No vertical may be promoted merely because code or a service exists. Promotion requires the exit gate in `governance/verticals.json`.

## Protected revenue core

These components remained healthy after Stage 1:

| Component | Verified production evidence | Governance mode |
|---|---|---|
| Baby API | HTTP 200 on `127.0.0.1:8080/` | Production support |
| Wix Agent | HTTP 200 on `127.0.0.1:8082/ready` | Record-only |
| Dominion Web | HTTP 200 on `127.0.0.1:8090/` | Production |
| n8n | HTTP 200 on `127.0.0.1:5678/healthz` | Approved automation only |
| Alpha Engine | HTTP 200 on `127.0.0.1:8787/health` | Paper-only |
| Caddy | `active/running` | Production edge |
| Gatekeeper | `active/running` | Revenue rail |
| Store API | `active/running` | Production payment surface |

Stage 1 did not restart canonical services, delete persistent data, read secrets, or collect logs.

## Stage-1 verified actions

The following duplicate units were stopped and disabled only after their canonical replacements were confirmed `active/running`:

| Vertical | Canonical unit preserved | Duplicate removed from execution | Prior accumulated restarts |
|---|---|---:|---:|
| Health / Alchemist | `dominion-alchemist.service` | `alchemist-api.service` | 25,063 |
| Orchestration / Conductor | `dominion-conductor.service` | `conductor-api.service` | 3,372 |
| Governance / Juris | `dominion-juris.service` | `juris-api.service` | 38,097 |

The stuck `dominion-surplus-scraper.service` was quarantined after 2,739 accumulated restarts. The human-facing surplus dashboard and review queue were preserved.

The following approval-gated publishers remain inactive:

- `conductor-autonomous.service`
- `dominion-social-poster.service`
- `dominion-publish.service`
- `dominion-youtube.service`
- `dominion-kdp.service`

## Human-approval gates

TikTok publishing defaults to disabled and requires all of the following:

1. A configured operator token.
2. A matching `X-Operator-Token` header.
3. `X-Human-Approval: APPROVED`.
4. An explicitly configured and verified account.
5. `TIKTOK_PUBLISH_ENABLED=true` set by the human operator.

The surplus vertical remains `research_only`. It may not autonomously contact claimants, collect sensitive identity data, sign, submit, or file documents.

## Remaining Stage-2 reconciliation

- The reported Compose project is `desktop-tutorial`, sourced from `/home/malachisingleton8/desktop-tutorial/docker-compose.yml`, while the canonical repository is `/home/malachisingleton8/dominion-ops`.
- Multiple production containers and systemd units exist outside one declared deployment manifest.
- `dominion-conductor.service` is active but was reported disabled for boot; boot persistence must be verified before changing it.
- Caddy is active but was reported disabled for boot; package or socket ownership must be verified before changing it.
- `dominion-juris.service` is currently running but has a high historical restart count; Stage 2 must measure restart delta rather than assume current instability.
- Browser agents and Obsidian were not reachable on their expected ports and remain non-core.
- The Conductor port was reachable but `/healthz` returned 404, so its health contract is not aligned.
- The surplus webroot `/var/www/surplus` was absent.
- Backup, timer, resource-limit, restart-policy, and rollback execution still require explicit verification.
- Digital-product publication and delivery still require a controlled checkout and delivery proof.

## Stage sequence

### Stage 1 — Stabilize — COMPLETE

- Removed proven duplicate restart loops.
- Preserved the healthy revenue core.
- Disabled approval-gated autonomous publishers.
- Quarantined the stuck surplus scraper.
- Produced a before/after report with zero core regressions.

### Stage 2 — Unify control — ACTIVE

- Declare one canonical deployment root.
- Map every active service and container to one vertical and one owner.
- Verify boot persistence without restarting healthy services.
- Measure restart deltas for canonical services.
- Correct the Conductor health contract.
- Add restart budgets, resource limits, backup verification, and rollback tests.
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
