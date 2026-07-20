"""Read-only Wix store readiness checks.

This module deliberately contains no page, policy, product, or inventory mutation
helpers. Shipping terms, warranties, product capabilities, and legal language must
come from verified business and supplier records rather than generated guesses.
"""

from datetime import datetime, timezone

import wix_client as wix


def _description_text(product: dict) -> str:
    """Return the best available plain-text product description."""
    for key in ("plainDescription", "description"):
        value = product.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def audit_store(catalog_version: str = "v3") -> dict:
    """Audit catalog content without changing Wix or supplier state."""
    products = wix.get_all_products(catalog_version)
    weak_products = []

    for product in products:
        description = _description_text(product)
        if len(description) < 150:
            weak_products.append(
                {
                    "id": product.get("id"),
                    "name": product.get("name"),
                    "description_characters": len(description),
                }
            )

    return {
        "audited_at": datetime.now(timezone.utc).isoformat(),
        "catalog_version": catalog_version,
        "mode": "read_only",
        "products": {
            "total": len(products),
            "need_description_review": len(weak_products),
            "weak_products": weak_products,
        },
        "manual_verification_required": [
            "published Wix pages and navigation",
            "business identity and contact details",
            "shipping regions, rates, and delivery estimates",
            "return, refund, warranty, privacy, and terms language",
            "enabled payment methods and a Wix owner test order",
            "supplier facts and exact fulfillment variant mappings",
        ],
        "mutations_available": False,
    }
