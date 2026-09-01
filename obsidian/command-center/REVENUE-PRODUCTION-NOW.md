# Revenue Production — Current Mission

> [!mission] Operating mode
> `CURRENT_MODE=REVENUE_PRODUCTION`
>
> Revenue Engine hardening is locked complete. Do not reopen infrastructure work without a verified defect or approved new requirement.

## Current Objective

Move from verified runtime readiness to real market activity and measurable commercial evidence.

**RADAH MEMSHALAH — רָדָה מֶמְשָׁלָה** execution order:

1. Verify the current live funnel baseline and attribution path.
2. Fix only conversion-blocking VoltEdge storefront trust/friction defects.
3. Activate the already-built SimilarWeb 7-day capture; do not rebuild it.
4. Use buyer-intent demand evidence to drive YouTube/content and owned organic distribution.
5. Route qualified traffic through the governed revenue path.
6. Measure views → clicks → product views → carts → checkout → purchases → attributed revenue.
7. Feed verified results back into Buddy, Revenue Operations, and Obsidian.
8. Double down on winners; stop weak loops; make no revenue claims without purchase evidence.

## Owner / Governance Alignment

This mission must move fast **inside** effective authority and stop cleanly at true Founder gates.

| Mission step | Default action | Authority treatment |
| --- | --- | --- |
| Read funnel, attribution, runtime, store and market evidence | Execute | Bounded/read-only evidence work; record provenance and freshness. |
| Diagnose VoltEdge friction and prepare fixes | Execute | Internal analysis/drafting is allowed. Broader live store mutations require their applicable authority. |
| Reversible Wix CRO on `plainDescription` | Execute only through the active revenue policy | `BOUNDED_STANDING_AUTHORIZATION`: current revision, before snapshot, after verification, rollback and statistical gates required. |
| Price, inventory, provider or destructive Wix changes | Stop and surface | Not automatically authorized by the revenue policy. |
| SimilarWeb 7-day capture | Reuse existing capability | Activate only if the existing release/runtime path already carries effective authorization; otherwise surface the exact activation gate rather than rebuilding it. |
| Generate SEO/content/video packages | Execute | Internal production may proceed with evidence and originality controls. |
| Publish/post externally | Stop before consequence | `FOUNDER_APPROVAL_REQUIRED` under the applicable publishing/channel policy. |
| Paid traffic/spend | Stop before spend | `FOUNDER_APPROVAL_REQUIRED`; automatic paid spend is disabled. |
| Measure traffic/conversion/revenue | Execute | Read/attribute only; do not fabricate or infer purchases/revenue. |
| Auto-promote a CRO winner | Execute only when policy gates pass | Requires the configured paid-purchase success event, visitor/conversion thresholds, confidence, lift, revenue-per-visitor guard, current revision and rollback evidence. |

Full owner control surface: [[Dominion-Command-Center/18-Owner-Governance|Owner Governance]].

## Mandatory Pre-Execution Delta Check

Before building, changing, or activating anything, record:

- `ALREADY_BUILT`
- `ALREADY_DEPLOYED`
- `ALREADY_TESTED`
- `ALREADY_MERGED`
- `DUPLICATE_RISK`
- `BUSINESS_VALUE`
- `TRUE_DELTA`
- `AUTHORITY_CLASS`
- `APPROVAL_REQUIRED`

If `TRUE_DELTA` is empty, do not code or rebuild. Reuse the existing capability and move to operation/measurement.

## Locked State

- `REVENUE_ENGINE_RUNTIME_VERIFIED=YES`
- `REVENUE_ENGINE_LOCKED_COMPLETE=YES`
- Canonical runtime proof release: `12a6775373f04592db00983222268daa2b06f851`
- Completion receipt: `runtime/releases/revenue-engine-locked-20260901.json`

## First Constraint

The next constraint is **production evidence**, not additional infrastructure. The operating question is: **where does the live funnel currently lose the buyer?**

## Current Revenue Policy Boundary

`governance/revenue_execution_policy.json` is `production_bounded`.

Allowed automatic external action:

- reversible CRO: **true**;
- Wix field: `plainDescription` only;
- max treatment traffic: 50%;
- one active experiment per product;
- current revision, before snapshot, after verification and rollback required.

Automatic actions explicitly disabled:

- price change;
- paid spend;
- provider change;
- inventory change;
- destructive change;
- legal/compliance-sensitive claim;
- live trading.

## Completion Standard for This Phase

This phase does not close on activity. It closes when the system has current evidence for the full path and at least one verified commercial outcome or a precise measured blocker:

`DEMAND → CONTENT → TRAFFIC → CLICK → PRODUCT → CART → CHECKOUT → PURCHASE → ATTRIBUTED_REVENUE → LEARNING`

For every stage, preserve:

`OWNER → EVIDENCE → AUTHORITY → ACTION → RECEIPT → NEXT CONSTRAINT`

[[Dominion-Command-Center/09-Revenue|Revenue]] · [[Dominion-Command-Center/18-Owner-Governance|Owner Governance]] · [[Dominion-Command-Center/15-Founder-Oversight|Founder Oversight]] · [[Dominion-Command-Center/14-Daily-State|Daily State]] · [[Dominion-Command-Center/00-HOME|Command Center]]
