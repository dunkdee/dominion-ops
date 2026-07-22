# Wix and Dominion Storefront Layout Review

**Human authority:** Dewayne Singleton  
**Audit date:** July 22, 2026  
**Rule:** No guessed Wix storefront or product URL may be deployed.

## Audit evidence

Workflow run `29929384854` completed successfully and produced the private artifact `dominion-wix-storefront-layout-audit-v2`.

The audit reviewed five public pages across desktop and mobile. The audited primary URL was `https://dominionhealing.org/`.

## Critical distinction

The audited domain is the custom Dominion Healing static site, not the Wix-published physical-product storefront. The initial three product URLs were constructed under `dominionhealing.org/product-page/...` and returned HTTP 404 because they were attached to the wrong domain.

## Findings from the live static site

1. `index.html` and `store.html` returned HTTP 200.
2. Both pages lacked meta descriptions.
3. The mobile homepage had 72 pixels of horizontal overflow.
4. Public navigation/footer lacked About, Shipping, Returns/Refunds, Privacy, and Terms links.
5. Five direct-purchase buttons contained unresolved Stripe placeholder paths.
6. The static store promised a 30-day, no-questions-asked refund without linking an operational refund policy.
7. Amazon-controlled book prices were shown as fixed site prices.
8. The static page label “Store” did not distinguish digital products from the separate Wix physical-product catalog.

## Verified Wix routing

Read-only workflow run `29933469816` completed successfully. Terminal job `88968903261` concluded `success`.

Wix returned:

- Primary published storefront: `https://www.voltedgegoods.com/`
- Public business name: `VoltEdge Electronics`
- Site display name: `VoltEdge Electronics`
- Currency: `USD`
- Time zone: `America/New_York`
- Contact email present: yes
- Contact phone present: yes
- Public description present: yes

Three sampled visible products returned exact public pages on `www.voltedgegoods.com`:

- Esoulk Black 18W PD Charger & USB-A 3ft C To iPhone Cable
- Samsung S10E Triangle Package Case
- Portable Wireless Bluetooth Speaker with TWS Function

The mapping run made no Wix, product, inventory, order, database, network, volume, DNS, container, or secret change.

## Reviewed source fixes committed

The following changes are committed on `main` but are not yet deployed:

- Responsive shared stylesheet with mobile overflow protection and keyboard focus states.
- Homepage meta description, canonical URL, About section, clearer navigation, safer contact wording, and policy links.
- Static store renamed and worded as a Dominion Healing digital-product store.
- Verified VoltEdge Electronics navigation and calls to action using `https://www.voltedgegoods.com/`.
- Explicit separation of Dominion Healing digital products from VoltEdge physical electronics.
- Unresolved checkout links replaced with verified-link request paths instead of dead payment URLs.
- Unsupported “no questions asked” guarantee removed.
- Amazon prices replaced with Amazon-controlled pricing language.
- Credit-dispute wording changed from a legal-compliance claim to FCRA/FDCPA-informed educational wording.
- Shipping, Returns and Refunds, Privacy, and Terms pages added.

Relevant commits:

- Homepage base correction: `def447362db84043ea92b3191140216080c6e66b`
- Digital-store base correction: `ea09c6d4d4a96c552967138d313a1845fdadfebd`
- Responsive stylesheet: `503de3efbe4b89c9a2b6f4cf618bfa061c03f96e`
- Shipping policy: `2f774221fbacc89422fc50eee9c4a645f0e36bf6`
- Returns policy: `0f63e61b454adab29a36cc9ea4bb84446e7edeb8`
- Privacy policy: `4202581b06b38c717e7ec1f7c62709538a23e2a7`
- Terms: `cebf52263e43dc2f605ca6d61d06d14ac578475a`
- Verified VoltEdge homepage routing: `35eec7332fc9026eea4761bb3d9d852d0e2db248`
- Verified VoltEdge digital-store routing: `4150b700d7dae9fe79633dfd04e0dc88f223d2de`
- Guarded deployment engine hardening: `54cc746313a622afe715f4fe0e11f908b2bb3cbc`
- Guarded deployment workflow: `0ae1ea7f03e13428f1935f05dec55ee497df75b3`

## Workflow hardening

The completed routing mapper was retired after success.

The older `Deploy Site Compliance Fixes` workflow was retired because it could overwrite public files and alter Caddy without the new source validation, terminal reporting, protected-service checks, and automatic rollback contract.

The active deployment path is:

- Workflow: `Production Dominion Site Hardening Deploy`
- Authorization: `DEPLOY_DOMINION_SITE_HARDENING`
- Scope: exactly seven reviewed static files
- Backup: private VM recovery directory
- Validation: source gates, exact VoltEdge URL, live public markers, all protected HTTP services
- Failure behavior: restore every previous file automatically
- Excluded: Wix mutation, product changes, inventory, orders, Caddy, DNS, containers, databases, networks, and volumes

## Current gate

1. Human runs `Production Dominion Site Hardening Deploy`.
2. Verify terminal workflow status, seven installed hashes, live public markers, backup path, and rollback state.
3. Re-run the desktop/mobile public audit against Dominion Healing.
4. Run a separate desktop/mobile visual audit against `https://www.voltedgegoods.com/`.
5. Verify the Dominion contact-form path without sending sensitive data.
6. Keep direct Dominion digital checkout links disabled until verified payment links, delivery rules, and refund terms pass controlled checkout testing.
7. Keep Wix product-description rollout blocked until the description round-trip canonicalization probe passes.
