# 15 · Founder Oversight

> [!governance] Founder control surface
> This page is an owner-facing evidence and approval surface. It does **not** grant authority by itself. Effective authority comes from the System Constitution, `governance/authority_matrix.json`, applicable mission policy, and a valid scoped Founder approval where required.

## Current Owner Role

**Human Overseer / Founder = final authority for consequential Dominion actions.**

Dominion remains one governed system:

`FOUNDER INTENT → GOVERNED PLAN → AUTHORIZED CAPABILITY → EXECUTION → VERIFICATION → RECEIPT → LEARNING`

The Founder should not be pulled into routine internal work that is already within effective authority. The Founder should be surfaced only when a decision crosses a real authority boundary, requires explicit risk acceptance, or changes the operating mandate.

[[Dominion-Command-Center/18-Owner-Governance|Open Owner Governance →]]

## What the Founder Must See for Every Consequential Mission

- objective and business value;
- verified facts, unknowns, assumptions, contradictions, and truth state;
- `ALREADY_BUILT`, `ALREADY_DEPLOYED`, `ALREADY_TESTED`, `ALREADY_MERGED`;
- `DUPLICATE_RISK` and exact `TRUE_DELTA`;
- accountable lane/operator;
- action class and effective authority;
- required Council/human approval, if any;
- evidence references and exact version/hash being authorized;
- success condition, stop condition, rollback condition, and blast radius;
- execution receipt and post-action verification;
- learning/memory destination and follow-up obligation.

## Current Authority Classes

| Class | Owner treatment |
| --- | --- |
| `BOUNDED_STANDING_AUTHORIZATION` | Existing versioned policy already authorizes the exact action. Execute within that boundary and surface receipts, not repeated permission requests. |
| `FOUNDER_APPROVAL_REQUIRED` | Prepare the decision packet, stop before external consequence, and request a scoped Founder decision. |
| `PROHIBITED` | Reject. Founder approval cannot convert an action prohibited by the active policy into ordinary agent authority without the required governance/amendment path. |
| `BLOCKED` | Preserve the blocker and evidence. Do not improvise around missing approval, legal/security veto, stale evidence, or failed acceptance. |

## Current Revenue Production Boundary

The Revenue Engine hardening is `LOCKED COMPLETE`. Current work is production and commercial evidence, not another infrastructure rebuild.

The active `governance/revenue_execution_policy.json` allows a narrow bounded CRO path:

- automatic reversible CRO: **enabled**;
- Wix mutation limited to `plainDescription`;
- max treatment traffic: 50%;
- current revision + before snapshot + after verification required;
- rollback required;
- automatic promotion requires paid-purchase evidence plus the configured statistical gates.

The same policy explicitly keeps these automatic actions **disabled**:

- price changes;
- paid spend;
- provider changes;
- inventory changes;
- destructive changes;
- legal/compliance-sensitive claims;
- live trading.

Therefore the old blanket statement `Wix: RECORD_ONLY` is no longer an accurate description of the current revenue plane. Wix is **production-bounded** for the exact reversible CRO capability above; broader Wix changes remain governed separately.

## Founder-Held Execution Gates

The authority matrix keeps these actions at the Human Overseer boundary or higher:

- merge to `main`;
- production deployment;
- external publishing;
- customer/claimant contact;
- spending or moving money;
- reactivating a suspended or retired agent;
- legal submission/signing;
- consequential credential/network/provider changes under applicable policy;
- any action outside a standing bounded authorization.

Two actions remain prohibited to agents:

- export/read secret values into owner-facing output, source control, reports, prompts, or logs;
- expand their own permissions.

## Approval Contract

Founder approval is **scoped and non-transitive**.

An approval should bind to:

`ACTION + TARGET + VERSION/HASH + EVIDENCE + SCOPE + EXPIRY(if applicable) + STOP/ROLLBACK CONDITIONS`

Examples:

- content approval ≠ publishing approval;
- publishing approval ≠ paid-spend approval;
- product-description CRO approval ≠ price-change approval;
- merge approval ≠ unrelated deployment approval.

## Current Revenue Decision Queue

### System should execute and report receipts

- read live funnel/attribution state;
- diagnose storefront trust/friction;
- collect SimilarWeb/market evidence through existing authorized paths;
- create internal SEO/content/video packages;
- measure views → clicks → product views → carts → checkout → paid purchases → attributed revenue;
- run only already-authorized bounded CRO automation.

### Surface to Founder at the boundary

- publish/post externally;
- contact customers;
- spend money or launch paid traffic;
- change prices;
- make broader store/catalog/inventory mutations;
- deploy new production behavior;
- alter credentials/providers/networks;
- execute destructive changes;
- make legal/compliance-sensitive claims;
- move from paper to live-money trading.

## Evidence Standard

Every consequential record must use `VERIFIED`, `INFERRED`, `UNKNOWN`, or `BLOCKED`, cite retrievable evidence, and exclude secrets, private keys, tokens, raw customer data, and raw environment files.

Normative sources:

- `governance/SYSTEM_CONSTITUTION.md`
- `governance/authority_matrix.json`
- `governance/revenue_execution_policy.json`
- applicable mission/release policy and receipts

> [!warning] Truth boundary
> Obsidian is a governed control surface, not the authority source and not runtime proof. GitHub governs versioned policy/code. Foundation VM proves runtime. A real paid purchase proves commercial conversion.

[[Dominion-Command-Center/REVENUE-PRODUCTION-NOW|Revenue Production Now]] · [[Dominion-Command-Center/18-Owner-Governance|Owner Governance]] · [[Dominion-Command-Center/00-HOME|← Command Center]]
