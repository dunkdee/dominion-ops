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
