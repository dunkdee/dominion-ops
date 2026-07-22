#!/usr/bin/env python3
"""Audit a published Wix storefront visually and semantically without mutations.

The script runs on a clean GitHub Actions runner with Playwright. It only loads
public pages, records public visible text and screenshots in a private artifact,
and generates a redacted summary suitable for the repository audit branch.
It never submits forms, clicks purchase controls, changes a cart, authenticates,
or calls Wix management mutation endpoints.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse, urlunparse

from playwright.async_api import Browser, Page, async_playwright

MAX_PAGES = 18
DESKTOP = {"width": 1440, "height": 1000}
MOBILE = {"width": 390, "height": 844}
PAGE_HINTS = (
    "shop", "store", "product", "about", "contact", "faq", "shipping",
    "return", "refund", "privacy", "terms", "policy", "cart",
)
POLICY_HINTS = ("shipping", "return", "refund", "privacy", "terms")
PLACEHOLDER_PATTERNS = (
    r"\blorem ipsum\b", r"\bcoming soon\b", r"\buntitled\b",
    r"\btest product\b", r"\bplaceholder\b",
)
VAGUE_CTA = {"click here", "more", "learn more", "read more", "submit"}


def clean_url(value: str) -> str:
    parsed = urlparse(value.strip())
    path = parsed.path or "/"
    return urlunparse((parsed.scheme or "https", parsed.netloc, path, "", parsed.query, ""))


def same_origin(a: str, b: str) -> bool:
    pa, pb = urlparse(a), urlparse(b)
    return pa.scheme == pb.scheme and pa.netloc == pb.netloc


def safe_name(url: str, viewport_name: str) -> str:
    parsed = urlparse(url)
    label = re.sub(r"[^a-zA-Z0-9]+", "-", parsed.path.strip("/") or "home").strip("-")[:60]
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:10]
    return f"{label}-{viewport_name}-{digest}.png"


def choose_primary_url(metadata: dict[str, Any]) -> str:
    urls = metadata.get("published_urls") or []
    for row in urls:
        if isinstance(row, dict) and row.get("primary") and row.get("url"):
            return clean_url(str(row["url"]))
    for row in urls:
        if isinstance(row, dict) and row.get("url"):
            return clean_url(str(row["url"]))
    for candidate in metadata.get("fallback_candidates") or []:
        if candidate:
            return clean_url(str(candidate))
    raise RuntimeError("no_published_storefront_url")


async def extract_page(page: Page, url: str) -> dict[str, Any]:
    return await page.evaluate(
        """() => {
          const visible = (el) => {
            if (!el) return false;
            const s = getComputedStyle(el);
            const r = el.getBoundingClientRect();
            return s.display !== 'none' && s.visibility !== 'hidden' && r.width > 0 && r.height > 0;
          };
          const text = (el) => (el?.innerText || el?.textContent || '').replace(/\s+/g, ' ').trim();
          const rows = (selector) => [...document.querySelectorAll(selector)].filter(visible).map(text).filter(Boolean);
          const links = [...document.querySelectorAll('a[href]')].filter(visible).map(a => ({
            text: text(a), href: a.href, aria: a.getAttribute('aria-label') || ''
          }));
          const buttons = [...document.querySelectorAll('button,[role="button"],input[type="submit"],input[type="button"]')]
            .filter(visible).map(b => text(b) || b.getAttribute('aria-label') || b.getAttribute('title') || b.value || '');
          const bodyText = text(document.body).slice(0, 30000);
          const navText = rows('header a, header button, nav a, nav button');
          const footerText = rows('footer a, footer button, footer p, footer span');
          const images = [...document.images].filter(visible);
          const missingAlt = images.filter(img => !img.hasAttribute('alt') || !img.alt.trim()).length;
          const emptyLinks = links.filter(x => !x.text && !x.aria).length;
          const unlabeledButtons = buttons.filter(x => !x.trim()).length;
          const forms = [...document.forms].filter(visible).length;
          const prices = rows('[data-hook*="price"], [class*="price" i], [aria-label*="price" i]').slice(0, 20);
          const addToCart = buttons.filter(x => /add to (cart|bag)|buy now/i.test(x));
          return {
            final_url: location.href,
            title: document.title || '',
            meta_description: document.querySelector('meta[name="description"]')?.content || '',
            canonical: document.querySelector('link[rel="canonical"]')?.href || '',
            h1: rows('h1'), h2: rows('h2'), h3: rows('h3'),
            nav_text: navText.slice(0, 100), footer_text: footerText.slice(0, 150),
            buttons: buttons.slice(0, 100), links: links.slice(0, 300),
            body_text: bodyText, forms, prices, add_to_cart: addToCart,
            missing_alt_count: missingAlt, empty_link_count: emptyLinks,
            unlabeled_button_count: unlabeledButtons,
            mobile_overflow_px: Math.max(0, document.documentElement.scrollWidth - window.innerWidth),
            has_cookie_banner: /cookie|privacy preferences|accept all/i.test(bodyText),
          };
        }"""
    )


def page_issues(record: dict[str, Any], viewport_name: str) -> list[str]:
    issues: list[str] = []
    if record.get("status") and int(record["status"]) >= 400:
        issues.append("http_error")
    if not str(record.get("title") or "").strip():
        issues.append("missing_page_title")
    if not str(record.get("meta_description") or "").strip():
        issues.append("missing_meta_description")
    h1 = record.get("h1") or []
    if not h1:
        issues.append("missing_h1")
    elif len(h1) > 1:
        issues.append("multiple_h1")
    if record.get("missing_alt_count", 0):
        issues.append("images_missing_alt")
    if record.get("empty_link_count", 0):
        issues.append("empty_accessible_links")
    if record.get("unlabeled_button_count", 0):
        issues.append("unlabeled_buttons")
    if viewport_name == "mobile" and record.get("mobile_overflow_px", 0) > 4:
        issues.append("mobile_horizontal_overflow")
    body = str(record.get("body_text") or "").lower()
    if any(re.search(pattern, body, re.I) for pattern in PLACEHOLDER_PATTERNS):
        issues.append("placeholder_or_test_wording")
    button_texts = {str(item).strip().lower() for item in record.get("buttons") or []}
    if button_texts.intersection(VAGUE_CTA):
        issues.append("vague_call_to_action")
    if "product-page" in str(record.get("final_url") or ""):
        if not record.get("prices"):
            issues.append("product_price_not_detected")
        if not record.get("add_to_cart"):
            issues.append("add_to_cart_not_detected")
    return sorted(set(issues))


async def visit(browser: Browser, url: str, viewport_name: str, viewport: dict[str, int], output: Path) -> dict[str, Any]:
    context = await browser.new_context(viewport=viewport, locale="en-US")
    page = await context.new_page()
    console_errors: list[str] = []
    page.on("console", lambda msg: console_errors.append(msg.text[:300]) if msg.type == "error" else None)
    record: dict[str, Any] = {"requested_url": url, "viewport": viewport_name, "status": None}
    try:
        response = await page.goto(url, wait_until="domcontentloaded", timeout=60000)
        record["status"] = response.status if response else None
        try:
            await page.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            pass
        await page.wait_for_timeout(2500)
        record.update(await extract_page(page, url))
        screenshot = output / "screenshots" / safe_name(record.get("final_url") or url, viewport_name)
        screenshot.parent.mkdir(parents=True, exist_ok=True)
        await page.screenshot(path=str(screenshot), full_page=True)
        record["screenshot"] = str(screenshot.relative_to(output))
    except Exception as exc:
        record["error_type"] = type(exc).__name__
        record["error_message"] = str(exc)[:300]
    record["console_errors"] = console_errors[:30]
    record["issues"] = page_issues(record, viewport_name)
    await context.close()
    return record


def candidate_urls(primary: str, home: dict[str, Any], metadata: dict[str, Any]) -> list[str]:
    selected = [primary]
    links = home.get("links") or []
    ranked: list[tuple[int, str]] = []
    for item in links:
        href = str(item.get("href") or "")
        label = f"{item.get('text') or ''} {href}".lower()
        if not href or not same_origin(primary, href):
            continue
        score = sum(1 for hint in PAGE_HINTS if hint in label)
        if score:
            ranked.append((score, clean_url(href)))
    for _, href in sorted(ranked, key=lambda row: (-row[0], row[1])):
        if href not in selected:
            selected.append(href)
    for product in metadata.get("sample_products") or []:
        slug = str(product.get("slug") or "").strip("/")
        if slug:
            href = clean_url(urljoin(primary, f"/product-page/{slug}"))
            if href not in selected:
                selected.append(href)
    return selected[:MAX_PAGES]


def summarize(records: list[dict[str, Any]], metadata: dict[str, Any], primary: str) -> dict[str, Any]:
    desktop = [row for row in records if row.get("viewport") == "desktop"]
    all_issues: dict[str, int] = {}
    for row in records:
        for issue in row.get("issues") or []:
            all_issues[issue] = all_issues.get(issue, 0) + 1
    nav = " ".join(" ".join(row.get("nav_text") or []) for row in desktop).lower()
    footer = " ".join(" ".join(row.get("footer_text") or []) for row in desktop).lower()
    pages = " ".join(str(row.get("final_url") or "") for row in desktop).lower()
    required = {}
    for hint in ("shop", "about", "contact", *POLICY_HINTS):
        required[hint] = hint in nav or hint in footer or hint in pages
    home = next((row for row in desktop if clean_url(str(row.get("requested_url") or "")) == primary), desktop[0] if desktop else {})
    recommendations: list[str] = []
    if not home.get("h1"):
        recommendations.append("Add one clear homepage H1 stating what the store sells and who it serves.")
    if not home.get("buttons"):
        recommendations.append("Add a visible primary homepage call to action such as Shop Products.")
    if not required.get("shipping"):
        recommendations.append("Add a clearly labeled Shipping Policy link in the footer and product-page support area.")
    if not required.get("return") and not required.get("refund"):
        recommendations.append("Add a clearly labeled Returns & Refunds link in the footer and product-page support area.")
    if not required.get("privacy"):
        recommendations.append("Add a Privacy Policy link in the footer.")
    if not required.get("terms"):
        recommendations.append("Add a Terms & Conditions link in the footer.")
    if not required.get("contact"):
        recommendations.append("Add a Contact link with a monitored support channel.")
    if all_issues.get("vague_call_to_action"):
        recommendations.append("Replace vague buttons such as More or Click Here with action-specific wording.")
    if all_issues.get("mobile_horizontal_overflow"):
        recommendations.append("Correct horizontal overflow on the affected mobile pages.")
    if all_issues.get("placeholder_or_test_wording"):
        recommendations.append("Remove placeholder, test, untitled, or coming-soon wording from published pages.")
    props = metadata.get("site_properties") or {}
    business_name = str(props.get("businessName") or props.get("siteDisplayName") or "").strip()
    return {
        "primary_url": primary,
        "pages_audited": len(desktop),
        "viewport_records": len(records),
        "issue_counts": dict(sorted(all_issues.items())),
        "required_link_presence": required,
        "business_name_present_in_public_properties": bool(business_name),
        "contact_email_present_in_public_properties": bool(props.get("email")),
        "contact_phone_present_in_public_properties": bool(props.get("phone")),
        "recommendations": recommendations,
        "sampled_product_pages": sum("product-page" in str(row.get("final_url") or "") for row in desktop),
    }


async def run(args: argparse.Namespace) -> int:
    metadata = json.loads(Path(args.metadata).read_text(encoding="utf-8"))
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    primary = choose_primary_url(metadata)
    records: list[dict[str, Any]] = []
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        home = await visit(browser, primary, "desktop", DESKTOP, output)
        records.append(home)
        urls = candidate_urls(primary, home, metadata)
        for url in urls[1:]:
            records.append(await visit(browser, url, "desktop", DESKTOP, output))
        for url in urls:
            records.append(await visit(browser, url, "mobile", MOBILE, output))
        await browser.close()
    private_report = {
        "audit": "wix-storefront-layout-wording",
        "primary_url": primary,
        "metadata": metadata,
        "records": records,
        "summary": summarize(records, metadata, primary),
        "safety": {
            "public_pages_only": True,
            "forms_submitted": False,
            "buttons_clicked": False,
            "cart_changed": False,
            "checkout_started": False,
            "wix_management_mutations": False,
            "full_visible_text_private_artifact_only": True,
        },
    }
    (output / "private_report.json").write_text(json.dumps(private_report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    public_summary = {
        "audit": private_report["audit"],
        "primary_url": primary,
        "summary": private_report["summary"],
        "safety": private_report["safety"],
        "success": bool(records) and any(row.get("status") == 200 for row in records),
    }
    (output / "public_summary.json").write_text(json.dumps(public_summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0 if public_summary["success"] else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--metadata", required=True)
    parser.add_argument("--output", required=True)
    return asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
