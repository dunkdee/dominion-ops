# Dominion System Alignment Contract v1

Status: PROPOSED / NOT YET MERGED
Authority model: RADAH MEMSHALAH
Purpose: make every Dominion component understand its function, authority, dependencies, source-of-truth, handoffs, evidence requirements, and stop conditions without creating a second brain or parallel control plane.

## 1. Governing invariant

Dominion is one governed system with many specialized lanes. No component may become an independent authority, scheduler, memory system, governance plane, or source-of-truth.

Canonical operating loop:

`Signal -> Offer -> Content -> Conversion -> Receipt -> Refine`

Canonical execution loop for every consequential change:

`evidence -> authority -> dependency check -> implementation -> tests -> security/governance validation -> deployment -> runtime verification -> receipt -> measurement -> source-of-truth update -> closure`

A lane is not DONE until the full execution loop closes.

## 2. Source-of-truth precedence

1. GitHub: versioned law, code, schemas, workflows, release policy, approved configuration descriptors.
2. Foundation VM/runtime: live service/runtime truth.
3. Publisher/runtime databases and immutable receipts: publication/job/account state.
4. Commerce/platform providers: provider-native order, traffic, account, and publication evidence.
5. Command Center: operator view of canonical state; never an independent truth producer.
6. Obsidian / Dominion-Brain: operational memory and coordination layer synchronized from verified truth; never permitted to overrule GitHub/runtime evidence.

Conflict rule: if sources disagree, classify state as HOLD/UNKNOWN until reconciled. Never silently choose the more favorable state.

## 3. Core component functions

### Founder / Human Overseer
- Defines mission, scope, priorities, and consequential authority.
- Authorizes exact release scope before Five Council final review where required.
- May revoke or emergency-stop activity.
- Does not bypass law/security vetoes or required fail-closed controls.

### Five Council
- Final affirmative governance gate for consequential releases governed by policy.
- Independent review domains: Truth & Evidence; Law & Governance; Security & Risk; Engineering & Reliability; Business Value & Human Impact.
- Missing review, HOLD, VETO, DENY, stale release binding, or changed release scope blocks release.

### Conductor / orchestration layer
- Routes bounded work to the correct governed capability.
- Owns orchestration, not specialist domain truth.
- Must not create a competing scheduler, memory authority, or governance system.

### Buddy / operator interface
- Converts Founder intent into governed plans and authorized capability calls.
- Reports evidence-backed state and failures.
- Must route through canonical capabilities rather than duplicate them.

### Dominion Brain / Obsidian
- Stores verified operational context, current priorities, blockers, receipts, lessons, and coordination state.
- Synchronizes from canonical evidence.
- Must mark stale/unknown state explicitly and never fabricate live status.

### Command Center
- Phone-first control and observability surface.
- Shows canonical queue state, service health, approvals, receipts, blockers, traffic/revenue, and stop controls.
- Must consume existing canonical state rather than maintain a parallel operational database unless explicitly designated and reconciled.

### Dominion Publisher
- Single canonical publishing control plane.
- Owns approved campaign intake, normalized jobs, platform adapters, queue/retries, account health, immutable publication receipts, attribution, and publishing analytics.
- Does not replace storefront commerce.
- Does not permit account binding or publication outside Founder/governance controls.

### Content Engine / creative agents
- Generate governed campaign packages and platform-native variants.
- Must preserve campaign identity, provenance, rights, claims checks, CTA/destination, and attribution data.
- Do not publish directly around Publisher.

### VoltEdge / Wix commerce boundary
- Commerce destination, catalog, checkout/order, and provider-native commerce evidence.
- Does not own social publishing orchestration.
- Current fulfillment mutation remains governed separately and must stay fail-closed unless explicitly released.

### n8n / mission workflows
- Executes bounded automation steps under an explicit mission objective.
- Each workflow must have owner, trigger, inputs, outputs, dependencies, evidence, retry policy, rollback/containment, and lifecycle state.
- Status-only workflow sprawl is to be consolidated into mission pipelines rather than multiplied.

### Alchemist / Juris / specialist intelligence agents
- Produce domain-specific evidence and recommendations within bounded authority.
- Cannot self-promote uncertain claims into trusted truth.
- Must preserve provenance and route consequential external actions through governance.

### Orion / Alpha trading lane
- Separate governed market-intelligence/paper-trading mission lane.
- Paper-only unless an independent consequential live-money release is authorized.
- Must not distract from higher-priority production/revenue closure while queued behind them.

## 4. Canonical mission pipelines

### Pipeline A — Production release
`requirement -> exact scope -> dependency/regression assessment -> implementation branch/PR -> tests -> security/governance checks -> Founder scope authorization -> Five Council final review when consequential -> merge -> deployment -> runtime health -> receipt -> Command Center/Brain sync -> closure`

