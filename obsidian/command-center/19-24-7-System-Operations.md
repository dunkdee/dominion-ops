# 19 · 24/7 System Operations

> [!governance] Production operating rule
> Dominion is expected to operate continuously. The Founder oversees consequential boundaries; the governed system executes routine, reversible, authorized work and returns receipts.

## Continuous Loop

`FOUNDER INTENT → DOMINION BRAIN / OBSIDIAN → GOVERNED PLAN → AGENTS / COUNCIL → EXECUTION → VALIDATION → RECEIPT → RUNTIME EVIDENCE → DOMINION BRAIN`

This loop is designed to run 24 hours a day, 7 days a week without requiring the Founder to babysit routine synchronization, verification, monitoring, or bounded repair.

## Dominion Brain / Obsidian Synchronization

Standing authorization: `founder-governed-obsidian-sync-v1`.

The production Dominion Brain publisher now has two automatic execution paths:

1. **Event driven:** relevant changes merged to `main` trigger publication automatically.
2. **Hourly reconciliation:** an hourly scheduled run rechecks the current `main` state so a missed or interrupted synchronization can recover without Founder intervention.

Manual `workflow_dispatch` remains available as a recovery and controlled operator path.

## Required Acceptance

Every automatic Brain synchronization must prove:

- exact current `main` commit;
- Brain input validation PASS;
- rendered manifest integrity PASS;
- fast-forward-only VM repository synchronization;
- clean tracked VM state;
- rollback material present before replacement;
- generated Brain publication PASS;
- Obsidian backend loopback-only;
- authenticated vault route healthy;
- unauthenticated vault access returns HTTP 401;
- temporary secret/access material removed;
- retrievable workflow receipt emitted.

A failed gate is `HELD` or `BLOCKED`, never production success.

## Founder Boundary

The Founder is not required for routine Brain synchronization covered by the standing authorization above.

Fresh Founder authorization is still required for actions outside that boundary, including public unauthenticated publishing, credential or authentication changes, DNS/firewall/provider changes, customer contact, external messaging, spending, live trading, destructive operations, permission expansion, and other consequential actions governed elsewhere.

## Truth Boundary

Obsidian is the operational knowledge and coordination surface. It does not replace runtime evidence. GitHub preserves versioned governance/code; Foundation VM receipts prove live state; commercial outcomes prove revenue performance.

## Receipt Rule

No completion claim without evidence. Every production step must be traceable to an exact SHA, workflow/run receipt, acceptance output, or runtime artifact.

[[Dominion-Command-Center/15-Founder-Oversight|Founder Oversight]] · [[Dominion-Command-Center/08-Evidence|Evidence]] · [[Dominion-Command-Center/10-Architecture|Architecture]] · [[Dominion-Command-Center/00-HOME|← Command Center]]
