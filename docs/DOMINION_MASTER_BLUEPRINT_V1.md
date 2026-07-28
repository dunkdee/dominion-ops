# Dominion Master Blueprint v1.0

**Status:** Evidence baseline and living-document foundation  
**Canonical repository:** `dunkdee/dominion-ops`  
**Baseline commit:** `14a5f9e8c2b65ec441c7cacc2786bfbdae0ff201`  
**Prepared:** 2026-07-28  
**Authority:** Human Overseer retains final authority.  

> Structure creates sovereignty. Documentation preserves structure. Governance preserves sovereignty.

## 1. Purpose

This document is the canonical, evidence-backed operating blueprint for the Dominion ecosystem. It explains what Dominion is, what has been built, why each major capability exists, how the pieces fit together, what is verified, what remains unverified, and what must happen next.

Nothing is classified as Production without current deployment, runtime, test, or approved operational evidence. Repository presence proves that a capability is versioned; it does not by itself prove that the capability is live.

## 2. What Dominion Is

Dominion is a governed, human-directed AI business and operations ecosystem designed around the sequence:

**Cash flow → Systems → Scale**

Its purpose is to convert owned knowledge, digital products, commerce, publishing, content, market intelligence, automation, and specialized agents into repeatable revenue and durable operational capacity without surrendering final human authority.

Dominion is not one application. It is a layered operating system consisting of:

1. a constitutional governance layer;
2. a deterministic control plane;
3. a protected deployment and runtime layer;
4. an agent and workflow layer;
5. revenue and content verticals;
6. evidence, audit, recovery, and institutional-memory systems.

## 3. Why Dominion Exists

Dominion exists to solve five core problems:

- fragmented tools that do not share authority, evidence, or memory;
- AI systems that can generate output but cannot prove operational truth;
- business automations that drift from their original purpose;
- revenue initiatives that are launched without readiness, unit economics, or controls;
- loss of institutional memory when systems, agents, or operators change.

The design response is a default-deny, evidence-first ecosystem where actions are governed, deployments are reversible, claims are classified by evidence, and every production component has an accountable place in the architecture.

## 4. Governing Doctrine

The repository establishes the following operating doctrine:

- Human Overseer retains final authority.
- Unsupported model output cannot become an irreversible action.
- Consequential actions require explicit scope, evidence, approval, and rollback boundaries.
- Five Council review is the final affirmative gate for governed consequential releases.
- Legal and Security vetoes remain blocking.
- Production deployment is manual, exact-SHA authorized, protected-environment gated, health checked, and rollback capable.
- Revenue is not claimed without posted and reconciled evidence.
- External estimates cannot be represented as verified first-party results.
- Sensitive, legal, personal, and health-related data remain inside explicit evidence and handling boundaries.

## 5. Evidence Classes

All blueprint claims use one of these states:

- **Production** — current live state supported by deployment or runtime evidence.
- **Ready** — built and validated, but current live operation is not proven.
- **In Progress** — implemented partially or missing integration, approval, or runtime proof.
- **Needs Work** — present but failing, stale, unsafe, contradictory, or insufficiently documented.
- **Planned** — approved concept without implementation evidence.

## 6. Verified Repository Boundary

### 6.1 Canonical control repository

`dunkdee/dominion-ops` is the connected private repository and the versioned control source for governance, automation, deployment, applications, evidence contracts, and operational documentation.

**Status:** Production control source  
**Runtime status:** Repository itself verified; runtime state must be reconciled separately.

### 6.2 Branch and change model

Verified recent work uses protected feature branches and pull requests into `main`. Recent merged work shows separate changes for governance, runtime, revenue, Video Studio, Wix hardening, deployment, Obsidian, and content generation.

**Strength:** Traceable change history and review boundaries.  
**Gap:** A complete branch-retirement and stale-branch policy is not yet documented in this blueprint.

## 7. Architecture Inventory

### 7.1 Governance foundation

Verified repository components include:

- `governance/SYSTEM_CONSTITUTION.md`
- `governance/authority_matrix.json`
- `governance/five_council_policy.json`
- `governance/incident_learning_policy.json`
- `governance/legal_evidence_policy.json`
- `governance/constitutional_amendment_policy.json`
- break-glass recovery policy, disabled until runtime implementation
- `agents/registry.json`
- strict schemas for reports, incidents, actions, decisions, candidates, revenue, council reviews, and operating records
- deterministic validators and CI workflows

**Classification:** Ready / partially enforced in CI  
**Why it exists:** To prevent unrestricted autonomy, silent policy drift, unsupported claims, and irreversible actions without human-governed authority.

### 7.2 Control plane

