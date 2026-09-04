# E0-001 Watchmen / Sentinel secure-state migration

Status: **DEPLOYMENT CONDITION — NOT DEPLOY AUTHORITY**

Governance: RADAH MEMSHALAH · Golden Ratio Governance · Five Council · fail closed.

This runbook applies only after the exact release SHA has independent Five Council approval and the Founder authorizes release. It does not authorize merge or deployment by itself.

## Security truth

The historical repository-local Watchmen files and the historical Sentinel fallback log are **LEGACY / NON-AUTHORITATIVE**:

- `buddy_core/watchmen_audit.log`
- `buddy_core/watchmen_chain.json`
- `buddy_core/logs/sentinel_audit.log`

The old Watchmen chain used signing material that was published in repository source. No cryptographic continuity may be claimed between those artifacts and the new secure machine-local chain. The unsigned Sentinel fallback is not governance evidence.

The authoritative post-migration state is machine-local, outside the checkout:

- `~/.dominion/watchmen/watchmen_audit.log`
- `~/.dominion/watchmen/watchmen_chain.json`
- `~/.dominion/watchmen/watchmen_hmac.key`

or the explicitly approved `DOMINION_WATCHMEN_STATE_DIR` equivalent.

## Pre-deploy evidence

Before any runtime mutation:

1. Record exact merged release SHA and exact VM repository SHA.
2. Confirm the VM working tree is clean or stop.
3. Capture service state for Sentinel and dependent services.
4. Back up existing legacy artifacts, if present, to a timestamped location outside the Git checkout.
5. Record hashes, timestamps, ownership, and permissions of any discovered legacy artifacts.
6. Label the backup record `LEGACY_NON_AUTHORITATIVE`; do not import it into the new chain.

## Migration

1. Stop or hold Sentinel before changing audit state.
2. Locate all three legacy paths listed above.
3. Archive or remove those repo-local runtime files after the backup receipt exists.
4. Deploy only the independently approved exact release SHA.
5. Ensure the runtime user owns `~/.dominion/watchmen`.
6. Initialize the new Saraqael state by a governed startup/self-check.
7. On POSIX verify:
   - state directory mode = `0700`
   - signing key mode = `0600`
   - audit log mode = `0600`
   - chain state mode = `0600`
8. Verify the new chain starts truthfully from GENESIS/new state. Do not copy sequence/hash state from the legacy chain.
9. Verify Saraqael `verify_chain()` reports valid only for the new chain.
10. Verify Sentinel writes governed receipts through Saraqael.
11. Verify no repo-local audit artifacts are recreated.
12. Verify the Git working tree remains clean.

## Required negative acceptance test

Deliberately make the governed Saraqael receipt path unavailable in a controlled, reversible test condition.

Expected result:

- Sentinel surfaces `AUDIT_UNAVAILABLE` / equivalent operator-visible failure.
- Sentinel does not create `buddy_core/logs/sentinel_audit.log`.
- A consequential audited mutation is blocked before execution when the intent receipt cannot be created.
- A mutation whose completion receipt cannot be created is **not** counted or reported as completed/productive.
- Operational diagnostics, if emitted to `sentinel.log`, stdout, or systemd journal, are clearly NON-AUTHORITATIVE and are never substituted for a signed governance receipt.

Restore Saraqael availability and confirm the signed chain remains valid before continuing.

## Release acceptance

Do not mark E0-001 PROVEN until all of the following are evidenced:

- exact approved SHA deployed
- secure state directory and permissions verified
- legacy artifacts isolated/non-authoritative
- valid new chain verified
- Sentinel success receipt verified
- fail-closed negative test verified
- no repo-local audit artifacts recreated
- health and relevant negative tests pass
- deployment receipt records exact SHA, host, timestamp, result, rollback reference
- measurement confirms no false completion/productivity state

## Forward-safe rollback

Rollback must never restore the retired hard-coded signing key or treat the old chain as authoritative.

If the secure audit path fails after deployment:

1. **HOLD** audit-dependent autonomous mutations.
2. Preserve the current secure state directory and evidence; do not truncate or rewrite it.
3. Stop Sentinel if it cannot operate without producing unaudited consequential changes.
4. Restore only the last known secure implementation whose signing material remained outside source control.
5. Re-verify key/state ownership and permissions.
6. Re-run chain verification before resuming.
7. If chain continuity cannot be proven, preserve the old secure state as evidence, initialize a new explicitly discontinuous chain, and record the discontinuity in the rollback receipt.
8. Never reactivate the published legacy static signing key.
9. Never claim continuity that has not been cryptographically proven.

## Closure receipt fields

Record at minimum:

- release SHA
- VM SHA
- deployment timestamp
- runtime user
- state directory
- discovered legacy artifact hashes/locations
- legacy disposition
- permission verification
- new-chain verification result
- Sentinel governed-receipt result
- audit-unavailable negative-test result
- working-tree cleanliness
- rollback reference
- known limitations
- final status: `PROVEN`, `BLOCKED`, or `DEGRADED`
