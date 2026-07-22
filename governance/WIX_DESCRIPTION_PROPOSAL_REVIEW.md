# Wix Description Proposal Quality Review

**Human authority:** Dewayne Singleton  
**Scope:** Review-only product-description correction work  
**Rule:** No Wix mutation is authorized by this record.

## Proposal V1 — technically valid, content vetoed

Evidence: workflow run `29891005124` and private artifact `dominion-wix-catalog-description-proposal`.

The V1 workflow completed successfully and produced 62 revision-locked proposals for the 62 products in 24 duplicate-description groups. All product IDs, live revisions, current-description hashes, proposal hashes, and bounded-length checks passed. No product, inventory, order, container, database, network, volume, DNS, customer data, or secret was changed.

A direct quality inspection of the private proposal found only **8 normalized body templates across 62 descriptions**. The most-used template appeared **23 times**. Product names made the final hashes unique, but the underlying copy remained repetitive and too generic for production promotion.

**Decision:** V1 is rejected. It must not be applied to Wix.

## Proposal V2 — active review stage

The proposal generator and workflow were upgraded on `main`:

- Generator commit: `4c70b0d4cd1e7d66e618e7feb517d22d03fa0a04`
- Workflow commit: `9608b2e13a7f5168167c87ffac1a31b6a2d9b6ad`
- Workflow: `Production Wix Catalog Description Proposal V2`
- Authorization: `CREATE_WIX_DESCRIPTION_PROPOSAL_V2`

V2 builds product-specific copy from exact title facts, category, live variant count, SKU coverage, current description hash, and live product revision. It rejects unsupported marketing phrases, requires every title to be embedded, and remains private-artifact-only.

## Current gate

1. Run Proposal V2.
2. Inspect the private artifact for factuality, readability, repetition, and conversion quality.
3. Do not create a Wix write workflow unless V2 passes human-quality review.
4. Any later write must fail closed on revision or current-description hash drift and must preserve a rollback copy.
