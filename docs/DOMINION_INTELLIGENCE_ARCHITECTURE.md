# Dominion Intelligence Architecture

## Authority chain

Founder -> Dominion Command Center -> Nemotron primary intelligence -> Metatron and Obsidian context -> Conductor and specialist agents -> governed execution -> verification -> Dominion memory.

## Non-negotiable operating rules

1. The Founder retains final authority.
2. Nemotron is the primary reasoning layer, not an ungoverned executor.
3. Metatron supplies repository and technical context.
4. Obsidian is the durable business memory and operating record.
5. Conductor routes tools and specialist agents and remains a fallback reasoning path.
6. No task is complete without runtime or business evidence.
7. Every material decision, result, failure, and lesson is written back to Dominion-owned memory.
8. Paid services are not activated without explicit approval.

## One-ecosystem, multi-lane operating model

Dominion operates as one enterprise AI family with a shared identity, mission, memory contract, evidence standard, and Founder authority. “Family” is an operating identity encoded in prompts, metadata, routing, and records; it does not grant any model independent authority.

The Command Center may run multiple lanes concurrently when their scopes do not conflict:

- Intelligence lane: Nemotron reasons, plans, challenges assumptions, and produces verification gates.
- Context lane: Metatron, repositories, and Obsidian assemble the relevant technical and business record.
- Execution lane: Conductor routes bounded work to the correct specialist agents and workflows.
- Verification lane: independent checks collect health, quality, safety, KPI, and provenance evidence.
- Memory lane: approved outcomes, failures, and lessons are written back into Dominion-owned memory.
- Impact lane: vertical owners connect work to a named real-world problem and measurable outcome.

Each mission receives a mission ID, lane owners, bounded permissions, dependencies, a verification gate, and a memory destination. Lanes may execute in parallel, but conflicting writes, public publishing, payments, credential changes, and live financial actions require the applicable approval gate.

## Precision-to-frontier loop

1. Define the real problem, beneficiary, baseline, and success metric.
2. Retrieve evidence and label facts, assumptions, and unknowns.
3. Produce the smallest high-confidence plan and assign parallel lanes.
4. Execute quickly inside explicit permissions and budgets.
5. Verify the result with independent runtime and business evidence.
6. Measure quality, reach, conversion, reliability, cost, and real-world impact without gaming platforms or misleading people.
7. Record the lesson and improve the shared playbook.
8. Promote only workflows that repeatedly outperform the baseline.

## Closed-loop workflow

1. Intake: receive a mission from phone, laptop, API, or scheduled workflow.
2. Context: load the Dominion mission, relevant Obsidian notes, repository state, and vertical KPIs.
3. Plan: Nemotron produces an objective, action sequence, risks, verification gate, and memory note.
4. Govern: apply permissions, human approval requirements, budget limits, and scope boundaries.
5. Execute: Conductor invokes the correct specialist agent or workflow.
6. Verify: collect logs, URLs, metrics, artifacts, and failure evidence.
7. Record: store the exchange and verified outcome in Dominion memory.
8. Improve: compare outcomes to KPIs and update the vertical playbook.

## Deployment topology

- foundation-vm: control plane, Command Center, reverse proxy, orchestration, memory access, health checks.
- Nemotron worker: Dominion-governed OpenAI-compatible endpoint backed by the locally hosted `nemotron-3-nano:4b` model through Ollama; it is the primary reasoning layer and has no independent execution authority.
- Obsidian vault: read-only to the Command Center service; governed writers handle approved memory updates.
- Persistent command memory: append-only operational exchanges stored outside the container.

## First revenue vertical completion gate

The first vertical is not considered active until it has:

- a named customer and offer;
- a measurable traffic source;
- approved content and publishing workflow;
- lead capture and follow-up;
- revenue and conversion telemetry;
- failure alerts and retry ownership;
- a weekly improvement review stored in Obsidian.
