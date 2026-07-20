"""Generate a read-only, customer-data-free Wix catalog profitability report."""

import html
import os
import re
from datetime import datetime, timezone

import httpx


WIX_API_KEY = os.getenv("WIX_API_KEY", "")
WIX_SITE_ID = os.getenv("WIX_SITE_ID", "")
ZENDROP_CONFIGURED = bool(os.getenv("ZENDROP_API_KEY", ""))
TIMEOUT = 30.0

STANDARD_CARD_RATE = 0.029
STANDARD_CARD_FIXED = 0.30
BNPL_RATE = 0.06
BNPL_FIXED = 0.30

HEADERS = {
    "Authorization": WIX_API_KEY,
    "wix-site-id": WIX_SITE_ID,
    "Content-Type": "application/json",
}


def safe_text(value, limit=160):
    text = html.unescape(str(value or ""))
    text = "".join(char if char.isprintable() else " " for char in text)
    text = " ".join(text.split()).replace("|", "\\|")
    return text[:limit] or "MISSING"


def plain_length(value):
    plain = re.sub(r"<[^>]+>", " ", str(value or ""))
    return len(" ".join(html.unescape(plain).split()))


def number(value):
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, dict):
        for key in ("amount", "value", "price", "cost", "itemCost"):
            parsed = number(value.get(key))
            if parsed is not None:
                return parsed
        return None
    try:
        return float(str(value).replace(",", "").replace("$", "").strip())
    except (TypeError, ValueError):
        return None


def current_price(price_data):
    price_data = price_data or {}
    regular = number(price_data.get("price"))
    discounted = number(price_data.get("discountedPrice"))
    if discounted is not None and (regular is None or discounted <= regular):
        return discounted
    return regular


def item_cost(cost_data):
    cost_data = cost_data or {}
    return number(cost_data.get("itemCost", cost_data.get("cost")))


def money(value, currency):
    return "unknown" if value is None else f"{currency} {value:.2f}"


def percent(value):
    return "unknown" if value is None else f"{value:.1f}%"


def request_json(method, url, *, json_body=None):
    try:
        response = httpx.request(
            method,
            url,
            headers=HEADERS,
            json=json_body,
            timeout=TIMEOUT,
        )
    except Exception as exc:
        return None, {}, f"network_{exc.__class__.__name__}"
    try:
        payload = response.json()
    except Exception:
        payload = {}
    error = None if response.status_code == 200 else f"http_{response.status_code}"
    return response.status_code, payload, error


def query_products(privileged):
    products = []
    offset = 0
    while True:
        body = {
            "includeVariants": True,
            "query": {"paging": {"limit": 100, "offset": offset}},
        }
        if privileged:
            body["includeHiddenProducts"] = True
            body["includeMerchantSpecificData"] = True
        status, payload, error = request_json(
            "POST",
            "https://www.wixapis.com/stores-reader/v1/products/query",
            json_body=body,
        )
        if error:
            return products, False, f"products_offset_{offset}_{error}"
        page = payload.get("products", []) or []
        products.extend(page)
        total = payload.get("totalResults")
        if not page or len(page) < 100:
            break
        if isinstance(total, int) and len(products) >= total:
            break
        offset += len(page)
    return products, True, None


def query_inventory():
    items = []
    offset = 0
    while True:
        status, payload, error = request_json(
            "POST",
            "https://www.wixapis.com/stores-reader/v2/inventoryItems/query",
            json_body={"query": {"paging": {"limit": 100, "offset": offset}}},
        )
        if error:
            return items, False, f"inventory_offset_{offset}_{error}"
        page = payload.get("inventoryItems", []) or []
        items.extend(page)
        total = payload.get("totalResults")
        if not page or len(page) < 100:
            break
        if isinstance(total, int) and len(items) >= total:
            break
        offset += len(page)
    return items, True, None


