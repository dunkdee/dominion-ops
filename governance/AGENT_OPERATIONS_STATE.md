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
- The restored original Baby API failed because its `/app` bind source pointed to the vanished `desktop-tutorial/api` path.
- All canonical systemd restart deltas remained zero.
- Retired APIs remained masked and publishing timers remained disabled.
- No database, DNS, network definition, volume definition, repository checkout, or secret was changed.
- The failed full-cutover workflow was removed from `main` to prevent accidental rerun.

### Stage 2F-R1 — Baby API emergency recovery — COMPLETE

Evidence: workflow run `29885228305`.

- The failing original Baby API was preserved as `baby-api-failed-stage2f-29885228305-1`; it was not deleted.
- Canonical Baby API image `sha256:089445475d96ca3630fd4821af3c0304d38de5ece89a529b3782a398e38c3c82` is running under Compose project `dominion-ops`.
- Port 8080, HTTP health, canonical release `/app` mount, vault mount, production network, and 60-second stability passed.
- Restart count is zero and the container reports healthy.
- Wix, Dominion Web, n8n, Alpha Engine, and Conductor remained HTTP 200.
- Unaffected container identities were unchanged.
- Retired units remained masked and publishing timers remained disabled.
- The one-time Baby recovery workflow was removed from `main` after verification.

## Current production condition

- Baby API — port 8080 healthy; canonical `dominion-ops` ownership.
- Wix Agent — port 8082 healthy on the original manually managed image; record-only mode.
- Dominion Web — port 8090 healthy on original `desktop-tutorial` ownership.
- n8n — port 5678 healthy; approved automation only.
- Alpha Engine — port 8787 healthy; paper-only.
- Caddy, Gatekeeper, Store, Conductor, Guardian, Sentinel, Juris, Alchemist, and Gemini remain active under existing controls.

## Current active work

### Stage 2F-W1 — Isolated Wix failure diagnosis

**Goal:** Reproduce and classify the canonical Wix image's `/ready` failure without stopping or modifying the healthy production Wix container or its live volumes.

Required behavior:

1. Use the approved canonical Wix image only.
2. Start it under an isolated project, loopback test port, and temporary copied data/log volumes.
3. Never attach the production Wix volumes read/write.
4. Keep secret values and raw logs out of GitHub reports.
5. Classify only bounded error signals and health results.
6. Remove the isolated container, network, and temporary volumes after the test.
7. Verify production Wix, Baby API, Dominion Web, n8n, Alpha, and Conductor remain HTTP 200.
8. Do not authorize another full cutover until the canonical Wix image passes isolated `/ready` and stability gates.

## Blocked until Wix diagnosis and correction pass

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