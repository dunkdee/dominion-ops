# Dominion Incident Response

## Trigger

Open an incident for any mistake, failure, near miss, policy violation, knowledge defect, reasoning defect, security event, unexplained drift, unsupported completion claim, or unauthorized action.

## Immediate sequence

1. Stop or isolate the affected automation when safe.
2. Preserve logs, workflow identifiers, commits, inputs, outputs, model and prompt versions, tool calls, and timestamps.
3. Protect secrets and private data; record references or hashes rather than copying sensitive values.
4. Determine blast radius and whether customers, money, production, legal obligations, or credentials are affected.
5. Escalate according to severity and the authority matrix.
6. Verify containment independently.

## Analysis

The owner must distinguish:

- direct root cause;
- contributing conditions;
- detection gap;
- policy or permission gap;
- knowledge-source defect;
- reasoning defect;
- test gap;
- observability gap; and
- recovery or rollback weakness.

Do not use “human error” or “AI hallucination” as the final root cause. Identify the control that allowed the error to escape.

## Closure

An incident may close only after:

- evidence is preserved;
- root cause is recorded;
- corrective and preventive controls are approved;
- code, policy, prompt, permission, runbook, or monitoring changes are versioned;
- regression tests pass;
- production verification passes where applicable;
- recurrence monitoring is active; and
- unresolved risk is either removed or explicitly accepted by the Human Overseer.

Recurrence reopens the incident family and increases control priority.
