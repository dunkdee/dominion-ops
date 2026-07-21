# VoltEdge Goods — Public Wix Launch Readiness

**Audit date:** 2026-07-20  
**Public site:** https://www.voltedgegoods.com  
**Decision:** **HOLD — not ready for paid public traffic**

This report is read-only. It excludes API keys and customer/order data. No order was placed, no payment method was charged, and Zendrop remains record-only.

## What is working

- The apex domain redirects to `https://www.voltedgegoods.com/`.
- HTTPS responds successfully and HSTS is enabled.
- `robots.txt` permits crawling and points to the sitemap.
- The all-products category and product-detail URLs are publicly reachable.
- The private catalog audit found 94 products and 246 sellable price/variant rows.
- No sellable row had a missing/zero price or missing entered COGS.
- All audited rows passed the configured 40% card-fee baseline and BNPL stress calculation.
- The Wix agent is operator-token protected, production is record-only, and the legacy bulk store writers have been removed from `main`.

## Launch blockers

### 1. Template identity and contact information are still public

The site still shows Wix template content, including:

- `TechShed` branding on informational pages;
- the template copyright year `2035`;
- the sample address `500 Terry Francine Street, San Francisco, CA 94158`;
- the sample email `info@mysite.com`;
- the sample phone `123-456-7890`;
- generic opening hours and career-form language.

**Required correction:** In the Wix Editor, replace every template identity field with the exact business name and the business-contact values already verified in Wix Business Info. Do not publish a home address or personal phone number unless that is an intentional business decision.

### 2. Unverified sales and service promises are public

The homepage currently advertises or implies:

- free shipping over $50;
- best/low prices guaranteed;
- up to 30% off;
- curb-side pickup;
- 24/7 availability/support;
- product categories such as laptops, drones, and smartphones.

These claims were not verified against the current shipping rules, discount configuration, support coverage, pickup settings, or live catalog.

**Required correction:** Remove each claim unless its exact operational setting is confirmed in Wix and it can be fulfilled consistently.

### 3. Policy and help pages are template filler

The current Terms, Help Center, and Shipping & Returns pages include generic Wix instructional language such as “click here to add your own text” and FAQ examples explaining what an FAQ is. The terms also mention payment methods that were not verified.

**Required correction:** Replace the template text with business-specific, reviewed content. Do not publish AI-inferred legal terms, shipping times, warranties, refund promises, payment methods, supplier claims, or response-time guarantees.

### 4. Search visibility is incomplete

- The sitemap exposes category and standard-page sitemaps.
- No product sitemap was found at the standard product-sitemap paths tested.
- All 94 products were reported without custom SEO fields.

**Required correction:** In Wix SEO settings, verify product indexing and the Wix Stores product sitemap, then submit the canonical sitemap in Google Search Console. Write product SEO from verified product facts only.

### 5. Product merchandising needs review

- 14 products have fewer than three media items.
- Existing descriptions are long enough to pass a character threshold, but appear generic and were not supplier-fact certified.
- Exact Wix-to-Zendrop variant mappings are absent/unverified.

**Required correction:** Add accurate media, specifications, compatibility, contents, dimensions, and warranty information from supplier records. Keep Zendrop record-only until every sellable Wix variant has one exact reviewed supplier mapping.

### 6. Profitability is screened, not certified

Entered price/COGS rows passed the configured fee-and-margin thresholds, but final profitability still depends on independently verified:

- supplier landed cost;
- shipping subsidy;
- advertising acquisition cost;
- refunds, returns, chargebacks, and reshipments;
- taxes and duties;
- Wix plan/app costs;
- currency conversion and payout fees.

**Required correction:** Do not increase advertising spend until these values are added to the unit-economics model and a test order confirms the actual checkout total.

## Page-by-page Wix Editor correction packet

### Global header and footer

1. Replace every `TechShed` reference with the approved store name.
2. Replace `© 2035 by TechShed` with the current year and the exact legal/business name.
3. Remove fake address, email, phone, and hours.
4. Link Contact, About, Shipping & Returns, Privacy, and Terms from the footer.
5. Verify cart, account, search, category, and policy links on desktop and mobile.

### Homepage

Safe starting copy, pending owner approval:

> **Practical tech for everyday use.**  
> Browse electronics and accessories with clear product information and secure checkout.

Remove the holiday sale, free-shipping, low-price guarantee, curbside-pickup, and 24/7 claims unless the matching Wix settings are active and verified.

### About

Safe starting copy, pending owner approval:

> VoltEdge Goods is an online electronics and accessories store focused on practical products and clear shopping information. Product availability, specifications, delivery options, and final totals are shown on product pages and at checkout.

Do not claim certified manufacturers, quality inspection, worldwide delivery, guaranteed returns, or response times without records proving each statement.

### Contact

Use only the approved values from Wix Business Info:

- public support email;
- public business phone, if staffed;
- mailing/return address, only if approved for publication;
- truthful support hours;
- contact-form response expectations that can be met.

### Shipping & Returns

Owner/legal review must confirm and publish:

- countries/regions served;
- processing time and business-day definition;
- carriers and estimated transit ranges;
- rates, any free-shipping threshold, and exclusions;
- tracking process;
- duties/taxes responsibility;
- return window and eligibility;
- return-shipping responsibility;
- damaged/wrong-item process;
- refund method and timing;
- non-returnable items and cancellation rules.

### Privacy and Terms

Owner/legal review must confirm the operating entity, jurisdiction, contact information, data practices, payment processors, fulfillment providers, cookies/analytics, retention, consumer rights, warranties, limitations, cancellation rules, and governing law. Remove any payment method that is not enabled in the live Wix dashboard.

### Help Center

Delete the template FAQ tutorial. Publish only verified answers for ordering, payment, order status, address changes, cancellations, shipping, returns, damaged items, warranties, and support contact.

## Owner-only checkout verification

Wix states that the site owner must perform the store test-order flow. Use a manual/test payment option so no live card is charged. Verify:

1. product selection and variant choice;
2. cart quantity changes and removal;
3. shipping destination, rate, and tax calculation;
4. coupon behavior, if coupons are advertised;
5. final total and currency;
6. order confirmation page and email;
7. the order appears once in Wix;
8. the Wix agent records the order but does not submit it to Zendrop;
9. cancellation/refund workflow using the test order.

Official Wix references:

- https://support.wix.com/en/article/previewing-the-checkout-process-1420066
- https://support.wix.com/en/article/wix-stores-managing-emails-sent-to-customers

## Launch gate

Paid traffic may begin only after all items below are evidenced:

- [ ] All template identity/contact text is removed.
- [ ] All public claims match configured operations.
- [ ] Policies are business-specific and owner/legal reviewed.
- [ ] Payment methods, shipping, tax, and confirmation email pass an owner test order.
- [ ] Every advertised product has accurate media/specifications and a profitable verified landed cost.
- [ ] Every sellable variant has an exact fulfillment mapping, or remains on manual fulfillment.
- [ ] Desktop and mobile navigation, cart, checkout, policies, and contact are tested.
- [ ] Product indexing/sitemap behavior is verified.
- [ ] Zendrop remains record-only until a separately approved fulfillment cutover.

Until every gate is checked, the correct status is **HOLD**, not “launch ready.”
