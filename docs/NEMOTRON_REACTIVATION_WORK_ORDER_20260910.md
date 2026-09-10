# Nemotron Reactivation Work Order — 2026-09-10

**Authority:** Founder-directed reactivation under RADAH MEMSHALAH.

## Objective

Return `dominion-nemotron.service` to governed production as the primary local reasoning worker used by Dominion Command Center, without reopening public ingress or weakening fail-closed controls.

## Scope

Authorized changes are limited to:

1. reconcile the integrity contract so Nemotron is monitored as an active governed service rather than a containment hold;
2. bind Nemotron to loopback only on TCP 11435;
3. deploy the reviewed worker and unit from an exact merged SHA;
4. enable/start only `dominion-nemotron.service` after preflight verifies the governed Ollama dependency on 11434 and the required model;
5. verify `/health`, Command Center routing, integrity-agent PASS, persistence, and rollback evidence.

No firewall opening, DNS change, external publication, money movement, credential change, Oracle activation, live trading, or unrelated service restart is authorized.

## Required preflight

- TCP 11435 is free before activation.
- Governed Ollama on 127.0.0.1:11434 answers HTTP 200.
- `nemotron-3-nano:4b` is already present in Ollama. This lane does not pull an unpinned model.
- `dominion-nemotron.service` is inactive before mutation.
- Command Center is healthy before mutation.
- Current integrity state is PASS before changing the policy contract.

Any mismatch is `UNKNOWN`/`BLOCKED` and must stop before mutation.

## Required post-state proof

All are mandatory:

- `dominion-nemotron.service` active and enabled.
- TCP 11435 listens on `127.0.0.1` only.
- `GET http://127.0.0.1:11435/health` returns 200 with `model_available=true` and model `nemotron-3-nano:4b`.
- Command Center `/api/chat` returns a nonempty answer with `source=nemotron` for a no-side-effect health probe.
- Integrity contract treats Nemotron as active, not held, and no longer requires 11435 absent.
- The integrity agent reaches PASS with zero defects on its own scheduled cycle after activation.
- Command Center remains healthy.
- A runtime receipt records exact release SHA, unit hash, worker hash, health result, and rollback target.

## Rollback

If any acceptance proof fails after activation:

1. stop and disable only `dominion-nemotron.service`;
2. restore the prior unit and prior integrity contract from backups created by the activation lane;
3. reload systemd;
4. verify TCP 11435 absent, Ollama 11434 healthy, Command Center healthy, and integrity PASS under the restored hold;
5. record `ROLLED_BACK`, never `DONE`.

## Release governance

This is a consequential `reactivate_suspended_or_retired_agent` / `production_deployment` action. Technical readiness, Founder scope authorization, and Five Council final release approval must bind to the exact PR head/release request before production activation.
