# Dominion Video Studio

A self-hosted, phone-first control plane for consented avatar and voice-video production.

## Operating modes

- `proof_render`: CPU-compatible end-to-end validation. Combines the approved portrait, recorded voice and script captions into an MP4 using FFmpeg.
- `external_clone`: queues the same governed project contract for a detachable GPU worker such as InfiniteTalk, MuseTalk or another commercially permitted engine.

The control plane remains usable without a GPU. Heavy inference is isolated so it can run on an approved local GPU, an existing GCP GPU worker, or another replaceable worker without changing the phone interface or project records.

## Safety and governance

- A complete consent record is required before a project can be created or generated.
- Only the subject's authorized likeness, voice and uploaded media may be used.
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
5. Run `proof_render`.
6. Review the MP4 for framing, audio, subtitle timing and mobile usability.
7. Attach the first neural clone worker only after the complete control-plane test passes.

## External GPU worker contract

Set `VIDEO_STUDIO_WORKER_TOKEN` on the server and worker. The included generic worker:

1. Claims one `external_clone` job from `POST /api/workers/claim`.
2. Downloads authorized media through token-protected asset endpoints.
3. Runs the configured `VIDEO_CLONE_COMMAND` with portrait, voice, script and output placeholders.
4. Uploads the MP4 to `POST /api/workers/jobs/{job_id}/output`.
5. Reports failures to `POST /api/workers/jobs/{job_id}/complete`.

The worker does not bundle third-party code or model weights. Install and configure only an engine whose code and weights have been verified for the intended commercial use.

## GCP placement

Recommended zero-surprise deployment:

- Existing GCP VM: FastAPI control plane, SQLite data, FFmpeg proof renderer and Caddy route.
- Persistent VM disk: first-subject assets and exports.
- Detachable GPU worker: disabled until a no-cost, credit-backed or explicitly approved GPU is available.
- n8n: optional internal notification and scheduling only, not the customer-facing product core.

## Current limitations

- The proof renderer validates operations; it does not animate the face.
- SQLite is appropriate for the first-subject test but should move to PostgreSQL before multi-tenant commercialization.
- Authentication must be added at the reverse proxy or application layer before any public exposure.
- The first neural clone engine still has to be installed on a compatible GPU worker and connected through `VIDEO_CLONE_COMMAND`.
