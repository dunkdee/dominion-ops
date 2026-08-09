# Dominion Agent Team — Current Operating State

**Prepared:** 2026-08-09  
**Authority:** Dewayne Singleton  
**Purpose:** Shared current-state briefing for all Dominion agents.  
**This file does not grant new authority.**

## Command structure

- **Human Overseer — Dewayne Singleton:** final approval for protected actions.
- **Coordinator:** sequences work, reconciles evidence, prevents conflicting changes.
- **Conductor:** routes approved work and tracks execution state.
- **Governor / Policy Gate:** applies default-deny authority rules.
- **Guardian:** runtime drift and regression detection.
- **Sentinel:** independent runtime verification and challenge.
- **Juris:** legal/compliance review; no signing, filing, or legal representation.
- **Five Council:** independent review across Truth/Evidence, Law/Governance, Security/Risk, Engineering/Reliability, Business Value/Human Impact.
- **Engineering:** implementation within approved scope.
- **Research:** read-only evidence gathering unless separately authorized.
- **Revenue Operations:** analysis, measurement, and approved funnel operations within effective authority; no autonomous protected external action.

## Named operational agents/services that require reconciliation into the registry

The current governance map explicitly notes that production contains more named services than the machine-readable registry. These include, among others:

- Buddy
- Alchemist
- Alpha Engine
- Gatekeeper
- Gemini
- store / commerce operators
- KDP / Email Drip operators
- surplus operators
- social/content/video operators
- watchdog / health / healer services
- platform and Wix operators

Each live component must be classified as exactly one of:

1. registered independent agent;
2. worker owned by a registered agent;
3. shared platform service;
4. standby / rollback component;
5. duplicate to consolidate;
6. obsolete component to retire.

No live component may remain ownerless.

## Current revenue and production boundaries

### Email Drip

- RC3 canonicalization/hardening is under review in PR #102.
- Production send mode is contained in HOLD.
- PrivateEmail SMTP is the controlled production rail.
- No automatic SendGrid fallback.
- Free Audit remains zero-email hold.
- Live activation requires exact-SHA deployment, production-faithful preflight, a current live-authorization gate, and acceptance verification.

### Meta / Facebook

`RESTRICTED_HOLD`.

No automated login, re-authentication, posting, ads, Pixel/CAPI restoration, replacement-account behavior, or workaround activity until restriction scope is legitimately resolved.

### Proposal Queue

Protected and closed. Do not mutate, disable, or restart unless Dewayne explicitly reopens the work.

### Trading

Paper-only. No live-money execution without explicit approval and applicable production gates.

### Obsidian / Browser Agents

**Current truth state: `UNKNOWN`.**

Evidence is contradictory and time-separated:

- older `governance/RUNTIME_ALIGNMENT.md` text records an unresolved Stage 2F-W1 Wix prerequisite;
- later August 1 production evidence records the Wix healthcheck correction deployed with `DEPLOY_GATE=PASS` and Wix classified `ACTIVE — healthy`;
- prior production inventory records `obsidian-remote` running healthy with Syncthing present, but the vault itself stale and not proven connected to the full control plane;
- an authenticated exact-SHA Obsidian verification/deployment workflow exists on `main`.

Therefore neither “blocked” nor “fully active” is currently justified without a fresh live verification. Preparation, review, and generation of the brain pack may proceed. Production claims about Obsidian require current runtime evidence.

## Shared operating doctrine

1. Inventory before building.
2. Verify before claiming.
3. Reuse before duplicating.
4. GitHub carries versioned code, governance, contracts, and reviewed brain content.
5. Obsidian mirrors operational knowledge; it does not override GitHub policy.
6. Runtime evidence decides live-state truth.
7. Consequential production work requires bounded scope, rollback, and post-action verification.
8. No secrets or customer PII in GitHub, Obsidian, prompts, screenshots, or reports.
9. Fail closed on ambiguous configuration, corrupted state, missing suppression data, or unknown send history.
10. No agent may expand its own authority.
11. Truth states are exactly `VERIFIED`, `INFERRED`, `UNKNOWN`, or `BLOCKED`.

## Current priority queue

1. Finish RC3 Email Drip hardening and current independent review findings.
2. Merge only exact reviewed GitHub SHAs with passing CI.
3. Reconcile current Obsidian live state from production evidence; do not rely on the stale Wix block.
4. Render and publish the governed brain generation while preserving `Dominion-Operator-Notes`.
5. Reconcile named agents/services into `agents/registry.json` ownership classes and validate the control-plane chain.
6. Validate GitHub ↔ Obsidian ↔ runtime parity without copying secrets.
7. Activate revenue execution lanes only inside their approved contact, pricing, publishing, payment, and compliance gates.

## Required report format

```yaml
agent:
duty:
evidence:
result:
risks:
next_action:
human_approval_required:
```

If evidence is insufficient, `result` must be `UNKNOWN`.