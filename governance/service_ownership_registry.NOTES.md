# Registry Evidence Notes

The registry is reconciled against two read-only passes over foundation-vm,
both ending `MUTATIONS_PERFORMED=0`:

- `foundation-vm-inventory.yml`, run 34448533182, 2026-09-10T07:09:14Z —
  `evidence/foundation-vm/inventory-20260910.md`
- `foundation-vm-attribution.yml`, run 34458046789, 2026-09-10T08:58:25Z —
  `evidence/foundation-vm/attribution-20260910.md`

The second pass ran privileged and captured the process-to-port mapping the
first deliberately omitted.

## How truth_state is assigned here

- `VERIFIED` — read directly off the VM: systemd unit state, container state,
  and container ports published by `docker ps`.
- `INFERRED` — the repository declares the port and the port is listening, but
  no pid was captured for it. This was true of every systemd port after the
  inventory pass; the attribution pass promoted the ports it actually proved by
  reading the owning pid and cgroup. An INFERRED port has **not** been proven
  and must not be quoted as fact.
- `UNKNOWN` — no evidence attributes the asset to anything.
- `BLOCKED` — a governance invariant is violated, or the unit is failed.

Health probes do not raise truth_state. A probe proves that something answers
on a port, never which unit answers, and the probe labels were chosen by the
inventory script before it ran.

## Port attribution sources

Most port-to-service attributions come from `buddy_core/sentinel.py`
(`PORT_MANIFEST` and `SERVICES`), with the remainder from
`buddy_core/config/FOUNDER_OPERATING_CONTEXT.md`,
`governance/system_integrity_agent.json`, `config/command-center.env.example`,
and the services' own bind calls. These are repository declarations, not VM
evidence.

## Fields that must not be silently filled

- `owner_agent_id` — null for all 62 services. Accountable ownership has not
  been assigned and must not be inferred from a service's name.
- `rollback_reference` — null throughout.
- `repository_path` — set only where a source tree was actually located.
- complete dependency graph
- data classification and secret access boundaries

## obsidian_home

The schema requires a non-empty `obsidian_home` on every service. These paths
are **declarations of where documentation shall live**, following the
convention of the original seed entries. They were not verified against the
Obsidian vault, and the 2026-08-15 containment record leaves Obsidian stores
unreconciled with no synchronization authorized.
