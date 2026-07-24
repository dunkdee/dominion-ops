# Dominion Control Plane Architecture

## Purpose

The control plane converts model proposals into bounded, evidence-backed, reversible operations. It is the prerequisite for expanding the agent workforce or activating new revenue automation.

```text
Event or approved objective
        ↓
Coordinator / Orchestrator
        ↓
Agent proposal
        ↓
Evidence and schema validation
        ↓
Governor policy decision
        ↓
Independent council review
        ↓
Human approval when required
        ↓
Bounded executor
        ↓
Post-action verification
        ↓
Immutable audit record
        ↓
Incident-learning loop when needed
```

## Trust boundaries

- **Model boundary:** model text is untrusted until validated.
- **Tool boundary:** tools are denied by default and scoped per agent.
- **Data boundary:** secrets and classified data are referenced, not copied.
- **Execution boundary:** production, publishing, money, legal action, and customer contact require explicit authority.
- **Memory boundary:** proposed lessons do not become active policy without review and version control.
- **Vertical boundary:** each business vertical has isolated credentials, data, budgets, and failure domains while reusing approved shared services.

## Required components

1. **Agent registry** — identity, purpose, lifecycle, permissions, prohibitions, escalation.
2. **Governor** — deterministic policy evaluation against action, risk, data, and approval context.
3. **Five Council** — independent cross-domain review with preserved dissent and vetoes.
4. **Evidence store** — source references, hashes, test results, workflow runs, and approvals.
5. **Audit ledger** — append-only decision and execution records.
6. **Incident system** — detection, containment, root cause, corrective control, regression, recurrence monitoring.
7. **Revenue operations** — measured funnels and experiments that remain inside governance boundaries.
8. **Observability** — reliability, quality, cost, security, drift, and revenue metrics.

## Initial implementation boundary

This repository change establishes governance contracts and CI validation. It does **not** grant new production permissions, start Obsidian, contact customers, publish content, spend money, or bypass the existing Wix diagnosis and cutover blocks.

Runtime enforcement must be implemented and verified before registered agents are promoted to broader autonomy.
