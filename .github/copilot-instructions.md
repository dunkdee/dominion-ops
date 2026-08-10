# Dominion Copilot review instructions

Review as a senior production-safety engineer. Be concise, evidence-based, and fail closed.

- GitHub is the canonical code-control source. Production VM state is runtime evidence, not an alternate code-authoring lane.
- Never suggest committing `.env`, passwords, tokens, API keys, private keys, customer lead stores, suppression lists, or raw logs containing PII.
- For production mutations require: inventory -> verify -> smallest change -> tests/preflight -> explicit Founder GO -> atomic apply -> controlled restart -> acceptance evidence.
- Production file replacement must use same-directory temporary files, flush/fsync, preserve uid/gid/mode, `os.replace`, and parent-directory fsync where applicable.
- Rollback must be explicit and production-safe; do not recommend plain overwrite/cp as the rollback mechanism for governed files.
- Email Drip defaults to HOLD. Flag any path that can send customer email without explicit `DRIP_SEND_MODE=live` plus a production-faithful blast-radius preflight.
- A due-email preflight must enforce the same eligibility rules as the deployed scheduler, including valid email, valid `captured_at`, suppression state, source/book resolution, schedule timing, content presence, and already-sent state.
- Email state may advance only after the real transport returns success. Mock/test transport must never advance production state.
- PrivateEmail SMTP is the existing preferred mail rail. Flag fallback to SendGrid after SMTP failure unless separately authorized.
- `free_audit` must remain mapped to zero-email hold unless explicitly redesigned and approved.
- Meta/Facebook is RESTRICTED_HOLD. Flag login automation, posting, advertising, Pixel/CAPI restoration, replacement accounts, or restriction workarounds.
- Proposal Queue is protected and must remain untouched unless the PR explicitly targets it.
- Do not treat service health as proof that a real-world side effect is safe; verify immediate startup behavior and blast radius.
- Reject broad refactors, unrelated cleanup, new infrastructure, new providers, or duplicate services when the existing Dominion capability can be reused.
- Require deterministic tests for eligibility, hold/live behavior, suppression fail-closed behavior, atomic writes, rollback, and no-secret/no-PII output where those paths change.
- Call out unsupported health, medical, financial, legal, testimonial, pricing, or performance claims in customer-facing email content.
