# Wix Storefront Hardening State

**Human authority:** Dewayne Singleton  
**Priority:** Revenue-ready storefront without unreviewed production drift  
**Rule:** No full-catalog, layout, navigation, policy, publishing, checkout, fulfillment, or pricing mutation is authorized by this record.

## Verified catalog state

- Wix catalog API and Wix Agent are operational.
- 94 visible products and 246 variants were mapped.
- Product names, descriptions, revisions, slugs, prices, media, main images, options, variants, and SKUs are present.
- All 94 products lack explicit brand metadata.
- 62 products belong to 24 duplicate-description groups.
- Proposal V1 was rejected for repetitive wording.
- Proposal V2 passed structural and direct quality review only for a controlled canary.

## Description write-path state

The three-product canary failed closed on its first product because Wix returned a canonicalized `plainDescription` whose raw hash differed from the submitted V2 string.

- Wix accepted the partial update and incremented the product revision.
- The canary stopped before the remaining two products.
- The first product was restored from a root-only rollback copy.
- Net persistent product changes were zero.
- The failed canary workflow was removed.
- The only approved description write test is the mandatory-rollback one-product round-trip probe.

## Storefront layout and wording review

A new read-only workflow is prepared:

- Workflow: `Production Wix Storefront Layout Audit`
- Authorization: `AUDIT_WIX_STOREFRONT_LAYOUT_READ_ONLY`
- Script commit: `0e2a06e8a2647f3a23aaa81f649fc90156bbd838`
- Workflow commit: `f4f988cf94a2c40213ae0825b55ed93b24a84b5a`

The audit must:

1. Discover the live Wix published URL using the official site-URLs API, with public-domain fallbacks only.
2. Capture private desktop and mobile screenshots.
3. Inspect homepage, store/navigation links, representative product pages, contact/about pages, footer policies, headings, calls to action, titles, metadata, image alt text, button/link labels, mobile overflow, console errors, and placeholder wording.
4. Avoid form submissions, button clicks, cart changes, checkout, authentication, Wix management mutations, publishing, and customer/order data.
5. Confirm protected service health and unchanged container inventory before and after.
6. Publish only a redacted summary to the audit branch; full visible text and screenshots remain in the private artifact.

## Wording standard

Any later wording change must be:

- specific about what the store sells and who it serves;
- factually bounded by verified business and product information;
- free of invented specifications, warranties, shipping promises, certifications, medical claims, and unsupported superlatives;
- action-specific in calls to action;
- consistent across header, homepage, product pages, footer, contact, and policy pages;
- usable on mobile without clipping or horizontal overflow;
- reviewed before publication.

## Current gates

1. Run and review the read-only storefront layout audit.
2. Run and review the mandatory-rollback description round-trip probe.
3. Prepare a written correction plan separating editor/layout changes from catalog-content changes.
4. Apply no changes until each target has a rollback path and explicit human approval.
5. Do not authorize the remaining 59 duplicate-description products until the canary and storefront rendering checks pass.
