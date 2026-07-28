# Dominion Elite Skill Architecture

The advantage comes from composable skills, not giant prompts. Each skill has a clear input contract, tool boundary, quality gate, and learning loop.

## Skill tiers

### Tier 0 — Governance Core

These skills are always active.

- **Intent Lock** — restates the actual objective, deadline, constraints, and success metric before work begins.
- **Authority Gate** — blocks publishing, spending, production changes, customer claims, legal actions, and irreversible operations without human approval.
- **Cost Guard** — prefers free, open-source, or already-owned resources and rejects hidden paid dependencies.
- **Truth Guard** — separates verified facts, assumptions, estimates, and recommendations.
- **Drift Detector** — compares current work against Dominion doctrine, active priorities, and the requested deliverable.

### Tier 1 — Intelligence Skills

- **Deep Research** — builds a source-backed answer from primary or authoritative sources.
- **Competitive Intelligence** — maps competitors, offers, positioning, traffic channels, gaps, and exploitable weaknesses.
- **Demand Mining** — identifies urgent audience pain, high-intent questions, repeated objections, and underserved topics.
- **Trend Detection** — distinguishes durable demand from temporary noise.
- **Opportunity Scoring** — ranks ideas by speed to cash, margin, difficulty, defensibility, and fit with existing assets.
- **Repository Intelligence** — uses Metatron to retrieve architecture decisions, prior failures, conventions, and trusted patterns.

### Tier 2 — Strategy Skills

- **Offer Engineering** — turns capabilities into a clear offer with audience, outcome, mechanism, proof, price logic, objections, and CTA.
- **Campaign Architecture** — converts one objective into a full funnel and distribution plan.
- **Content Pillar Design** — creates repeatable topic systems instead of random posting.
- **Channel Selection** — chooses channels by audience intent, format fit, speed, cost, and conversion path.
- **Growth Loop Design** — makes each customer, post, lead, or result feed the next cycle.
- **Scale Readiness** — checks whether a workflow can be repeated, delegated, measured, and automated.

### Tier 3 — Traffic Skills

- **Hook Engineering** — produces hooks based on curiosity, pain, proof, contrast, identity, urgency, and specificity.
- **Search Capture** — targets high-intent keywords, questions, metadata, and on-page structure.
- **Social Packaging** — adapts one idea into native TikTok, Reels, Shorts, Facebook, X, LinkedIn, and YouTube formats.
- **Content Repurposing** — converts one source asset into clips, posts, emails, threads, articles, lead magnets, and scripts.
- **Distribution Sequencing** — decides what posts first, what follows, and how each asset points to the next step.
- **Engagement Mining** — converts comments, questions, and objections into future content and offers.
- **Viral Quality Check** — scores clarity, emotional pull, novelty, retention, shareability, and CTA strength without guaranteeing virality.

### Tier 4 — Brand Skills

- **Voice Lock** — keeps language direct, grounded, authoritative, practical, and recognizably Dominion.
- **Positioning** — defines who the brand serves, what it stands against, and why it is different.
- **Message Hierarchy** — keeps mission, promise, proof, mechanism, and CTA consistent across channels.
- **Visual Direction** — specifies layout, typography, imagery, tone, and asset consistency.
- **Trust Building** — strengthens proof, transparency, credibility, and expectation setting.
- **Brand Drift Review** — rejects generic, contradictory, overhyped, or off-mission output.

### Tier 5 — Conversion Skills

- **Landing Page Conversion** — improves headline, offer clarity, proof, objection handling, CTA, and friction.
- **Sales Copy** — writes persuasive copy without fabricated proof or deceptive urgency.
- **Lead Magnet Design** — creates valuable assets that naturally move users to the offer.
- **Email Sequence Design** — builds welcome, nurture, launch, reactivation, and follow-up sequences.
- **Funnel Diagnosis** — identifies where attention, trust, intent, or conversion is being lost.
- **Experiment Design** — defines one variable, one hypothesis, one metric, and a decision rule.

### Tier 6 — Production Skills

- **Workflow Builder** — designs n8n, API, queue, storage, and notification flows with rollback and observability.
- **Coding Agent** — plans, edits, tests, documents, and submits minimal behavior-preserving changes.
- **Automation Hardening** — adds retries, idempotency, rate limits, secrets hygiene, logging, and failure recovery.
- **Asset Generator** — produces scripts, briefs, page copy, campaign assets, templates, and structured data.
- **Deployment Verification** — checks service health, authentication, public reachability, logs, rollback, and post-deploy state.
- **Documentation Builder** — creates operator-ready instructions, runbooks, contracts, and handoff notes.

### Tier 7 — Evaluation Skills

Every major output must pass these independent checks.

- **Accuracy Critic** — verifies claims and flags uncertainty.
- **Brand Critic** — checks voice, positioning, and message consistency.
- **Conversion Critic** — checks whether the audience understands why to act now.
- **Operator Critic** — checks whether the output is executable with current tools and access.
- **Scalability Critic** — checks repeatability, automation potential, bottlenecks, and unit economics.
- **Red Team** — finds failure modes, security issues, compliance risks, and misleading claims.

## Skill execution contract

Each skill must declare:

```yaml
skill_name: ""
purpose: ""
required_inputs: []
optional_inputs: []
allowed_tools: []
forbidden_actions: []
output_schema: {}
quality_checks: []
human_gate: false
learning_fields:
  result: ""
  metric_change: ""
  failure_reason: ""
  reusable_lesson: ""
```

## Routing policy

1. Start with the smallest set of skills required.
2. Retrieve Metatron context before planning or editing a known repository.
3. Run intelligence before strategy when facts or market conditions matter.
4. Run strategy before production for campaigns, offers, funnels, and major builds.
5. Run at least one independent critic before human review.
6. Publish only after the required human gate.
7. Store only durable, verified lessons as Metatron candidates.

## Edge-building upgrades

- Use multi-pass work: generate, critique, revise, verify.
- Separate planner and critic roles to reduce self-approval bias.
- Preserve structured inputs and outputs so any model can replace another.
- Track skill-level results instead of judging whole agents vaguely.
- Promote skills based on measured outcomes, not model reputation.
- Maintain fallback implementations for critical skills.
- Build channel adapters once and reuse them across every vertical.
- Turn failures into test cases and Metatron decision candidates.

## Initial priority stack

For immediate Dominion growth, activate these first:

1. Demand Mining
2. Opportunity Scoring
3. Offer Engineering
4. Hook Engineering
5. Content Repurposing
6. Social Packaging
7. Landing Page Conversion
8. Workflow Builder
9. Accuracy Critic
10. Brand Critic
11. Conversion Critic
12. Metatron Learning

This stack supports speed, traffic, branding, conversion, and scale without creating uncontrolled agent sprawl.
