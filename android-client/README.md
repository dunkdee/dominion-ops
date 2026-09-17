# Dominion Creator Android

Native consumer Android client for the Dominion Creator product.

## Current build

- Kotlin + Jetpack Compose.
- `compileSdk = 36`, `targetSdk = 36`, `minSdk = 26`.
- Provisional application ID: `org.dominionhealing.creator` until the Play Console package is formally registered.
- No WebView wrapper.
- No production/admin secrets in the client.
- No private Dominion Control / Publisher API access.
- The current functional beta feature builds and shares a creator campaign brief locally on-device.
- Remote workflow execution is intentionally disabled until public mobile API authentication, authorization, idempotency, and receipt loops are proven.

## Build

Use JDK 17 and Gradle 8.13:

```bash
gradle --no-daemon :app:assembleDebug :app:lintDebug :app:testDebugUnitTest
```

The release `.aab`, Play signing, billing, public mobile API, account lifecycle, privacy/deletion, and production rollout remain separate closure gates. Do not label this branch Play-production-ready until those gates have real receipts.
