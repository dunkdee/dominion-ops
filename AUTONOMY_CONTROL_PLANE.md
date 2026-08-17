# Dominion Autonomy Control Plane

**Authority:** Dewayne Singleton, Founder and final decision-maker  
**Policy:** `automation_control_policy.json`  
**Default:** if evidence, authority, identity, or scope is uncertain, stop and report `BLOCKED`.

## Outcome

Dominion is autonomous for observation, evidence collection, and narrowly bounded recovery. It is not autonomous for publishing, outreach, spending, trading, legal filings, credentials, firewalls, public ingress, quarantined agents, or canonical-state changes. Those actions require explicit Founder authorization for an exact commit.

Autonomy means the system can keep watch, detect faults, recover the approved Buddy services, prove what it did, and stop when the repair boundary is exhausted. It does not mean an agent may silently expand its own authority.

## Definition of online

A component is `VERIFIED_ONLINE` only when current evidence identifies all nine fields:

1. canonical source or reproducible build;
2. accountable owner;
3. running process or unit;
4. expected listening port;
5. intended route and exposure boundary;
6. health contract with the expected response;
7. current logs without an unexplained failure;
8. persistence and restart behavior; and
9. tested rollback or recovery path.

A file existing, a process running, a port listening, or a self-reported `status: ok` is not enough by itself.

## Canonical lanes

### 1. CI validation

Runs on pull requests and selected pushes. It receives no production credentials and cannot mutate production. It validates code, policy, workflow triggers, confirmation gates, and repair scope.

### 2. Runtime observation

`.github/workflows/watchdog.yml` runs on a schedule and by manual request. It may use the VM connection only to read service state, listeners, HTTP health contracts, containment holds, and firewall-rule absence. It may not restart, rebuild, deploy, write configuration, or repair.

An observer failure is evidence, not permission to improvise a fix.

### 3. Buddy bounded self-repair

`.github/workflows/fix-buddy-brains.yml` is repurposed as the bounded self-heal lane and may restart only:

- `dominion-buddy-web.service`
- `dominion-proposal-queue.service`
- `dominion-sentinel.service`

It first observes, then waits for the configured cooldown, performs no more than two failed repair attempts, verifies the runtime again, and opens a circuit when recovery is not proven. It cannot patch source, rebuild containers, touch credentials, change networking, invoke external actions, or restart any other service.

The older `buddy-production-repair.yml` is a temporary legacy exception because live Buddy source is still VM-only and unreconciled. Its scope must not expand. It is removed only after Buddy source is canonical, reproducible, tested outside the live path, deployed by hash, and independently accepted.

### 4. Founder-approved apply

Consequential workflows require a manual dispatch, the exact main-branch commit SHA, a workflow-specific typed confirmation, protected-environment controls where configured, post-change health evidence, and a rollback path. A merge is not an authorization to publish, send, spend, trade, change credentials, open ingress, or activate a held agent.

## State vocabulary

- `VERIFIED_ONLINE` — all required online evidence is current and passes.
- `RUNNING_HEALTH_UNVERIFIED` — a process exists, but the full health contract is not proven.
- `DEGRADED` — useful service remains, but a required capability is impaired.
- `BLOCKED` — work cannot safely proceed without missing evidence or a decision.
- `EXTERNAL_ACTION_HOLD` — the system may operate internally but cannot create the named outside effect.
- `QUARANTINED` — execution is prohibited pending explicit release.
- `RETIRED` — intentionally removed from service and must not be restarted.
- `UNKNOWN` — evidence is missing or conflicting.

Nothing `UNKNOWN`, `QUARANTINED`, `RETIRED`, or `EXTERNAL_ACTION_HOLD` may be started, published, or externally activated by automation.

## Repair rules

1. Observe before changing.
2. Operate only on the exact allowlist.
3. Preserve existing automatic repair for Buddy, but keep it bounded and evidenced.
4. Never substitute a different port, process, service, route, or duplicate instance to make a health check green.
5. Never treat a successful command exit as acceptance evidence by itself.
6. Stop after the attempt limit; do not loop forever.
7. Record the attempted action, before/after state, result, and rollback or remediation.
8. Never print secrets or personal data in workflow output.

## System health versus external authorization

The health board must report these separately:

- **System online:** internal components and approved agent capabilities are healthy.
- **External actions authorized:** the Founder has granted current, scoped authorization for the specific outside effect.

The first does not imply the second.

## Acceptance sequence

1. Merge policy and workflow changes only after CI passes.
2. Run the observer manually and preserve its output.
3. Confirm all known containment holds remain enforced.
4. Run Buddy self-heal once while healthy; it must make no restart.
5. Conduct a controlled failure test for one allowlisted Buddy service, confirm one bounded restart and recovery, then restore the pre-test state.
6. Confirm the circuit breaker blocks a repeated unresolved failure after two attempts.
7. Reconcile Buddy live source before claiming canonical self-evolution or full live conformance.

Until those runtime steps pass, the repository contains the control plane, but production autonomy remains `UNVERIFIED`.
