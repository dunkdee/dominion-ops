# Dominion Operating Map

**Authority:** Dewayne Singleton, Human Overseer  
**Purpose:** One authoritative reading map for how Dominion is governed, organized, operated, reviewed, and improved.  
**Operating order:** Cash flow → Systems → Scale  
**Status:** Governance index and reconciliation plan. This file does not grant production authority.

---

## 1. Required reading order for every agent and operator

Every session, agent startup, recovery, deployment, or major task begins in this order:

1. `governance/SYSTEM_CONSTITUTION.md` — supreme operating law.
2. `STATE.md` — current session and operational state; verify freshness before relying on it.
3. `README.md` — repository boundary and control-plane entry points.
4. `agents/registry.json` — identity, lifecycle state, permissions, prohibitions, and escalation.
5. `governance/authority_matrix.json` — default-deny action authority and approval requirements.
6. `governance/five_council_policy.json` — independent review, dissent, and veto behavior.
7. `governance/incident_learning_policy.json` — how failures become versioned controls.
8. `governance/verticals.json` — business lanes, priorities, modes, dependencies, and exit gates.
9. `architecture/CONTROL_PLANE.md` — how proposals become bounded execution.
10. Applicable vertical contract, SOP, runbook, deployment document, and current incident record.
11. Runtime inventory and live evidence from the production VM before making production claims.

If two sources conflict, execution stops. The conflict must be classified, recorded, and resolved through the applicable governance process.

---

## 2. Dominion family structure

Dominion is one coordinated operating family, not a collection of isolated agents.

```text
Human Overseer
    ↓
Five Council
    ↓
Governor / Policy Gate
    ↓
Coordinator
    ↓
Conductor / Orchestrator
    ↓
Vertical Operators and Specialist Agents
    ↓
Workers, tools, services, and workflows
    ↓
Guardian / Sentinel / Health / Incident Learning
```

All members share the same mission, current priorities, evidence standards, authority boundaries, and learning system. Each member has a separate duty, but no member maintains a separate reality.

---

## 3. Non-negotiable laws

1. Human final authority remains with the Human Overseer.
2. Evidence comes before assertion.
3. Truth states are `VERIFIED`, `INFERRED`, `UNKNOWN`, or `BLOCKED`.
4. Tools and actions are denied by default.
5. No agent may expand its own authority, permissions, budget, or production access.
6. A proposer cannot be the sole approver of a consequential action.
7. Production changes require bounded scope, rollback, and post-action verification.
8. Secrets and private data never enter Git, prompts, reports, logs, screenshots, or Obsidian notes.
9. No unreviewed self-modification of code, prompts, memory, policy, permissions, or procedure.
10. Every failure, near miss, and knowledge defect must enter the incident-learning loop.
11. Revenue priorities never override law, security, privacy, or human-impact controls.
12. Nothing is complete without retrievable proof of the actual result.

---

## 4. Action authority

The authority model is default-deny.

| Risk | Council requirement | Human approval |
|---|---:|---:|
| Low | None | Not normally required |
| Moderate | 2 approvals | Not normally required |
| High | 4 approvals | Depends on action; protected actions remain human-only |
| Critical | 5 approvals | Required |
| Prohibited | Reject | Cannot be delegated |

Human-only or explicitly controlled actions include production deployment, merge to main, external publication, customer or claimant contact, spending or moving money, legal submission, production secret rotation, public DNS changes, and reactivation of suspended or retired agents.

Law/Governance and Security/Risk retain independent veto power where their domains apply.

---

## 5. Current registered roles

The machine-readable registry currently defines:

- Human Overseer
- Coordinator
- Conductor
- Governor
- Guardian
- Sentinel
- Juris
- Five Council: Truth and Evidence
- Five Council: Law and Governance
- Five Council: Security and Risk
- Five Council: Engineering and Reliability
- Five Council: Business Value and Human Impact
- Revenue Operations
- Engineering
- Research

### Registry gap

The production VM contains many additional named services and operational agents that are not yet represented as full registry members. Examples include watchdogs, healthcheck services, platform operators, store/Wix operators, content/video services, KDP, SEO, affiliate, social, surplus, dashboards, Buddy, Alchemist, Alpha, and other conductor variants.

**Required correction:** every live service or agent must be matched to exactly one of these outcomes:

- registered independent agent;
- worker owned by a registered agent;
- shared platform service;
- standby/rollback component;
- duplicate to consolidate;
- obsolete component to retire.

No live component should remain ownerless.

---

## 6. Vertical operating order

The vertical registry currently orders work as follows:

1. Commerce and fulfillment
2. KDP publishing
3. Analytics services
4. Digital products
5. Services lead generation
6. Content and traffic
7. Surplus
8. Trading — paper only
9. Intelligence and orchestration
10. Governance and legal
11. Infrastructure

Maximum activation rule: no more than two primary revenue verticals should be promoted in the same operating wave.

Each vertical must have:

- named operator;
- explicit mode;
- input contract;
- output contract;
- dependencies;
- human approval gates;
- health signal;
- failure queue;
- evidence location;
- measurable exit gate;
- separate accountability for revenue, cost, quality, and risk.

---

## 7. Standard agent home contract

Each agent receives an Obsidian home with the same structure:

```text
Agents/<agent-id>/
├── 00-Identity.md
├── 01-Mission.md
├── 02-Authority.md
├── 03-Inputs.md
├── 04-Outputs.md
├── 05-Dependencies.md
├── 06-SOPs.md
├── 07-Health-and-Metrics.md
├── 08-Incidents-and-Lessons.md
├── 09-Current-State.md
└── 10-Change-Log.md
```

Every agent home must link back to the Constitution, authority matrix, vertical registry, current state, and applicable runbooks. Agent notes may explain policy but may not replace or contradict normative GitHub policy.

---

## 8. Shared Obsidian vault structure

```text
Dominion-Brain/
├── 00-Constitution/
├── 01-Founder-Authority/
├── 02-Five-Council/
├── 03-Control-Plane/
├── 04-Agents/
├── 05-Verticals/
├── 06-Operations/
├── 07-Incidents/
├── 08-Evidence/
├── 09-Revenue/
├── 10-Architecture/
├── 11-SOPs/
├── 12-Decisions/
├── 13-Learning/
├── 14-Daily-State/
└── 99-Archive/
```

GitHub remains authoritative for versioned law, policy, code, contracts, and deployment records. Obsidian is the operational knowledge and coordination layer. Production runtime remains authoritative for live state. These three sources must be reconciled rather than treated as interchangeable.

---

## 9. Standard work packet

All consequential work should use one packet:

```yaml
objective:
requester:
assigned_owner:
vertical:
risk_level:
verified_facts: []
unknowns: []
assumptions: []
evidence: []
dependencies: []
required_reviews: []
human_approval_required:
success_conditions: []
stop_conditions: []
rollback_plan:
execution_result:
post_action_verification:
lessons:
follow_up_owner:
```

This packet becomes the shared language between agents and prevents silent handoffs or conflicting interpretations.

---

## 10. Operating movement

```text
Approved goal
  → Coordinator creates work packet
  → Conductor routes by registry and vertical
  → Assigned agent gathers evidence and proposes action
  → Governor evaluates policy and authority
  → Five Council reviews when required
  → Human Overseer authorizes protected action
  → Bounded executor performs the action
  → Sentinel/Guardian independently verifies result
  → Evidence and state are updated
  → Incident-learning loop runs when needed
  → Reusable learning is promoted through review
```

No agent may mark its own consequential work complete without independent verification.

---

## 11. Immediate reconciliation work

1. Preserve and reconcile VM-only Git changes against approved GitHub state.
2. Build a complete service-to-agent ownership table from the runtime inventory.
3. Map every systemd unit, timer, cron job, container, port, Caddy route, repository, and workflow to one owner and one purpose.
4. Identify duplicate watchdog, monitor, healer, conductor, scheduler, and dashboard responsibilities.
5. Update `agents/registry.json` with approved missing identities or classify them as workers/services.
6. Create Obsidian homes from the standard contract.
7. Synchronize current state without copying secrets.
8. Validate every active vertical against its exit gate.
9. Keep only two primary revenue lanes active per wave.
10. Add deterministic checks so unregistered or ownerless production services fail governance validation.

---

## 12. Current known document issue

`STATE.md` is required reading but contains dated session information and may not reflect the latest production audit. It must be treated as session memory, not unquestioned live truth. The runtime inventory, current workflow evidence, and direct production verification must be used to refresh it.

---

## 13. Definition of aligned

Dominion is aligned when:

- every active component has one owner and one purpose;
- every agent reads the same governing sources;
- every vertical has contracts, gates, evidence, and measurable outcomes;
- GitHub, Obsidian, and VM runtime state agree or explicitly record their differences;
- duplicate authority and duplicate scheduling are removed;
- every consequential action is traceable from objective through verification;
- lessons improve the whole family through reviewed, shared controls;
- the system advances revenue without sacrificing law, reliability, or founder authority.