Verified control-plane capabilities include:

- default-deny Governor decisions;
- ALLOW, HOLD, and DENY records;
- append-only hash-chained evidence ledger;
- independent Five Council aggregation;
- Law and Security veto handling;
- fail-closed agent onboarding;
- controlled shadow cohorts;
- proposal-bound council review records;
- simulation and shadow revenue analysis;
- deterministic validation and regression tests.

**Classification:** Ready for governed evaluation; production execution authority remains bounded.  
**Why it exists:** To separate analysis and recommendations from permission to execute.

### 7.3 Unified operating map and ownership

Verified components include:

- `governance/DOMINION_OPERATING_MAP.md`
- service ownership registry schema and seed registry;
- VM → GitHub → Obsidian reconciliation model;
- Founder → Council → Governor → Coordinator → Conductor → agent hierarchy;
- work-packet, identity, lifecycle, memory, evidence, escalation, rollback, and succession requirements.

The ownership registry was intentionally introduced with explicit null owners and rollback fields where evidence was incomplete.

**Classification:** In Progress  
**Why it exists:** To eliminate duplicate ownership, orphan services, split-brain memory, and undocumented dependencies.

### 7.4 Deployment control plane

Verified deployment design includes:

- manual `Deploy Foundation VM — Governed` workflow;
- exact 40-character SHA reachable from `main`;
- protected `foundation-vm-production` environment;
- VM connection secrets held outside Git;
- constitutional and control-plane validation before deployment;
- authorized Git bundle transfer rather than requiring VM-side GitHub authentication;
- repository identity checks;
- Docker, disk, Compose, and health preflight;
- local drift quarantine and protected backup;
- exact container identity reconciliation;
- structured failure context with redaction;
- automatic rollback and previous-release restoration;
- issue-based deployment evidence mirror.

**Classification:** Production-capable deployment system, with individual runtime releases requiring exact evidence.  
**Why it exists:** To prevent uncontrolled push deployment, secret leakage, unverified drift, and unrecoverable service changes.

### 7.5 Foundation VM runtime inventory system

A read-only `Production Ecosystem Audit` workflow has been expanded to collect:

- host capacity and uptime;
- Docker containers, images, and Compose projects;
- systemd services and timers;
- listening ports and local health probes;
- cron locations and counts without command bodies;
- Caddy locations and validation state;
- major Dominion directories;
- Git repositories, branches, deployed SHAs, dirty state, and sanitized origins;
- `.env` locations and key names only, never values.

**Classification:** Ready; current report must be refreshed and reconciled before claiming a complete runtime inventory.  
**Why it exists:** The VM is runtime ground truth, while GitHub is the versioned control source.

### 7.6 Docker and service boundary

Recent deployment evidence references governed identities for:

- Wix Agent;
- Dominion Web;
- Baby Logger;
- Baby API;
- Browser Agents;
- Obsidian Remote;
- Video Studio components.

Exact-name and exact-identity reconciliation was added to prevent accidental removal of unrelated containers.

**Classification:** Mixed — service contracts are versioned; current live state must be confirmed per service.  
**Major risk:** Historical fixed container names and legacy containers created repeated deployment collisions.  
**Required correction:** Standardize Compose project labels, service labels, image naming, paths, persistent volumes, and retirement records for every runtime service.

### 7.7 Obsidian / Dominion Brain

Verified design includes:

- governed Obsidian Remote workflow;
- exact deployed-SHA verification;
- protected password handling;
- localhost-only service binding through Caddy;
- authenticated local and external verification;
- unauthenticated `401` proof;
- DNS readiness marker;
- temporary-secret cleanup;
- vault mount under `/vaults/Dominion` and persistent `/config`.

**Classification:** Ready or Production only after the latest exact-SHA workflow evidence is recorded.  
**Why it exists:** To provide phone-first and laptop-accessible institutional memory without exposing the vault directly.

### 7.8 AI agent ecosystem

Verified foundations include:

- governed agent registry;
- lifecycle states;
- controlled eight-agent shadow cohort;
- default-deny tool catalog;
- identity, authority, prohibited actions, inputs, outputs, dependencies, escalation, health, and memory-home requirements;
- Browser Agent deployment/build system;
- specialized operational workflows for Juris, intelligence, Wix, trading audits, content, and other services.

**Classification:** In Progress  
**Gap:** The repository does not yet prove a complete, current registry for every claimed agent or tool in the wider ecosystem. Counts such as 90+ agents or 199 tools must remain unverified until the registry and VM audit reconcile them.

### 7.9 Workflow and automation estate