### Pipeline B — Traffic and revenue
`market/traffic signal -> governed offer -> Content Engine -> approval/provenance -> Publisher queue -> official platform adapter -> immutable post receipt -> UTM attributed VoltEdge visit -> cart/checkout/order/revenue evidence -> analytics -> refine/scale/stop decision -> Brain/Command Center update`

### Pipeline C — Platform account binding
`configured app -> protected credentials -> governed consent -> provider callback/token proof -> read-only candidate enumeration -> Founder account selection -> bind -> health proves token + bound account -> receipt -> Brain/Command Center sync`

### Pipeline D — Commerce
`catalog truth -> storefront trust/conversion state -> attributed visitor -> checkout -> provider order receipt -> governed downstream action -> revenue evidence -> analytics -> refinement`

### Pipeline E — Knowledge/research
`question -> source discovery -> provenance/evidence grading -> contradiction check -> bounded conclusion -> specialist receipt -> validated promotion -> Brain update`

### Pipeline F — Paper trading
`market data -> signal -> risk/governance check -> paper decision -> simulated execution -> outcome -> performance evidence -> lesson -> Brain/Command Center sync`

## 5. Current priority alignment

Priority 0: preserve one-brain governance and source-of-truth convergence.

Priority 1: close Publisher/Meta release and runtime chain.
- PR #277 remains a security-hardening release until governance permits merge.
- After merge: controlled Meta consent/token/account binding.
- Then: one approved Publisher canary with immutable receipt.

Priority 2: prove Publisher -> Command Center/Obsidian -> attributed VoltEdge traffic/revenue chain under Issue #260.

Priority 3: consolidate operational workflow sprawl under Issue #199 into mission pipelines with explicit objectives, receipts, rollback, and holds.

Priority 4: reconcile enterprise inventory under Issue #81 using current runtime evidence. Do not treat repository presence as proof of production state.

Priority 5: storefront/commerce conversion hardening and current Wix contracts without prematurely enabling fulfillment mutation.

Priority 6: queued specialist/trading expansion only after higher-priority production/revenue closure.

## 6. Required machine-readable registry fields

Every active component and mission must eventually expose or map to:
- unique_id
- name
- role
- authority_class
- owner
- lifecycle_state: DONE | IN_PROGRESS | BLOCKED | UNKNOWN | PARKED
- source_of_truth
- code_or_runtime_location
- inputs
- outputs
- dependencies
- dependents
- auth_boundary
- read_write_destructive_classification
- health_check
- evidence_receipt_type
- retry_policy
- rollback_or_containment
- command_center_surface
- obsidian_home
- last_verified_at
- exact_release_sha_or_version
- current_blocker
- next_action

## 7. Alignment rules

- No direct platform publishing outside canonical Publisher once that adapter is integrated.
- No duplicate scheduler for a mission already owned by Publisher, Conductor, n8n, systemd, or another designated canonical scheduler.
- No duplicate memory authority beside Dominion Brain/approved canonical stores.
- No UI status may claim LIVE/HEALTHY/DONE from static config alone.
- No component may infer another component's success from its own local success.
- Every external side effect must have an attributable actor, approved scope where required, and resulting receipt.
- Every receipt must be consumable by the Command Center/Brain synchronization path.
- Every failed handoff becomes BLOCKED/UNKNOWN with an explicit recovery path.
- Retire or quarantine duplicate/stale components only after dependency evidence proves they are unused and rollback is available.

## 8. Acceptance criteria for system alignment

System alignment is VERIFIED only when:
- all production components have one declared role and owner;
- every component has a source-of-truth and dependency map;
- duplicate authorities/schedulers/memory paths are identified and have a disposition;
- Command Center and Obsidian display the same canonical states as GitHub/runtime/provider receipts;
- active mission workflows map to explicit pipelines instead of disconnected status checks;
- Meta/Publisher canary produces a real publication receipt and attributed destination link;
- revenue telemetry reports measured truth, including zero when no order occurs;
- CI/governance checks protect the architecture and fail closed on drift;
- unresolved contradictions are BLOCKED/UNKNOWN rather than cosmetically marked complete;
- the final active release SHA and runtime evidence are recorded.

## 9. Non-goals

This contract does not authorize:
- direct merge to main;
- production deployment;
- account binding;
- external publication;
- live trading;
- money movement;
- credential exposure;
- Wix fulfillment activation;
- new paid infrastructure;
- replacement of existing canonical subsystems without separate regression/dependency proof.

## 10. Immediate execution sequence

1. Finish PR #277 governance/release path without scope expansion.
2. Close Meta account-binding runtime proof.
3. Publish one governed canary through Dominion Publisher and retain receipt.
4. Verify that receipt is visible through canonical Command Center/Obsidian state.
5. Verify attribution into VoltEdge and record measured traffic/conversion/revenue truth.
6. Inventory active workflows/components against this contract and mark duplicate, stale, missing-owner, and missing-receipt paths.
7. Consolidate those paths under Issue #199 and update Issue #81 enterprise inventory.
8. Only then advance parked tool additions or lower-priority expansion lanes.
