import os
import re
import json
from datetime import datetime, timezone
from typing import Optional

import wix_client as wix
import empire


# ── Policy & page content ─────────────────────────────────────────────────────

SHIPPING_POLICY_HTML = """<h2>Shipping Policy</h2>
<p>At VoltEdge Electronics we are committed to getting your order to you fast and reliably.</p>

<h3>Processing Time</h3>
<p>Orders are processed within <strong>1–2 business days</strong> after payment confirmation. You'll receive an email confirmation immediately after purchase.</p>

<h3>Delivery Estimates</h3>
<table>
<tr><th>Shipping Method</th><th>Estimated Delivery</th></tr>
<tr><td>Standard Shipping</td><td>7–15 business days</td></tr>
<tr><td>Express Shipping</td><td>3–7 business days</td></tr>
</table>

<h3>Free Shipping</h3>
<p>Enjoy <strong>FREE standard shipping on all orders over $50.</strong></p>

<h3>Order Tracking</h3>
<p>Once your order ships you'll receive a tracking number via email. Use it to track your package in real time.</p>

<h3>International Orders</h3>
<p>We ship worldwide. International orders may be subject to local customs duties and import taxes, which are the responsibility of the recipient.</p>

<h3>Questions?</h3>
<p>Email us at <a href="mailto:support@voltedgegoods.com">support@voltedgegoods.com</a> — we respond within 24 hours.</p>"""

RETURN_POLICY_HTML = """<h2>Return &amp; Refund Policy</h2>
<p>We stand behind every product we sell. If you're not 100% satisfied, we'll make it right.</p>

<h3>30-Day Return Window</h3>
<p>You have <strong>30 days</strong> from the date of delivery to return your item for a full refund or exchange.</p>

<h3>Return Conditions</h3>
<ul>
<li>Item must be unused and in its original condition</li>
<li>Original packaging with all accessories, manuals, and components included</li>
<li>Electronics must be factory reset before return</li>
<li>No signs of physical damage or wear beyond unboxing</li>
</ul>

<h3>Defective or Damaged Items</h3>
<p>If your item arrives defective or damaged we will provide a <strong>prepaid return label</strong> and either send a replacement or issue a full refund — your choice, no questions asked.</p>

<h3>How to Start a Return</h3>
<ol>
<li>Email <a href="mailto:support@voltedgegoods.com">support@voltedgegoods.com</a> with your order number and reason for return</li>
<li>We'll respond within 24 hours with a return authorization and instructions</li>
<li>Ship the item back using the instructions provided</li>
<li>Refund processed within <strong>5–7 business days</strong> of receiving your return</li>
</ol>

<h3>Non-Returnable Items</h3>
<p>Items marked as final sale, digital downloads, and items returned after 30 days are not eligible for return.</p>"""

PRIVACY_POLICY_HTML = """<h2>Privacy Policy</h2>
<p><em>Last updated: July 2026</em></p>
<p>VoltEdge Electronics (\"we,\" \"us,\" or \"our\") is committed to protecting your personal information and your right to privacy.</p>

<h3>What We Collect</h3>
<ul>
<li><strong>Personal Information:</strong> Name, email address, shipping address, phone number (collected when you place an order)</li>
<li><strong>Payment Information:</strong> Processed securely by our payment provider — we never store your card details</li>
<li><strong>Usage Data:</strong> Pages visited, products viewed, browser type (via cookies and analytics)</li>
</ul>

<h3>How We Use Your Information</h3>
<ul>
<li>Process and fulfill your orders</li>
<li>Send order confirmations and shipping updates</li>
<li>Respond to customer service inquiries</li>
<li>Send promotional emails (you can unsubscribe at any time)</li>
<li>Improve our website and product selection</li>
</ul>

<h3>We Do Not Sell Your Data</h3>
<p>We will never sell, rent, or trade your personal information to third parties for their marketing purposes.</p>

<h3>Third-Party Services</h3>
<p>We use trusted third-party services for payment processing and order fulfillment. These partners only receive the data necessary to complete your order.</p>

<h3>Data Security</h3>
<p>We use SSL encryption and industry-standard security practices to protect your information.</p>

<h3>Your Rights</h3>
<p>You have the right to access, correct, or delete your personal data at any time. Email us at <a href="mailto:support@voltedgegoods.com">support@voltedgegoods.com</a>.</p>

<h3>Cookies</h3>
<p>We use cookies to enhance your browsing experience. You may disable cookies in your browser settings, though some site features may not function correctly.</p>"""