Repository search identifies a large GitHub Actions estate, including deployment, diagnostics, health, environment checks, vault, Gemini content, product creation, intelligence, Docker, n8n, Wix, surplus, Datadog, Juris, trading, browser agents, Alpha Engine, blueprint upload, and activation workflows.

**Classification:** Needs Work as a portfolio, even where individual workflows function.  
**Reason:** A high workflow count creates duplication, obsolete pathways, privilege drift, and unclear ownership unless every workflow has lifecycle status, trigger, permissions, secrets, owner, evidence output, and retirement date.

### 7.10 n8n and orchestration

The repository and known architecture reference n8n as an orchestration layer, but this audit has not yet obtained a current exported list of all production n8n workflows and activation states.

**Classification:** In Progress / runtime unverified  
**Required evidence:** Workflow IDs, names, active state, triggers, credentials boundary, upstream/downstream dependencies, failure routing, owner, and last successful execution.

### 7.11 Content engine

The repository contains a Vertex AI Gemini content engine with a `campaign` command that produces:

- long-form video planning;
- multiple vertical variants;
- platform posts;
- funnel assets;
- experiments;
- originality, claims, synthetic-media, music-license, and copyright checks;
- stop/scale rules based on retention and qualified traffic.

The PR explicitly states that production publishing, credentials, accounts, DNS, and paid services were not activated by that change.

**Classification:** Ready as a generation engine; publishing pipeline In Progress.  
**Why it exists:** To turn one verified idea into platform-specific campaigns while keeping publication and claims governed.

### 7.12 Video Studio / clone platform

Verified repository capabilities include:

- consent records for likeness, voice, and source media;
- project, asset, render, status, download, and approval APIs;
- mobile operator interface;
- CPU proof renderer;
- detachable authenticated worker contract;
- isolated Docker deployment;
- persistent storage, upload limits, health/readiness checks;
- engine-spec adapter with shell-free execution;
- rollback readiness checks;
- CPU preview and synthetic canary specs;
- fail-closed premium worker template;
- license approval requirements.

The repository explicitly does not prove that a premium neural model, weights, or GPU worker is installed.

**Classification:** Ready control plane; neural clone output capability In Progress.  
**Why it exists:** To own a zero-paid-tools, phone-first media platform while keeping inference modular and preventing unapproved GPU spending or unlicensed model use.

### 7.13 Wix commerce

Verified evidence includes:

- Wix Catalog V3 agent;
- read-only catalog/store audit;
- hardened operator routes;
- removal of generated legal, warranty, shipping, product, and payment claims;
- record-only Zendrop boundary;
- backed-up production cutover with retained rollback container and database backup;
- localhost-only service binding and runtime hardening;
- removal of the one-time cutover workflow after completion;
- later revenue plan retaining storefront, checkout, fulfillment, unit-economics, and content blockers.

**Classification:** Mixed. Backend/agent cutover has historical production evidence; public-store revenue readiness remains unverified.  
**Why it exists:** First primary cash-flow vertical.  
**Critical gap:** Full customer journey, checkout, fulfillment, supplier mapping, legal copy, catalog accuracy, margin, analytics, and live order evidence.

### 7.14 KDP publishing

Verified repository evidence includes a partial title inventory and Stage 7 operating contract. The recorded titles include `Shadow Hearts` and `Rising Above the Storms: A Road to Mental Wellness`, observed as live paperbacks at $14.99, while explicitly not proving complete account coverage, rights, proofs, sales, royalties, or profit.

**Classification:** In Progress  
**Why it exists:** Second primary Wave 1 revenue vertical.  
**Critical gap:** Canonical title registry, rights package, source files, metadata, proof approval, pricing rationale, royalty exports, sales reconciliation, and marketing funnel.

### 7.15 Market intelligence and analytics

Verified capabilities include:

- external-estimate adapter;
- `EXTERNAL_ESTIMATED` evidence classification;
- sensitive-data rejection;
- storefront growth-audit builder;
- policy to monetize analysis rather than raw identifiable records;
- Similarweb trial capture readiness without prohibited scraping;
- target manifest, metric manifest, evidence hashes, duplicate rejection, and daily completeness reporting;
- explicit separation between estimated signals and verified revenue.

**Classification:** Ready for governed data capture and draft analysis; commercial service In Progress.  
**Critical gap:** Approved pricing, real licensed data capture, pilot customer, delivery process, and posted revenue.

### 7.16 Revenue operating architecture

The Stage 7 revenue manifesto establishes:

1. Wix commerce and fulfillment;
2. KDP publishing;
3. analytics services as shadow support and next cash engine.

The plan limits each wave to two primary revenue verticals and does not treat a large strategic outcome as a forecast or guarantee.

