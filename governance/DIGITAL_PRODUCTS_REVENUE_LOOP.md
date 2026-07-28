# Dominion Digital Products Revenue Loop

## Objective

Turn existing Dominion-owned educational products into verified, measurable sales without publishing dead checkout links or pretending revenue exists.

## First offers

1. The Art of True Healing — $27
2. Credit Dispute Toolkit — $47
3. AI Automation Blueprint — $47

## Required closed loop

Traffic -> landing page -> tracked CTA -> verified checkout -> payment confirmation -> delivery -> support/refund handling -> revenue telemetry -> Dominion memory -> Nemotron review and optimization.

## Revenue-ready gate

An offer is `revenue_ready` only when all of the following are true:

- Verified checkout URL is configured.
- Verified delivery target or workflow is configured.
- Refund terms are published.
- Funnel telemetry is enabled.

Until then, the Command Center reports the offer as `blocked` and campaigns must not send buyers to checkout.

## API contract

- `GET /api/revenue` returns vertical and offer readiness.
- `POST /api/revenue/events` records page views, CTA clicks, leads, checkout starts, purchases, delivery, refunds, and support events.
- `GET /health` exposes the count of offers that have passed all revenue gates.

## Environment configuration

- `CHECKOUT_ART_OF_TRUE_HEALING`
- `DELIVERY_ART_OF_TRUE_HEALING`
- `CHECKOUT_CREDIT_DISPUTE_TOOLKIT`
- `DELIVERY_CREDIT_DISPUTE_TOOLKIT`
- `CHECKOUT_AI_AUTOMATION_BLUEPRINT`
- `DELIVERY_AI_AUTOMATION_BLUEPRINT`

Secrets and private delivery locations must remain in runtime environment configuration, not Git.

## Activation order

1. Confirm the final downloadable file for one offer.
2. Create or verify its payment link.
3. Configure checkout and delivery environment values.
4. Deploy Command Center.
5. Verify `/api/revenue` reports exactly that offer as `revenue_ready`.
6. Run a controlled purchase with explicit Founder approval.
7. Verify payment, delivery, refund/support language, event telemetry, and memory write-back.
8. Replace the public request-link CTA with the verified checkout only after the test passes.
9. Launch the first content and outreach campaign.
10. Review visits, CTA clicks, checkout starts, purchases, refunds, and net revenue before scaling.
