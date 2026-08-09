# Dominion-Brain Obsidian Layout

This is the operational mirror layout defined by the Dominion operating map. GitHub remains authoritative for policy/code; Obsidian mirrors reviewed knowledge for daily operations.

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

## Agent home contract

Every registered agent receives:

```text
04-Agents/<agent-id>/
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

Each home must link back to:

- `governance/SYSTEM_CONSTITUTION.md`
- `governance/DOMINION_OPERATING_MAP.md`
- `governance/authority_matrix.json`
- `agents/registry.json`
- current runtime evidence
- applicable vertical contracts/runbooks

## Sync rules

1. GitHub → Obsidian is one-way for normative policy/code/contracts.
2. Obsidian may hold working notes, decisions, incident notes, daily state, and human coordination.
3. Any durable lesson or policy change must return to GitHub through review before becoming authoritative.
4. Never mirror `.env`, credentials, raw customer records, secret-bearing logs, private keys, tokens, or sensitive screenshots.
5. Live service status must be tagged with evidence timestamp and source; stale status must not be presented as current truth.
6. Activation of Obsidian automation remains blocked until the current Stage 2F-W1 Wix gate passes. This file prepares structure only.
