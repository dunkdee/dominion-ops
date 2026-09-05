# Governed external.message backend

This capability closes the first real external-delivery gap without expanding Buddy's authority.

## Boundary

`external.message` remains a privileged write. Buddy must first stage the message, freeze the exact recipient/subject/body, bind those fields into the existing authorization payload hash, obtain Founder authorization, and redeem that authorization once. Only then can the SMTP transport run.

The transport uses the existing Dominion PrivateEmail-compatible SMTP configuration (`SMTP_HOST`, `SMTP_PORT`, `SMTP_EMAIL`, `SMTP_PASSWORD`). It is additionally disabled unless `BUDDY_EXTERNAL_MESSAGE_MODE=live`.

## Receipt semantics

A `VERIFIED` message means the configured SMTP server returned `250` after receiving the complete DATA payload. Evidence records the accepted message's `Message-ID`, provider label, acceptance timestamp, SMTP-response digest, destination digest, and exact authorized-content digest. This proves SMTP acceptance; it does **not** claim inbox placement, reading, conversion, or recipient action.

If the connection fails before DATA begins, the action is `BLOCKED`. If a transport failure happens after DATA transmission begins, the state is intentionally `DELIVERED_UNVERIFIED` with a do-not-retry marker because blind retry could duplicate a message.

## Security invariants

- no recipient is invented after authorization;
- exactly one explicit email destination is required;
- only the authorization-fingerprinted payload reaches the transport;
- staged artifact content is read only from the governed staged directory and its SHA-256 is rechecked;
- the canonical message envelope is preserved unchanged on resume;
- credentials remain environment-only and are never included in receipts/errors;
- TLS is required before SMTP authentication;
- one authorization produces at most one transport attempt;
- message size and timeout are bounded;
- live transport remains opt-in at runtime.

This backend deliberately does not add bulk outreach, list expansion, contact discovery, or automatic retry. Those require separate governed capabilities and evidence contracts.

## Verification evidence

After aligning the legacy Buddy regression with the new explicit-destination safety boundary, the focused candidate suite completed **89 passed, 0 failed** across Buddy operator behavior, the governed message backend, authorization policy/execution, and the #235 security-closure regressions. Exact-head repository CI remains the controlling pre-merge evidence.
