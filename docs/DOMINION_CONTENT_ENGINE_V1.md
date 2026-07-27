# Dominion Content Engine V1

## Objective

Build an owned, phone-first content operating system that turns one verified idea into an original, platform-specific campaign across YouTube, YouTube Shorts, TikTok, Instagram Reels, Facebook, LinkedIn, and X, then connects qualified traffic to Dominion offers.

This is not a copy-and-repost system. Competitive content is used only to identify abstract patterns such as topic demand, hook structure, pacing, audience intent, title framing, and conversion path. Scripts, music, footage, thumbnails, and wording must remain original or properly licensed.

## Current repository inventory

The repository already contains:

- a Vertex AI Gemini content engine in `apps/gemini/engine.py`
- YouTube script and metadata generation
- a YouTube OAuth/upload client
- a prototype long-form video pipeline
- video-studio and clone worker components elsewhere in the repository
- n8n and Foundation VM infrastructure

The existing pieces are a useful base, but they do not yet form a complete Socialaize-style operating loop.

## V1 implemented in this change

`apps/gemini/engine.py campaign` now creates one coherent campaign package containing:

- a campaign thesis and unique point of view
- source and fact-verification planning
- YouTube long-form titles, thumbnails, hook, outline, script, B-roll, music direction, and CTA
- at least five materially different vertical-video variants for Shorts, TikTok, and Reels
- Facebook, LinkedIn, and X variants
- a lead magnet and landing-page funnel
- follow-up email concepts and tracking events
- hook and thumbnail experiments
- stop-or-scale rules based on retention and qualified traffic
- claim, copyright, music, synthetic-media, and platform-policy checks

Example:

```bash
python apps/gemini/engine.py campaign \
  --topic "Three practical lessons from The Art of Healing" \
  --offer "The Art of Healing book" \
  --audience "adults seeking practical holistic education" \
  --objective "book_sales_and_authority"
```

The result is JSON so n8n, the dashboard, Obsidian, or a later publishing service can consume it without scraping prose.

## Gap analysis

### Existing but incomplete

1. **Content generation**
   - Existing scripts and captions are single-output functions.
   - V1 adds coherent campaign packaging and originality requirements.

2. **Video production**
   - The YouTube pipeline expects a remote `Higgins` backend or a stub.
   - The stub does not produce a usable final video.
   - The paid/unverified backend must be replaced by a commercially approved, owned or open-source worker before production use.

3. **YouTube upload**
   - OAuth and resumable upload code exists.
   - It still requires a one-time authorized OAuth setup and production token handling.

### Missing production layers

1. **Competitive intelligence ingestion**
   - collect public video metadata and permitted transcripts
   - record source URL, title, publish date, duration, views, engagement, topic, and hook pattern
   - never download or republish protected content as production assets

2. **Trend and opportunity scoring**
   - compare demand, competition, freshness, brand fit, and monetization path
   - rank opportunities before generation

3. **Asset provenance ledger**
   - track whether every visual, music track, voice, clip, and source is owned, licensed, public-domain, or platform-cleared
   - fail closed when provenance is missing

4. **Human approval gate**
   - draft first
   - present script, claims, thumbnail, music source, and CTA for approval
   - publish only after explicit approval

5. **Cross-platform publishers**
   - YouTube publisher exists in prototype form
   - Meta, TikTok, LinkedIn, X, Pinterest, Threads, Bluesky, and Mastodon require separate governed adapters and credentials

6. **Analytics feedback loop**
   - ingest impressions, click-through rate, retention, completion rate, saves, shares, qualified clicks, leads, and sales
   - connect each campaign to revenue events
   - automatically recommend keep, revise, scale, or stop

7. **Obsidian operating view**
   - write campaign briefs, approvals, results, and agent notes into the vault after remote access is live

## Recommended execution order

1. Merge and deploy the V1 campaign generator.
2. Add a governed research intake schema and opportunity scorer.
3. Connect the campaign JSON to n8n and an approval queue.
4. Replace the prototype video backend with the approved clone/video worker.
5. Complete YouTube OAuth and private test uploads.
6. Add analytics ingestion and revenue attribution.
7. Add the remaining platform adapters one at a time.
8. Expose campaign status and agent notes in Obsidian.

## Revenue model

Views are distribution, not guaranteed income. The engine should optimize for multiple revenue paths:

- YouTube long-form advertising after Partner Program eligibility
- Shorts revenue sharing after eligibility
- book and digital-product sales
- email-list growth
- affiliate offers with verified terms
- sponsorships and licensing
- services and automation leads

The primary control metric is qualified revenue per campaign, supported by retention and conversion metrics. Raw view count alone is not a scale decision.

## Governance rules

- No copied scripts, thumbnails, music, footage, or voice likenesses.
- No fabricated testimonials, earnings, medical, legal, or financial claims.
- No publishing without asset provenance and approval.
- No platform credential committed to Git.
- No new paid service or GPU spend without explicit approval.
- Every campaign must have a measurable offer, destination, and tracking plan.
