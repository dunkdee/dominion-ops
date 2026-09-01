# 18 · Owner Governance

> [!governance] Control surface only
> This page does **not** grant authority. It translates the current normative Dominion governance into an owner-facing operating view. When this page conflicts with machine-readable policy, the machine-readable policy wins and execution stops until the conflict is resolved.

## Authority Order

1. **Human Overseer / Founder:** final authority for the consequential actions defined by Dominion governance.
2. **System Constitution:** `governance/SYSTEM_CONSTITUTION.md`.
3. **Authority Matrix:** `governance/authority_matrix.json` — default deny, explicit allowed roles, approvals, constraints, and prohibited actions.
4. **Mission-specific policy:** for the current revenue plane, `governance/revenue_execution_policy.json`.
5. **Runtime evidence:** Foundation VM receipts prove what is actually live; policy never substitutes for runtime evidence.
6. **Obsidian:** displays the governed operating picture; it does not create authority by itself.

**RADAH MEMSHALAH — רָדָה מֶמְשָׁלָה**

## Owner Decision Classes

| Class | Meaning | Current examples |
| --- | --- | --- |
| `BOUNDED_STANDING_AUTHORIZATION` | A versioned active policy already permits the exact bounded action. No wider authority is implied. | Revenue CRO may automatically change only Wix `plainDescription` within the active revenue execution policy, with current revision, before/after evidence, rollback, statistical gates, and max 50% treatment traffic. |
| `FOUNDER_APPROVAL_REQUIRED` | The action may be prepared internally, but execution requires the Human Overseer under the applicable authority rule. | Merge to `main`, production deployment, external publishing, customer contact, spending/moving money, reactivating suspended/retired agents, consequential credential/network changes. |
| `PROHIBITED` | No agent may perform the action. | Export secret values; autonomous permission expansion. |
| `BLOCKED` | Evidence, approval, policy, legal, security, or reliability requirements are not satisfied. | Missing approval receipt, stale evidence, policy conflict, failed acceptance gate. |

## Approval Is Scoped, Not Transitive

A Founder approval must bind to the exact action, target, scope, evidence, version/hash, expiration where applicable, and rollback/stop conditions. Approval for one action does **not** authorize adjacent actions.

Examples:

- approving a content draft does not approve public publishing;
- approving organic publishing does not approve paid spend;
- approving a reversible product-description experiment does not approve a price change;
- approving a merge does not by itself approve production deployment when deployment has its own gate.

## Current Revenue Standing Boundary

The active revenue execution policy is `production_bounded` and currently permits only the specifically defined reversible CRO path.

**Automatically permitted by the revenue policy:**

- reversible CRO: `true`;
- Wix field: `plainDescription` only;
- one active experiment per product;
- current revision required;
- before snapshot required;
- after verification required;
- rollback required;
- max treatment traffic: 50%;
- automatic winner promotion requires a **paid purchase** success event and the configured statistical gates.

**Not automatically permitted:**

- price changes;
- paid spend;
- provider changes;
- inventory changes;
- destructive changes;
- legal/compliance-sensitive claims;
- live trading.

Those remain outside the standing revenue authorization and must follow their separate Founder/governance path.

## Revenue Production Decision Flow

For every production mission:

`OWNER INTENT → VERIFIED FACTS → EXISTING CAPABILITY → TRUE DELTA → POLICY DECISION → EXECUTION → VERIFICATION → RECEIPT → LEARNING`

Before implementation or external action, record:

- `ALREADY_BUILT`
- `ALREADY_DEPLOYED`
- `ALREADY_TESTED`
- `ALREADY_MERGED`
- `DUPLICATE_RISK`
- `BUSINESS_VALUE`
- `TRUE_DELTA`
- `AUTHORITY_CLASS`
- `APPROVAL_REQUIRED`
- `ROLLBACK_OR_STOP_CONDITION`

If `TRUE_DELTA` is empty, do not build a duplicate. If effective authority is missing, return `BLOCKED` instead of improvising authorization.

## Owner Queue — Current Mission

### Execute without reopening infrastructure

- read current funnel and attribution evidence;
- diagnose storefront friction;
- produce internal content/SEO/video packages;
- gather buyer-intent evidence;
- measure traffic, clicks, carts, checkout, purchases, and attributed revenue;
- run only already-authorized bounded automation.

### Surface to Founder when execution reaches the boundary

- public publishing or platform posting;
- customer contact;
- any paid traffic/spend;
- price changes;
- production deployment or consequential service/config changes not already covered by an active release policy;
- credentials/provider/network changes;
- destructive operations;
- legal/compliance-sensitive claims;
- live-money trading.

## Truth Rule

`READY`, `LIVE`, `PRODUCING`, and `REVENUE` are separate claims.

- Code/tests prove implementation quality.
- Deployment receipts prove release state.
- Runtime health proves service availability.
- Traffic/click/cart/checkout telemetry proves funnel activity.
- A paid purchase proves commercial conversion.
- Attributed paid revenue proves revenue evidence.

Never collapse these states into one success label.

[[Dominion-Command-Center/REVENUE-PRODUCTION-NOW|Revenue Production Now]] · [[Dominion-Command-Center/15-Founder-Oversight|Founder Oversight]] · [[Dominion-Command-Center/03-Control-Plane|Control Plane]] · [[Dominion-Command-Center/00-HOME|Command Center]]
