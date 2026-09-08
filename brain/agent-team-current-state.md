# Dominion Agent Team — Current Operating State

**Prepared:** 2026-09-08  
**Authority:** Dewayne Singleton, Founder / Human Overseer  
**Purpose:** Shared current-state briefing for all Dominion agents during final production convergence.  
**This file does not grant new authority.**

## Command structure

- **Founder / Human Overseer:** final authority for protected actions.
- **Coordinator:** sequences work, reconciles evidence, prevents conflicting changes.
- **Conductor:** routes approved work and tracks execution state.
- **Governor / Policy Gate:** applies default-deny authority rules and Founder gates.
- **Guardian:** runtime drift and regression detection.
- **Sentinel:** independent runtime verification and challenge.
- **Five Council:** independent review across Truth/Evidence, Law/Governance, Security/Risk, Engineering/Reliability, and Business Value/Human Impact.
- **Buddy:** Founder-facing operator using canonical Dominion context and governed model routing.
- **Dominion Model Gateway:** selects approved intelligence routes; it does not authorize external effects.
- **Publisher:** executes approved content distribution and records immutable receipts.
- **Revenue Operations:** measures traffic, conversion, experiments, attribution, and revenue outcomes.
- **Obsidian Scribe:** maintains the operational-memory mirror from governed sources and verified runtime evidence.

## Final production closure — five modules

Dominion is now operating against one narrow closure program. New architecture is not added unless a verified production defect requires it.

### 1. Publisher + Meta

**Code state:** READY.  
**Runtime completion state:** NOT YET VERIFIED.

The canonical `dominion_publisher` service owns Meta Facebook/Instagram binding, approval-gated queueing and publishing, idempotency, receipts, and attributed destination URLs. Meta app configuration, account binding, and controlled-publish proof are separate runtime gates.

Required runtime finish line:

1. Publisher health is online.
2. Meta app record exists in the encrypted Publisher vault.
3. Founder-authorized Facebook Page / linked Instagram professional account is bound.
4. One controlled approved VoltEdge canary publishes successfully.
5. Provider post ID, destination URL, timestamp, and Publisher receipt are retained.

Never mark Meta complete from code existence alone. Until the controlled publish receipt exists, the state remains `BLOCKED` or `UNKNOWN` according to the observed runtime phase.

### 2. Obsidian / Dominion Brain

**Code state:** READY.  
**Production synchronization state:** requires current publication receipt.

The only canonical brain path is `scripts/render_dominion_brain.py` followed by the governed production Brain publisher. Legacy vault seed/setup paths remain retired.

Every governed generation must carry the current production priorities, agent roles, Publisher phase, storefront state, traffic/revenue outcomes, blockers, Founder approvals, and evidence links. GitHub remains authoritative for versioned law/code; Foundation VM remains authoritative for live runtime; Obsidian is the operational memory and coordination mirror.

No secret value, provider token, customer PII, or credential may be written into the Brain.

### 3. Command Center

**Code state:** READY FOR CURRENT RELEASE VERIFICATION.

The Command Center is the canonical live convergence surface. It must report, without fabrication:

- Publisher runtime and Meta phase;
- queue/receipt ledger truth;
- controlled-publish proof;
- system-integrity state;
- lane access;
- revenue runtime and current constraint;
- latest evidence/receipts.

A subsystem being built or configured is not equivalent to runtime PASS. Command Center truth must remain timestamped and evidence-backed.

### 4. VoltEdge / Wix storefront

**Observed 2026-09-08:** the live VoltEdge site is published on Wix Catalog V3. Wix analytics for the store from launch through 2026-09-08 returned `orders_count=0`; therefore no product can truthfully be labeled a Best Seller yet.

**Corrective action:** the empty visible `Best Sellers` category was hidden rather than populated with invented winners. Category ID `04d1b50a-f6c7-47b4-a0ac-92068af18500` advanced to revision `3` with `visible=false`.

Storefront finish line is conversion-safe public presentation: no fabricated best-seller claims, no placeholder/trust copy, accurate policies/contact information, working product destinations, and checkout readiness. Storefront changes must be verified on the live site after publication.

### 5. Traffic + revenue loop

**Code state:** READY FOR CONTROLLED PRODUCTION EVIDENCE.

The Revenue Runtime already supports deterministic experiment assignment, impression/click tracking, UTM attribution, server-side `add_to_cart`, `checkout`, `purchase`, and `refund` events, evaluation, pause, and rollback. Automatic paid spend is not authorized.

Production finish line:

`approved campaign -> Dominion Publisher -> platform post -> attributed VoltEdge visit -> click/session -> cart -> checkout -> purchase/refund event -> revenue receipt -> evaluation -> Dominion Brain`

A traffic claim requires source/campaign attribution. A revenue claim requires purchase evidence. No agent may promote a winner from impressions or clicks alone when policy requires purchase evidence.

## Current operating priority

1. Finish only the remaining Meta runtime gates and controlled canary.
2. Publish the current governed Dominion Brain and verify its production digest/receipt.
3. Verify Command Center exact-release truth after Publisher/Brain convergence.
4. Remove any remaining live VoltEdge trust/placeholder defects without fabricating merchandising evidence.
5. Run one measurable traffic-to-purchase loop and retain attribution/revenue receipts.
6. Only after those five gates close, resume secondary builds such as Orion, Juris, Alchemist, or additional platform adapters.

## Platform boundaries

- **Meta:** official governed Publisher path only; no credential scraping, MFA bypass, account circumvention, or unauthorized posting.
- **TikTok:** existing governance hold remains effective until separately changed through reviewed policy; do not silently activate disabled TikTok runtime paths.
- **Trading:** paper-only unless a separate live-money release is explicitly authorized.
- **Payments / credentials / public publishing:** applicable Founder gates remain in force.

## Shared operating doctrine

1. Inventory before building.
2. Verify before claiming.
3. Reuse before duplicating.
4. GitHub carries versioned code, governance, contracts, and reviewed brain content.
5. Obsidian mirrors operational knowledge; it does not override GitHub policy.
6. Runtime evidence decides live-state truth.
7. Consequential production work requires bounded scope, rollback, and post-action verification.
8. No secrets or customer PII in GitHub, Obsidian, prompts, screenshots, or reports.
9. Fail closed on ambiguous configuration, corrupted state, missing evidence, or stale runtime truth.
10. No agent may expand its own authority.
11. Truth states are exactly `VERIFIED`, `INFERRED`, `UNKNOWN`, or `BLOCKED`.
12. Do not reopen completed architecture while a narrower production closure is available.

## Required report format

```yaml
agent:
duty:
evidence:
result:
risks:
next_action:
human_approval_required:
```

If evidence is insufficient, `result` must be `UNKNOWN` or `BLOCKED`, never an inferred PASS.