def inventory_status(item, product):
    stock = product.get("stock") or {}
    if stock.get("inStock") is True:
        return "IN_STOCK"
    if stock.get("inStock") is False:
        return "OUT_OF_STOCK"
    if not item:
        return "RECORD_MISSING"
    variants = item.get("variants") or []
    states = []
    for variant in variants:
        if variant.get("inStock") is True:
            states.append(True)
        elif variant.get("inStock") is False:
            states.append(False)
        availability = str(variant.get("availabilityStatus") or "").upper()
        if availability == "IN_STOCK":
            states.append(True)
        elif availability in ("OUT_OF_STOCK", "NOT_AVAILABLE"):
            states.append(False)
    if any(states):
        return "IN_STOCK"
    if states and not any(states):
        return "OUT_OF_STOCK"
    return "TRACKED_STATUS_UNKNOWN"


def seo_configured(product):
    seo = product.get("seoData") or {}
    return bool(seo.get("tags") or seo.get("settings") or seo.get("keywords"))


def minimum_price_for_margin(cost, target_margin):
    denominator = 1.0 - STANDARD_CARD_RATE - target_margin
    if cost is None or denominator <= 0:
        return None
    return (cost + STANDARD_CARD_FIXED) / denominator


def profitability(price, cost, rate, fixed):
    if price is None or price <= 0 or cost is None:
        return None, None
    profit = price - cost - (price * rate + fixed)
    return profit, profit / price * 100


