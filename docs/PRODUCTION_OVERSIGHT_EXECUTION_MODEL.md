# Production Oversight Execution Model

## Purpose

Dominion operates as a governed AI execution system with the Founder as overseer rather than routine operator. Routine, reversible, internal work should be executed by the system and produce receipts automatically. Founder intervention is reserved for consequential authority gates, destructive operations, external side effects, or unresolved exceptions.

## Operating model

1. **System executes.** Agents, workflows, MCP-connected services, SDKs, APIs, and runtime services perform routine work without requiring the Founder to babysit each step.
2. **Receipts are mandatory.** Every production action must return verifiable evidence such as commit SHA, PR number, workflow run ID, deployment receipt, artifact, hash, health result, or provider receipt.
3. **Validation precedes production closure.** A change is not closed because code exists. It is closed only after the relevant tests, deployment, runtime verification, and evidence pass.
4. **External authority remains governed.** Sending messages, publishing, spending, credential/network mutation, destructive changes, or equivalent consequential actions remain behind the defined Founder authority boundary.
5. **Failures become bounded remediation.** When new evidence exposes a defect, fix only the proven blocker, add regression coverage, redeploy, and resume from the failed gate. Do not reopen already-proven work without new evidence.
6. **Knowledge must be written.** Decisions, changes, failures, fixes, acceptance criteria, and receipts must be captured as durable documentation. GitHub contains execution evidence and implementation records; the Dominion knowledge layer/Obsidian remains the intended canonical knowledge center for synchronized operating knowledge.

## Governed external-message closure loop

- A successful `Deploy Buddy Runtime` automatically triggers `Governed External Message Canary` in **VERIFY ONLY** mode.
- Automatic verification is pinned to the exact SHA reported by the successful deployment workflow.
- Automatic verification cannot send a message.
- `SEND CANARY` remains an explicit Founder-gated manual action and retains the existing actor and triggering-actor checks.
- Canary evidence is uploaded as `governed-message-canary-evidence`.
- Production closure requires the actual evidence chain, not merely a green workflow badge.

## Receipt standard

For each completed production step, retain as applicable:

- objective and scope
- exact commit/release SHA
- PR number and head SHA
- CI/check results
- deployment workflow run ID
- runtime health evidence
- hashes or signed/tamper-evident audit evidence
- external provider receipt when an external action is authorized
- replay/duplicate prevention evidence when required
- unresolved risks or explicit next gate

## Oversight rule

The Founder should receive concise exception-oriented reporting: what completed, the receipt, what failed if anything, and only the next decision that genuinely requires Founder authority. Routine execution should not be pushed back onto the Founder when the system has the capability and authorization to perform it safely.