**Classification:** Ready as governance and strategy; live revenue activation not proven.  
**Why it exists:** To prevent the ecosystem from spreading execution across too many verticals before cash flow is verified.

### 7.17 Legal and Juris boundary

Verified operational evidence shows:

- governed legal-evidence policy;
- legal hold behavior;
- Juris service and trust-case recovery workflows;
- strict one-time private artifact handling;
- no trust contents committed to Git;
- exact-path, size, and SHA-256 checks;
- prior observation that a Juris service was active while assumed API routes returned errors.

**Classification:** Needs Work  
**Critical gap:** Current API contract, health endpoint, service ownership, case lifecycle, source-of-truth boundary, legal review status, and verified recovery procedures.

### 7.18 Trading systems

Repository workflows and prior architecture reference Alpha Engine and trading-bot audits. The governance foundation prohibits live money movement without explicit gates.

**Classification:** Planned / shadow unless fresh evidence proves otherwise.  
**Required boundary:** No live-trading claim is permitted without brokerage/exchange connection evidence, paper-performance history, risk controls, legal review, operator authorization, and reconciled transactions.

### 7.19 Surplus vertical

A surplus-service workflow exists in the repository workflow estate, but the current GitHub-side audit does not prove a complete production pipeline.

**Classification:** In Progress / Needs Work  
**Required evidence:** Data sources, legal basis, claimant workflow, document generation, contact approvals, payment handling, case management, success metrics, and production health.

## 8. Security and Reliability Assessment

### Proven strengths

- default deny;
- exact-SHA production authorization;
- protected production environment;
- secret-free Git history boundary;
- least-privilege validation workflows;
- fail-closed behavior;
- explicit legal and security vetoes;
- rollback and drift quarantine;
- exact container ownership checks;
- authenticated localhost-first exposure;
- redacted diagnostics;
- evidence mirroring to GitHub issues;
- explicit prohibition on unsupported revenue claims.

### Material weaknesses

- large and partially classified workflow estate;
- incomplete current runtime inventory;
- historical container-name and local-drift problems;
- service ownership registry contains unresolved fields;
- no verified complete n8n inventory;
- no verified complete agent/tool inventory;
- mixed states across code readiness, deployment readiness, and revenue readiness;
- incomplete backup/restore objectives per service;
- incomplete customer-journey and financial reconciliation evidence;
- potential documentation drift between GitHub, VM, Obsidian, and external platforms.

## 9. Readiness Scorecard

Scores reflect repository evidence and are not a substitute for fresh runtime verification.

| Area | Score | Assessment |
|---|---:|---|
| Governance | 9/10 | Strong constitutional, default-deny, council, legal, incident, and validation foundation. |
| Deployment safety | 8/10 | Strong exact-SHA, rollback, quarantine, and identity controls; operational complexity remains high. |
| Repository engineering | 8/10 | Good PR traceability and validators; workflow estate needs consolidation. |
| Runtime observability | 6/10 | Deep audit workflow exists, but a fresh canonical runtime report is still required. |
| Agent governance | 7/10 | Strong contracts and cohort controls; complete inventory and ownership are unresolved. |
| Security | 7/10 | Strong boundaries and secret handling; full threat model and recovery testing remain incomplete. |
| Institutional memory | 6/10 | Obsidian architecture is strong; synchronization and freshness proof are incomplete. |
| Content production | 6/10 | Campaign engine is built; publishing, analytics feedback, and media worker integration remain incomplete. |
| Clone/video platform | 6/10 | Control plane and worker contract are strong; premium neural output is not proven. |
| Wix revenue readiness | 5/10 | Hardened backend exists; complete live commerce evidence remains missing. |
| KDP revenue readiness | 4/10 | Partial inventory exists; rights, royalty, proof, and funnel evidence are incomplete. |
| Analytics revenue readiness | 5/10 | Product and controls exist; licensed data, pricing, pilot, and sales are missing. |
| n8n automation | 4/10 | Known strategic layer, but production export and execution evidence are missing. |
| Backup and disaster recovery | 6/10 | Deployment rollback is strong; service-level RPO/RTO and restore drills are incomplete. |
| Overall enterprise readiness | 6/10 | Strong governed foundation; not yet a fully reconciled, revenue-proven enterprise system. |

## 10. Highest-Priority Gap Register

### P0 — Must be completed before broad activation

