#!/usr/bin/env python3
"""
affiliate_content_engine.py — AI SEO Blog Posts + Email Sequences for Affiliate Revenue
========================================================================================
Generates:
  - SEO blog posts targeting buyer-intent keywords
  - Email drip sequences that promote affiliate products
  - Product review/comparison articles
  - Landing page copy

Affiliate Programs (high-commission, recurring):
  - NordVPN: $40-100 per sale
  - Bluehost: $65 per signup
  - Jasper AI: 30% recurring
  - ConvertKit: 30% recurring
  - Shopify: $150 per signup
  - ClickFunnels: 30% recurring
  - Canva Pro: up to $36 per signup

Revenue target: 100 articles → 10K organic visits/month → 200 clicks → $2-5K/month
"""
import os
import json
import logging
import re
from datetime import datetime
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv(Path.home() / ".env")
load_dotenv(Path.home() / "buddy_core/.env")

HOME = Path.home()
ARTICLES_DIR = HOME / "affiliate_content" / "articles"
EMAILS_DIR = HOME / "affiliate_content" / "emails"
ARTICLES_DIR.mkdir(parents=True, exist_ok=True)
EMAILS_DIR.mkdir(parents=True, exist_ok=True)

GEMINI_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [AFFILIATE] %(message)s",
    handlers=[
        logging.FileHandler(HOME / "logs" / "affiliate_engine.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("affiliate")

# Affiliate product catalog
PRODUCTS = {
    "nordvpn": {"name": "NordVPN", "commission": "$40-100/sale", "link_placeholder": "[AFFILIATE_LINK_NORDVPN]", "category": "security"},
    "bluehost": {"name": "Bluehost", "commission": "$65/signup", "link_placeholder": "[AFFILIATE_LINK_BLUEHOST]", "category": "hosting"},
    "jasper": {"name": "Jasper AI", "commission": "30% recurring", "link_placeholder": "[AFFILIATE_LINK_JASPER]", "category": "ai_tools"},
    "canva": {"name": "Canva Pro", "commission": "$36/signup", "link_placeholder": "[AFFILIATE_LINK_CANVA]", "category": "design"},
    "shopify": {"name": "Shopify", "commission": "$150/signup", "link_placeholder": "[AFFILIATE_LINK_SHOPIFY]", "category": "ecommerce"},
    "convertkit": {"name": "ConvertKit", "commission": "30% recurring", "link_placeholder": "[AFFILIATE_LINK_CONVERTKIT]", "category": "email"},
}

# SEO keyword targets (buyer-intent)
ARTICLE_TOPICS = [
    {"title": "Best VPN for Privacy in 2026 (Tested & Reviewed)", "product": "nordvpn", "keywords": "best vpn, vpn review, nordvpn review"},
    {"title": "How to Start a Blog That Makes Money in 2026", "product": "bluehost", "keywords": "start a blog, make money blogging, best blog hosting"},
    {"title": "Best AI Writing Tools Compared (I Tested 7)", "product": "jasper", "keywords": "ai writing tools, best ai writer, jasper ai review"},
    {"title": "How to Build a Shopify Store in 1 Day", "product": "shopify", "keywords": "shopify tutorial, start online store, shopify review"},
    {"title": "Best Email Marketing Platform for Beginners", "product": "convertkit", "keywords": "email marketing, convertkit review, best email platform"},
    {"title": "Canva Pro vs Free: Is It Worth the Upgrade?", "product": "canva", "keywords": "canva pro review, canva free vs pro, best design tool"},
    {"title": "5 Tools Every Online Business Needs in 2026", "product": "jasper", "keywords": "online business tools, best business software"},
    {"title": "How to Protect Your Privacy Online (Complete Guide)", "product": "nordvpn", "keywords": "online privacy, protect privacy, vpn guide"},
    {"title": "How to Create a Sales Funnel That Actually Converts", "product": "shopify", "keywords": "sales funnel, funnel builder, shopify sales"},
    {"title": "The Best Side Hustle Tools to Make Money From Home", "product": "bluehost", "keywords": "side hustle tools, work from home, make money online"},
]


def gemini_generate(prompt, max_tokens=8192):
    if not GEMINI_KEY:
        return ""
    try:
        r = requests.post(GEMINI_URL, params={"key": GEMINI_KEY},
            json={"contents": [{"parts": [{"text": prompt}]}],
                  "generationConfig": {"maxOutputTokens": max_tokens, "temperature": 0.7}},
            timeout=60)
        r.raise_for_status()
        return r.json()["candidates"][0]["content"]["parts"][0]["text"]
    except Exception as e:
        log.error("Gemini: %s", e)
        return ""


def generate_article(topic: dict) -> dict:
    """Generate a full SEO blog post."""
    product = PRODUCTS[topic["product"]]
    prompt = f"""Write a 2000-word SEO blog post for:
Title: {topic["title"]}
Target keywords: {topic["keywords"]}
Affiliate product: {product["name"]}

Requirements:
- Engaging introduction with a hook
- Use H2 and H3 headings for structure
- Include the target keywords naturally (3-5 times)
- Personal experience tone ("I tested...", "In my experience...")
- Include pros and cons
- Include a clear CTA to try the product: {product["link_placeholder"]}
- Add FAQ section at the end (3-5 questions)
- Mention the product naturally 4-5 times
- End with a strong recommendation
- Format in Markdown
- NO fake statistics or fabricated claims
- Include "Disclosure: This post contains affiliate links" at the top
"""
    content = gemini_generate(prompt)
    if not content:
        return None

    safe = re.sub(r'[^a-zA-Z0-9]', '_', topic["title"][:50])
    filepath = ARTICLES_DIR / f"{datetime.now().strftime('%Y%m%d')}_{safe}.md"
    filepath.write_text(content, encoding="utf-8")

    log.info("Article: %s (%d words)", topic["title"][:40], len(content.split()))
    return {"title": topic["title"], "path": str(filepath), "product": topic["product"]}


def generate_email_sequence(product_key: str, num_emails: int = 5) -> dict:
    """Generate email drip sequence for an affiliate product."""
    product = PRODUCTS[product_key]
    prompt = f"""Write a {num_emails}-email sequence promoting {product["name"]}.

Email 1: Welcome + pain point identification
Email 2: Educational content about the problem
Email 3: Introduce {product["name"]} as the solution
Email 4: Case study / social proof
Email 5: Limited time offer + strong CTA

For each email provide:
SUBJECT: [subject line]
BODY: [full email text with {product["link_placeholder"]} where the affiliate link goes]

Make them conversational, value-first. No spam vibes.
Include "You're receiving this because you signed up at dominionhealing.org" footer.
"""
    content = gemini_generate(prompt)
    if not content:
        return None

    filepath = EMAILS_DIR / f"{product_key}_sequence.md"
    filepath.write_text(content, encoding="utf-8")

    log.info("Email sequence: %s (%d emails)", product["name"], num_emails)
    return {"product": product_key, "path": str(filepath), "emails": num_emails}


def generate_batch(num_articles: int = 5):
    """Generate a batch of articles and email sequences."""
    log.info("=" * 60)
    log.info("GENERATING %d ARTICLES + EMAIL SEQUENCES", num_articles)
    log.info("=" * 60)

    import random
    topics = random.sample(ARTICLE_TOPICS, min(num_articles, len(ARTICLE_TOPICS)))

    articles = []
    for t in topics:
        result = generate_article(t)
        if result:
            articles.append(result)

    # Generate email sequences for unique products
    products_used = set(t["product"] for t in topics)
    sequences = []
    for p in products_used:
        result = generate_email_sequence(p)
        if result:
            sequences.append(result)

    log.info("=" * 60)
    log.info("DONE: %d articles, %d email sequences", len(articles), len(sequences))
    log.info("=" * 60)

    return {"articles": articles, "sequences": sequences}


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch", type=int, default=3, help="Number of articles")
    parser.add_argument("--list", action="store_true", help="Show topics")
    args = parser.parse_args()

    if args.list:
        for t in ARTICLE_TOPICS:
            print(f"  [{t['product']}] {t['title']}")
    else:
        generate_batch(args.batch)