TERMS_OF_SERVICE_HTML = """<h2>Terms of Service</h2>
<p><em>Last updated: July 2026</em></p>
<p>By using voltedgegoods.com and placing orders with VoltEdge Electronics, you agree to these Terms of Service.</p>

<h3>Products &amp; Pricing</h3>
<p>We reserve the right to modify prices at any time without prior notice. All prices are displayed in USD. Products are subject to availability, and we reserve the right to limit quantities.</p>

<h3>Orders &amp; Payment</h3>
<p>By placing an order you represent that you are authorized to use the payment method provided. We reserve the right to cancel orders in cases of pricing errors, suspected fraud, or product unavailability — you will be notified and fully refunded if this occurs.</p>

<h3>Shipping &amp; Delivery</h3>
<p>Delivery times are estimates and not guaranteed. VoltEdge Electronics is not responsible for delays caused by carriers, customs, or circumstances beyond our control.</p>

<h3>Returns</h3>
<p>Returns are subject to our Return Policy, available at voltedgegoods.com/return-policy.</p>

<h3>Intellectual Property</h3>
<p>All content on this website including images, descriptions, and logos is the property of VoltEdge Electronics or its licensors and may not be reproduced without written permission.</p>

<h3>Limitation of Liability</h3>
<p>VoltEdge Electronics shall not be liable for any indirect, incidental, special, or consequential damages arising from the use of our products or website.</p>

<h3>Changes to Terms</h3>
<p>We may update these Terms at any time. Continued use of our website constitutes acceptance of the updated Terms.</p>

<h3>Contact</h3>
<p>Questions? Email <a href="mailto:support@voltedgegoods.com">support@voltedgegoods.com</a></p>"""

ABOUT_US_HTML = """<h2>About VoltEdge Electronics</h2>
<p>Welcome to <strong>VoltEdge Electronics</strong> — your premier destination for cutting-edge consumer electronics and tech accessories.</p>

<h3>Our Mission</h3>
<p>We believe everyone deserves access to premium technology without paying premium retail prices. That's why we source the latest electronics directly from top global manufacturers, delivering innovation straight to your door at prices that make sense.</p>

<h3>What We Offer</h3>
<ul>
<li>Latest consumer electronics and smart devices</li>
<li>Premium phone cases, chargers, and accessories</li>
<li>Professional-grade audio equipment</li>
<li>Smart home technology and automation</li>
<li>Gaming gear and accessories</li>
<li>Wearable tech and fitness trackers</li>
</ul>

<h3>The VoltEdge Difference</h3>
<ul>
<li><strong>Verified Quality:</strong> Every product is sourced from certified manufacturers and quality-checked before shipping</li>
<li><strong>Worldwide Shipping:</strong> Fast, tracked delivery to your door in 7–15 days</li>
<li><strong>30-Day Returns:</strong> Shop with complete confidence — if it's not right, we'll fix it</li>
<li><strong>Secure Shopping:</strong> SSL-encrypted checkout protects your information every time</li>
<li><strong>Real Support:</strong> Email us at support@voltedgegoods.com — a real person responds within 24 hours</li>
</ul>

<h3>Get in Touch</h3>
<p>Have questions or need help? We'd love to hear from you.<br>
<strong>Email:</strong> <a href="mailto:support@voltedgegoods.com">support@voltedgegoods.com</a></p>"""

