# Dominion Integrity Installation Checklist

This checklist is the minimum installation/runtime proof required for the current revenue-learning objective.

## P0 runtime gates

- [ ] DeerFlow current `main` SHA deployed through `deploy-deerflow-runtime.yml`
- [ ] `DEERFLOW_CAPABILITY_PROOF=PASS`
- [ ] `DEERFLOW_RUNTIME_HEALTH=PASS`
- [ ] restart/persistence proof captured
- [ ] governance-denial proof captured
- [ ] rollback/regression proof captured
- [ ] first bounded Dominion synchronization mission receipt captured
- [ ] Empire Status Snapshot emits `REVENUE_SNAPSHOT_RECEIPT=PASS`
- [ ] n8n revenue/orders gateway URL and tool secret are valid and reachable
- [ ] VoltEdge payment-provider onboarding proven
- [ ] VoltEdge delivery method calculation closes with no blocking violation
- [ ] mobile storefront trust/conversion path verified
- [ ] analytics/UTM source-to-order attribution verified
- [ ] one authorized real-order canary completed
- [ ] order/receipt/fulfillment state verified
- [ ] governed refund path and refund receipt verified
- [ ] Publisher/Meta canary points only to the proven destination
- [ ] YouTube/content canary attribution captured
- [ ] adaptive learning record contains signal, action, cost, traffic, conversion, revenue, contribution, failure reason, lesson, and next action

## Anti-drift acceptance

No item is DONE from repository code, CI, or documentation alone when runtime evidence is required. No new orchestrator, publisher, analytics authority, memory store, scheduler, or command plane may be introduced to close these items.
