# Dominion Public API Intake

**Governance:** RADAH MEMSHALAH — רָדָה מֶמְשָׁלָה

## Purpose

Dominion may use public or free-tier APIs to strengthen traffic intelligence, revenue intelligence, attribution, content research, lead quality, location context, and operating automation. Discovery is not activation.

The source discovery pool begins with `public-apis/public-apis`. Entries are first recorded in `governance/public_api_candidate_registry.json` and remain quarantined until individually verified.

## Separation of duties

- `governance/public_api_candidate_registry.json` is **discovery and qualification metadata only**.
- `governance/mcp_connector_registry.json` remains the only reviewed runtime connector registry.
- A candidate entry must never contain credentials, request headers, executable targets, arbitrary URLs, shell commands, or write capabilities.
- Listing a provider does not mean Dominion endorses it, trusts it, or has verified that a free tier still exists.

## Intake sequence

1. **Discover**
   - Record provider and source listing.
   - Assign a Dominion lane and concrete use case.
   - Assign an internal priority score.
   - State remains `QUARANTINED`.

2. **Provider verification**
   - Confirm official provider identity and documentation.
   - Confirm current pricing/free-tier terms.
   - Confirm authentication method.
   - Confirm HTTPS transport and current API base URL from official docs.
   - Confirm rate limits, quotas, response size, and failure semantics.

3. **Rights and terms review**
   - Review provider terms of service.
   - Review data licensing/redistribution constraints.
   - Review privacy implications and data-minimization requirements.
   - For scraping/retrieval providers, separately review target-site restrictions and do not assume a scraping provider grants rights to collect a target site.

4. **Capability-overlap review**
   - Prefer existing approved systems where they already satisfy the need.
   - Do not add a second provider merely because it is available.
   - Alternative providers may remain registered as fallbacks but are not activated automatically.

5. **Read-only probe**
   - Build a fixed-target, GET/read-only probe outside production.
   - Run at least three successful probes at separate times where practical.
   - Capture status, latency, schema, freshness, and failure behavior.
   - Evidence receipts must not store raw credentials, PII, or unrestricted response bodies.

6. **Review state**
   - `QUARANTINED` → discovered only.
   - `REVIEWING` → official docs/terms/runtime evidence being gathered.
   - `VERIFIED_READ_ONLY` → provider and read-only probe verified; not yet a production connector.
   - `APPROVED_FOR_RUNTIME` → reviewed for promotion into the canonical MCP connector registry.

7. **Runtime promotion**
   - Add a separate reviewed entry to `governance/mcp_connector_registry.json`.
   - Fixed target only.
   - Read-only effect first.
   - Explicit allowed parameters and validation rules.
   - Server-side secret handling only when authentication is required.
   - Existing MCP receipt and fail-closed behavior applies.

## Initial prioritization

The first seed focuses on APIs with plausible near-term value to the current revenue-first operating model:

1. Search/SERP intelligence — opportunity discovery and keyword/competitor evidence.
2. News intelligence — fresh signals for content and demand detection.
3. Public webpage evidence snapshots — governed competitive monitoring.
4. Aggregate geographic attribution — only after privacy/data-minimization review.
5. Lead-quality validation — only with strict PII handling.
6. Currency normalization — revenue analytics.
7. Supplemental market data — only when it adds coverage beyond existing approved market-data systems.
8. Geocoding/context sources — secondary operational value.

## Expansion pass

After the initial candidate contract is green, expand the source list by parsing the useful categories from the Public APIs repository, especially:

- Business
- Finance
- Jobs
- News
- Open Data
- Shopping
- Social
- Tracking
- Video
- Geocoding
- Currency Exchange
- Data Validation

New entries remain quarantined by default. High candidate count is not the objective; high-value, reliable, governable coverage is.

## Validation

Run:

```bash
python3 scripts/validate_public_api_candidate_registry.py
python3 -m unittest tests.test_public_api_candidate_registry -v
```

Both must pass before registry changes are considered reviewable.
