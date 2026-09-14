# Revenue Snapshot Integrity

Dominion's adaptive revenue loop must not treat a skipped measurement as success.

## Required behavior

The Empire Status Snapshot workflow fails closed when the n8n gateway URL is absent, malformed, unreachable, or when the tool secret is absent. A successful run must parse the `roi_snapshot` response as a JSON object and emit `REVENUE_SNAPSHOT_RECEIPT=PASS`.

This preserves the canonical sequence:

Traffic → Conversion → Payment → Receipt → Attribution → Learning → Optimization → Scale

A green workflow without a measurement receipt is not evidence of a completed measurement cycle.

## Authority boundary

This change does not add a new analytics system, scheduler, orchestrator, memory store, or source of truth. It only hardens the existing scheduled revenue snapshot so failure remains visible under RADAH MEMSHALAH.
