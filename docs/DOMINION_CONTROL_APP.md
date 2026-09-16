# Dominion Control App — Production Runbook

## Scope
`apps/frontend` is the private operator UI for the existing Dominion Publisher. It does not duplicate Publisher business logic or credentials. The browser talks only to same-origin Next.js API routes; those routes call the loopback Publisher service with the server-side operator token.

## Security invariants
- Never expose `DOMINION_PUBLISHER_OPERATOR_TOKEN`, provider tokens, app secrets, or the session secret through `NEXT_PUBLIC_*` variables.
- UI access uses `DOMINION_FRONTEND_ACCESS_KEY`; sessions are HMAC-signed, HttpOnly, Secure, SameSite=Strict cookies.
- State-changing endpoints require same-origin requests.
- Meta account binding requires the UI confirmation and the backend `X-Human-Approval: APPROVED` gate.
- Live Meta posting is intentionally not exposed while repository governance is `RESTRICTED_HOLD`.
- Queueing and receipt lookup are allowed because they do not create a public post.

## Required server-only configuration
Create `~/.config/dominion/frontend.env` with mode `0600` and these keys:
- `DOMINION_FRONTEND_ACCESS_KEY`
- `DOMINION_FRONTEND_SESSION_SECRET` (at least 32 random bytes)
- `DOMINION_PUBLISHER_BASE_URL=http://127.0.0.1:5112`
- `DOMINION_PUBLISHER_OPERATOR_TOKEN` (existing Publisher operator token)
- `DOMINION_FRONTEND_PUBLIC_URL=https://app.dominionhealing.org`

Do not commit the values.

## Build gates
The PR is not mergeable until `Frontend Control App CI` proves all of the following on the committed lockfile:
1. `npm ci` succeeds.
2. TypeScript passes with no emit.
3. Next.js production build succeeds.
4. Integration smoke proves bad login rejection, session creation, secret isolation, explicit Meta binding approval, queue receipt creation, receipt lookup, and absence of a live-publish endpoint.
5. Negative controls prove no `NEXT_PUBLIC_*` credential exposure and preserve `RESTRICTED_HOLD`.
6. The production container builds.

If the branch has no package lock, the first branch CI run generates and commits it. The following run must complete the full proof.

## Production activation
Production mutation remains a separate governed step requiring Founder GO.

1. Inventory the current app container/image and Caddy route.
2. Build a uniquely tagged image from the merged commit: `docker build -t dominion-control:<git-sha> apps/frontend`.
3. Start the candidate on an unused loopback port with `--network host`, `PORT=<candidate-port>`, and the `0600` env file.
4. Require `GET /api/healthz` = HTTP 200 before cutover.
5. Verify login, Publisher health, accounts, Meta candidates, and queue/receipt path. Do not exercise live publish.
6. Switch the Caddy `app.dominionhealing.org` reverse proxy to the approved production port and validate Caddy before reload.
7. Keep the previous image/tag available for immediate rollback.
8. Record commit SHA, image tag, health response, and operator acceptance evidence.

## Caddy target
The intended public operator hostname is `https://app.dominionhealing.org`, reverse-proxied to the frontend on loopback. TLS must be valid before exposing login.

## Rollback
If post-cutover acceptance fails:
1. Restore the previous Caddy upstream and reload only after config validation.
2. Stop the candidate container.
3. Restart the prior known-good image with the unchanged env file.
4. Re-run `/api/healthz` and authenticated Publisher status.
5. Record rollback evidence. Do not alter Publisher vault files during frontend rollback.

## Closure receipt
Code closure requires a merged commit plus a green locked CI run. Runtime closure additionally requires production activation evidence from the actual VM. A green code build alone is not a production PASS.
