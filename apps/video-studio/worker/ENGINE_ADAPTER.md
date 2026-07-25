# Dominion Premium Worker Drop-In Contract

The Video Studio control plane is intentionally independent of any specific neural model.
A premium renderer is attached by deploying the generic `external_worker.py` beside the
approved engine and pointing `VIDEO_CLONE_ENGINE_SPEC` to one JSON file.

## Required runtime variables

```text
VIDEO_STUDIO_URL=https://approved-internal-video-studio-route
VIDEO_STUDIO_WORKER_TOKEN=<server-worker-token>
VIDEO_STUDIO_WORKER_ID=<unique-worker-id>
VIDEO_CLONE_ENGINE_SPEC=/opt/dominion-engine/engine-spec.json
VIDEO_STUDIO_POLL_SECONDS=5
```

The worker token is never placed in Git. The worker receives a separate random lease for
each claimed job. The lease is bound to the worker ID and job, stored only as a hash by the
control plane, and invalidated after completion, failure, or consent revocation.

## Engine-spec fields

| Field | Requirement |
|---|---|
| `schema_version` | Must equal `1` |
| `engine_id` | Stable lowercase identifier |
| `engine_version` | Pinned code/model version |
| `license_status` | Must be `approved_for_intended_use` |
| `license_reference` | Governance record or reviewed license location |
| `commercial_use_verified` | Must be `true` |
| `command` | JSON argument array; no shell command string |
| `required_assets` | Must include `portrait` and `voice`; may include `source_video` |
| `supported_formats` | Any of `vertical`, `landscape`, `square` |
| `timeout_seconds` | Between 60 and 14,400 seconds |

Allowed command placeholders:

```text
{portrait}
{voice}
{source_video}
{script_file}
{output_format}
{output}
```

The command must create an H.264 MP4 at `{output}`. The control plane independently runs
`ffprobe` and rejects empty, invalid, non-H.264, or out-of-scope uploads.

## Drop-in sequence

1. Pin the engine source commit, model-weight version, CUDA/PyTorch stack, and container digest.
2. Verify every code, model-weight, face-detector, audio-encoder, and base-model license for the intended commercial use.
3. Copy `engine-spec.premium-template.json` outside Git and fill in the approved values.
4. Leave `license_status` blocked until the Law and Governance record is complete.
5. Build the worker image with `external_worker.py`, `engine_adapter.py`, the engine, and its weights.
6. Mount the approved engine spec read-only and inject the worker token through the runtime secret store.
7. Run a synthetic canary first; do not use personal media during infrastructure validation.
8. Run the Human Overseer's consented portrait/voice test only after the synthetic canary, rollback, deletion, and Five Council gates pass.
9. Keep output private and review-only until the Human Overseer approves publication separately.

## Fail-closed behavior

The worker refuses to start when:

- the engine spec is missing or malformed;
- the engine or version identifier is invalid;
- commercial-use verification is not affirmative;
- the license reference is missing;
- a command uses an unknown placeholder;
- required portrait/voice placeholders are absent;
- the requested format is unsupported;
- required assets are missing;
- the renderer exceeds its declared timeout.

The premium engine can therefore be replaced without changing the core system, while every
replacement remains independently governed, version-pinned, testable, and reversible.
