# Wix and Dominion Storefront Layout Review

**Human authority:** Dewayne Singleton  
**Audit date:** July 22, 2026  
**Rule:** No guessed Wix storefront or product URL may be deployed.

## Audit evidence

Workflow run `29929384854` completed successfully and produced the private artifact `dominion-wix-storefront-layout-audit-v2`.

The audit reviewed five public pages across desktop and mobile. The audited primary URL was `https://dominionhealing.org/`.

## Critical distinction

The audited domain is the custom Dominion Healing static site, not a confirmed Wix-published storefront domain. Three product URLs were constructed under `dominionhealing.org/product-page/...` and returned HTTP 404. This does not prove that the Wix catalog is unpublished; it proves that the product URLs were attached to an unverified domain.

## Findings from the live static site

1. `index.html` and `store.html` returned HTTP 200.
2. Both pages lacked meta descriptions.
3. The mobile homepage had 72 pixels of horizontal overflow.
4. Public navigation/footer lacked About, Shipping, Returns/Refunds, Privacy, and Terms links.
5. Five direct-purchase buttons contained unresolved placeholder paths:
   - `STRIPE_BOOK_LINK`
   - `STRIPE_PROTOCOL_LINK`
   - `STRIPE_LEGAL_LINK`
   - `STRIPE_MEMBERSHIP_LINK`
   - `STRIPE_BLUEPRINT_LINK`
6. The static store promised a 30-day, no-questions-asked refund without linking an operational refund policy.
7. Amazon-controlled book prices were shown as fixed site prices, creating an avoidable pricing-consistency risk.
8. The static page label “Store” did not distinguish digital products from the separate Wix physical-product catalog.

## Source fixes committed

The following review-stage changes are committed on `main` but are not yet deployed:

- Responsive shared stylesheet with mobile overflow protection and keyboard focus states.
- Homepage meta description, canonical URL, About section, clearer navigation, safer contact wording, and policy links.
- Static store renamed and worded as a digital-product store.
- Unresolved checkout links replaced with verified-link request paths instead of dead payment URLs.
- Unsupported “no questions asked” guarantee removed.
- Amazon prices replaced with “View on Amazon” / Amazon-controlled pricing language.
- Credit-dispute wording changed from a legal-compliance claim to FCRA/FDCPA-informed educational wording.
- Shipping, Returns and Refunds, Privacy, and Terms pages added.

Relevant commits:

- Homepage: `def447362db84043ea92b3191140216080c6e66b`
- Digital store: `ea09c6d4d4a96c552967138d313a1845fdadfebd`
- Responsive stylesheet: `503de3efbe4b89c9a2b6f4cf618bfa061c03f96e`
- Shipping policy: `2f774221fbacc89422fc50eee9c4a645f0e36bf6`
- Returns policy: `0f63e61b454adab29a36cc9ea4bb84446e7edeb8`
- Privacy policy: `4202581b06b38c717e7ec1f7c62709538a23e2a7`
- Terms: `cebf52263e43dc2f605ca6d61d06d14ac578475a`

## Wix routing hardening

A read-only mapper now queries Wix for:

- published primary and secondary site URLs;
- public business-profile completeness flags;
- exact public product-page URLs returned by Product V3 for three sample products.

Files:

- `scripts/runtime/wix_published_routing_map.py`
- `.github/workflows/production-wix-published-routing-map.yml`

## Current gate

1. Run `Production Wix Published Routing Map`.
2. Verify terminal workflow status and returned public Wix URLs.
3. Update Dominion Healing navigation using the exact Wix URL returned by Wix, never a constructed URL.
4. Run static-source preview validation.
5. Deploy the reviewed static files with backup, public probes, and automatic rollback.
6. Re-run desktop/mobile visual audit against both the static site and confirmed Wix storefront.
7. Keep Wix product-description rollout blocked until the description round-trip canonicalization probe passes.
