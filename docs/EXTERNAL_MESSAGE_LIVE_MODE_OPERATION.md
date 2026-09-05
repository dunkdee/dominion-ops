# Governed External Message Live-Mode Operation

## Purpose

This document records the production operating contract for enabling and maintaining `BUDDY_EXTERNAL_MESSAGE_MODE=live` while preserving Dominion's existing external-action authorization boundary.

## Founder authorization

On 2026-09-05, the Founder directed that Dominion operate continuously with the system handling routine internal execution and reconciliation while the Founder remains overseer. The same directive explicitly requires receipts, documentation, and no manual babysitting for routine work.

This authorization is narrowly recorded in `governance/buddy/buddy_authority_policy.json` as:

`FOUNDER_STANDING_EXTERNAL_MESSAGE_LIVE_MODE_RECONCILIATION`

It authorizes the automatic internal mutation required to keep the governed external-message transport in `live` mode and to restart the bounded Buddy services only when that mode changes.

It does **not** authorize sending an external message.

## Automatic production lane

Workflow:

`.github/workflows/external-message-live-mode-production.yml`

Execution cadence:

- when the activation workflow itself is promoted to `main`
- after a successful `Deploy Buddy Runtime` run
- hourly reconciliation
- explicit manual dispatch when needed

Permitted internal actions:

- inspect only `BUDDY_EXTERNAL_MESSAGE_MODE`
- set that key to `live` without exposing or replacing unrelated `.env` values
- enforce `0600` on the runtime `.env` file
- restart only these services when the mode actually changes:
  - `dominion-buddy-web.service`
  - `buddy-bridge.service`
  - `dominion-buddy.service`
- verify Buddy bridge health
- execute the governed canary in verify-only mode
- write a machine-local receipt

Forbidden by this lane:

- sending email
- granting or redeeming a message authorization
- changing SMTP credentials
- printing SMTP secrets
- bypassing Saraqael
- bypassing the authorization ledger
- changing the external-message payload

## Verification contract

A reconciliation run is PASS only when all of the following are true:

- effective external-message mode is `live`
- the deployed release receipt contains a valid 40-character release SHA
- deployed Buddy file hashes match the release receipt and canonical Git source
- AuthorizationLedger loads
- Saraqael self-check passes
- `external.message` is registered
- SMTP configuration is present/valid without revealing values
- the canary exits with `CANARY_RESULT=VERIFY_ONLY_NO_SEND`

No external message is sent by this verification.

## Persistent receipt

Successful reconciliation writes:

`~/.dominion/buddy/external_message_live_mode_receipt.json`

Required safe fields:

- schema
- observed_at
- deployed_release_sha
- mode
- changed_this_run
- verify_only
- external_send_performed

`external_send_performed` must be `false` for this lane.

## Separate consequential gate

A real production canary remains a separate Founder-authorized action. Closure of governed external messaging requires evidence for:

1. initial execution `HELD`
2. exact approval ID and payload hash
3. Founder grant/resume
4. SMTP delivery receipt and content hash
5. Saraqael governed receipt bound to the same authorization
6. replay rejection as already consumed
7. no duplicate second delivery
8. final `CANARY_PASS`

The automatic live-mode lane cannot perform this consequential send on its own.
