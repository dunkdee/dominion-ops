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

### Stage 2B — Deployment reconciliation map

- Live Docker Compose project reports the name `desktop-tutorial`.
- Its recorded manifest path no longer exists.
- The VM repository checkout is an orphaned local feature branch with a private local `.env`.
- The correct Conductor health endpoint is `/health`, not `/healthz`.

### Stage 2C — Parallel canonical release preparation

Evidence: workflow run `29866812526`.

- Immutable release prepared at `/home/malachisingleton8/dominion-releases/dominion-ops-10646094aa3a`.
- The local `.env` was preserved with mode `0600` and matching recovery hash.
- Compose validation passed and production containers remained unchanged.

### Stage 2D — Independent preflight — VETOED AS DESIGNED

Evidence: workflow run `29867278124`.

- Runtime, secrets, deployment, rollback, and agent-runtime gates passed.
- Governance vetoed because retired APIs had reactivated.
- Isolated builds were correctly skipped.

### Stage 2D-R / R2 — Reactivation tracing

Evidence: workflow runs `29868756275` and `29869539712`.

- Scheduler and worker references were only `After=` ordering directives.
- No matching user cron entry was found.
- Installed retired units' `Restart=always` policies sustained the loops.

### Stage 2D-R3 — Persistent retirement — COMPLETE

Evidence: workflow run `29874133137`.

- Root-only backups were created under `/var/lib/dominion/unit-retirement/stage2d-r3-29874133137`.
- Persistent masks were installed for the three retired APIs and obsolete port healer.
- All protected canonical services remained active, restart deltas were zero, and all protected HTTP checks remained 200.

### Stage 2D-R4 — Independent gates and isolated builds — COMPLETE

Evidence: workflow run `29879295855`.

- All prerequisite gates passed.
- Approved images were built for Baby API, Dominion Web, and Wix Agent.
- Production remained unchanged.

### Stage 2E — Exact cutover and rollback map — COMPLETE

Evidence: workflow run `29880455592`.

- Baby API, Baby Logger, and Dominion Web are owned by orphaned Compose project `desktop-tutorial`.
- Wix Agent is manually managed but shares the same network.
- Exact image IDs, ports, mounts, network ID, restart policies, and Wix volumes were recorded.

### Stage 2F — Guarded canonical cutover — FAILED CLOSED

Evidence: workflow run `29883264403`.

- Canonical Baby API and Dominion Web replacements passed their service-level migration checks before Wix was attempted.
- New Wix Agent failed its `/ready` health gate.
- The workflow removed all three new containers and restored Wix data from the quiescent local snapshot.
- Wix Agent, Dominion Web, n8n, Alpha Engine, and Conductor returned HTTP 200 after rollback.
- The restored original Baby API failed to recover, entered a restart loop, and left port 8080 unavailable.
- All canonical systemd restart deltas remained zero.
- Retired APIs remained masked and publishing timers remained disabled.
- No database, DNS, network definition, volume definition, repository checkout, or secret was changed.
- The failed full-cutover workflow was removed from `main` to prevent accidental rerun.

## Current production condition

- **Baby API — port 8080 unavailable; emergency recovery required.**
- Wix Agent — port 8082 healthy, record-only mode.
- Dominion Web — port 8090 healthy.
- n8n — port 5678 healthy, approved automation only.
- Alpha Engine — port 8787 healthy, paper-only.
- Caddy, Gatekeeper, Store, Conductor, Guardian, Sentinel, Juris, Alchemist, and Gemini remain active under existing controls.

## Current active work

### Stage 2F-R1 — Baby API emergency recovery

**Goal:** Restore port 8080 using only the already-tested canonical Baby API image while preserving the failing original container for diagnosis.

Required behavior:

1. Require exact human authorization `RECOVER_BABY_STAGE_2F`.
2. Refuse drift in the original container ID, old/new image IDs, release hashes, network ID, or governance state.
3. Classify recent Baby API error signals without publishing raw logs.
4. Preserve the failing original container under a unique stopped name; do not delete it.
5. Start only canonical Baby API through Compose project `dominion-ops`.
6. Reuse the existing production network and vault mount.
7. Verify exact image, ownership, network, mounts, port 8080, HTTP 200, and 60-second stability.
8. Leave Wix, Dominion Web, n8n, Alpha, Conductor, databases, DNS, volumes, and repositories unchanged.

## Blocked until Baby API recovery is verified

- Any further full-stack cutover.
- Deleting failed or rollback containers and local Wix archives.
- Resetting or deleting the old VM checkout.
- Starting Browser Agents or Obsidian.
- Migrating n8n, PostgreSQL, SEO, or Movie Generator.
- Production publishing, live trading, or surplus claimant contact.

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
