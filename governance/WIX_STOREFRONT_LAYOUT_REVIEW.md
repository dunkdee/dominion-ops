# Wix and Dominion Storefront Layout Review

**Human authority:** Dewayne Singleton  
**Audit date:** July 22, 2026  
**Rule:** No guessed Wix storefront or product URL may be deployed.

## Initial audit evidence

Workflow run `29929384854` completed successfully and produced the private artifact `dominion-wix-storefront-layout-audit-v2`.

The audit reviewed the custom Dominion Healing static site and exposed that the initial Wix product URLs had been constructed under the wrong domain.

## Initial live-site findings

1. The homepage and digital-store page lacked meta descriptions.
2. The mobile homepage had 72 pixels of horizontal overflow.
3. Public navigation/footer lacked About, Shipping, Returns/Refunds, Privacy, and Terms links.
4. Five direct-purchase buttons contained unresolved Stripe placeholder paths.
5. The static store promised a 30-day, no-questions-asked refund without an operational policy link.
6. Amazon-controlled book prices were presented as fixed site prices.
7. The static Store label did not distinguish Dominion digital products from the separate Wix physical-product catalog.

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

The routing run made no Wix, product, inventory, order, database, network, volume, DNS, container, or secret change.

## Production deployment result

Guarded deployment run `29936230606` completed successfully. Terminal job `88978408083` concluded `success`.

Exactly seven reviewed files were deployed to `/home/malachisingleton8/aura-ecosystem/agency-website`:

- `index.html`
- `store.html`
- `site.css`
- `shipping.html`
- `returns.html`
- `privacy.html`
- `terms.html`

The previous site state was backed up to:

`/home/malachisingleton8/.dominion-recovery/site-hardening/29936230606-1`

Backup directory mode: `0700`.

All seven public probes returned HTTP 200 with the required live markers on the first attempt. Baby API, Wix Agent, Dominion Web, n8n, Alpha Engine, and Conductor remained HTTP 200 before and after deployment. Container inventory remained unchanged. Rollback was not required.

The deployment changed only the seven reviewed static files. It made no Wix, product, inventory, order, customer-data, Caddy, DNS, database, network, volume, container, environment-secret, or raw-log change.

## Deployed corrections

- Responsive shared stylesheet with mobile overflow protection and keyboard focus states.
- Homepage meta description, canonical URL, About section, clearer navigation, safer contact wording, and policy links.
- Static store renamed and worded as a Dominion Healing digital-product store.
- Verified VoltEdge Electronics navigation and calls to action using `https://www.voltedgegoods.com/`.
- Explicit separation of Dominion Healing digital products from VoltEdge physical electronics.
- Unresolved checkout links replaced with verified-link request paths instead of dead payment URLs.
- Unsupported no-questions-asked guarantee removed.
- Amazon prices replaced with Amazon-controlled pricing language.
- Credit-dispute wording changed from a legal-compliance claim to FCRA/FDCPA-informed educational wording.
- Shipping, Returns and Refunds, Privacy, and Terms pages added.

## Workflow hardening

The completed routing mapper and successful one-time deployment workflow were retired after verification.

The older broad deployment action was retired because it could overwrite public files and alter Caddy without the guarded source validation, terminal reporting, service checks, and automatic rollback contract.

The obsolete single-domain visual audit was retired because it constructed Wix product routes on the Dominion Healing domain.

The active next verification path is:

- Workflow: `Production Storefront Post-Deploy Audit`
- Scope: public desktop/mobile rendering of `dominionhealing.org` and `www.voltedgegoods.com`
- Wix samples: three exact verified product pages
- Private artifact: screenshots and detailed visible-text findings
- Excluded: form submission, button clicks, cart, checkout, Wix management calls, VM access, product/inventory/order changes

## Current gate

1. Run `Production Storefront Post-Deploy Audit`.
2. Review the private desktop/mobile screenshots and wording findings for both sites.
3. Verify the Dominion contact-form path with clearly synthetic data before activating direct digital checkout links.
4. Keep direct Dominion digital checkout links disabled until payment links, delivery rules, and refund terms pass controlled checkout testing.
5. Keep Wix product-description rollout blocked until the description round-trip canonicalization probe passes.
