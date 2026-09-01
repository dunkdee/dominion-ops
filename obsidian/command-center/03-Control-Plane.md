# 03 · Control Plane

> [!governance] Purpose
> The control plane determines how work is authorized, delegated, verified, escalated, and stopped.

## Required Reading

- [[Dominion-Brain/03-Control-Plane/CONTROL_PLANE|Control Plane Contract]]
- [[Dominion-Brain/03-Control-Plane/DOMINION_OPERATING_MAP|Dominion Operating Map]]
- [[Dominion-Brain/03-Control-Plane/AGENT_OPERATIONS_STATE|Agent Operations State]]
- [[Dominion-Brain/03-Control-Plane/RUNTIME_ALIGNMENT|Runtime Alignment]]
- [[Dominion-Brain/00-Constitution/SYSTEM_CONSTITUTION|System Constitution]]
- [[Dominion-Command-Center/18-Owner-Governance|Owner Governance]]

## Execution Rule

`INVENTORY → VERIFY → REUSE/CONNECT → TRUE DELTA → POLICY DECISION → EXECUTE → VERIFY → RECEIPT → LEARN`

Unsupported model output cannot become irreversible action. Consequential actions follow the applicable authority matrix, mission policy, Council review, and Human Overseer gate.

## Owner Governance Resolution Order

When authority is unclear, resolve in this order:

1. System Constitution.
2. `governance/authority_matrix.json`.
3. Mission-specific policy and active release contract.
4. Scoped Founder approval/standing authorization, if the policy permits it.
5. Current runtime evidence and acceptance receipts.

If these disagree, the system returns `BLOCKED`; it does not choose the most permissive interpretation.

## Standing Authorization vs Founder Approval

**Standing authorization** is narrow, versioned and bounded. It applies only to the exact action already allowed by an active policy.

**Founder approval** is required when the action crosses the Human Overseer boundary defined in the authority matrix or applicable policy.

Approval is never transitive. Authorization for a draft does not authorize publication; authorization for reversible CRO does not authorize price changes or paid spend; authorization for merge does not silently authorize unrelated deployment.

## Pre-Execution Contract

Before consequential execution, record:

`ALREADY_BUILT` · `ALREADY_DEPLOYED` · `ALREADY_TESTED` · `ALREADY_MERGED` · `DUPLICATE_RISK` · `BUSINESS_VALUE` · `TRUE_DELTA` · `AUTHORITY_CLASS` · `APPROVAL_REQUIRED` · `STOP/ROLLBACK`

If `TRUE_DELTA` is empty, reuse the existing capability and do not implement a duplicate.

## Current Revenue Example

The active revenue policy permits bounded reversible Wix CRO only on `plainDescription`, with current-revision proof, snapshots, after-verification, rollback, max 50% treatment traffic, and paid-purchase/statistical winner gates.

It does **not** automatically permit price changes, paid spend, provider changes, inventory changes, destructive changes, legal/compliance-sensitive claims, or live trading.

That distinction is the model for all lanes: **maximum useful operation inside exact authority; fail closed outside it.**

[[Dominion-Command-Center/REVENUE-PRODUCTION-NOW|Revenue Production Now]] · [[Dominion-Command-Center/15-Founder-Oversight|Founder Oversight]] · [[Dominion-Command-Center/00-HOME|← Command Center]]
