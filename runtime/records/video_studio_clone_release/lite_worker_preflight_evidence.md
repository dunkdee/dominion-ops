# Dominion Lite CPU Worker Preflight Evidence

**Release docket:** `video_studio_clone_release_20260724`  
**Evidence date:** `2026-07-25`  
**Source workflow:** `Dominion Lite CPU Worker Preflight`  
**Result:** `PASS — OWNED CPU PREVIEW WORKER`

## Verified canary

The candidate worker image was built on `foundation-vm` and executed against synthetic portrait/audio/script inputs. Rendering ran with container networking disabled and least-privilege controls. The resulting MP4 was inspected before all synthetic work files and the canary image were removed.

```text
release_sha=059cf381583f34b83eaf7bd0f7a16331b31ddf2c
worker=dominion_lite_cpu
worker_image_build=passed
synthetic_render=passed
output_format=720x1280_h264_aac
output_bytes=72174
output_sha256=5ad7ecaf55e012b9cbe6f99b6201fed267e4b5bb6c41d49acc85290bb4632bd6
build_seconds=10
render_seconds=12
network_during_render=none
production_container_unchanged=passed
personal_media_used=false
claim=cpu_preview_not_neural_clone
```

## Claim boundary

This evidence proves that the first-party Dominion Lite CPU component can build and produce a technically valid moving portrait preview on the existing VM. It does not prove phoneme-accurate neural lip sync, premium expression synthesis, identity preservation under a neural model, or commercial readiness of any third-party model.

## Security and privacy boundary

- Synthetic media only; no Human Overseer portrait or voice was transferred.
- Rendering container network mode was `none`.
- Container used a read-only root filesystem, temporary `/tmp`, dropped capabilities, `no-new-privileges`, process/memory/CPU limits, and a single mounted synthetic workspace.
- Existing `dominion-video-studio` container identity was unchanged.
- The generated canary MP4 was not uploaded as a routine artifact; only its metadata, size, and SHA-256 digest were preserved.

## Release implication

This clears the CPU-worker build and synthetic-render engineering gate. Remaining release blockers include authenticated Caddy verification, deployment of the control plane, end-to-end worker claim/lease/output validation on the VM, a private authorized-subject preview, Human Overseer quality review, independent Five Council records, and the final release evaluator.
