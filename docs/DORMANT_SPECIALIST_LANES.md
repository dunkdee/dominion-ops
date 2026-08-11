# Dominion Dormant Specialist Lanes

## Status

This document and its machine-readable companion establish **contracts only**. They do not start services, grant credentials, change budgets, publish, contact anyone, process payments, deploy production changes, or enable trading.

The binding lane registry is `governance/specialist_lane_contracts.json`. Its deterministic guard is `scripts/validate_specialist_lane_contracts.py`.

## Operating model

Dominion is one enterprise family with one mission, one evidence standard, shared operational memory, and Founder final authority. Multiple lanes may prepare work in parallel only after a bounded mission is approved and their writes do not conflict.

Every lane begins:

- lifecycle: `REGISTERED`
- activation: `DORMANT`
- budget: `$0`
- routing owner: `coordinator`
- independent verifier: `sentinel`
- protected-action gate: recorded approval by `human_overseer`

No lane can self-activate, grant itself tools, expand a budget, or treat model output as authorization.

## Lane roster

| Lane | Internal purpose | Never autonomous |
|---|---|---|
| Research & strategy | Source-grounded strategy and problem framing | External research action beyond permitted sources, publication, customer contact |
| Content & distribution | Accurate useful drafts and approved measurement plans | Publishing, deceptive platform manipulation, health/legal/income claims |
| Operations & customer support | Internal SOP, triage, and response drafts | Sending messages, mutating customer records, handling protected data |
| Revenue & lead workflow | Ethical qualification and offer drafts | Contacting prospects, submitting offers, pricing commitments, payments |
| Security & quality verification | Independent evidence/test/safety challenge | Approving its own proposal, weakening a hold, production changes |

The contract treats audience reach as a quality-and-measurement problem, not an algorithm-gaming problem. Real-world benefit, accuracy, accessibility, trust, and measured outcomes take priority over vanity metrics.

## Shared-memory interface

GitHub is authoritative for versioned law, policy, contracts, and code. Obsidian is the operational coordination layer. Runtime evidence remains authoritative for live state.

Every lane must use these Obsidian destinations:

- agent home: `Dominion-Brain/04-Agents/<lane>/`
- evidence: `Dominion-Brain/08-Evidence/`
- decisions: `Dominion-Brain/12-Decisions/`
- learning: `Dominion-Brain/13-Learning/`
- current state: `Dominion-Brain/14-Daily-State/`

Each consequential handoff must separate `VERIFIED`, `INFERRED`, `UNKNOWN`, and `BLOCKED`. No secret, credential, private key, customer record, or raw environment data belongs in a packet or note.

## Mission and KPI interface

A lane accepts a mission only with an ID, objective, bounded scope, evidence references, constraints, and approval reference. It returns a truth-labeled result, risks, verification plan, memory references, stop condition, and an explicit human action requirement where applicable.

KPIs are interfaces, not promises. They begin `UNKNOWN` with `BASELINE_REQUIRED`; promotion requires measured evidence, independent verification, and a recorded human decision. Each metric declares a definition, evidence source, truth state, and reporting cadence so a lane cannot claim success from untraceable output.

## Promotion sequence

`REGISTERED → SPEC_REVIEW → SIMULATION → SHADOW → CANARY → LIMITED_PRODUCTION → PRODUCTION`

A movement is blocked until the lane has:

1. a specific bounded mission and evidence packet;
2. a named independent verifier;
3. tests/simulation appropriate to the risk;
4. stop and rollback conditions;
5. recorded governance review; and
6. Founder approval whenever the authority matrix requires it.

Existing holds remain unchanged: TikTok is inactive, Wix is record-only, trading is paper-only, and payments/live trading are off.
