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
- Source archive SHA-256 matched the expected value.
- The local `.env` was copied into the release with mode `0600`; its hash matched the protected recovery copy.
- Recovery copies were created under `/home/malachisingleton8/.dominion-recovery/stage2c-29866812526`.
- Compose validation passed for all six declared services.
- No production container was started, stopped, recreated, or changed.
- The orphaned VM checkout remained untouched.

### Stage 2D — Independent preflight — VETOED AS DESIGNED

Evidence: workflow run `29867278124`.

- Runtime, secrets, deployment, rollback, and agent-runtime gates passed.
- Canonical Conductor, Guardian, Sentinel, and Juris were active/running.
- The governance gate vetoed because retired APIs had reactivated.
- The isolated image build was correctly skipped.
- No cutover was authorized and production containers were unchanged.

### Stage 2D-R / R2 — Reactivation tracing

Evidence: workflow runs `29868756275` and `29869539712`.

- Scheduler and worker references to `conductor-api.service` were only `After=` ordering directives and did not start it.
- Their commands ran only `scheduler.py` and `worker.py`.
- The retired names in `buddy_core/port_healer.py` occurred in a stale comment.
- No matching user cron entry was found.
- The continuing failure mechanism was the installed retired unit files using `Restart=always`.

### Stage 2D-R3 — Persistent retirement — COMPLETE

Evidence: workflow run `29874133137`.

- Root-only backups were created under `/var/lib/dominion/unit-retirement/stage2d-r3-29874133137`.
- Persistent `/dev/null` masks were installed for:
  - `alchemist-api.service`
  - `conductor-api.service`
  - `juris-api.service`
  - `dominion-port-healer.service`
- All four units verified `inactive/dead/masked` after the change.
- Canonical Caddy, Alchemist, Alpha, Conductor, Gatekeeper, Guardian, Juris, Sentinel, Store, and Gemini services remained `active/running`.
- Every protected canonical service recorded a zero restart delta over 90 seconds.
- Baby API, Wix, Dominion Web, n8n, Alpha Engine, and Conductor remained HTTP 200.
- Production container inventory was unchanged.
- No rollback was required; the retirement remains locally reversible from the recorded backups.

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

### Stage 2D-R4 — Independent gate verification and isolated builds

**Goal:** Re-run all prerequisite evidence after durable retirement and build only the protected core images without changing production execution.

Required evidence:

1. Runtime endpoints remain HTTP 200 before and after build.
2. Release `.env` remains local, regular, mode `0600`, and hash-matched.
3. Release source marker, Compose hash, and six-service manifest match the approved release.
4. Recovery `.env`, Compose copies, and R3 unit-file backups remain present.
5. All four retired units remain persistent `masked` and inactive.
6. Canonical Conductor, Guardian, Sentinel, and Juris remain active/running; Watchmen status remains reachable.
7. Only `baby-api`, `dominion-web`, and `wix-agent` images are built under isolated Stage-2D-R4 tags.
8. Running container inventory remains identical and canonical restart deltas remain zero.

## Blocked until Stage 2D-R4 evidence exists

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
