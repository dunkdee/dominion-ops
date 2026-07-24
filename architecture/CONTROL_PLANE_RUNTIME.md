# Dominion Control-Plane Runtime — Stage 2

## Status

**Mode:** `simulation_only`

This stage converts the governance contracts into deterministic runtime primitives without granting production authority. It does not start Obsidian, Browser Agents, publishing, customer contact, live trading, money movement, or production deployment.

## Runtime flow

```text
Action request
  -> Governor default-deny evaluation
  -> Evidence and constraint checks
  -> Legal fail-closed check
  -> Independent council records
  -> Human gate when required
  -> ALLOW, HOLD, or DENY decision
  -> Hash-chained evidence record
```

An `ALLOW` result means only that the submitted request satisfies the current policy contract. An executor must still be separately configured and authorized. Stage 2 contains no production executor.

## Components

### Governor

`control_plane/governor.py` reads the canonical authority matrix, agent registry, Five Council policy, and runtime activation gates. Unknown actors and actions are denied. Missing evidence, unresolved law, unsatisfied controls, insufficient approvals, and active rollout blocks produce deterministic holds or denials.

### Evidence ledger

`control_plane/ledger.py` writes canonical JSONL records linked by SHA-256 hashes. Verification detects content alteration, deletion, reordering, and broken linkage.

The hash chain is an application integrity control, not a claim of filesystem immutability. Production adoption requires restricted service identities, backups, retention, and write-once or object-lock storage where appropriate.

### Five Council aggregator

`control_plane/council.py` requires proposal-bound, independently attributable council records. Duplicate reviews and mismatched proposal hashes fail closed. Law and Security vetoes override approval counts. Critical proposals require all five approvals and recorded Human Overseer approval.

### Agent onboarding

`control_plane/onboarding.py` validates candidate specifications. It never edits `agents/registry.json`, grants production authority, or promotes candidates. A valid candidate becomes only `ELIGIBLE_FOR_SPEC_REVIEW`.

### Revenue simulation

`control_plane/revenue_simulation.py` models funnel economics with deterministic decimal arithmetic. It creates no leads, sends no messages, publishes nothing, and moves no money.

## Canonical CLI

Run from the repository root:

```bash
python3 scripts/control_plane.py simulate-revenue \
  --input runtime/examples/revenue_scenario.json \
  --ledger runtime/ledger/local.jsonl

python3 scripts/control_plane.py onboard \
  --input runtime/examples/agent_candidate.json \
  --ledger runtime/ledger/local.jsonl

python3 scripts/control_plane.py verify-ledger \
  --ledger runtime/ledger/local.jsonl
```

Action and council commands accept JSON records conforming to the schemas under `governance/schemas/`.

## Promotion boundary

No Stage 2 component may be promoted into autonomous production execution until all requirements in `governance/runtime_activation_gates.json` are closed with evidence. The existing Wix isolation diagnosis and operational blocks remain authoritative.

Promotion requires a separate pull request, passed regression tests, threat-model review, rollback evidence, Five Council review at the applicable risk level, and recorded Human Overseer approval.
