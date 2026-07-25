# Dominion Video Studio End-to-End Worker Preflight Evidence

**Release docket:** `video_studio_clone_release_20260724`  
**Evidence date:** `2026-07-25`  
**Source workflow:** `Dominion Video Studio End-to-End Worker Preflight`  
**Result:** `PASS — SYNTHETIC CONTROL-PLANE/WORKER LOOP`

## Verified end-to-end result

The protected pull-request candidate was copied to `foundation-vm`. An isolated control plane and detachable Dominion Lite CPU worker were built and connected on an internal Docker network. Synthetic portrait and voice assets were uploaded through the normal consent/project/asset/job API. The worker claimed the job through a hash-backed per-job lease, downloaded only that job's assets, rendered a vertical MP4, uploaded it through the validated worker endpoint, and moved the project to `review_ready`.

```text
release_sha=4fd37575819c0e452ca6f3d9f0e8b5909a0bb32a
result=passed
control_plane_ready=passed
consent_project_asset_job_flow=passed
worker_claim_lease_download=passed
cpu_render=passed
validated_output_upload=passed
project_review_ready=passed
output_format=720x1280_h264_aac
output_bytes=69603
output_sha256=d3167eabf428194eb497a24e1c0f9d9f945946175e1c1938573e962913e52504
render_seconds=16
api_transport=internal_docker_network
docker_network_internal=true
localhost_binding=127.0.0.1:18097
production_container_unchanged=passed
personal_media_used=false
public_exposure=not_performed
claim=cpu_preview_not_neural_clone
```

## Security boundary

- The API client, control plane, and worker communicated only on an internal Docker network.
- The control plane was bound to host IP `127.0.0.1` only.
- Worker asset access required the configured worker secret, matching worker identity, and a random per-job lease whose SHA-256 hash alone was stored by the server.
- The lease was bound to one claimed job and cleared when the job completed.
- Uploaded output was required to be nonempty MP4 media and pass FFprobe validation for an H.264 video stream and valid dimensions.
- Synthetic test media only; no Human Overseer portrait, voice, output, secret, or model weight was placed in Git or the evidence artifact.
- The existing production container identity was unchanged, and isolated containers, network, volume, images, and work files were removed after the test.

## Capability boundary

This evidence validates the first-party CPU preview path and the complete governed transport loop. It does not establish premium neural lip sync, facial-expression synthesis, body animation, or third-party neural-model commercial clearance.

## Release implication

The following technical-readiness gates are now evidenced:

- control-plane VM compatibility;
- immutable isolated build;
- consent/project/asset/job flow;
- job-scoped worker lease transport;
- CPU preview rendering;
- validated output upload and review-ready transition;
- internal-network isolation and localhost-only host binding;
- production-container non-interference and cleanup.

Production deployment, authenticated Caddy access, use of the Human Overseer's personal media, premium neural-worker activation, independent Five Council decisions, and final release approval remain separately gated.
