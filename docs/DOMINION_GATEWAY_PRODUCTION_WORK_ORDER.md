# Dominion Gateway — Production Work Order

## Objective
Deliver one Dominion-owned, governed model gateway that routes approved models by measured capability, gives every authorized agent the same canonical Dominion context, preserves Founder authority, and fails closed rather than fabricating completion.

This gateway is Dominion-only. It is not a public multi-tenant service.

## Authority and execution chain
Founder -> Five Council -> Governor -> Coordinator -> Conductor -> Dominion Model Gateway -> Specialist Agents / Tools -> Guardian / Sentinel -> Verification -> Dominion Memory.

The gateway selects intelligence. It does not independently authorize external effects. Conductor remains the execution/orchestration authority. Existing Founder gates for public publishing, payments, credential changes, and live financial actions remain intact.

## Required runtime components

1. `apps/command-center/model_gateway.py`
   - one internal routing contract
   - strict allowlist
   - provider/model health state
   - task-class routing
   - bounded retries and timeouts
   - ordered fallback
   - fail-closed behavior
   - response metadata identifying route used

2. Shared Dominion context
   - mission
   - current architecture
   - active priorities
   - verified decisions
   - agent identities and roles
   - current runtime state
   - relevant Obsidian / governed memory
   - only the minimum context required for each task

3. Model registry
   Candidate routes may include GPT-6 Astra, Fable 5, Gemini, Qwen, DeepSeek, Grok, Perplexity, Manus, Hermes, local Ollama/Nemotron, and any additional Founder-approved route. A name in the registry is not proof of availability. Promotion requires a verified working route and benchmark receipt.

4. Capability profiles
   Every route is scored for at least:
   - planning / reasoning
   - code generation and review
   - research
   - multimodal work
   - long-context synthesis
   - latency
   - reliability
   - tool-use quality
   - privacy / local execution
   - cost class

5. Routing policy
   - normal task: highest-ranked healthy approved route for the task class
   - high-impact decision: primary answer plus independent verifier when policy requires it
   - provider failure: circuit-break and fallback to next healthy route
   - all routes unavailable: return explicit unavailable state; never invent success

6. Evaluation loop
   Capture task ID, route, latency, success/failure, verifier result, and measurable task outcome. Promotion, demotion, and default-route changes require evidence rather than preference.

7. Resilience
   - health checks
   - provider timeout budgets
   - circuit breakers
   - bounded retry
   - fallback ordering
   - degraded-mode local route
   - rollback to last-known-good registry
   - no single provider dependency

8. Observability
   Expose non-secret gateway status to Command Center:
   - enabled route count
   - healthy route count
   - degraded routes
   - last successful route
   - task-class defaults
   - recent failure counts
   - active registry version

## Agent positions

### Five Council
Challenges plans, identifies omissions, checks strategic alignment, and returns an advisory verdict. It does not execute production changes.

### Governor
Applies policy, permissions, budgets, and Founder gates. Blocks unauthorized scope expansion.

### Coordinator
Sequences missions, prevents conflicting writes, tracks dependencies, and reconciles evidence.

### Conductor
Owns execution routing. It sends bounded jobs to the gateway or specialist tools and maintains mission execution state.

### Model Gateway
Selects the best approved model for the task, performs failover, emits routing receipts, and never grants itself execution authority.

### Buddy
Founder-facing operator. Uses the same canonical Dominion context and gateway rather than maintaining a conflicting private truth source.

### Metatron
Repository and technical-context specialist. Supplies current code/config/runtime evidence.

### Guardian / Sentinel
Independent integrity, safety, drift, and health verification. May block or quarantine failed routes/workflows.

### Learning / Evaluation
Scores outcomes and recommends routing changes. Cannot silently promote a model into production.

### Revenue Operations
Owns measurable business outcomes, attribution, offer/traffic experiments, and conversion telemetry.

### Publisher
Owns authorized social/content publication only after applicable approval gates and canary verification.

### Orion
Owns trading research and paper-trading intelligence within its separate trading governance. Live financial execution remains separately gated.

### Storefront / Wix lane
Owns public storefront accuracy, conversion defects, product merchandising, trust content, and checkout readiness.

### Traffic lane
Owns qualified traffic generation, channel tests, attribution tags, content distribution, and traffic receipts.

## Production lane order after gateway closure

1. **Storefront / Wix** — eliminate trust defects, empty collections, placeholder copy, policy errors, broken links, and conversion blockers.
2. **Publisher** — finish deployment defect, prove healthy callback/service, then one authorized canary publication with receipt.
3. **Traffic** — launch controlled measurable traffic loops tied to specific offers and attribution.
4. **Revenue** — prove visitor -> click -> checkout -> purchase telemetry; optimize the first constraint only.
5. **Additional verticals** — activate one at a time only when owner, offer, KPI, workflow, telemetry, failure handling, and governance are defined.

## Claude Code terminal execution order

1. Checkout PR branch and run all gateway and Command Center CI locally where practical.
2. Confirm `model_gateway.py` is packaged into the production Command Center image and imports successfully.
3. Run unit tests, image build, container boot, `/health`, `/api/status`, and `/api/chat` fallback acceptance.
4. Inspect every failing gate. Repair only the first actual defect; do not bypass or weaken tests.
5. Verify no credentials, tokens, or private memory are committed or logged.
6. Verify current Nemotron -> Buddy fallback still works when no external route is enabled.
7. Verify an unavailable or disabled provider fails closed and falls through deterministically.
8. Return evidence: commit SHA, CI run IDs, exact passing checks, container health result, and any remaining blocker.
9. Send the evidence and diff to the Five Council for adversarial review: architecture gap, security gap, governance gap, reliability gap, cost/scaling gap, or hidden single point of failure.
10. Address substantiated findings only, rerun CI, and merge when all required gates are green.

## Production hardening gate
Gateway is not production-complete until all are true:

- all required CI green
- production image builds and boots
- health/status surfaces report truthful state
- local fallback proven
- at least one approved external route proven when its access exists
- provider outage drill proves fallback
- all-route outage proves fail-closed behavior
- no secret leakage
- no direct agent bypass around Conductor/Governor
- routing receipts persisted
- rollback procedure tested
- observability present
- Council review has no unresolved severity-1 finding

## Definition of done
The gateway is DONE only when the merged main-branch release is deployed, healthy, exercised by a controlled canary task, produces a routing/evaluation receipt, and can survive loss of its preferred model without loss of governance or fabricated success.

After that closure, engineering focus moves to production: Wix/storefront, Publisher, qualified traffic, conversion/revenue telemetry, then additional verticals.