FAQ_HTML = """<h2>Frequently Asked Questions</h2>

<h3>Shipping</h3>
<p><strong>How long does shipping take?</strong><br>Standard shipping takes 7–15 business days. Express shipping (3–7 days) is available at checkout.</p>

<p><strong>Do you ship internationally?</strong><br>Yes! We ship to most countries worldwide. International orders may be subject to local customs duties, which are the buyer's responsibility.</p>

<p><strong>How do I track my order?</strong><br>You'll receive a tracking number via email as soon as your order ships. Use it to track your package at any time.</p>

<p><strong>Is shipping free?</strong><br>Yes — free standard shipping on all orders over $50!</p>

<h3>Returns &amp; Refunds</h3>
<p><strong>What is your return policy?</strong><br>We offer a 30-day return window from the delivery date. Items must be unused and in original condition. See our full <a href="/return-policy">Return Policy</a>.</p>

<p><strong>My item arrived damaged or defective. What do I do?</strong><br>We're sorry to hear that! Email support@voltedgegoods.com with your order number and a photo of the issue. We'll send a replacement or full refund immediately — no return required for defects.</p>

<p><strong>How long do refunds take?</strong><br>Refunds are processed within 5–7 business days after we receive your return.</p>

<h3>Products &amp; Quality</h3>
<p><strong>Are your products authentic?</strong><br>Absolutely. All products are sourced directly from verified manufacturers and quality-checked before shipping.</p>

<p><strong>Do products come with a warranty?</strong><br>Yes. All electronics carry a minimum 30-day defect warranty. Many items also include manufacturer warranties.</p>

<h3>Payment &amp; Security</h3>
<p><strong>What payment methods do you accept?</strong><br>We accept all major credit and debit cards (Visa, Mastercard, Amex, Discover) and PayPal.</p>

<p><strong>Is my payment information secure?</strong><br>100%. We use SSL encryption and never store your card details. All payments are processed through certified, PCI-compliant payment providers.</p>

<h3>Contact &amp; Support</h3>
<p><strong>How can I reach customer support?</strong><br>Email us at <a href="mailto:support@voltedgegoods.com">support@voltedgegoods.com</a>. We respond within 24 hours, 7 days a week.</p>"""


PAGES_TO_CREATE = [
    {"title": "Shipping Policy", "slug": "shipping-policy", "content": SHIPPING_POLICY_HTML},
    {"title": "Return Policy", "slug": "return-policy", "content": RETURN_POLICY_HTML},
    {"title": "Privacy Policy", "slug": "privacy-policy", "content": PRIVACY_POLICY_HTML},
    {"title": "Terms of Service", "slug": "terms-of-service", "content": TERMS_OF_SERVICE_HTML},
    {"title": "About Us", "slug": "about-us", "content": ABOUT_US_HTML},
    {"title": "FAQ", "slug": "faq", "content": FAQ_HTML},
]


# ── Product description generator ─────────────────────────────────────────────

def _detect_category(name: str) -> str:
    n = name.lower()
    if any(k in n for k in ["earbuds", "earphone", "headphone", "headset", "speaker", "audio", "sound"]):
        return "audio"
    if any(k in n for k in ["charger", "charging", "cable", "usb", "power bank", "powerbank", "adapter", "cord"]):
        return "charging"
    if any(k in n for k in ["case", "cover", "screen protector", "tempered", "phone holder", "mount"]):
        return "phone_accessories"
    if any(k in n for k in ["smart", "wifi", "alexa", "smart home", "bulb", "plug", "strip", "sensor", "hub"]):
        return "smart_home"
    if any(k in n for k in ["gaming", "game", "controller", "joystick", "rgb", "gamepad"]):
        return "gaming"
    if any(k in n for k in ["watch", "band", "fitness", "tracker", "wearable", "bracelet"]):
        return "wearable"
    if any(k in n for k in ["laptop", "tablet", "ipad", "keyboard", "mouse", "webcam", "monitor"]):
        return "computing"
    if any(k in n for k in ["led", "light", "lamp", "strip light", "fairy"]):
        return "lighting"
    return "electronics"


