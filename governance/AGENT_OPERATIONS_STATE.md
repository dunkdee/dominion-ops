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
| Sentinel | Independent runtime verification | Observe, challenge, and report |
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
- The local `.env` was copied into the release with mode `0600`; its hash matched the protected recovery copy.
- Compose validation passed for all six declared services.
- Production containers and the orphaned checkout remained unchanged.

### Stage 2D — Independent preflight — VETOED AS DESIGNED

Evidence: workflow run `29867278124`.

- Runtime, secrets, deployment, rollback, and agent-runtime gates passed.
- The governance gate vetoed because retired APIs had reactivated.
- The isolated image build was correctly skipped.
- No cutover was authorized and production containers were unchanged.

### Stage 2D-R / R2 — Reactivation tracing

Evidence: workflow runs `29868756275` and `29869539712`.

- Scheduler and worker references to `conductor-api.service` were only `After=` ordering directives.
- Their commands ran only `scheduler.py` and `worker.py`.
- The retired names in `buddy_core/port_healer.py` occurred in a stale comment.
- No matching user cron entry was found.
- The installed retired unit files' `Restart=always` policies sustained their own loops after activation.

### Stage 2D-R3 — Persistent retirement — COMPLETE

Evidence: workflow run `29874133137`.

- Root-only backups were created under `/var/lib/dominion/unit-retirement/stage2d-r3-29874133137`.
- Persistent masks were installed for `alchemist-api.service`, `conductor-api.service`, `juris-api.service`, and `dominion-port-healer.service`.
- All four units verified `inactive/dead/masked`.
- Canonical Caddy, Alchemist, Alpha, Conductor, Gatekeeper, Guardian, Juris, Sentinel, Store, and Gemini remained `active/running`.
- Every protected canonical service recorded a zero restart delta over 90 seconds.
- All six protected HTTP checks remained 200.
- No rollback was required.

### Stage 2D-R4 — Independent gates and isolated builds — COMPLETE

Evidence: workflow run `29879295855`.

- Runtime, secrets, deployment, rollback, governance, agent-runtime, build, and post-build-stability gates all passed.
- The deterministic Five Council recorded five passes and no veto.
- Conductor, Guardian, Sentinel, and Juris were active/running; Watchmen status returned HTTP 200.
- Approved images were built for Baby API, Dominion Web, and Wix Agent.
- Retired units remained masked, publishing timers remained disabled, canonical restart deltas remained zero, and production containers were unchanged.

### Stage 2E — Exact cutover and rollback map — COMPLETE

Evidence: workflow run `29880455592`.

- Baby API, Baby Logger, and Dominion Web are owned by the orphaned `desktop-tutorial` Compose project.
- Wix Agent is manually managed outside Compose but shares `desktop-tutorial_default`.
- Exact current container IDs, image IDs, ports, mounts, restart policies, labels, network ID, and Wix volume names were recorded.
- Approved R4 image IDs were reconfirmed.
- Wix is loopback-only on port 8082, reuses two named volumes, and retains its hardening controls.
- Baby API and Dominion Web are publicly bound on ports 8080 and 8090.
- The mapping operation was read-only; containers, images, networks, volumes, repositories, databases, DNS, and secrets remained unchanged.

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

### Stage 2F — Guarded canonical Compose cutover

**Goal:** Move Baby API, Baby Logger, Dominion Web, and Wix Agent into the canonical `dominion-ops` Compose project while preserving the current containers and Wix data as locally recoverable rollback assets.

Required behavior:

1. Require the exact human authorization `CUTOVER_STAGE_2F`.
2. Refuse any drift in current container IDs, image IDs, approved replacement image IDs, release hashes, network ID, or Wix volume names.
3. Preserve full original container inspections only in a root-only VM cutover directory.
4. Stop and rename each original container instead of deleting it.
5. Create quiescent local Wix data and log archives before the new Wix image starts.
6. Disconnect stopped rollback containers so old aliases cannot compete with new services.
7. Create replacements through Compose project `dominion-ops` using the existing production network and exact Wix volumes.
8. Verify image IDs, ownership labels, ports, mounts, security controls, health, systemd restart deltas, retired masks, publishing timers, and unrelated-container stability.
9. Automatically remove new containers and restore original names, network aliases, restart policies, Wix data, and health if any gate fails.
10. Preserve successful rollback containers and local archives until separately authorized cleanup.

Formal change record: `governance/STAGE2F_CUTOVER_PLAN.md`.

## Blocked until Stage 2F evidence exists

- Deleting preserved rollback containers or local Wix archives.
- Resetting, deleting, or renaming the old VM checkout.
- Starting Browser Agents or Obsidian.
- Migrating n8n, PostgreSQL, SEO, or Movie Generator.
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
