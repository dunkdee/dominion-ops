# Dominion YouTube Traffic / Revenue Loop

## Objective

Use permitted public performance metadata to identify high-value video demand, then create materially original Dominion content designed to route qualified viewers into measurable Dominion revenue paths.

This is a research-and-originality system, not a copying system.

## Operating loop

1. Collect permitted/public metadata from approved sources.
2. Rank videos by demand velocity, engagement, outlier performance, freshness, buyer intent, brand fit, and monetization fit.
3. Convert top signals into original campaign briefs.
4. Generate materially different scripts, titles, thumbnails, examples, visuals, and calls to action.
5. Require provenance and approval before publishing.
6. Publish through governed platform adapters.
7. Track impressions, CTR, retention, qualified clicks, leads, sales, affiliate events, and attributable revenue.
8. Scale winners, revise borderline campaigns, and stop losers.
9. Feed outcomes back into Dominion Intelligence.

## Opportunity score

The initial scorer in `apps/youtube/opportunity_agent.py` weights:

- views per day / velocity: 24%
- engagement: 14%
- channel outlier ratio: 14%
- freshness: 8%
- monetization fit: 16%
- Dominion brand/lane fit: 10%
- buyer intent: 14%

The score is evidence for prioritization, not a revenue guarantee. The production scale metric remains **qualified revenue per campaign**.

## Evidence intake

Accepted inputs include approved exports or public metadata obtained through authorized APIs, platform analytics, manually recorded research, or other permitted research tooling. The system must retain source URL/video ID, title, channel, publish date, views, engagement signals, topic, and any available channel baseline.

Do not bypass platform restrictions, scrape authenticated surfaces without permission, or download/reuse protected scripts, thumbnails, music, footage, or voice likenesses.

## Faceless production strategy

Faceless does not mean generic. Every production brief must specify a distinctive thesis, original script, owned/licensed/public-domain visual plan, original thumbnail concept, platform-specific hook, measurable CTA, and tracked destination. Winning competitor videos are used to understand audience demand and abstract creative patterns only.

## Revenue routing

Each campaign must declare the best-fit monetization route before production. Examples include store products, books, affiliate offers with verified terms, services, software/SaaS, lead capture, sponsorship opportunities, and YouTube monetization after eligibility.

A video with high view potential but no credible revenue path should rank below a commercially aligned opportunity with slightly lower raw traffic potential.

## Next integration points

- Feed approved research exports into `apps/youtube/opportunity_agent.py`.
- Pass top-ranked `original_brief` objects into the existing Gemini campaign generator.
- Route campaign JSON to n8n approval/production queues.
- Complete the owned/open-source faceless video worker.
- Add YouTube analytics and first-party conversion/revenue attribution.
- Add lane-specific scoring profiles so commerce, books, music/media, SaaS, affiliate, services, and new-market discovery can weight signals differently.
