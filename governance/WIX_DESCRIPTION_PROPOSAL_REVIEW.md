# Wix Description Proposal Quality Review

**Human authority:** Dewayne Singleton  
**Scope:** Product-description correction work  
**Rule:** No full-catalog Wix mutation is authorized by this record.

## Proposal V1 — technically valid, content vetoed

Evidence: workflow run `29891005124` and private artifact `dominion-wix-catalog-description-proposal`.

The V1 workflow produced 62 revision-locked proposals, but direct quality review found only **8 normalized body templates** across 62 descriptions; the most-used template appeared **23 times**.

**Decision:** V1 is rejected and must not be applied to Wix.

## Proposal V2 — passed for limited canary

Evidence: workflow run `29891782530` and private artifact `dominion-wix-catalog-description-proposal-v2`.

V2 produced 62 revision-locked proposals across ten product categories. Automated gates confirmed:

- all product IDs, names, current-description hashes, and revisions are present;
- every title is embedded;
- all variant counts and SKU coverage are present;
- all proposed hashes are unique and differ from current descriptions;
- generated text remains within the bounded length contract;
- unsupported generated marketing phrases are absent;
- no brand or SEO change is proposed;
- no Wix or production mutation occurred during proposal generation.

Direct artifact review found materially improved product-specific copy based on exact title facts, product category, and live variant/SKU counts. Some category-level structure remains repetitive, so V2 is approved only for a controlled three-product canary rather than the full 62-product rollout.

## Three-product canary — prepared, human execution required

- Engine commit: `afbd89cc7f408e20e0f29f7dc5b9800eaaa1a388`
- Workflow commit: `121ccc73d93c9117a080fbaacf78b573fb697b33`
- Workflow: `Production Wix Description Canary`
- Authorization: `APPLY_WIX_DESCRIPTION_CANARY`
- Scope: exactly three products representing charging, phone-case, and audio categories.

The canary must:

1. Regenerate V2 from current live catalog data.
2. Fail closed on product revision or current-description hash drift.
3. Store full prior descriptions in a root-only `0600` rollback file on the VM.
4. Update only `plainDescription` for the three approved product IDs.
5. Verify new description hashes and incremented revisions.
6. Roll back every applied description if any write, verification, container, or protected-health gate fails.
7. Leave inventory, orders, variants, SKUs, prices, media, brands, SEO, containers, databases, networks, volumes, and DNS unchanged.

## Current gate

1. Human runs the three-product canary.
2. Verify terminal workflow evidence and rollback state.
3. Perform a read-only API and storefront rendering check on the three products.
4. Do not authorize the remaining 59 duplicate-description products until the canary passes review.
