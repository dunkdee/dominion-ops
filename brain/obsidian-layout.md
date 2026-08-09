# Dominion-Brain Obsidian Layout

This is the governed operational mirror layout defined by the Dominion operating map. GitHub remains authoritative for policy/code; Obsidian mirrors reviewed knowledge for daily operations. Runtime truth still requires current live evidence.

```text
Vault root/
├── Dominion-Brain/                  # reviewed generated mirror
│   ├── 00-Constitution/
│   ├── 01-Founder-Authority/
│   ├── 02-Five-Council/
│   ├── 03-Control-Plane/
│   ├── 04-Agents/
│   ├── 05-Verticals/
│   ├── 06-Operations/
│   ├── 07-Incidents/
│   ├── 08-Evidence/
│   ├── 09-Revenue/
│   ├── 10-Architecture/
│   ├── 11-SOPs/
│   ├── 12-Decisions/
│   ├── 13-Learning/
│   ├── 14-Daily-State/
│   └── 99-Archive/
└── Dominion-Operator-Notes/         # preserved human/runtime notes
    └── <agent-id>/
        ├── 08-Incidents-and-Lessons.md
        ├── 09-Current-State.md
        └── 10-Change-Log.md
```

## Agent home contract

Every registered agent receives these 11 files in the generated `Dominion-Brain/04-Agents/<agent-id>/` home:

```text
00-Identity.md
01-Mission.md
02-Authority.md
03-Inputs.md
04-Outputs.md
05-Dependencies.md
06-SOPs.md
07-Health-and-Metrics.md
08-Incidents-and-Lessons.md
09-Current-State.md
10-Change-Log.md
```

The first eight are governed generated knowledge. The final three are generated bridge notes that point to the corresponding preserved file under `Dominion-Operator-Notes/<agent-id>/`; operators do not write durable evidence into generated files.

Each home links to the rendered equivalents of the canonical startup documents: constitution, state, repository README, registry, authority matrix, Five Council policy, incident-learning policy, vertical registry, control-plane contract, applicable runbooks, and current verified runtime evidence.

## Generation and publication rules

1. The renderer writes only to a **fresh staging directory that does not already exist**.
2. A failed render removes its partial staging tree; it never mutates the current operational mirror.
3. The manifest identifies an immutable aggregate SHA-256 of the exact governed source set used for the generation.
4. A separate governed synchronization step validates the manifest and publishes the completed generation to the operational vault.
5. `Dominion-Operator-Notes` is never replaced by the generated mirror and is preserved across refreshes.

## Sync rules

1. GitHub → `Dominion-Brain` is one-way for normative policy/code/contracts.
2. `Dominion-Operator-Notes` may hold sanitized working notes, decisions, incident evidence, daily state, and human coordination.
3. Any durable lesson or policy change must return to GitHub through review before becoming authoritative.
4. Never mirror `.env`, credentials, raw customer records, secret-bearing logs, private keys, tokens, or sensitive screenshots.
5. Live service status must carry an evidence timestamp and source; stale status must not be presented as current truth.
6. Current Obsidian activation state is `UNKNOWN` until fresh runtime verification reconciles the stale historical records. No activation claim may be made solely from the old Wix block or prior healthy-container evidence.