# external.message acceptance criteria

This capability is not production-ready merely because code and CI are green.

Pre-merge acceptance:
- exact recipient, subject, body, and content digest are frozen before Founder authorization;
- only authorization-fingerprinted fields reach the executor;
- missing/malformed/tampered payloads fail closed;
- SMTP credentials remain environment-only;
- live transport remains disabled unless explicitly configured;
- SMTP 250 DATA acceptance is required before `VERIFIED` delivery evidence can exist;
- transport uncertainty after DATA begins becomes `DELIVERED_UNVERIFIED` and must not auto-retry;
- Saraqael audit still gates verified consequential delivery;
- temporary applicator/patcher files are absent;
- focused security/authority tests and full repository suite are green on the exact PR head.

Production proof, separately after governed merge/deploy:
1. deploy the exact merged SHA;
2. confirm governed SMTP configuration without exposing secrets;
3. send one Founder-approved canary to a Founder-controlled destination;
4. verify exact authorization -> SMTP acceptance receipt -> Saraqael audit linkage;
5. verify duplicate/replay attempt is blocked;
6. verify failed/ambiguous transport remains truthful and does not auto-retry;
7. record measurement/learning only from verified delivery evidence.
