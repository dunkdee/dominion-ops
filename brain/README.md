# Dominion Brain Pack

**Authority:** Dewayne Singleton, Human Overseer  
**Canonical source:** GitHub (`dunkdee/dominion-ops`)  
**Operational mirror:** Obsidian / Dominion-Brain  
**Live-state authority:** verified production runtime evidence

## Purpose

This directory is the version-controlled knowledge pack that Dominion agents and the Obsidian operational brain consume. It does not grant production authority and it must never contain secrets, customer PII, private keys, tokens, `.env` values, or raw customer records.

## Required reading order

The brain mirrors the exact startup order defined by `governance/DOMINION_OPERATING_MAP.md`:

1. `governance/SYSTEM_CONSTITUTION.md`
2. `STATE.md` — verify freshness before relying on it
3. repository `README.md`
4. `agents/registry.json`
5. `governance/authority_matrix.json`
6. `governance/five_council_policy.json`
7. `governance/incident_learning_policy.json`
8. `governance/verticals.json`
9. `architecture/CONTROL_PLANE.md`
10. applicable vertical contract, SOP, runbook, deployment document, and current incident record
11. verified runtime inventory/live evidence before production claims

`governance/DOMINION_OPERATING_MAP.md`, current agent-operation records, and current runtime-alignment records remain available in the mirror as navigation and reconciliation documents; they do not replace the required order above.

## Truth model

- **GitHub:** law, policy, code, contracts, reviewed operating knowledge.
- **Obsidian:** human-readable operational knowledge and coordination mirror.
- **Production runtime:** authoritative only for verified live state.

When these disagree, agents must report the conflict and stop consequential execution until reconciled.

Truth states are exactly: `VERIFIED`, `INFERRED`, `UNKNOWN`, or `BLOCKED`.

## Generated versus operator-owned knowledge

Generated Dominion-Brain files are governed mirrors and may be replaced by a later reviewed generation. Durable runtime observations, incidents, lessons, current-state notes, and change logs belong in the sibling `Dominion-Operator-Notes/<agent-id>/` tree. Each generated agent home contains bridge notes pointing to that preserved operator-owned location.

The renderer creates only a fresh staging generation. A separate governed synchronization step publishes a validated generation into the operational vault. Failed render attempts are removed rather than partially published.

## Agent reporting contract

Every consequential agent report must include:

- `agent`
- `duty`
- `evidence`
- `result`
- `risks`
- `next_action`
- `human_approval_required`

No agent may claim completion without retrievable evidence.

## Current protected boundaries

- Email Drip production remains HOLD until RC3 review, merge, exact-SHA deployment, production-faithful preflight, and controlled acceptance complete.
- Meta/Facebook remains `RESTRICTED_HOLD`.
- Proposal Queue is protected and must remain untouched unless explicitly reopened.
- Trading remains paper-only unless explicitly authorized otherwise.
- **Obsidian activation state is `UNKNOWN` pending current live verification.** Historical evidence conflicts: an older runtime-alignment document records a Wix prerequisite, while later August 1 evidence records Wix repaired and healthy and prior inventory records `obsidian-remote` healthy but the vault stale. No agent may infer current Obsidian activation from either stale record alone.