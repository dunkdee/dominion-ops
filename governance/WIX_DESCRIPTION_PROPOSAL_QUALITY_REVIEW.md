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

Direct artifact review found materially improved product-specific copy based on exact title facts, product category, and live variant/SKU counts. Some category-level structure remains repetitive, so V2 was approved only for a controlled three-product canary rather than the full 62-product rollout.

## Three-product canary — failed closed and rolled back

Evidence: workflow run `29894579230`.

The canary targeted exactly three approved products representing charging, phone-case, and audio categories. Wix accepted the first update and incremented its product revision from `6` to `7`, but the returned `plainDescription` raw hash did not match the submitted V2 HTML hash. The engine stopped before touching the remaining two products.

Rollback evidence:

- rollback performed: `true`;
- rollback success: `true`;
- restored product: `31ab3699-504b-468c-a314-c7e5737b6683`;
- root-only backup mode: `0600`;
- net product changes: `0`;
- inventory, orders, variants, SKUs, prices, media, brands, SEO, containers, databases, networks, volumes, and DNS remained unchanged;
- Baby API, Wix Agent, Dominion Web, n8n, Alpha Engine, and Conductor remained HTTP 200.

**Decision:** The original canary workflow is retired and must not be rerun. The failure is treated as a Wix `plainDescription` canonicalization/serialization verification issue, not approval for a broader rollout.

## Round-trip canonicalization probe — active gate

- Probe engine commit: `5cca9efbf98fb7f718ac51fe8d2c4f961e16a617`
- Workflow commit: `951622bcf1d1420d855710869f76577eaa3afa2f`
- Workflow: `Production Wix Description Round-Trip Probe`
- Authorization: `PROBE_WIX_DESCRIPTION_ROUNDTRIP`
- Scope: one previously targeted charging product only.

The probe must:

1. Regenerate V2 from current live catalog data.
2. Fail closed on live revision or current-description hash drift.
3. Save the original description in a root-only `0600` rollback file.
4. Temporarily write the V2 description to one product.
5. Measure submitted versus Wix-returned raw hashes, semantic text hashes, text lengths, tag counts, and revision movement without publishing full descriptions.
6. Always restore the original description before completion.
7. Use an independent fallback rollback if the primary probe process fails.
8. Leave zero persistent product changes and keep every protected service HTTP 200.

## Current gate

1. Human runs the one-product round-trip probe.
2. Verify terminal workflow evidence, semantic-text equivalence, tag canonicalization, and rollback success.
3. Correct the canary verification contract using the observed Wix behavior.
4. Do not authorize a persistent canary or the remaining 59 products until the round-trip probe passes and the corrected canary is reviewed.
