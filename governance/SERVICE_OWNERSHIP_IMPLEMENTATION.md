# Service Ownership Implementation Sequence

## Purpose

Convert the Dominion operating map into an enforceable runtime ownership system without changing production authority.

## Sequence

1. Capture the complete production inventory from Docker, systemd, cron, reverse-proxy routes, listening ports, and approved external integrations.
2. Normalize each component into `governance/service_ownership_registry.json`.
3. Resolve every `owner_agent_id` against `agents/registry.json`.
4. Resolve every `vertical_id` against `governance/verticals.json`.
5. Verify dependency edges and reject circular dependencies unless an explicit exception is approved.
6. Assign one Obsidian home, one health signal, one lifecycle state, and one rollback reference to every active component.
7. Flag orphan services, duplicate owners, unverified production states, missing evidence, and stale captures.
8. Produce a reconciliation report comparing production runtime state against GitHub declarations.
9. Obtain Engineering, Security, Governance, Business, and Human review before modifying runtime behavior.
10. Apply approved corrections through reversible, idempotent changes with post-change evidence.

## Fail-closed conditions

A component may not be promoted or materially changed when any of the following is unresolved:

- no accountable owner;
- no lifecycle state;
- no evidence record;
- unknown data classification;
- missing rollback procedure;
- dependency cycle;
- policy contradiction;
- production authority ambiguity;
- stale runtime evidence;
- repository and runtime disagreement without an approved reconciliation decision.

## Required validators

CI must eventually enforce:

- JSON Schema validity;
- unique `service_id` values;
- valid agent and vertical references;
- one accountable owner per active service;
- no orphan dependency references;
- cycle detection;
- production services require VERIFIED evidence;
- production services require a health signal and rollback reference;
- evidence freshness threshold;
- Obsidian home uniqueness or explicitly declared shared ownership;
- prohibited authority combinations;
- reconciliation report freshness.

## Current boundary

The initial registry is a verified runtime seed, not a declaration that all ownership questions are resolved. Null `owner_agent_id` values and null rollback references are intentional blockers that must remain visible until evidence supports resolution.