def build_report():
    limitations = []
    fatal_errors = []

    if not WIX_API_KEY or not WIX_SITE_ID:
        fatal_errors.append("required_wix_configuration_missing")

    version_status, version_payload, version_error = request_json(
        "GET", "https://www.wixapis.com/stores/v3/provision/version"
    )
    version = safe_text(
        version_payload.get("version")
        or version_payload.get("catalogVersion")
        or "UNKNOWN",
        40,
    )
    if version_error:
        limitations.append(f"catalog_version_{version_error}")
    elif "V1" not in version.upper():
        fatal_errors.append(f"unsupported_catalog_{version}")

    properties = {}
    property_status, property_payload, property_error = request_json(
        "GET", "https://www.wixapis.com/site-properties/v4/properties"
    )
    if property_error:
        limitations.append(f"site_properties_{property_error}")
    else:
        properties = property_payload.get("properties", {}) or {}

    products = []
    merchant_access = True
    if not fatal_errors:
        products, products_ok, products_error = query_products(privileged=True)
        if not products_ok and products_error and any(
            code in products_error for code in ("http_401", "http_403", "http_428")
        ):
            products, products_ok, products_error = query_products(privileged=False)
            merchant_access = False
            limitations.append("merchant_cost_and_hidden_product_access_unavailable")
        if not products_ok:
            fatal_errors.append(products_error or "product_query_failed")

    inventory = []
    inventory_ok = False
    if products:
        inventory, inventory_ok, inventory_error = query_inventory()
        if not inventory_ok:
            limitations.append(inventory_error or "inventory_query_failed")
    inventory_by_product = {
        item.get("productId"): item for item in inventory if item.get("productId")
    }

    currency = safe_text(properties.get("paymentCurrency") or "USD", 12)
    business_fields = (
        ("Site display name", "siteDisplayName"),
        ("Business name", "businessName"),
        ("Business description", "description"),
        ("Logo", "logo"),
        ("Business email", "email"),
        ("Business phone", "phone"),
        ("Business address", "address"),
        ("Time zone", "timeZone"),
        ("Payment currency", "paymentCurrency"),
        ("Language", "language"),
        ("Locale", "locale"),
        ("Business configuration", "businessConfig"),
        ("Consent policy", "consentPolicy"),
    )
    missing_business = [
        label for label, key in business_fields if not properties.get(key)
    ]

    product_rows = []
    pricing_rows = []
    for product in sorted(products, key=lambda value: str(value.get("name") or "").lower()):
        name = safe_text(product.get("name"), 120)
        visible = product.get("visible") is not False
        description_chars = plain_length(product.get("description"))
        media = product.get("media") or {}
        media_count = len(media.get("items") or product.get("mediaItems") or [])
        brand_present = bool(product.get("brand"))
        seo_present = seo_configured(product)
        info_count = len(product.get("additionalInfoSections") or [])
        inv_status = inventory_status(
            inventory_by_product.get(product.get("id")), product
        )
        content_flags = []
        if not visible:
            content_flags.append("HIDDEN")
        if description_chars < 200:
            content_flags.append("DESCRIPTION_UNDER_200_CHARS")
        if media_count < 3:
            content_flags.append("FEWER_THAN_3_MEDIA_ITEMS")
        if not brand_present:
            content_flags.append("BRAND_MISSING")
        if not seo_present:
            content_flags.append("CUSTOM_SEO_MISSING")
        if info_count == 0:
            content_flags.append("PRODUCT_INFO_SECTIONS_MISSING")
        if inv_status == "RECORD_MISSING":
            content_flags.append("INVENTORY_RECORD_MISSING")
        if inv_status == "OUT_OF_STOCK":
            content_flags.append("OUT_OF_STOCK")
        product_rows.append(
            {
                "name": name,
                "visible": visible,
                "type": safe_text(product.get("productType") or "UNKNOWN", 24),
                "description_chars": description_chars,
                "media_count": media_count,
                "brand": brand_present,
                "seo": seo_present,
                "info_count": info_count,
                "inventory": inv_status,
                "flags": content_flags,
            }
        )

        managed = bool(product.get("manageVariants"))
        variants = product.get("variants") or []
        entries = variants if managed and variants else [None]
        for entry in entries:
            details = (entry or {}).get("variant") or {}
            choices = (entry or {}).get("choices") or {}
            label = (
                "; ".join(
                    f"{safe_text(key, 40)}={safe_text(value, 60)}"
                    for key, value in sorted(choices.items())
                )
                if entry
                else "Base product"
            )
            price_data = details.get("priceData") or product.get("priceData") or product.get("price")
            cost_data = details.get("costAndProfitData") or product.get("costAndProfitData")
            price = current_price(price_data)
            cost = item_cost(cost_data)
            sku = safe_text(details.get("sku") or product.get("sku"), 60)
            row_visible = visible and details.get("visible") is not False
            standard_profit, standard_margin = profitability(
                price, cost, STANDARD_CARD_RATE, STANDARD_CARD_FIXED
            )
            _, stress_margin = profitability(price, cost, BNPL_RATE, BNPL_FIXED)
            row_flags = []
            if not row_visible:
                row_flags.append("NOT_VISIBLE")
            if price is None or price <= 0:
                row_flags.append("PRICE_MISSING_OR_ZERO")
            if cost is None:
                row_flags.append("COGS_MISSING")
            elif cost <= 0 and str(product.get("productType") or "").lower() == "physical":
                row_flags.append("PHYSICAL_COGS_ZERO_REVIEW")
            if sku == "MISSING":
                row_flags.append("SKU_MISSING")
            if standard_margin is not None and standard_margin < 40:
                row_flags.append("STANDARD_MARGIN_BELOW_40")
            if stress_margin is not None and stress_margin < 40:
                row_flags.append("BNPL_MARGIN_BELOW_40")
            pricing_rows.append(
                {
                    "product": name,
                    "variant": safe_text(label, 160),
                    "visible": row_visible,
                    "sku": sku,
                    "price": price,
                    "cost": cost,
                    "profit": standard_profit,
                    "standard_margin": standard_margin,
                    "stress_margin": stress_margin,
                    "min_40": minimum_price_for_margin(cost, 0.40),
                    "min_50": minimum_price_for_margin(cost, 0.50),
                    "flags": row_flags,
                }
            )

    price_missing = sum(
        "PRICE_MISSING_OR_ZERO" in row["flags"] for row in pricing_rows
    )
    cost_missing = sum("COGS_MISSING" in row["flags"] for row in pricing_rows)
    zero_physical_cost = sum(
        "PHYSICAL_COGS_ZERO_REVIEW" in row["flags"] for row in pricing_rows
    )
    standard_below_40 = sum(
        "STANDARD_MARGIN_BELOW_40" in row["flags"] for row in pricing_rows
    )
    stress_below_40 = sum(
        "BNPL_MARGIN_BELOW_40" in row["flags"] for row in pricing_rows
    )
    weak_descriptions = sum(
        "DESCRIPTION_UNDER_200_CHARS" in row["flags"] for row in product_rows
    )
    weak_media = sum(
        "FEWER_THAN_3_MEDIA_ITEMS" in row["flags"] for row in product_rows
    )
    missing_seo = sum("CUSTOM_SEO_MISSING" in row["flags"] for row in product_rows)
    hidden = sum("HIDDEN" in row["flags"] for row in product_rows)

    if fatal_errors:
        audit_result = "INCOMPLETE"
    elif limitations:
        audit_result = "COMPLETE_WITH_LIMITATIONS"
    else:
        audit_result = "COMPLETE"

    pricing_data_gate = (
        "PASS"
        if pricing_rows and price_missing == 0 and cost_missing == 0 and zero_physical_cost == 0
        else "BLOCKED"
    )
    baseline_margin_gate = (
        "PASS"
        if pricing_rows
        and price_missing == 0
        and cost_missing == 0
        and standard_below_40 == 0
        else "BLOCKED"
    )

    lines = []
    add = lines.append
    add("# Wix Catalog Launch and Profitability Audit")
    add("")
    add(f"- Generated: {datetime.now(timezone.utc).isoformat()}")
    add(f"- Audit result: **{audit_result}**")
    add("- Mode: **READ ONLY**")
    add("- Customer/order data: **EXCLUDED**")
    add("- API keys and secret values: **EXCLUDED**")
    add(f"- Catalog version: **{version}**")
    add(f"- Currency used for display: **{currency}**")
    add(f"- Merchant-specific catalog access: **{merchant_access}**")
    add(f"- Zendrop key configured on current container: **{ZENDROP_CONFIGURED}**")
    add("")
    add("## Executive launch gates")
    add("")
    add("| Gate | Status | Evidence |")
    add("|---|---:|---|")
    add(f"| Catalog retrieval | {'PASS' if products and not fatal_errors else 'BLOCKED'} | {len(products)} products retrieved |")
    add(f"| Price and Wix COGS entry | {pricing_data_gate} | {price_missing} missing/zero prices; {cost_missing} missing COGS; {zero_physical_cost} physical rows with zero COGS |")
    add(f"| Baseline 40% margin after standard card fee | {baseline_margin_gate} | {standard_below_40} rows below target |")
    add(f"| BNPL 40% stress margin | {'PASS' if pricing_rows and stress_below_40 == 0 and cost_missing == 0 else 'REVIEW'} | {stress_below_40} rows below target |")
    add(f"| Business profile completeness | {'PASS' if properties and not missing_business else 'REVIEW'} | {len(missing_business)} API-visible fields missing |")
    add("| True profitability certification | **NOT CERTIFIED** | Supplier landed cost, shipping subsidy, advertising allowance, return/chargeback reserve, taxes, and Wix plan cost are not independently verified |")
    add("")
    add("### Pricing assumptions")
    add("")
    add("- Standard-card baseline: 2.9% + USD 0.30 per transaction.")
    add("- BNPL stress case: 6.0% + USD 0.30 per transaction.")
    add("- Cross-border fees and the non-returned processing fee on refunds are not modeled.")
    add("- Minimum-price columns solve for 40% and 50% margin after the standard-card fee only.")
    add("")
    add("## Business information completeness")
    add("")
    add(f"Site Properties API status: {property_status if property_status is not None else 'network_error'}")
    add("")
    add("| Field | Configured |")
    add("|---|---:|")
    for label, key in business_fields:
        add(f"| {label} | {'YES' if properties.get(key) else 'NO'} |")
    add("")
    add("## Catalog summary")
    add("")
    add(f"- Products: **{len(product_rows)}**")
    add(f"- Sellable base/variant pricing rows: **{len(pricing_rows)}**")
    add(f"- Hidden products: **{hidden}**")
    add(f"- Descriptions under 200 characters: **{weak_descriptions}**")
    add(f"- Products with fewer than 3 media items: **{weak_media}**")
    add(f"- Products missing custom SEO: **{missing_seo}**")
    add(f"- Inventory API status: **{'PASS' if inventory_ok else 'LIMITED'}**")
    add("")
    add("## Product content and launch information")
    add("")
    add("| Product | Visible | Type | Description chars | Media | Brand | Custom SEO | Info sections | Inventory | Flags |")
    add("|---|---:|---|---:|---:|---:|---:|---:|---|---|")
    for row in product_rows:
        add(
            f"| {row['name']} | {row['visible']} | {row['type']} | "
            f"{row['description_chars']} | {row['media_count']} | {row['brand']} | "
            f"{row['seo']} | {row['info_count']} | {row['inventory']} | "
            f"{', '.join(row['flags']) or 'none'} |"
        )
    add("")
    add("## Product and variant profitability")
    add("")
    add("| Product | Variant | Visible | SKU | Current price | Wix COGS | Profit after standard fee | Standard margin | BNPL stress margin | Min price @ 40% | Min price @ 50% | Flags |")
    add("|---|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---|")
    for row in pricing_rows:
        add(
            f"| {row['product']} | {row['variant']} | {row['visible']} | {row['sku']} | "
            f"{money(row['price'], currency)} | {money(row['cost'], currency)} | "
            f"{money(row['profit'], currency)} | {percent(row['standard_margin'])} | "
            f"{percent(row['stress_margin'])} | {money(row['min_40'], currency)} | "
            f"{money(row['min_50'], currency)} | {', '.join(row['flags']) or 'none'} |"
        )
    add("")
    add("## Audit limitations and errors")
    add("")
    add(f"- Limitations: {', '.join(safe_text(item, 120) for item in limitations) or 'none'}")
    add(f"- Fatal errors: {', '.join(safe_text(item, 120) for item in fatal_errors) or 'none'}")
    add("- Public desktop/mobile layout, navigation, checkout, policy-page text, shipping rules, tax rules, and payment activation require separate customer-journey verification.")
    add("")
    add("## Required next actions")
    add("")
    if missing_business:
        add(f"1. Complete API-visible business fields: {', '.join(missing_business)}.")
    else:
        add("1. Business profile fields visible through the API are complete.")
    add(f"2. Resolve {cost_missing} missing COGS rows and {zero_physical_cost} zero physical-product COGS rows using verified landed supplier costs.")
    add(f"3. Reprice or reduce verified cost for {standard_below_40} rows below the 40% standard-card baseline target.")
    add(f"4. Improve {weak_descriptions} weak descriptions, {weak_media} weak media sets, and {missing_seo} missing custom SEO records.")
    add("5. Verify Zendrop product/variant mapping and landed costs before enabling automated fulfillment or approving final prices.")
    add("6. Run a public desktop/mobile, cart, checkout, payment, shipping, tax, returns, privacy, terms, and contact-flow launch test.")
    add("")
    add("## Source references")
    add("")
    add("- Wix Catalog V1 Query Products: https://dev.wix.com/docs/api-reference/business-solutions/stores/catalog-v1/catalog/query-products")
    add("- Wix Site Properties: https://dev.wix.com/docs/api-reference/business-management/site-properties/properties/get-site-properties")
    add("- Wix COGS tracking: https://support.wix.com/en/article/wix-stores-tracking-the-cost-of-goods")
    add("- Wix Payments US fees: https://support.wix.com/en/article/wix-payments-service-fees")

    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    print(build_report(), end="")
