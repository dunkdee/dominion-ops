# Stage 6 — Seven-Day Market-Intelligence Trial Readiness

## Objective

Prepare Dominion to use a time-limited Similarweb trial efficiently without starting the trial early, scraping the Similarweb platform, or confusing estimated market data with verified business performance.

## Legal and platform boundary

Similarweb's published Terms prohibit robots, spiders, scrapers, and other automated means from accessing or collecting data from its Platform or Site. They also restrict sharing Platform data without prior consent and prohibit using the Platform to build a competing service.

Accordingly, Dominion permits only:

- local Excel or CSV exports made available by the subscription;
- manual recorded capture from authorized account views;
- Similarweb Data Exporter access when included in the account;
- Similarweb API access when the account is entitled and an API key is provided by the Human Overseer.

The generic Claude-built Browser Agent is not authorized to scrape Similarweb. It may later process already-downloaded files in an offline, read-only workflow after a separate runtime review.

## Pre-trial sequence

1. Review and approve the target-domain manifest.
2. Confirm the actual trial duration, enabled modules, historical depth, export options, API entitlement, credit balance, and billing terms shown in the account.
3. Prepare private raw, normalized, manifest, and evidence-ledger storage.
4. Run the repository fixture through readiness, ingestion, deduplication, and completeness tests.
5. Record the Human Overseer's billing and cancellation checkpoint.
6. Start the trial manually only after readiness returns `READY_TO_ACTIVATE_TRIAL`.
7. Collect using permitted exports or entitled API calls.
8. Normalize every capture with provider, domain, period, evidence, acquisition method, and payload hash.
9. Reject duplicates and produce a completeness report each day.
10. Stop collection on Day 7 and archive the evidence package.

## Initial target allocation

The committed plan contains 15 domains:

- one DominionHealing owned-site baseline;
- six large wellness-category leaders;
- five direct or adjacent wellness benchmarks;
- three market-intelligence product benchmarks.

The target list is provisional and intentionally remains pending Human Overseer review. No trial activation occurs merely because the plan is merged.

## Data classification

All Similarweb-derived records are:

```text
SOURCE_KIND: EXTERNAL_ESTIMATED
REVENUE_VERIFIED: false
LICENSE_STATUS: INTERNAL_USE_ONLY_UNLESS_SEPARATELY_LICENSED
```

Permitted internal uses include market benchmarking, competitor context, opportunity hypotheses, and scenario inputs. Raw Similarweb data is not a Dominion resale product and is not authorized for external distribution.

## Credit controls

- Discover available API tables, history, and remaining credits before paid requests.
- Use the platform's displayed export cost before confirming an export.
- Keep a 15% reserve for missing-data recovery and final-day gaps.
- Cap entitled API activity at two requests per second unless the account documentation specifies a lower limit.
- Do not retry credit-consuming failures blindly.

## Billing control

The repository does not assume that every trial has identical duration or billing terms. The Human Overseer must record what the subscription page shows at signup. Automatic cancellation is not authorized because account cancellation is a consequential external action and may require direct account-owner confirmation.

## Completion gate

Stage 6 repository readiness is complete when:

- all compatibility validators pass;
- the 15-domain manifest is schema-valid;
- prohibited acquisition methods fail closed;
- fixture ingestion remains `TEST_ONLY`;
- actual permitted exports can become only `ACCEPTED_ESTIMATED_SIGNAL`;
- duplicate captures are rejected;
- completeness reporting identifies all missing targets;
- both required pull-request checks pass.

The real seven-day collection window remains unstarted until the Human Overseer confirms the target list and the live account capabilities.
