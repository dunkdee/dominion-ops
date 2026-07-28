# Dominion Prompt OS

Dominion Prompt OS is a model-neutral prompt workflow for turning one business objective into fast, reusable, brand-consistent execution across Claude, GPT, Gemini, Copilot, Ollama, and future agents.

## Core loop

1. **Intent intake** — define objective, audience, offer, channel, deadline, constraints, and success metric.
2. **Context retrieval** — Metatron supplies repository decisions, brand rules, prior wins, rejected approaches, and known risks.
3. **Planner** — converts the objective into a compact execution plan with deliverables, dependencies, and the next irreversible action.
4. **Specialist routing** — sends work to the correct lane: traffic, branding, conversion, product, research, engineering, or operations.
5. **Production** — generates the asset, code, campaign, workflow, or content package.
6. **Critic gate** — checks accuracy, originality, brand fit, compliance, conversion strength, and operational readiness.
7. **Human GO** — Dewayne approves publishing, spending, customer-facing claims, infrastructure changes, and irreversible actions.
8. **Distribution** — adapts the approved core asset into channel-native formats.
9. **Measurement** — records output, reach, clicks, leads, sales, failures, and lessons.
10. **Metatron learning** — strong decisions become candidates; only human-reviewed decisions become canonical.

## Non-negotiables

- Cash flow -> systems -> scale.
- Zero fluff and zero invented results.
- One source asset should produce many channel assets.
- Every output must include a clear next action.
- No paid tools or new infrastructure charges without explicit approval.
- Never publish, spend, merge, deploy, email, or modify production without the required human gate.
- Brand voice: direct, grounded, authoritative, healing-centered, practical, and unmistakably Dominion.

## Standard input contract

```yaml
objective: ""
audience: ""
offer: ""
channel: ""
deadline: ""
success_metric: ""
constraints: []
available_assets: []
known_context: []
required_approval: true
```

## Standard output contract

```yaml
strategy:
  objective: ""
  angle: ""
  audience_pain: ""
  promise: ""
execution:
  primary_asset: ""
  derivative_assets: []
  distribution_steps: []
quality_gate:
  factual_risks: []
  brand_risks: []
  conversion_risks: []
measurement:
  leading_metrics: []
  outcome_metrics: []
next_action: ""
human_approval_required: true
```

## Agent roles

- **Governor** — protects doctrine, priorities, cost limits, and human authority.
- **Metatron** — repository memory, conventions, lessons, and decision retrieval.
- **Router** — selects the smallest capable agent and tool chain.
- **Strategist** — builds the campaign or execution plan.
- **Traffic Agent** — hooks, search demand, distribution, repurposing, and growth loops.
- **Brand Agent** — voice, positioning, visual consistency, and trust.
- **Conversion Agent** — offer clarity, proof, objections, CTA, and funnel progression.
- **Builder** — produces code, workflows, pages, automations, and assets.
- **Critic** — rejects weak, unsafe, inaccurate, generic, or off-brand output.
- **Observer** — records results and creates Metatron candidate lessons.

## Scaling rule

Do not create a separate prompt for every small task. Use one master contract, reusable specialist modules, and channel adapters. Store only proven decisions in Metatron so the system becomes faster without becoming noisy.
