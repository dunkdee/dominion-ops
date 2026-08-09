# Dominion Brain Pack

**Authority:** Dewayne Singleton, Human Overseer  
**Canonical source:** GitHub (`dunkdee/dominion-ops`)  
**Operational mirror:** Obsidian / Dominion-Brain  
**Live-state authority:** verified production runtime evidence

## Purpose

This directory is the version-controlled knowledge pack that all Dominion agents and the Obsidian operational brain consume. It does not grant production authority and it must never contain secrets, customer PII, private keys, tokens, `.env` values, or raw customer records.

## Required reading order

1. `governance/SYSTEM_CONSTITUTION.md`
2. `governance/DOMINION_OPERATING_MAP.md`
3. `governance/AGENT_OPERATIONS_STATE.md`
4. `governance/RUNTIME_ALIGNMENT.md`
5. `agents/registry.json`
6. `governance/authority_matrix.json`
7. `brain/agent-team-current-state.md`
8. Applicable vertical contract / runbook / incident record

## Truth model

- **GitHub:** law, policy, code, contracts, reviewed operating knowledge.
- **Obsidian:** human-readable operational knowledge and coordination mirror.
- **Production runtime:** authoritative only for verified live state.

When these disagree, agents must report the conflict and stop consequential execution until reconciled.

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

- Email Drip production remains HOLD until RC3 review, merge, deployment, and a separate live-activation GO.
- Meta/Facebook remains `RESTRICTED_HOLD`.
- Proposal Queue is protected and must remain untouched unless explicitly reopened.
- Trading remains paper-only unless explicitly authorized otherwise.
- Obsidian and Browser Agent **activation** remain blocked by the current Stage 2F-W1 Wix gate. Preparation and generation of the brain pack are allowed; activation is not.
