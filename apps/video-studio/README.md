# Dominion Video Studio

A self-hosted, phone-first control plane for consented avatar and voice-video production.

## Operating modes

- `proof_render`: CPU-compatible end-to-end validation. Combines the approved portrait, recorded voice and script captions into an MP4 using FFmpeg.
- `external_clone`: queues the same governed project contract for a detachable premium worker or another commercially permitted engine.

The control plane remains usable without a GPU. Heavy inference is isolated so it can run on an approved local GPU, an existing GCP GPU worker, or another replaceable worker without changing the phone interface, consent records, project database, or review flow.

## Safety and governance

- A complete consent record is required before a project can be created or generated.
- Only the subject's authorized likeness, voice and uploaded media may be used.
- Consent can be revoked; revocation cancels jobs, expires worker leases and removes source/output media while retaining a non-media audit record.
- Uploads and generated files are stored outside the container image.
- The service binds to localhost by default; expose it only through the existing authenticated reverse proxy.
- No API keys, model weights or personal media belong in Git.

## Run locally or on the existing GCP VM

```bash
cp .env.example .env
docker compose up -d --build
curl http://127.0.0.1:8094/ready
```

Open it through the approved Caddy route after authentication and TLS are configured.

## First controlled test

1. Open the mobile page.
2. Confirm consent for your own likeness and voice.
3. Create a short vertical test project.
4. Upload one clear portrait and one clean voice recording.
5. Run `proof_render` or the governed CPU preview worker.
6. Review the MP4 for framing, audio, subtitle timing and mobile usability.
7. Attach the first neural clone worker only after the complete control-plane, rollback, deletion and synthetic-worker tests pass.

## Detachable worker contract

Set `VIDEO_STUDIO_WORKER_TOKEN` on the server and worker. The included generic worker:

1. Loads and validates `VIDEO_CLONE_ENGINE_SPEC`.
2. Refuses unapproved, malformed or unsupported engine specifications.
3. Claims one `external_clone` job from `POST /api/workers/claim`.
4. Downloads authorized media through job-specific lease-protected endpoints.
5. Executes the engine command as an argument vector without a shell.
6. Uploads the MP4 to `POST /api/workers/jobs/{job_id}/output`.
7. Reports failures to `POST /api/workers/jobs/{job_id}/complete`.

The engine spec declares the pinned engine/version, license record, commercial-use verification, required media, supported output formats, command arguments and timeout. The worker does not bundle third-party code or model weights. Install and configure only an engine whose code, dependencies, base models and weights have been verified for the intended commercial use.

See `worker/ENGINE_ADAPTER.md` and `worker/engine-spec.premium-template.json`. A future premium renderer is dropped in by mounting its approved code/weights and spec; the control plane does not need to be rewritten.

## GCP placement

Recommended zero-surprise deployment:

- Existing GCP VM: FastAPI control plane, SQLite data, FFmpeg proof renderer and Caddy route.
- Persistent VM disk: first-subject assets and exports.
- Detachable premium worker: disabled until an owned, no-cost, credit-backed or explicitly approved GPU is available.
- n8n: optional internal notification and scheduling only, not the customer-facing product core.

## Current limitations

- The proof and CPU preview renderers validate operations; they are not the premium neural face-animation engine.
- SQLite is appropriate for the first-subject test but should move to PostgreSQL before multi-tenant commercialization.
- Authentication must remain enforced at the reverse proxy or application layer before any public exposure.
- The premium neural engine still has to be installed on compatible hardware and connected through an approved engine spec.
