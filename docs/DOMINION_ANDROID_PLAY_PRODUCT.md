# Dominion Android / Google Play Product

Status: implementation lane on `feat/dominion-play-launch-clean`.

## Product boundary

This is the public consumer Android product. It is separate from the private Dominion Control / Publisher operator console.

The public app must never expose Publisher operator credentials, Meta/provider secrets, private control-plane endpoints, infrastructure mutation controls, or private receipts that do not belong to the signed-in consumer.

The consumer experience is phone-first: a user creates an account, provides the information required for an allowed workflow, explicitly activates that workflow, observes progress/results, and can earn non-cash in-app points under a documented rewards policy. The product must not claim guaranteed income or fabricate earnings.

## Google Play baseline — September 2026

- Native Android application; do not ship a bare website wrapper.
- `compileSdk = 36` and `targetSdk = 36` (Android 16).
- Production artifact is an Android App Bundle (`.aab`).
- Signed release build compatible with Play App Signing.
- Accurate Data safety disclosure and public privacy policy.
- IARC content rating completed before production.
- Store listing assets, support contact, terms, privacy, and account-deletion path complete.
- No restricted permission unless core functionality truly requires it and the declaration is complete.
- For personal Play developer accounts created after 2023-11-13, production access remains blocked until Google’s required closed-test criteria are satisfied.

## Commercial model

The app may be a paid Play download and/or use Play-compliant digital subscriptions/products. Digital entitlement is server-authoritative and purchase tokens must be verified server-side before access is granted.

Points are not represented as money, securities, guaranteed earnings, gambling value, or withdrawable cash unless a later separately reviewed legal/product design explicitly establishes that capability.

## Required customer loops

No feature is complete until its full loop works and produces an auditable result:

1. Install -> launch -> supported-device check.
2. Account create/sign-in -> verified session -> secure logout -> account deletion.
3. Terms/privacy consent -> versioned consent receipt.
4. Purchase/entitlement -> server verification -> entitlement restore after reinstall/device change.
5. Profile/intake -> validated data -> save -> edit/delete.
6. Workflow activation -> explicit confirmation -> server job receipt -> progress state.
7. Result -> customer-visible evidence/status -> retry/recovery for failed jobs.
8. Points event -> immutable reason/source -> balance update -> history.
9. Notification/deep link -> correct destination -> no duplicate action.
10. Offline/network loss -> recoverable state without duplicate submissions.
11. App update -> session and entitlement preserved.
12. Support/privacy -> contact, export where applicable, account/data deletion.

## Architecture

### Android client
- Kotlin + Jetpack Compose.
- Unidirectional state flow.
- Android Keystore-backed secret storage.
- No backend/admin secret embedded in APK/AAB.
- HTTPS production traffic only.
- Minimal permissions.
- Privacy-filtered crash/error telemetry.

### Public mobile API
The Android client uses a dedicated consumer API boundary and never calls private Publisher operator routes.

Minimum domains:
- `/v1/mobile/auth/*`
- `/v1/mobile/profile/*`
- `/v1/mobile/entitlements/*`
- `/v1/mobile/workflows/*`
- `/v1/mobile/points/*`
- `/v1/mobile/receipts/*`
- `/v1/mobile/account/delete`

Every state-changing endpoint requires authenticated user context, authorization to the user's own resources, idempotency protection, validation, rate limiting, and a receipt/event record.

### Billing
- Google Play purchase token is sent to the backend.
- Backend verifies entitlement before granting access.
- Entitlement state is server-authoritative.
- Duplicate/replayed purchase tokens fail closed.
- Refund/cancel/expiry state removes or downgrades entitlement correctly.

## Security closure gates

- No secrets in source, APK/AAB resources, logs, analytics, crash payloads, or client BuildConfig.
- Dependency/static analysis clean or explicitly reviewed.
- Exported Android components minimized and explicit.
- Deep links reject untrusted parameters.
- Auth tokens revocable and scoped.
- Rate limiting and abuse controls on public API endpoints.
- Points and entitlement mutations are server-side only.
- Replayed/tampered workflow requests do not duplicate execution.

## Quality closure gates

- Unit tests for state, repository, and domain rules.
- API contract tests.
- Instrumented tests for login, purchase restore, workflow activation, points history, logout/account deletion, process recreation, and offline recovery.
- Release build smoke-tested on representative Android devices/sizes.
- Accessibility, dynamic text, touch targets, and contrast checked.
- No crash, ANR, frozen loading state, placeholder copy, broken navigation, or dead button accepted.

## Play Store closure gates

- Production `.aab` built from locked dependencies.
- versionCode/versionName controlled by release process.
- Signing and Play App Signing configured without committing private keys.
- Privacy policy and account-deletion path live.
- Data safety form matches actual SDK/data behavior.
- Content rating, app-access instructions, ads declaration, and target audience accurate.
- Production screenshots/icon/feature graphic complete.
- Developer-account testing-track requirements satisfied.
- Pre-launch report blockers resolved.
- Production rollout receipt recorded.

## Definition of done

The Android product is not done when screens exist or an APK installs. It is done only when the native client, public backend, auth, billing/entitlement, workflows, points, receipts, privacy/deletion, tests, signed AAB, Play policy forms, testing-track requirements, and production release evidence are all closed end-to-end.
