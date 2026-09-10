# Status

State: RECONCILED — WITH OPEN BLOCKERS

The registry has been reconciled against live foundation-vm evidence
(workflow run 34448533182, 2026-09-10), satisfying step 1 of the recovery
sequence in `governance/runtime/2026-08-15-containment-record.md`. It now
records 62 services, up from a 7-entry container-only seed.

Complete: runtime inventory reconciliation, lifecycle state, truth state,
port attribution to the limit the evidence supports.

Not complete: accountable agent assignment (`owner_agent_id` is null
throughout), rollback references, repository paths for most services, the
dependency graph, and CI enforcement of this registry.

Open blockers recorded as BLOCKED or UNKNOWN:

- `nemotron-listener-11435` — a listener occupies a port the governance
  contract declares must be absent. Containment breach.
- `dominion-system-integrity` — the agent that enforces that contract is
  in a failed state.
- `caddy-upstream-5120` — Caddy forwards a public route to a dead port.
- `unattributed-listeners` — eight listening ports have no identified
  owner, one of which (8200) collides with the Council Node bind port.
- `dominion-growth-engine` — a registered timer with no observed service unit.

These remain BLOCKED or UNKNOWN until evidence proves otherwise. They are
not assumed benign and not assumed absent.
