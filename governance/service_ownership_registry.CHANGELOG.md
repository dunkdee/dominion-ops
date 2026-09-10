# Changelog

## 1.0.0 — initial schema and seed

- Added the initial service ownership registry schema.
- Seeded verified production services from the existing ecosystem audit.
- Added the safe implementation and reconciliation sequence.
- Preserved unresolved ownership and rollback fields as explicit blockers.

## 1.0.0 (data revision) — 2026-09-10 runtime reconciliation

Reconciled against read-only foundation-vm inventory (workflow run
34448533182, `MUTATIONS_PERFORMED=0`). Schema unchanged.

- Grew the registry from 7 container-only entries to **62 services**: 11
  containers, 35 systemd units, 13 timer-driven units, 2 unattributed
  runtime assets, 1 dead reverse-proxy route.
- Introduced `INFERRED` for every systemd port binding. The inventory ran
  `ss` without `-p`, so no process-to-port mapping was captured and no
  systemd port can be called VERIFIED.
- Recorded three BLOCKED entries: the TCP 11435 containment breach, the
  failed `dominion-system-integrity` agent, and the dead Caddy upstream
  on 5120.
- Corrected the seed: `dominion-web` is 8090 (not 3000), `wix-agent` is
  8082 (not 8090), `dominion-db` publishes 5432, `baby-api` is 8080 (not
  8001), `movie-generator` is 8001 (not 20202).
- Resolved Alchemist (5050) and AuricEdge (9380) as real, managed systemd
  units declared in `buddy_core/sentinel.py` — not stale, not unowned.
- Recorded the 8200 port conflict against the Council Node bind port.

## 1.0.0 (data revision) — 2026-09-10 listener attribution

Folded in the privileged attribution pass (run 34458046789,
`MUTATIONS_PERFORMED=0`). Schema unchanged. 62 services to 64.

- **TCP 11435 attributed and reclassified.** It is a second `ollama serve`
  (pid 3192050) started by hand over SSH at 2026-09-09 21:16:51 UTC, living in
  a user login session scope, reparented to init. It is NOT Nemotron:
  `dominion-nemotron.service` is loaded/inactive/disabled and containment
  held. Classification UNAUTHORIZED / ORPHANED. The policy was correct, not
  stale — it detected this in 19 seconds.
- **The integrity agent is healthy.** ExecMainStatus=2 with exactly one defect
  of twenty checks, and its deployed script and contract are byte-identical to
  the repository copies. `Type=oneshot` without `SuccessExitStatus` renders a
  DEGRADED verdict as `failed`.
- **Port 8200 is `dominion-3d-dashboard.service`**, up since 2026-06-07.
  Council Node cannot use it.
- **Port 8091 is `dominion-command-center`** running with `network_mode=host`,
  which is why the container publishes no ports yet serves it.
- **The 5090 storefront has no Caddy route.** `store.dominionhealing.org`
  proxies to 5080, `dominion-store.service`. Its source tree is not a git
  checkout, so no deployed SHA exists.
- Added `google-ops-agent-otel` (20201) and `google-ops-agent-fluentbit`
  (20202), correcting the seed's attribution of 20202 to movie-generator.
- Unattributed listeners narrowed from eight to four.
- Alchemist, AuricEdge and Caddy promoted INFERRED to VERIFIED on proven pids.