def _product_description(name: str) -> str:
    cat = _detect_category(name)
    templates = {
        "audio": (
            f"<p>Elevate your listening experience with the <strong>{name}</strong>. "
            f"Engineered for audiophiles and everyday listeners alike, this premium audio device delivers "
            f"rich, immersive sound with crystal-clear highs and deep, punchy bass.</p>"
            f"<p><strong>Key Features:</strong></p>"
            f"<ul>"
            f"<li>High-fidelity sound with advanced driver technology</li>"
            f"<li>Comfortable ergonomic design for extended wear</li>"
            f"<li>Bluetooth with stable, low-latency wireless connection</li>"
            f"<li>Long-lasting battery life to keep the music going</li>"
            f"<li>Built-in microphone for crystal-clear hands-free calls</li>"
            f"</ul>"
            f"<p>Whether you're commuting, working out, or unwinding at home, the {name} delivers studio-quality sound wherever you go.</p>"
            f"<p><strong>Free shipping on orders over $50 | 30-day returns guaranteed</strong></p>"
        ),
        "charging": (
            f"<p>Keep every device powered up with the <strong>{name}</strong>. "
            f"Built with advanced charging technology, this essential accessory delivers fast, safe, and reliable power for all your devices.</p>"
            f"<p><strong>Key Features:</strong></p>"
            f"<ul>"
            f"<li>Fast charging compatible with all major smartphones and tablets</li>"
            f"<li>Universal compatibility across devices and brands</li>"
            f"<li>Built-in safety protection — overvoltage, overcurrent, and overheating prevention</li>"
            f"<li>Durable construction built to last through daily use</li>"
            f"<li>Compact and travel-friendly design</li>"
            f"</ul>"
            f"<p>Never run out of power again. The {name} is your dependable charging companion at home, work, or on the go.</p>"
            f"<p><strong>Free shipping on orders over $50 | 30-day returns guaranteed</strong></p>"
        ),
        "phone_accessories": (
            f"<p>Protect and upgrade your device with the <strong>{name}</strong>. "
            f"Precision-crafted for a perfect fit, this premium accessory blends maximum protection with sleek everyday style.</p>"
            f"<p><strong>Key Features:</strong></p>"
            f"<ul>"
            f"<li>Military-grade drop protection tested to real-world standards</li>"
            f"<li>Slim profile that doesn't add unnecessary bulk</li>"
            f"<li>Precise cutouts for all ports, buttons, and cameras</li>"
            f"<li>Premium materials that look great and feel even better</li>"
            f"<li>Wireless charging compatible</li>"
            f"</ul>"
            f"<p>Give your device the protection it deserves. The {name} keeps your phone safe without sacrificing style.</p>"
            f"<p><strong>Free shipping on orders over $50 | 30-day returns guaranteed</strong></p>"
        ),
        "smart_home": (
            f"<p>Transform your living space with the <strong>{name}</strong>. "
            f"This intelligent device integrates seamlessly into your home, giving you effortless control at your fingertips — or with your voice.</p>"
            f"<p><strong>Key Features:</strong></p>"
            f"<ul>"
            f"<li>Simple setup — fully operational in minutes</li>"
            f"<li>Voice control compatible with Alexa and Google Home</li>"
            f"<li>Remote control from anywhere via smartphone app</li>"
            f"<li>Energy-efficient design that reduces electricity costs</li>"
            f"<li>Scheduling and automation for true hands-free convenience</li>"
            f"</ul>"
            f"<p>Make your home smarter, more efficient, and more comfortable with the {name}.</p>"
            f"<p><strong>Free shipping on orders over $50 | 30-day returns guaranteed</strong></p>"
        ),
        "gaming": (
            f"<p>Level up your setup with the <strong>{name}</strong>. "
            f"Engineered for competitive gamers and casual players alike, this high-performance accessory gives you the edge you need to dominate.</p>"
            f"<p><strong>Key Features:</strong></p>"
            f"<ul>"
            f"<li>Ultra-responsive performance built for competitive play</li>"
            f"<li>Ergonomic design optimized for extended gaming sessions</li>"
            f"<li>Premium build quality that holds up through intense gameplay</li>"
            f"<li>Universal compatibility across major platforms</li>"
            f"<li>Customizable settings to match your personal play style</li>"
            f"</ul>"
            f"<p>Dominate the competition. The {name} is the weapon every serious gamer needs in their arsenal.</p>"
            f"<p><strong>Free shipping on orders over $50 | 30-day returns guaranteed</strong></p>"
        ),
        "wearable": (
            f"<p>Stay connected, motivated, and in control with the <strong>{name}</strong>. "
            f"This stylish wearable keeps you informed about your health and your world — all from your wrist.</p>"
            f"<p><strong>Key Features:</strong></p>"
            f"<ul>"
            f"<li>Real-time health and fitness tracking — steps, heart rate, calories, and more</li>"
            f"<li>Sleek, stylish design suitable for any occasion</li>"
            f"<li>Long battery life — days of use on a single charge</li>"
            f"<li>Smartphone notifications for calls, texts, and apps</li>"
            f"<li>Water-resistant for workouts, rain, and everyday wear</li>"
            f"</ul>"
            f"<p>Health, connectivity, and style all in one device. The {name} is built for the way you live.</p>"
            f"<p><strong>Free shipping on orders over $50 | 30-day returns guaranteed</strong></p>"
        ),
        "lighting": (
            f"<p>Set the perfect mood with the <strong>{name}</strong>. "
            f"From vibrant color scenes to warm relaxing tones, this premium lighting solution transforms any space instantly.</p>"
            f"<p><strong>Key Features:</strong></p>"
            f"<ul>"
            f"<li>16 million colors and adjustable brightness levels</li>"
            f"<li>App control for custom scenes and schedules</li>"
            f"<li>Voice control compatible with Alexa and Google Home</li>"
            f"<li>Energy-efficient LED technology</li>"
            f"<li>Easy installation — no electrician required</li>"
            f"</ul>"
            f"<p>Create the perfect atmosphere for any occasion with the {name}.</p>"
            f"<p><strong>Free shipping on orders over $50 | 30-day returns guaranteed</strong></p>"
        ),
        "electronics": (
            f"<p>Experience premium technology with the <strong>{name}</strong>. "
            f"Crafted with precision engineering and quality materials, this device is built to perform, impress, and last.</p>"
            f"<p><strong>Key Features:</strong></p>"
            f"<ul>"
            f"<li>Superior build quality engineered for long-lasting performance</li>"
            f"<li>Intuitive design for effortless everyday use</li>"
            f"<li>Broad compatibility with modern devices and platforms</li>"
            f"<li>Compact form factor that fits seamlessly into your lifestyle</li>"
            f"<li>Backed by VoltEdge's quality and satisfaction guarantee</li>"
            f"</ul>"
            f"<p>The {name} delivers exceptional value and performance — because you deserve technology that just works.</p>"
            f"<p><strong>Free shipping on orders over $50 | 30-day returns guaranteed</strong></p>"
        ),
    }
    return templates.get(cat, templates["electronics"])


