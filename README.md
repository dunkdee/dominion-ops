# Dominion Operations

Private operations, governance, automation, and deployment repository for the Dominion ecosystem.

## Operating rule

**Cash flow → Systems → Scale.** No agent or workflow may claim completion without recorded evidence, and no unsupported model output may become an irreversible action.

## Control-plane foundation

- [`governance/SYSTEM_CONSTITUTION.md`](governance/SYSTEM_CONSTITUTION.md) — non-negotiable system rules
- [`governance/authority_matrix.json`](governance/authority_matrix.json) — default-deny action authority
- [`governance/five_council_policy.json`](governance/five_council_policy.json) — independent final-defense review
- [`governance/incident_learning_policy.json`](governance/incident_learning_policy.json) — failure-to-control learning loop
- [`governance/legal_evidence_policy.json`](governance/legal_evidence_policy.json) — legal evidence and hold behavior
- [`agents/registry.json`](agents/registry.json) — agent identity, lifecycle, permissions, and escalation
- [`architecture/CONTROL_PLANE.md`](architecture/CONTROL_PLANE.md) — control-plane architecture
- [`operations/INCIDENT_RESPONSE.md`](operations/INCIDENT_RESPONSE.md) — incident response and closure
- [`scripts/validate_control_plane.py`](scripts/validate_control_plane.py) — deterministic CI validation

Run locally:

```bash
python3 scripts/validate_control_plane.py
```

## Current boundary

Governance contracts do not grant new production authority. Existing runtime blocks, human approval gates, Wix cutover requirements, and secret-handling rules remain in force.
