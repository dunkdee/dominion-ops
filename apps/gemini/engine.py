"""Dominion Gemini content engine — powered by Vertex AI."""

import json
import os
from typing import Any

from google import genai
from google.oauth2 import service_account

FLASH = "gemini-2.5-flash"
PRO = "gemini-2.5-pro"

SYSTEM = """You are the content engine for Dominion Healing, a personal sovereignty and wealth-building brand.
Tone: bold, faith-driven, empowering. Never timid. Every word builds authority and inspires action.
Audience: people ready to break free from limitation and build their empire.

Non-negotiable content rules:
- Produce original work. Never copy another creator's wording, script, music, footage, thumbnail, or trade dress.
- Competitive examples may be used only to extract general patterns such as hook structure, pacing, topic framing, and audience intent.
- Do not make unsupported medical, legal, financial, or earnings claims.
- Flag claims that require verification and identify where synthetic-media disclosure may be required.
- Recommend only owned, licensed, public-domain, or properly cleared music and visual assets.
- Every asset must add distinct educational, documentary, analytical, or entertainment value; avoid repetitive mass-produced templates.
"""

PLATFORM_SPECS = {
    "youtube": {
        "format": "8-12 minute long-form video",
        "primary_kpis": ["click-through rate", "average view duration", "returning viewers", "qualified clicks"],
    },
    "youtube_shorts": {
        "format": "20-50 second vertical video",
        "primary_kpis": ["viewed vs swiped away", "average percentage viewed", "rewatches", "qualified clicks"],
    },
    "tiktok": {
        "format": "15-60 second vertical video",
        "primary_kpis": ["two-second hold", "completion rate", "shares", "profile visits"],
    },
    "instagram_reels": {
        "format": "15-60 second vertical video",
        "primary_kpis": ["three-second hold", "completion rate", "saves", "profile visits"],
    },
    "facebook": {
        "format": "native video plus concise post",
        "primary_kpis": ["watch time", "shares", "comments", "landing-page clicks"],
    },
    "linkedin": {
        "format": "authority post or native video",
        "primary_kpis": ["dwell time", "saves", "qualified comments", "profile views"],
    },
    "x": {
        "format": "short post or thread",
        "primary_kpis": ["engagement rate", "bookmarks", "profile visits", "link clicks"],
    },
}


