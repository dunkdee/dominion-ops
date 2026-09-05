# Authorization runtime layout fix

## Failure proven in production

Two exact production deploy attempts exposed the same boundary bug:

- `Deploy Buddy Runtime` run `33959071351` failed after service restart because `AuthorizationLedger` rejected the machine-local signing-key path as if it were inside the repository checkout.
- After the first fix merged, run `33962057972` reproduced the failure. The Foundation VM home contains enough repo-like directory names (`.github`, `buddy_core`, `governance`, `tests`) that a marker heuristic still falsely classified the entire home directory as the checkout.

The actual canonical Git checkout is `~/dominion-ops`. The copied Buddy runtime is `~/buddy_core`, and machine-local security state belongs under `~/.dominion`.

## Root cause

Directory names are not authoritative proof that a directory is source-controlled. On this VM, treating repo-like folder names as checkout markers expands the repository boundary to `$HOME` and incorrectly rejects the approved machine-local key at `~/.dominion/authorization/ledger_hmac.key`.

## Final fix

Buddy core package initialization installs a checkout detector for the authorization ledger before any `BuddyOperator` instance is created. It recognizes a repository boundary only when actual `.git` metadata exists in the source path ancestry.

The authorization module independently rejects any signing key placed under the Buddy source tree itself. Therefore removing the directory-name heuristic does **not** allow keys under `~/buddy_core`; it only prevents unrelated home-directory state from being mislabeled as repository content.

No HMAC, payload binding, single-use, replay, expiry, permission, or fail-closed enforcement is weakened.

## Acceptance

- copied `~/buddy_core` beneath a home containing repo-like marker directories is **not** classified as a checkout;
- a real `.git` checkout is still detected;
- a key under Buddy source is still inside the explicit source boundary and rejected;
- the approved machine-local key location remains outside Buddy source;
- repository CI must pass before merge;
- after merge, `Deploy Buddy Runtime` must pass on the exact merged SHA before canary execution.