def _strip_html(html: str) -> str:
    return ' '.join(re.sub(r'<[^>]+>', ' ', html).split())


def _seo_for_product(name: str, desc_html: str) -> dict:
    plain = _strip_html(desc_html)
    snippet = plain[:140].rsplit(' ', 1)[0] + '...' if len(plain) > 140 else plain
    return {
        "seo_title": f"{name} | VoltEdge Electronics",
        "seo_description": f"Shop {name} at VoltEdge Electronics. {snippet} Free shipping on orders $50+. 30-day returns.",
    }


# ── Audit ──────────────────────────────────────────────────────────────────────

def audit_store(catalog_version: str = "v3") -> dict:
    result = {"audited_at": datetime.now(timezone.utc).isoformat()}

    # Pages
    try:
        pages = wix.get_pages()
        existing = {p.get("slug", "").lower() for p in pages}
        missing = [p["slug"] for p in PAGES_TO_CREATE if p["slug"] not in existing]
        result["pages"] = {"total": len(pages), "existing_slugs": sorted(existing), "missing": missing}
    except Exception as e:
        result["pages"] = {"error": str(e)}

    # Store settings
    try:
        settings = wix.get_store_settings()
        gen = settings.get("generalSettings", {})
        result["store_settings"] = {
            "has_return_policy": bool(gen.get("returnPolicy") or gen.get("returnPolicyText")),
            "has_shipping_policy": bool(gen.get("shippingPolicy") or gen.get("shippingPolicyText")),
            "raw_keys": list(settings.keys()),
        }
    except Exception as e:
        result["store_settings"] = {"error": str(e)}

    # Products
    try:
        products = wix.get_all_products(catalog_version)
        weak = [
            {"id": p.get("id"), "name": p.get("name"), "desc_chars": len((p.get("description") or "").strip())}
            for p in products
            if len((p.get("description") or "").strip()) < 150
        ]
        result["products"] = {"total": len(products), "need_description_update": len(weak), "weak_products": weak}
    except Exception as e:
        result["products"] = {"error": str(e)}

    return result


# ── Policy text update (checkout policies) ─────────────────────────────────────

SHIPPING_POLICY_TEXT = (
    "Standard shipping: 7–15 business days. Express: 3–7 business days. "
    "Free shipping on orders over $50. Tracking provided for all orders. "
    "International orders may be subject to customs duties."
)

