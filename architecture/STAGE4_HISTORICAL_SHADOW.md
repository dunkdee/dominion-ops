# Stage 4 — Historical-Data Shadow Observation

## Status

**Mode:** `shadow_only`  
**External execution:** disabled  
**Canonical registry mutation:** disabled

Stage 4 adds local-file adapters for already-exported historical funnel and revenue snapshots. It does not call Wix, payment providers, analytics platforms, customers, or any other external system.

## Evidence path

```text
Exported snapshot
  -> schema and field validation
  -> payload SHA-256 verification
  -> date and funnel-consistency checks
  -> personal-data and secret-material rejection
  -> deterministic funnel normalization
  -> proposal-bound Five Council records
  -> non-contact shadow observation
  -> TEST_ONLY, CONTINUE_SHADOW, HOLD, or next-review eligibility
```

## Repository evidence

The repository does not contain a verified actual-business historical revenue dataset. The committed Stage 4 observation therefore uses a clearly labeled repository fixture and must return `TEST_ONLY`.

An actual-business snapshot can be marked `VERIFIED` only when it:

- originates from an allowed export source;
- is labeled `ACTUAL_BUSINESS_HISTORY`;
- contains no personal data or secret material;
- includes evidence references and an `as_of` timestamp;
- matches its canonical payload hash;
- has valid date ranges, monotonic funnel counts, and nonnegative economics.

## Council records

`runtime/records/stage4/` contains one canonical proposal envelope, five independently bound council records, their aggregate decision, the adapted fixture snapshot, and the first non-contact observation.

These council records are deterministic automated evidence reviews. They are not human legal advice, licensed-counsel opinions, or authorization for production execution.

## Hard boundary

Even a successful actual-history observation can only become `OBSERVED_ELIGIBLE_FOR_NEXT_REVIEW`. It cannot:

- contact a customer or claimant;
- publish content;
- move or spend money;
- deploy production;
- enable live trading;
- promote an agent;
- start Obsidian or Browser Agents;
- mutate the canonical registry.

Production progression still requires closure of the Wix isolation block, verified actual historical input, threat-model and rollback evidence, applicable council review, and recorded Human Overseer approval.
