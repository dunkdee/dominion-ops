# Ethical Revenue and Impact Pipeline

## Status

**STAGED_NOT_ACTIVATED.** This is a shared control contract for the first safe part of Dominion's revenue and impact loop:

```text
measure permitted evidence
→ create internal draft
→ human decision
→ record truthful outcome and learning
```

It is not a lead-generation engine, campaign launcher, checkout system, publishing system, or customer-contact tool. It cannot publish, schedule content, message a prospect or customer, accept client data, set a price, enable checkout, spend money, move money, change credentials, or change production configuration.

## Current governed scope

The contract is intentionally limited to the modes already recorded in `governance/verticals.json`:

| Vertical | Allowed mode | Allowed output now |
| --- | --- | --- |
| DominionHealing Wix store | record-only | factual health, order-state, and measurement records |
| Content and traffic | draft-only | internal content drafts and approval dockets |
| Analytics services | shadow-only | internal analysis, benchmarks, and measurement drafts |

A draft is not approved content. A measurement record is not a revenue claim. An approval docket is not approval. An outcome record is not permission to repeat or scale an action.

## Required record discipline

Every pipeline record must preserve:

- mission and vertical IDs;
- evidence references and a truth state;
- facts separately from assumptions and unknowns;
- limits on what the evidence can support;
- an approval reference or an explicit hold;
- the result and a follow-up owner.

Use only these truth states: `VERIFIED`, `INFERRED`, `UNKNOWN`, and `BLOCKED`. Revenue becomes `VERIFIED` only after posted funds, known obligation, delivery, and reconciliation evidence exist.

## Approval boundary

No agent can approve a pipeline action. Any external effect needs a separate, recorded Human Overseer approval and must also satisfy the applicable vertical launch gates, authority-matrix action, independent review requirements, rollback plan, and verification plan.

This contract adds no approval and does not activate a vertical or runtime setting.

## Validation

Run:

```bash
python3 scripts/validate_ethical_revenue_impact_pipeline.py
python3 -m unittest tests/test_ethical_revenue_impact_pipeline.py
```

The validator fails closed if the pipeline is marked active, if its allowed modes drift from the vertical registry, if an external authority is enabled, if a prohibited action is omitted, or if the human approval boundary is weakened.
