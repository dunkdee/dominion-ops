# Dominion Commercial Closure Execution

Governance: RADAH MEMSHALAH

This document binds commercial closure to the existing canonical work instead of creating another architecture lane.

## Canonical execution spine

1. **Inventory truth — issue #81**
   - Every component is classified from current evidence.
   - Allowed final states: `VERIFIED_PASS`, `BLOCKED`, `RETIRED`.
   - Unknown state is not converted to PASS by inference.

2. **Infrastructure repair**
   - Close verified runtime defects before adding new orchestration or execution platforms.
   - Every mutation requires pre-state, rollback, tests, runtime verification, and evidence.

3. **Buddy production readiness — issue #101**
   - Buddy is the governed execution operator.
   - A capability exists only when its executor, authentication, health probe, execution proof, failure behavior, and receipt are verified.
   - Self-report never counts as completion.

4. **First verified revenue loop — issue #305**
   - Traffic -> visit -> checkout -> payment -> receipt -> attribution -> learning -> optimization.
   - Commercial readiness requires a real authorized order and governed refund receipt before traffic is scaled.

5. **Controlled scale**
   - Publisher, YouTube, Meta, TikTok, SEO, and email scale only after the revenue loop has attributable economics and a valid rollback path.

## Freeze rule

Until steps 1-4 are closed, do not introduce a replacement orchestrator, parallel memory authority, parallel analytics authority, or another system of record. A new tool can be evaluated only when it removes a verified capability gap and passes the existing governance path.

## Evidence rule

A statement such as `DONE`, `PASS`, `LIVE`, `DEPLOYED`, or `COMMERCIAL READY` requires machine-verifiable evidence appropriate to the claim. A successful HTTP response alone is not full production acceptance.

## Mistake protocol

When an implementation or earlier claim is wrong:

1. acknowledge the exact defect;
2. identify its blast radius;
3. correct the smallest safe scope;
4. rerun positive and negative controls;
5. verify runtime state;
6. record the receipt;
7. keep the affected gate open until the evidence passes.

## Commercial-ready gate

Dominion is not `COMMERCIAL READY` until every required gate in `governance/commercial_closure_gate_v1.json` is `VERIFIED_PASS` with current evidence.
