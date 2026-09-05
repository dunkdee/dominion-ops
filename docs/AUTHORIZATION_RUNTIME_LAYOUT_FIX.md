# Authorization runtime layout fix

## Failure proven in production

`Deploy Buddy Runtime` run `33959071351` reached the Foundation VM, updated the checkout to the intended release, copied Buddy runtime files, restarted services, then failed health verification because `AuthorizationLedger` rejected its machine-local signing-key path as if it were inside the repository checkout.

The copied production layout intentionally places `~/buddy_core` beside other home-directory state. A home directory containing both `.github` and `buddy_core` is not sufficient evidence that the entire home directory is a Dominion repository checkout.

## Fix

Buddy core package initialization now installs a stricter checkout detector for the authorization ledger before any `BuddyOperator` instance is created. The detector accepts either:

- a real `.git` checkout; or
- a source snapshot containing the canonical marker set `.github`, `buddy_core`, `governance`, and `tests`.

This preserves rejection of signing keys inside source while allowing the approved machine-local default under `~/.dominion/authorization/ledger_hmac.key` in the copied production runtime.

No HMAC, payload binding, single-use, replay, expiry, permission, or fail-closed enforcement is weakened.

## Acceptance

- copied Buddy runtime home is not classified as a repo checkout;
- canonical source snapshot still is;
- machine-local authorization key remains outside copied Buddy source;
- repository CI must pass before merge;
- after merge, `Deploy Buddy Runtime` must pass on the exact merged SHA before canary execution.
