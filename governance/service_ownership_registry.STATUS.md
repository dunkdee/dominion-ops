# Status

State: RECONCILED AND ATTRIBUTED — ONE OPEN DEFECT

Reconciled against live foundation-vm evidence in two passes: inventory
(run 34448533182) and privileged listener attribution (run 34458046789).
This completes step 1 of the recovery sequence in
`governance/runtime/2026-08-15-containment-record.md`.

64 services, up from a 7-entry container-only seed. Every listening TCP port
on the host now has a pid, and all but four have an owning unit or container.

Complete: runtime inventory, process-to-port attribution, lifecycle state,
truth state, the 11435 question, the integrity-agent question, the 8200
Council Node conflict.

Not complete: accountable agent assignment (`owner_agent_id` is null
throughout), rollback references, repository paths for services whose source
trees live outside dominion-ops, the dependency graph, and CI enforcement.

## Open

- `stray-ollama-11435` — **BLOCKED.** An unmanaged second `ollama serve`,
  started by hand over SSH on 2026-09-09 21:16:51 UTC, occupies a port the
  contract reserves as absent. Not Nemotron; containment held. Removal
  requires a governed mutation lane.
- `caddy-upstream-5120` — **BLOCKED.** Caddy forwards
  `tiktok.dominionhealing.org` to a port nothing listens on.
- `unattributed-listeners` — **UNKNOWN.** Four ports (5056, 5103, 5110, 8888)
  have a pid but no captured unit.
- `gemini-server` — **UNKNOWN.** The repository says removed, the VM says
  running, and two active units claim port 5055.
- `dominion-growth-engine` — **UNKNOWN.** Timer registered, service unit never
  observed.

## Resolved, previously open

- `dominion-system-integrity` is **healthy**, not malfunctioning. It exits 2 on
  any defect and the unit is `Type=oneshot` without `SuccessExitStatus`, so
  systemd renders a DEGRADED verdict as `failed`. One defect of twenty checks.
- Port **8200** belongs to `dominion-3d-dashboard.service`, running since
  2026-06-07. Council Node must be assigned a different port.
- Port **8091** is the `dominion-command-center` container on host networking.
- The storefront on **5090** has no Caddy route. The public storefront is
  `dominion-store.service` on **5080**.