RETURN_POLICY_TEXT = (
    "30-day returns on unused items in original packaging. "
    "Defective items get a prepaid return label and immediate replacement or full refund. "
    "Email support@voltedgegoods.com with your order number to start a return. "
    "Refunds processed within 5–7 business days."
)

PRIVACY_POLICY_TEXT = (
    "We collect only what's needed to process your order. "
    "We never sell your personal data. "
    "Full policy: voltedgegoods.com/privacy-policy"
)

TERMS_TEXT = (
    "By placing an order you agree to our Terms of Service. "
    "Products subject to availability. Prices may change without notice. "
    "Full terms: voltedgegoods.com/terms-of-service"
)


def setup_store_policies() -> dict:
    patch = {
        "returnPolicy": RETURN_POLICY_TEXT,
        "shippingPolicy": SHIPPING_POLICY_TEXT,
        "termsAndConditions": TERMS_TEXT,
        "privacyPolicy": PRIVACY_POLICY_TEXT,
    }
    try:
        resp = wix.update_store_settings(patch)
        return {"status": "updated", "policies_set": list(patch.keys()), "response": resp}
    except Exception as e:
        return {"status": "error", "error": str(e)}


# ── Pages ──────────────────────────────────────────────────────────────────────

def setup_pages() -> dict:
    try:
        existing_pages = wix.get_pages()
        existing_slugs = {p.get("slug", "").lower() for p in existing_pages}
    except Exception as e:
        return {"status": "error", "error": f"Could not list existing pages: {e}"}

    created, skipped, errors = [], [], []
    for page in PAGES_TO_CREATE:
        if page["slug"] in existing_slugs:
            skipped.append({"slug": page["slug"], "reason": "already exists"})
            continue
        try:
            r = wix.create_page(title=page["title"], slug=page["slug"])
            created.append({"slug": page["slug"], "title": page["title"], "page_id": r.get("page", {}).get("id")})
        except Exception as e:
            errors.append({"slug": page["slug"], "error": str(e)})

    return {
        "created": created,
        "skipped": skipped,
        "errors": errors,
        "note": (
            "Pages created with correct URLs. To add full content: "
            "use GET /store/pages to retrieve HTML, then paste into Wix Editor for each page."
        ),
    }


# ── Product descriptions & SEO ─────────────────────────────────────────────────

def enhance_products(catalog_version: str = "v3", dry_run: bool = False) -> dict:
    products = wix.get_all_products(catalog_version)
    updated, skipped, errors = [], [], []

    for p in products:
        pid = p.get("id")
        name = p.get("name", "") or ""
        existing = (p.get("description") or "").strip()

        if len(existing) >= 150:
            skipped.append({"id": pid, "name": name, "reason": "description already substantial"})
            continue

        new_desc = _product_description(name)
        seo = _seo_for_product(name, new_desc)

        if dry_run:
            updated.append({"id": pid, "name": name, "dry_run": True,
                            "seo_title": seo["seo_title"], "desc_preview": new_desc[:120] + "..."})
            continue

        try:
            wix.update_product_content(
                product_id=pid,
                description=new_desc,
                seo_title=seo["seo_title"],
                seo_description=seo["seo_description"],
                catalog_version=catalog_version,
            )
            updated.append({"id": pid, "name": name, "seo_title": seo["seo_title"]})
        except Exception as e:
            errors.append({"id": pid, "name": name, "error": str(e)})

    return {
        "run_at": datetime.now(timezone.utc).isoformat(),
        "dry_run": dry_run,
        "total_products": len(products),
        "updated": len(updated),
        "skipped": len(skipped),
        "errors": len(errors),
        "details": {"updated": updated, "errors": errors},
    }


# ── Full setup ─────────────────────────────────────────────────────────────────

def full_store_setup(catalog_version: str = "v3") -> dict:
    print("[store-setup] Setting checkout policies...")
    policies = setup_store_policies()

    print("[store-setup] Creating missing info pages...")
    pages = setup_pages()

    print("[store-setup] Enhancing product descriptions and SEO...")
    products = enhance_products(catalog_version, dry_run=False)

    result = {
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "policies": policies,
        "pages": pages,
        "products": products,
    }

    empire.notify_empire("store_setup_complete", {
        "policies_updated": policies.get("status") == "updated",
        "pages_created": len(pages.get("created", [])),
        "products_enhanced": products.get("updated", 0),
        "total_products": products.get("total_products", 0),
    })

    return result
