# Stage 3 — Controlled Shadow Operations

## Purpose

Stage 3 exercises the Dominion control plane against approved evidence while preserving a hard boundary against external execution. It is an observation, validation, and review stage—not a production activation stage.

## Invariants

- Runtime mode is `shadow_only`.
- External execution is disabled.
- Registry mutation and lifecycle promotion are disabled.
- An `ALLOW` policy decision does not authorize an external action.
- Obsidian runtime and Browser Agents remain blocked.
- Publishing, customer or claimant contact, spending, money movement, live trading, production deployment, signing, and filing remain blocked.
- Synthetic revenue fixtures can only produce `TEST_ONLY`.
- Verified historical inputs can at most become `ELIGIBLE_FOR_COUNCIL_REVIEW`.

## Controlled cohort

`agents/cohorts/stage3_core_shadow.json` defines the first shadow cohort. The manifest binds each agent to:

- duties already present in the canonical registry;
- a default-deny tool allowlist;
- explicit data classifications;
- a named escalation path;
- no lifecycle change.

Validation creates a report only. It does not start an agent, mutate the registry, or promote any lifecycle state.

## Proposal-bound council review

A proposal is canonicalized before review. The proposal envelope records:

- proposer;
- requested authority action and risk;
- evidence, assumptions, and unknowns;
- rollback plan;
- success criteria;
- a cryptographic proposal hash.

Each council review is independently bound to that proposal hash and to a registered reviewer whose role matches the council domain. The proposer cannot review its own proposal. Review tampering or proposal mismatch fails closed.

## Shadow revenue experiment

The shadow revenue engine compares a baseline and candidate funnel using deterministic arithmetic. Every experiment declares its source type:

- `SYNTHETIC_TEST` — CI and development only; never supports promotion.
- `HISTORICAL_VERIFIED` — requires evidence references and may only reach council review.

The engine does not generate leads, contact customers, publish content, charge a payment method, modify a storefront, or deploy code.

## Evidence flow

```text
Cohort manifest
  -> cohort validation report
  -> proposal envelope
  -> independent bound reviews
  -> council aggregate
  -> shadow revenue report
  -> append-only evidence ledger
  -> Human Overseer review
```

## Promotion boundary

Stage 3 does not authorize canary or production operation. A future promotion requires all activation-gate evidence, including closure of the existing Wix isolation diagnosis, reviewed threat model, tested rollback, verified real inputs, council review, and recorded Human Overseer approval.
