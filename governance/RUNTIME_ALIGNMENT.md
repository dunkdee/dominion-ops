# Dominion Production Runtime Alignment

**Snapshot:** 2026-07-21 19:32 UTC  
**Source:** `Production Ecosystem Audit` run `29861920503`  
**Operating order:** Cash flow → Systems → Scale

## Executive determination

The production VM is operational but not yet fully aligned. The revenue core is healthy. The principal drift is duplicate systemd ownership, unmanaged runtime sprawl, incomplete human-approval enforcement, and missing proof for several vertical exit gates.

No vertical may be promoted merely because code or a service exists. Promotion requires the exit gate in `governance/verticals.json`.

## Protected revenue core

These components were reachable and must not be disrupted during Stage 1 alignment:

| Component | Production evidence | Governance mode |
|---|---|---|
| Baby API | HTTP 200 on `127.0.0.1:8080/`; healthy Docker container | Production support |
| Wix Agent | HTTP 200 on `127.0.0.1:8082/ready`; healthy Docker container | Record-only |
| Dominion Web | HTTP 200 on `127.0.0.1:8090/` | Production |
| n8n | HTTP 200 on `127.0.0.1:5678/healthz` | Approved automation only |
| Alpha Engine | HTTP 200 on `127.0.0.1:8787/health`; canonical systemd unit running | Paper-only |
| Caddy | Canonical systemd unit running | Production edge |
| Gatekeeper | Canonical systemd unit running | Revenue rail |
| Store API | Canonical systemd unit running | Production payment surface |

## Canonical service ownership

The following canonical units were active and running. Their legacy duplicates were stuck in restart loops and are candidates for guarded removal:

| Vertical | Canonical unit | Legacy duplicate |
|---|---|---|
| Health / Alchemist | `dominion-alchemist.service` | `alchemist-api.service` |
| Orchestration / Conductor | `dominion-conductor.service` | `conductor-api.service` |
| Governance / Juris | `dominion-juris.service` | `juris-api.service` |

Stage 1 may stop and disable a legacy unit only when its canonical replacement is still `active/running` and the legacy unit is still `activating`, `failed`, or `auto-restart`.

## Human-approval gates

The following autonomous publishing units must remain disabled until their vertical exit gates are satisfied:

- `conductor-autonomous.service`
- `dominion-social-poster.service`
- `dominion-publish.service`
- `dominion-youtube.service`
- `dominion-kdp.service`

The TikTok API may remain available for OAuth and draft validation, but publishing must default to disabled and require:

1. A configured operator token.
2. A matching `X-Operator-Token` header.
3. `X-Human-Approval: APPROVED`.
4. An explicitly configured and verified account.
5. `TIKTOK_PUBLISH_ENABLED=true` set by the human operator.

## Surplus vertical

The surplus dashboard and human review queue were running. The scraper was stuck in startup. Stage 1 may quarantine only the stuck scraper while preserving:

- `dominion-surplus-dashboard.service`
- `dominion-review-queue.service`

The surplus vertical remains `research_only`. It may not autonomously contact claimants, collect sensitive identity data, sign, submit, or file documents.

## Runtime drift requiring later reconciliation

- The reported Compose project is `desktop-tutorial`, sourced from `/home/malachisingleton8/desktop-tutorial/docker-compose.yml`, while the canonical repository is `/home/malachisingleton8/dominion-ops`.
- Multiple production containers and systemd units exist outside one declared deployment manifest.
- Browser agents and Obsidian were not reachable on their expected ports.
- The Conductor port was reachable but `/healthz` returned 404, so its health contract is not aligned.
- The surplus webroot `/var/www/surplus` was absent.
- Backup, timer, restart-policy, and rollback execution still require explicit verification.
- Digital-product publication and delivery still require a test checkout and delivery proof.

## Stage sequence

### Stage 1 — Stabilize

- Remove proven duplicate restart loops.
- Preserve the healthy revenue core.
- Disable approval-gated autonomous publishers.
- Quarantine the stuck surplus scraper.
- Produce a before/after report and fail on core regression.

### Stage 2 — Unify control

- Declare one canonical deployment root.
- Map every active service to one vertical and one owner.
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

Scale remains prohibited until the relevant Stage 3 exit gate is evidenced and recorded.
