# Dominion Control-Plane Runtime

## Current status

**Current mode:** `shadow_only`  
**Current stage:** Stage 3 — Controlled Shadow Operations

Stage 2 established deterministic runtime primitives. Stage 3 adds controlled cohort validation, canonical proposal envelopes, independently bound Five Council reviews, and verified-input shadow revenue analysis. It still grants no production authority.

The runtime does not start Obsidian or Browser Agents, publish content, contact customers or claimants, trade live, move money, sign or file documents, or deploy production changes.

## Runtime flow

```text
Action or proposal
  -> Governor default-deny evaluation
  -> Evidence and constraint checks
  -> Legal fail-closed check
  -> Canonical proposal envelope
  -> Independently bound council reviews
  -> Human gate when required
  -> ALLOW, HOLD, DENY, APPROVE, or VETO record
  -> Hash-chained evidence record
```

An `ALLOW` result means the request satisfies the policy contract. In `shadow_only` mode, `execution_authorized` remains false because external execution is disabled.

## Components

### Governor

`control_plane/governor.py` reads the authority matrix, agent registry, Five Council policy, and activation gates. Unknown actors and actions are denied. Missing evidence, unresolved law, unsatisfied controls, insufficient approvals, and active rollout blocks fail closed.

### Evidence ledger

`control_plane/ledger.py` writes canonical JSONL records linked by SHA-256 hashes. Verification detects content alteration, deletion, reordering, and broken linkage. Production adoption still requires storage-level retention, restricted identities, backups, and write-once controls.

### Five Council review

`control_plane/council.py` provides threshold aggregation. `control_plane/proposals.py` adds canonical proposal envelopes and cryptographically bound independent reviews. The proposer cannot review its own proposal. Reviewer roles must match council domains. Law and Security vetoes remain authoritative.

### Agent onboarding and cohorts

`control_plane/onboarding.py` validates individual candidate specifications. `control_plane/cohort.py` validates controlled shadow assignments for registered agents. Neither component edits `agents/registry.json`, changes lifecycle states, starts runtimes, or grants production authority.

### Revenue analysis

`control_plane/revenue_simulation.py` performs deterministic funnel simulation. `control_plane/shadow_revenue.py` compares baseline and candidate scenarios using source-declared observations. Synthetic inputs can only return `TEST_ONLY`; verified historical inputs can at most become `ELIGIBLE_FOR_COUNCIL_REVIEW`.

## Canonical CLI

```bash
python3 scripts/control_plane.py validate-cohort \
  --input agents/cohorts/stage3_core_shadow.json

python3 scripts/control_plane.py prepare-proposal \
  --input runtime/examples/stage3_proposal.json

python3 scripts/control_plane.py shadow-revenue \
  --input runtime/examples/shadow_revenue_experiment.json

python3 scripts/control_plane.py verify-ledger \
  --ledger runtime/ledger/local.jsonl
```

## Promotion boundary

No runtime component may enter autonomous canary or production execution until every requirement in `governance/runtime_activation_gates.json` is closed with evidence. The existing Wix isolation diagnosis and operational blocks remain authoritative.

Promotion requires a separate reviewed pull request, passed regressions, threat-model review, rollback evidence, proposal-bound council review at the applicable risk, and recorded Human Overseer approval.
