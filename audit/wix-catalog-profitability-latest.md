# Wix Catalog Launch and Profitability Audit

- Generated: 2026-07-20T21:03:01.151766+00:00
- Audit result: **INCOMPLETE**
- Mode: **READ ONLY**
- Customer/order data: **EXCLUDED**
- API keys and secret values: **EXCLUDED**
- Catalog version: **V3_CATALOG**
- Currency used for display: **USD**
- Merchant-specific catalog access: **True**
- Zendrop key configured on current container: **False**

## Executive launch gates

| Gate | Status | Evidence |
|---|---:|---|
| Catalog retrieval | BLOCKED | 0 products retrieved |
| Price and Wix COGS entry | BLOCKED | 0 missing/zero prices; 0 missing COGS; 0 physical rows with zero COGS |
| Baseline 40% margin after standard card fee | BLOCKED | 0 rows below target |
| BNPL 40% stress margin | REVIEW | 0 rows below target |
| Business profile completeness | REVIEW | 1 API-visible fields missing |
| True profitability certification | **NOT CERTIFIED** | Supplier landed cost, shipping subsidy, advertising allowance, return/chargeback reserve, taxes, and Wix plan cost are not independently verified |

### Pricing assumptions

- Standard-card baseline: 2.9% + USD 0.30 per transaction.
- BNPL stress case: 6.0% + USD 0.30 per transaction.
- Cross-border fees and the non-returned processing fee on refunds are not modeled.
- Minimum-price columns solve for 40% and 50% margin after the standard-card fee only.

## Business information completeness

Site Properties API status: 200

| Field | Configured |
|---|---:|
| Site display name | YES |
| Business name | YES |
| Business description | YES |
| Logo | NO |
| Business email | YES |
| Business phone | YES |
| Business address | YES |
| Time zone | YES |
| Payment currency | YES |
| Language | YES |
| Locale | YES |
| Business configuration | YES |
| Consent policy | YES |

## Catalog summary

- Products: **0**
- Sellable base/variant pricing rows: **0**
- Hidden products: **0**
- Descriptions under 200 characters: **0**
- Products with fewer than 3 media items: **0**
- Products missing custom SEO: **0**
- Inventory API status: **LIMITED**

## Product content and launch information

| Product | Visible | Type | Description chars | Media | Brand | Custom SEO | Info sections | Inventory | Flags |
|---|---:|---|---:|---:|---:|---:|---:|---|---|

## Product and variant profitability

| Product | Variant | Visible | SKU | Current price | Wix COGS | Profit after standard fee | Standard margin | BNPL stress margin | Min price @ 40% | Min price @ 50% | Flags |
|---|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---|

## Audit limitations and errors

- Limitations: none
- Fatal errors: unsupported_catalog_V3_CATALOG
- Public desktop/mobile layout, navigation, checkout, policy-page text, shipping rules, tax rules, and payment activation require separate customer-journey verification.

## Required next actions

1. Complete API-visible business fields: Logo.
2. Resolve 0 missing COGS rows and 0 zero physical-product COGS rows using verified landed supplier costs.
3. Reprice or reduce verified cost for 0 rows below the 40% standard-card baseline target.
4. Improve 0 weak descriptions, 0 weak media sets, and 0 missing custom SEO records.
5. Verify Zendrop product/variant mapping and landed costs before enabling automated fulfillment or approving final prices.
6. Run a public desktop/mobile, cart, checkout, payment, shipping, tax, returns, privacy, terms, and contact-flow launch test.

## Source references

- Wix Catalog V1 Query Products: https://dev.wix.com/docs/api-reference/business-solutions/stores/catalog-v1/catalog/query-products
- Wix Site Properties: https://dev.wix.com/docs/api-reference/business-management/site-properties/properties/get-site-properties
- Wix COGS tracking: https://support.wix.com/en/article/wix-stores-tracking-the-cost-of-goods
- Wix Payments US fees: https://support.wix.com/en/article/wix-payments-service-fees
