# Dominion Video Studio VM Preflight Evidence

**Release docket:** `video_studio_clone_release_20260724`  
**Evidence date:** `2026-07-25`  
**Source workflow:** `Dominion Video Studio VM Preflight PR`  
**Result:** `PASS — CONTROL-PLANE CANDIDATE ONLY`

## Verified result

The isolated candidate was copied to `foundation-vm`, built from the protected pull-request candidate, launched on a temporary localhost-only port, health checked, inspected, and removed.

```text
binding=127.0.0.1:18094
ready=passed
read_only_rootfs=passed
production_container_unchanged=passed
gpu_status=not_detected
public_exposure=not_performed
personal_media_used=false
```

## Defect found and corrected

The first isolated build failed because the base image used Debian package sources over outbound HTTP port 80. `foundation-vm` could pull the Docker base image over HTTPS but could not reach `deb.debian.org` over HTTP, so `ffmpeg` and `curl` could not be installed.

The candidate Dockerfile was corrected to:

- use `python:3.12-slim-bookworm`;
- rewrite Debian package sources to HTTPS;
- retry package-index retrieval;
- preserve the existing non-root, read-only, least-privilege container configuration.

The corrected image build and complete isolated preflight passed.

## Security boundary

- No production container was replaced, restarted, or modified.
- No public route was created.
- No portrait, voice recording, generated media, API key, model weight, or worker token was exported in the evidence artifact.
- The temporary candidate and temporary data volume were removed after verification.

## Release implication

This evidence clears the isolated control-plane VM preflight only. It does **not** establish that:

- the production service is deployed;
- authenticated Caddy access is configured;
- a neural clone worker is installed;
- the VM can perform GPU inference;
- a talking clone MP4 has been generated;
- Five Council final approval has been issued.

`foundation-vm` reported `gpu_status=not_detected`. The neural worker must therefore run on a separate already-owned GPU-capable machine, an explicitly approved no-cost worker, or a later separately authorized paid GPU resource.
