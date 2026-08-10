# RC3 Email Drip review scope

This branch exists to bring the deployed RC3 R4 Email Drip implementation under GitHub control and review it before any future live activation.

## Production facts captured before review

- Exact VM source SHA-256: `e4762cfc694df17df2df2d44df5429d219042d3be3209552ae9d4718f061cd6d`
- Service: `dominion-email-drip.service`
- Port: `8099`
- Production mode was found `live` during read-only diagnostic and was subsequently contained to `hold` through the governed GitHub workflow.
- Read-only production-faithful diagnostic found 6 lead records, 0 current transport candidates, and 1 ghost/invalid row with an empty email field.
- A sovereign-mind record captured on the containment date already had `welcome` recorded as sent before containment; review must account for the fact that real state advanced while the service was live.
- Free-audit transport candidates: 0.

## Review goals

1. Make GitHub the canonical source for Email Drip code and operations.
2. Eliminate scheduler/preflight drift by making any activation preflight exercise the deployed scheduler logic itself with transport stubbed and state protected.
3. Keep `DRIP_SEND_MODE=hold` fail-closed by default.
4. Ensure PrivateEmail SMTP is the controlled production rail and prevent unauthorized fallback after SMTP failure.
5. Prevent PII or secret exposure in logs, Actions output, tests, or review artifacts.
6. Preserve suppression fail-closed behavior, unsubscribe generation, free-audit zero-email hold, and state advancement only after successful transport.
7. Add deterministic synthetic tests before proposing any future live activation.
8. Do not modify Meta/Facebook or Proposal Queue.

## Non-authority

This branch and PR do not authorize merge, live email activation, production lead mutation, or deployment of changed Email Drip source. Those remain separate Founder GO gates.