1. Generate and preserve a fresh Production Ecosystem Audit report.
2. Reconcile every VM service against the service ownership registry.
3. Produce a complete GitHub Actions registry and retire obsolete or duplicate workflows.
4. Export and classify every n8n workflow.
5. Complete the agent and tool registry with evidence-backed counts.
6. Assign one accountable owner and one rollback/recovery reference to each active service.
7. Define and test service-level backup, restore, RPO, and RTO expectations.
8. Verify public endpoints, authentication, DNS, Caddy routes, certificates, and health checks.
9. Record the exact currently deployed SHA for every production stack.
10. Build a revenue evidence ledger covering sales, fees, refunds, fulfillment, royalties, and margins.

### P1 — Required for Wave 1 success

1. Complete Wix customer-journey and fulfillment certification.
2. Complete canonical KDP title, rights, metadata, pricing, proof, and royalty inventory.
3. Connect the content engine to governed approval and publishing workflows.
4. Establish attribution from content to qualified traffic, checkout, sale, and margin.
5. Finish Video Studio neural worker selection and license review.
6. Establish an operational dashboard for health, revenue, incidents, and pending approvals.

### P2 — Scale preparation

1. Consolidate duplicate services, agents, and workflows.
2. Establish vertical P&L and shared-infrastructure cost allocation.
3. Add capacity planning, SLOs, alert routing, and error budgets.
4. Add vendor and third-party dependency register.
5. Add privacy, retention, consent, legal, and data-processing maps per vertical.
6. Create partner, investor, and government-contract editions derived from this canonical blueprint.

## 11. Target Enterprise Architecture

The target architecture is:

**Human Overseer**  
→ **Five Council and constitutional controls**  
→ **Governor and evidence ledger**  
→ **Coordinator / Conductor**  
→ **specialized agents and workflows**  
→ **services and verticals**  
→ **verified outputs, revenue, and audit records**

Cross-cutting systems:

- GitHub: versioned control source;
- Foundation VM: runtime ground truth;
- Obsidian Dominion Brain: governed institutional memory;
- n8n: workflow orchestration;
- Caddy: authenticated edge and routing;
- Docker Compose: service packaging and recovery unit;
- evidence ledgers and audit artifacts: truth and accountability layer.

## 12. White Paper — Executive Narrative

Dominion is a human-sovereign AI operating ecosystem designed to build cash flow, systematize execution, and scale only after evidence supports expansion. Unlike conventional automation stacks that connect tools without a common authority model, Dominion begins with constitutional governance, default-deny permissions, independent review, evidence classification, and reversible deployment.

The system unifies AI agents, workflows, cloud infrastructure, publishing, commerce, market intelligence, content generation, and consent-based media production under one operating doctrine. GitHub preserves the approved system definition. The Foundation VM provides runtime truth. Obsidian preserves institutional memory. The Governor, Council, evidence ledger, deployment gates, and service ownership registry provide control and accountability.

Dominion's near-term business strategy is deliberately narrow: establish verified cash flow through the Wix Store and KDP publishing, use governed content to create traffic, and develop analytics services as the next cash engine. Larger verticals—surplus, legal operations, trading, data collaboration, and government work—must inherit the same evidence, security, ownership, and readiness standards before activation.

The central value of Dominion is not merely automation. It is controlled compounding: every successful capability becomes a reusable service, every failure becomes a documented control improvement, every agent operates inside explicit authority, and every revenue claim must reconcile to evidence. This design protects the Founder’s final authority while allowing the system to become more capable, reliable, and scalable over time.

## 13. Definition of Done

No component is complete until it is:

- built;
- tested;
- security reviewed;
- verified with evidence;
- assigned an owner;
- assigned a lifecycle state;
- documented in the blueprint;
- connected to monitoring;
- given a recovery method;
- linked to dependencies and dependents;
- governed for consequential actions;
- measured against success criteria.

## 14. Living-Document Control

Every blueprint change must record:

- version;
- date;
- author or responsible agent;
- affected components;
- evidence references;
- reason for change;
- risk and impact;
- rollback or correction path;
- last verified date.

The blueprint must never silently convert assumptions into facts. Unverified claims remain explicitly marked.

## 15. Current Conclusion

Dominion has a stronger governance and deployment foundation than a typical early-stage AI ecosystem. The repository proves substantial work in constitutional controls, deterministic validation, rollback-safe deployment, governed revenue architecture, content generation, market intelligence, commerce hardening, and a modular Video Studio.

The main remaining problem is not absence of capability. It is reconciliation and completion: proving the current runtime, inventorying every workflow and agent, assigning ownership, consolidating duplicates, finishing customer-facing revenue paths, and connecting operational activity to posted financial evidence.

The correct next move is not to add more uncontrolled verticals. It is to finish the canonical inventory, close the P0 gaps, certify Wave 1, and only then scale.
