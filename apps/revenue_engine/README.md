# Dominion Revenue Engine

A deterministic, evidence-bound revenue intelligence layer for Dominion.

## Purpose

This package operationalizes the useful mechanism behind automated affiliate-income systems without pretending that AI creates guaranteed money. It can:

1. rank buyer-intent opportunities,
2. maintain a verified affiliate-program registry,
3. produce a **draft/shadow** site architecture,
4. gate affiliate content for evidence, disclosure, originality, and prohibited income claims,
5. aggregate observed revenue facts idempotently,
6. calculate funnel economics using `Decimal`,
7. identify one constraint and propose one variable to test,
8. issue deterministic decision receipts for the current governance boundary.

## Critical boundary

`revenue_operations` is currently a simulation agent. This package therefore performs **no network I/O, no affiliate enrollment, no publishing, no customer contact, no spending, no price changes, no production deployment, and no revenue-wave activation**.

A `SIMULATION_ONLY` decision means the analysis may be prepared. It is not permission to execute externally.

## Money model

```text
evidence-backed opportunity
→ approved affiliate program evidence
→ useful site/content plan
→ traffic
→ affiliate click
→ conversion
→ commission
→ payout
→ measure
→ identify largest constraint
→ change one variable
→ measure again
```

No revenue is labeled verified merely because a model predicted it. A `VERIFIED` object must carry evidence references.

## Running the tests

No third-party Python package is required.

```bash
python -m unittest discover -s tests -p 'test_revenue_engine.py' -v
python -m compileall -q apps/revenue_engine tests/test_revenue_engine.py
```

The test suite includes randomized score invariants, idempotency, money precision, evidence gates, affiliate approval gates, prohibited-action checks, single-variable learning-loop checks, and an AST hardening test that rejects network/process/browser automation imports and dynamic execution.