def client():
    project = os.environ.get("GCP_PROJECT_ID", "")
    location = os.environ.get("GCP_REGION", "us-central1")
    sa_json = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
    if sa_json:
        info = json.loads(sa_json)
        project = project or info.get("project_id", "")
        creds = service_account.Credentials.from_service_account_info(
            info, scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
        return genai.Client(vertexai=True, project=project, location=location, credentials=creds)
    return genai.Client(vertexai=True, project=project, location=location)


def _extract_json(text: str) -> dict[str, Any]:
    """Extract a JSON object from a model response, including fenced responses."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()

    start = cleaned.find("{")
    end = cleaned.rfind("}") + 1
    if start == -1 or end <= start:
        raise ValueError("Model response did not contain a JSON object")
    return json.loads(cleaned[start:end])


def youtube_script(topic: str, duration_minutes: int = 8) -> dict:
    prompt = f"""Write a complete YouTube video script on: {topic}

Format:
[HOOK - 30 seconds]: Attention-grabbing opening line or question
[INTRO - 60 seconds]: Who this is for, what they'll get
[BODY - {duration_minutes-2} minutes]: 3-5 main points, each with explanation and example
[CTA - 30 seconds]: Direct call to action (visit dominionhealing.org, comment, subscribe)
[END SCREEN - 15 seconds]: Subscribe + next video tease

Make it punchy. No filler. Every sentence earns its place."""
    c = client()
    r = c.models.generate_content(model=PRO, contents=SYSTEM + "\n\n" + prompt)
    return {"type": "youtube_script", "topic": topic, "script": r.text}


def tiktok_caption(topic: str) -> dict:
    prompt = f"""Write 3 TikTok caption options for a video about: {topic}

Each caption:
- Under 150 characters
- Bold opening hook
- 5-8 relevant hashtags
- Ends with engagement prompt

Format as Caption 1, Caption 2, Caption 3."""
    c = client()
    r = c.models.generate_content(model=FLASH, contents=SYSTEM + "\n\n" + prompt)
    return {"type": "tiktok_caption", "topic": topic, "captions": r.text}


def email_sequence(product: str, num_emails: int = 7) -> dict:
    prompt = f"""Write a {num_emails}-email welcome sequence for buyers of: {product}

Email sequence structure:
Email 1 (Day 0): Welcome + what they just did (confirm the decision)
Email 2 (Day 1): Quick win from the material
Email 3 (Day 3): Backstory — why this product exists
Email 4 (Day 5): Biggest mistake people make in this space
Email 5 (Day 7): Success story or transformation example
Email 6 (Day 10): Overcome an objection
Email 7 (Day 14): Next step / upsell to deeper work

For each email write: Subject line, Preview text, Body (200-300 words).
Tone: personal, direct, no corporate speak. Write like a mentor, not a marketer."""
    c = client()
    r = c.models.generate_content(model=PRO, contents=SYSTEM + "\n\n" + prompt)
    return {"type": "email_sequence", "product": product, "sequence": r.text}


def social_post(topic: str, platform: str = "twitter") -> dict:
    limits = {"twitter": 280, "x": 280, "instagram": 2200, "linkedin": 3000, "facebook": 500}
    limit = limits.get(platform.lower(), 280)
    prompt = f"""Write a {platform} post about: {topic}
Char limit: {limit}
Include relevant hashtags. Make it shareable. End with a question or CTA."""
    c = client()
    r = c.models.generate_content(model=FLASH, contents=SYSTEM + "\n\n" + prompt)
    return {"type": "social_post", "platform": platform, "topic": topic, "post": r.text}


def deep_research(query: str) -> dict:
    prompt = f"""Do deep research on: {query}

Provide:
1. Market size and opportunity
2. Top 5 competitors and their positioning
3. Gaps in the market (where Dominion Healing can win)
4. Best content angles to dominate this space
5. Recommended product ideas ($27-$997 range)
6. Top keywords/search terms to target

Be specific, not generic. Give actionable intel."""
    c = client()
    r = c.models.generate_content(model=PRO, contents=prompt)
    return {"type": "deep_research", "query": query, "research": r.text}


def product_description(product_name: str, price: int, features: list) -> dict:
    features_str = "\n".join(f"- {f}" for f in features)
    prompt = f"""Write a high-converting Gumroad product description for:
Product: {product_name}
Price: ${price}
Features:\n{features_str}

Structure:
- Opening hook (1-2 sentences, pain point or bold claim)
- Who this is for
- What's inside (bullet list)
- Transformation promise
- Urgency/scarcity element
- Closing CTA

Max 400 words. No fluff. Every line sells."""
    c = client()
    r = c.models.generate_content(model=PRO, contents=SYSTEM + "\n\n" + prompt)
    return {"type": "product_description", "product": product_name, "description": r.text}


def campaign_package(
    topic: str,
    offer: str = "",
    audience: str = "people seeking practical healing, sovereignty, and wealth-building education",
    objective: str = "authority_and_sales",
) -> dict[str, Any]:
    """Generate one original idea and package it for every major platform and funnel stage."""
    specs = json.dumps(PLATFORM_SPECS, indent=2)
    prompt = f"""Build a complete, production-ready cross-platform campaign package.

TOPIC: {topic}
OFFER: {offer or 'No direct offer supplied; use dominionhealing.org as the primary destination'}
AUDIENCE: {audience}
OBJECTIVE: {objective}
PLATFORM REQUIREMENTS:
{specs}

Return valid JSON only with this exact top-level structure:
{{
  "campaign": {{
    "thesis": "",
    "audience_problem": "",
    "unique_point_of_view": "",
    "source_and_fact_plan": [],
    "originality_statement": ""
  }},
  "youtube_long_form": {{
    "title_options": [],
    "thumbnail_text_options": [],
    "hook_30_seconds": "",
    "outline": [],
    "full_script": "",
    "b_roll_plan": [],
    "music_direction": {{
      "mood": "",
      "tempo_guidance": "",
      "licensing_rule": "owned, licensed, public-domain, or platform-cleared only"
    }},
    "cta": ""
  }},
  "vertical_video_variants": [
    {{
      "platforms": ["youtube_shorts", "tiktok", "instagram_reels"],
      "hook": "",
      "spoken_script": "",
      "shot_plan": [],
      "on_screen_text": [],
      "caption": "",
      "hashtags": [],
      "cta": ""
    }}
  ],
  "platform_posts": {{
    "facebook": "",
    "linkedin": "",
    "x": ""
  }},
  "funnel": {{
    "lead_magnet": "",
    "landing_page_headline": "",
    "landing_page_subheadline": "",
    "email_follow_up": [],
    "tracking_events": []
  }},
  "experiment_plan": {{
    "hook_tests": [],
    "thumbnail_tests": [],
    "success_metrics": [],
    "stop_or_scale_rules": []
  }},
  "compliance": {{
    "claims_to_verify": [],
    "synthetic_media_disclosure": "",
    "copyright_and_music_checks": [],
    "platform_policy_risks": []
  }}
}}

Requirements:
- Create at least 5 materially different vertical-video variants, not minor rewrites.
- Build one coherent campaign, not disconnected posts.
- The hook must promise a clear payoff without deception.
- Use competitive patterns only at the abstract level; no copied titles, scripts, footage, music, or thumbnails.
- Include an evidence plan and flag every factual claim that needs verification.
- Include a direct path from content to the offer or website.
- Include stop/scale rules based on retention and qualified traffic, not vanity views alone.
"""
    c = client()
    r = c.models.generate_content(
        model=FLASH,
        contents=SYSTEM + "\n\n" + prompt,
        config={"response_mime_type": "application/json"},
    )
    package = _extract_json(r.text)
    package["type"] = "campaign_package"
    package["topic"] = topic
    package["objective"] = objective
    return package


COMMANDS = {
    "youtube": youtube_script,
    "tiktok": tiktok_caption,
    "email": email_sequence,
    "social": social_post,
    "research": deep_research,
    "product": product_description,
    "campaign": campaign_package,
}


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Dominion Gemini Content Engine (Vertex AI)")
    parser.add_argument("command", choices=COMMANDS.keys())
    parser.add_argument("--topic", "--query", "--product", dest="topic", required=True)
    parser.add_argument("--platform", default="twitter")
    parser.add_argument("--duration", type=int, default=8)
    parser.add_argument("--emails", type=int, default=7)
    parser.add_argument("--price", type=int, default=47)
    parser.add_argument("--offer", default="")
    parser.add_argument("--audience", default="people seeking practical healing, sovereignty, and wealth-building education")
    parser.add_argument("--objective", default="authority_and_sales")
    args = parser.parse_args()

    fn = COMMANDS[args.command]
    if args.command == "youtube":
        result = fn(args.topic, args.duration)
    elif args.command == "social":
        result = fn(args.topic, args.platform)
    elif args.command == "email":
        result = fn(args.topic, args.emails)
    elif args.command == "product":
        result = fn(args.topic, args.price, [])
    elif args.command == "campaign":
        result = fn(args.topic, args.offer, args.audience, args.objective)
    else:
        result = fn(args.topic)

    print(json.dumps(result, indent=2))
