# Buddy Live-Source Reconciliation Work Order

## Determination

Buddy's canonical role and authority policy are defined in this repository, but the live implementation remains under `~/buddy_core` on the Foundation VM and is not reproducibly built from GitHub. Therefore live conformance is `UNVERIFIED`.

This work order moves Buddy toward canonical, reproducible operation without deleting memory, changing credentials, restarting production, or treating a hash as proof of behavioral correctness.

## Phase 1 — Read-only inventory

1. Record every source, configuration, prompt, skill, service-unit, and dependency path used by the Buddy services.
2. Record file size, mode, modification time, and SHA-256. Do not print file contents, environment values, tokens, private data, conversation memory, or customer data.
3. Record `ExecStart`, `WorkingDirectory`, user, environment-file paths, restart policy, listeners, routes, health endpoints, and recent restart counts for:
   - `dominion-buddy-web.service`
   - `dominion-proposal-queue.service`
   - `dominion-sentinel.service`
4. Identify which files are source code versus runtime data, memory, logs, credentials, caches, or generated artifacts.
5. Report and stop. No copy, edit, restart, or deployment is authorized by Phase 1.

## Phase 2 — Sanitized source staging

Requires a separate Founder authorization after Phase 1 review.

1. Copy source code only into a temporary staging directory.
2. Run secret, private-data, and generated-artifact scans.
3. Exclude `.env`, tokens, keys, databases, logs, raw memories, user conversations, backups, caches, and customer information.
4. Preserve a manifest linking staged source files to their observed VM hashes.
5. Run syntax checks and existing tests without using production credentials or external actions.
6. Report and stop before committing anything.

## Phase 3 — Canonical source and policy integration

Requires a reviewed pull request.

1. Import sanitized Buddy source under a canonical repository path.
2. Add an authorization adapter that validates direct Founder instructions and standing Founder policies against `buddy_authority_policy.json`.
3. Separate Founder-confirmed preferences, observed patterns, and agent inference in the memory model.
4. Implement bounded self-repair with the policy allowlist, two-attempt limit, cooldown, independent Sentinel evidence, and `BLOCKED` exhaustion state.
5. Require append-only authorization and action receipts with secret redaction.
6. Add tests proving that Buddy cannot infer authorization, expand his repair scope, claim the Founder's legal identity, or mark VM-only source as verified.

## Phase 4 — Shadow acceptance

1. Build an immutable candidate from the reviewed commit.
2. Run it on loopback or an isolated port with copied non-sensitive fixtures.
3. Test direct instructions, standing-policy scope, delegation, memory classification, repair success, repair exhaustion, authorization refusal, and rollback.
4. Compare outputs against the live service without allowing the candidate to perform external actions.
5. Record failures and repeat in a new reviewed change; do not patch the live source inline.

## Phase 5 — Governed promotion

Requires explicit Founder GO after shadow acceptance.

1. Back up the live source and service definitions.
2. Deploy the exact reviewed commit through an immutable release directory.
3. Restart only the three allowlisted Buddy services.
4. Verify process, bind, health contract, authentication, logs, restart count, public route behavior, and rollback.
5. Generate a deployment receipt containing the commit, source manifest hash, policy hash, service results, and rollback location.
6. Only then change `live_conformance.status` from `UNVERIFIED` to `VERIFIED` in a reviewed pull request.

## Stop conditions

- Any secret or private data appears in staged source or output.
- The live service uses an unrecorded source path or dependency.
- A required service has duplicate ownership.
- Tests require production credentials or external side effects.
- Rollback material is incomplete.
- Source or policy hashes do not match the reviewed release.

No phase may infer success from Buddy's own response string. Runtime conformance requires independent evidence.
