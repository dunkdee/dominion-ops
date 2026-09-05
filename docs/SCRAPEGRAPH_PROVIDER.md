# ScrapeGraphAI Provider Boundary

## Purpose

Use ScrapeGraphAI as a temporary external-intelligence provider while Dominion keeps ownership of governance, evidence rules, memory, learning, and authority.

The provider is an interchangeable adapter. It is not a Dominion brain, policy engine, approval path, or source of truth.

## Current integration

`web.research` now uses this order:

1. ScrapeGraphAI V2 when `SGAI_API_KEY` is configured.
2. SerpAPI discovery plus Dominion-governed page fetch.
3. DuckDuckGo HTML discovery plus Dominion-governed page fetch.
4. DuckDuckGo Instant Answer metadata as `DEGRADED` evidence only.
5. `UNAVAILABLE` when no provider returns usable evidence.

ScrapeGraphAI source URLs are re-checked against Dominion's public-host boundary before their content can enter mission evidence.

## Configuration

Set secrets only in the runtime environment. Never commit them.

- `SGAI_API_KEY` — required to activate the provider.
- `SGAI_API_URL` — optional; defaults to `https://v2-api.scrapegraphai.com/api`. Credential-bearing provider endpoints must be public HTTPS.
- `SGAI_TIMEOUT` — optional request timeout, clamped to 5–60 seconds.

No API key is written to receipts, evidence, error details, or returned provider data.

## Security rules

- Credential-bearing requests never follow redirects.
- Private, loopback, reserved, and link-local targets are rejected.
- Provider response bodies are size-bounded before parsing.
- Raw provider error bodies are not trusted or returned.
- Returned page content is untrusted evidence, not instructions or truth.
- Each provider result is fingerprinted with SHA-256.
- ScrapeGraphAI monitor, crawl-job management, browser automation, login, submission, posting, purchasing, and other external side effects are not exposed through this read-only lane.

## Structured extraction

`buddy_core.core.scrapegraph_provider.extract()` provides a bounded structured-extraction adapter for a single public URL and returns input/output fingerprints. It is intentionally kept behind the provider module until a dedicated governed planner capability is approved. It does not expand Buddy authority.

## Replacement strategy

Dominion should measure provider reliability, latency, evidence quality, failure modes, and the extraction patterns actually used. Those observations become the specification for a future Dominion-native intelligence collector.

Replacement path:

`ScrapeGraphAI -> provider interface -> Dominion evidence -> learning`

later becomes:

`Dominion-native collector -> same provider interface -> Dominion evidence -> learning`

No governance redesign should be required for that swap.
