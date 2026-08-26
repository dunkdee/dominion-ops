# 09 · Revenue

> [!revenue] Objective
> Move the strongest governed revenue lane from demand → conversion → paid revenue → fulfillment → retention → learning.

## Production Revenue Work Plane

**RADAH MEMSHALAH — רָדָה מֶמְשָׁלָה** now treats the Dominion Revenue Runtime as the live execution plane for the Commerce & Fulfillment lane.

| Runtime fact | Current governed state |
| --- | --- |
| Revenue service | `dominion-revenue-runtime.service` |
| Evaluator | `dominion-revenue-evaluator.timer` · every 10 minutes |
| RADAH work-plane cycle | every 30 minutes |
| Active experiment | `voltedge-speaker-offer-v1` |
| Live offer route | `https://dominionhealing.org/r/voltedge-speaker-offer-v1` |
| Success event | paid purchase |
| Traffic assignment | deterministic 50 / 50 |
| Automatic reversible CRO | enabled inside revenue execution policy |
| Automatic price change | **disabled** |
| Automatic paid spend | **disabled** |

> [!evidence] Activation receipt
> Production activation run `32929081710` verified the public canary route, Wix revision `10`, no price change, no spend change, and **zero synthetic traffic**. The activation baseline was 0 visitors, 0 clicks, 0 conversions, and $0 attributed revenue for both variants. That is a clean starting baseline, not a revenue claim. Current runtime receipts and the revenue ledger supersede this historical baseline as traffic arrives.

## Live Optimization Loop

**Qualified traffic → experiment impression → offer click → VoltEdge product view → checkout → paid purchase → revenue attribution → statistical evaluation → reversible winner promotion → next experiment**

The work plane routes the next job from current evidence:

1. **0 visitors:** traffic acquisition is the constraint. Produce buyer-intent SEO, short-form/video, CTA, and owned/organic distribution packages that point to the active experiment route.
2. **Visitors but no clicks:** message match is the constraint. Improve hook, offer clarity, CTA, and pre-click relevance.
3. **Clicks but no paid purchases:** conversion friction is the constraint. Diagnose product-page trust, objections, checkout, shipping, and offer friction.
4. **Paid purchases:** attribution and evidence accumulation become the constraint. Protect revenue per visitor and continue until the governed winner gate has enough evidence.
5. **Winner gate passes:** the Revenue Runtime may promote only the allowlisted reversible Wix field under `governance/revenue_execution_policy.json`, with current-revision verification and rollback evidence.

## Revenue Truth

- [[Dominion-Brain/05-Verticals/VERTICALS|Governed Verticals]]
- [[Dominion-Operator-Notes/revenue_operations/09-Current-State|Revenue Operations · Current State]]
- [[Dominion-Brain/00-Constitution/STATE|Canonical State]]
- Repository work-plane contract: `governance/revenue_workplane.json`

## Revenue Loop

1. Read the current live funnel constraint before creating work.
2. Reuse the strongest existing asset before building a new one.
3. Measure demand and conversion before diagnosing downstream checkout problems.
4. Track contribution margin, CAC, LTV, and attribution only when evidence exists.
5. Scale proven winners; stop weak loops; never fabricate a metric.

## Execution Ownership

- [[Dominion-Brain/04-Agents/revenue_operations/00-Identity|Revenue Operations]]
- [[Dominion-Brain/04-Agents/coordinator/00-Identity|Coordinator]]
- [[Dominion-Brain/04-Agents/conductor/00-Identity|Conductor]]
- **Dominion Revenue Runtime:** reversible CRO execution and measurement
- **RADAH MEMSHALAH work plane:** reads runtime evidence and routes the next bounded production mission

> [!governance] Gate
> A real customer purchase is the proof of commercial conversion. Infrastructure readiness, impressions, clicks, and experiment activation are not sales. Paid spend, price changes, provider changes, destructive changes, inventory mutation, and legal/compliance-sensitive claims remain Founder-held.

[[Dominion-Command-Center/00-HOME|← Command Center]]
