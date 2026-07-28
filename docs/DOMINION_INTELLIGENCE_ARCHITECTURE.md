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
- Nemotron worker: modular OpenAI-compatible inference endpoint running on approved local or future cloud compute.
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
