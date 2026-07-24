# Dominion Video Studio Clone Release — Five Council Review Docket

**Release ID:** `video_studio_clone_release_20260724`  
**Current gate:** `HOLD — TECHNICAL READINESS NOT YET VERIFIED`  
**Human Overseer instruction:** finish the clone correctly; require Five Council sign-off; show every Council finding.

## Authorized scope

- Implement changes only on a protected nonproduction branch.
- Prepare and validate a rollback-safe deployment of Dominion Video Studio to `foundation-vm`.
- Bind the service to localhost only until authenticated Caddy access is verified.
- Use only the Human Overseer's own authorized portrait and voice recording for the first test.
- Do not publish or distribute the clone output externally.
- Do not purchase GPU time, enable paid services, or add new GCP charges without a separate explicit authorization.
- Do not commit secrets, personal media, model weights, or generated clone media to Git.

## Verified evidence already present

- Video Studio control-plane foundation is merged on `main`.
- Consent, project, asset, job, output, and approval boundaries exist.
- The CPU proof-render path exists.
- The deployment helper binds to `127.0.0.1:8094` and performs a readiness check.
- The external worker contract exists.

## Material gaps blocking final release

- No production deployment evidence from `foundation-vm`.
- No authenticated Caddy route verification.
- No rollback test evidence.
- No installed or connected neural clone worker.
- No verified code-and-weight commercial-use license record for the selected worker.
- No first neural MP4, lip-sync score, identity-preservation review, or failure log.
- The Five Council agents are registered but no independent review records are yet bound to this release request.

## Pre-review issue statements

These are review questions and likely holds, **not official Council votes**. Official votes must be independently produced, evidence-backed, hash-bound to the final release request, and preserved verbatim.

### 1. Truth and Evidence

**Current expected state:** `HOLD`

Required evidence:

- prove the control plane is deployed and healthy;
- prove the selected neural worker is actually installed and callable;
- produce one complete MP4 from the authorized portrait and `.m4a` file;
- distinguish proof-render capability from true facial animation;
- record uncertainty and failures without calling the system complete prematurely.

### 2. Law and Governance

**Current expected state:** `APPROVE_WITH_CONDITIONS` or `HOLD`, depending on license evidence.

Required conditions:

- preserve explicit likeness-and-voice consent;
- limit first use to the Human Overseer's own media;
- verify both source-code and model-weight licenses for commercial use;
- define retention, deletion, and access rules for biometric-like media;
- prohibit impersonation, unauthorized cloning, external publication, and third-party subject ingestion without separate consent.

### 3. Security and Risk

**Current expected state:** `HOLD`

Required evidence:

- localhost-only binding confirmed;
- authenticated TLS reverse proxy confirmed before exposure;
- worker token stored only in protected secret storage;
- no secret or personal-media export to GitHub artifacts or logs;
- file permissions, storage location, retention, and deletion tested;
- rollback and emergency-stop procedures tested;
- worker download/upload endpoints tested against unauthorized access.

### 4. Engineering and Reliability

**Current expected state:** `HOLD`

Required evidence:

- versioned release directory or equivalent rollback-safe deployment;
- dirty working-tree protection on `foundation-vm`;
- deterministic build and health checks;
- automated tests for asset authorization, job claiming, output upload, and failure reporting;
- neural-worker compatibility evidence for the actual available hardware;
- render timeout, crash recovery, logs, and post-deploy verification;
- first-output QA for lip sync, identity drift, framing, audio, and motion.

### 5. Business Value and Human Impact

**Current expected state:** `APPROVE_WITH_CONDITIONS`

Required conditions:

- retain the zero-paid or already-owned infrastructure constraint;
- start with one subject and one short test before scaling;
- record render time, compute demand, failure rate, and operator effort;
- prevent premature commercialization before reliability, consent, privacy, and licensing gates pass;
- preserve a modular worker interface so the platform is not locked to a paid provider.

## Final release rule

Final deployment is permitted only when all of the following are true:

1. technical readiness is evidenced;
2. Human Overseer scope authorization is hash-bound to the release request;
3. all five independent Council review records are present;
4. every Council decision is `APPROVE` or `APPROVE_WITH_CONDITIONS`;
5. no Law or Security veto exists;
6. no hold or missing review exists;
7. the final evaluator returns `FINAL_RELEASE_APPROVED`;
8. execution remains inside the authorized scope above.

Until then, the release remains `HOLD`.