# Dominion Video Studio — Worker License Review

**Review date:** 2026-07-25  
**Release ID:** `video_studio_clone_release_20260724`  
**Status:** `CANDIDATE REVIEW — NOT FINAL LEGAL APPROVAL`

## Scope

This record identifies self-hosted video-worker candidates for the first authorized Dominion clone test. It does not authorize public release or declare any neural candidate commercially cleared. Every selected dependency and checkpoint must be recorded by immutable source, version, checksum, and license before production use.

## Owned fallback — Dominion Lite CPU

- Source: first-party code in `apps/video-studio/worker/dominion_lite_renderer.py`.
- Dependencies pinned for the candidate:
  - `opencv-python-headless==4.13.0.92` — PyPI metadata identifies Apache-2.0 licensing;
  - `numpy==2.3.3` — NumPy distributions use the BSD license family;
  - Debian Bookworm `ffmpeg` package — system multimedia runtime; bundled component notices must remain available in the final image inventory.
- Intended capability: audio-energy-driven mouth-region motion, subtle camera movement, caption rendering, and MP4 packaging on CPU-only hardware.
- Claim boundary: this is a controlled 2.5D preview renderer. It is **not** phoneme-accurate neural lip sync, identity synthesis, or full expression/body generation.
- Media boundary: only explicitly consented portrait and voice assets may be processed. Personal media, outputs, secrets, and worker tokens are prohibited from Git and ordinary CI artifacts.

**Dominion decision:** acceptable for an isolated, non-public first-subject preview after build, render, security, deletion, and quality tests pass. It does not replace the premium neural-worker requirement.

## Candidate A — EchoMimicV2

- Upstream: `https://github.com/antgroup/echomimic_v2`
- Repository license displayed by upstream: Apache-2.0.
- Intended capability: audio-driven portrait and semi-body human animation from a reference image.
- Upstream tested environments include NVIDIA V100 16 GB, RTX 4090D 24 GB, and A100 80 GB.
- Upstream weights are downloaded separately and include third-party components.

**Dominion decision:** preferred direct image-plus-audio pilot when the approved worker has compatible NVIDIA CUDA hardware. Hold commercial release until every downloaded checkpoint and dependency license is captured and reviewed.

## Candidate B — MuseTalk

- Upstream: `https://github.com/TMElyralab/MuseTalk`
- Upstream states the code is MIT licensed and its trained model may be used commercially.
- Intended capability: high-quality lip synchronization on an input video.
- Upstream explicitly requires users to comply with licenses for Whisper, VAE, DWPose, face detection/parsing, and other components.

**Dominion decision:** approved only as a fallback lip-sync stage after dependency verification. It does not by itself satisfy the requested still-image expression and body-motion requirement.

## Candidate C — InfiniteTalk

- Upstream: `https://github.com/MeiGen-AI/InfiniteTalk`
- Upstream states the repository models are licensed under Apache-2.0.
- Intended capability: image-to-video and video-to-video talking generation with lip, head, body, and expression alignment.
- The published setup depends on Wan2.1-I2V-14B and separate audio-encoder weights.

**Dominion decision:** quality/scale candidate, not the first deployment default. Hold installation until actual GPU capacity is known and every base-model and encoder license is independently verified.

## Candidate D — LatentSync

- Upstream: `https://github.com/bytedance/LatentSync`
- Repository license displayed by upstream: Apache-2.0.
- Intended capability: lip synchronization for existing video.

**Dominion decision:** optional repair or post-processing stage only. It is not a full portrait-animation worker.

## Excluded or held defaults

- Original Wav2Lip releases are not accepted as the commercial default without a separate current license determination.
- LivePortrait is held as a commercial default while its standard InsightFace detection dependency remains subject to non-commercial model restrictions; a commercially cleared detector replacement would be required.
- SadTalker is held pending complete dependency and model provenance review despite its top-level repository license statement.
- Unofficial forks, repackaged checkpoints, model mirrors, and community containers are excluded unless their complete provenance and licenses are verified against upstream sources.
- Internet test media from upstream repositories must not be used commercially.

## Hardware decision gate

1. The isolated `foundation-vm` preflight reported `gpu_status=not_detected`.
2. Keep the control plane on `foundation-vm` and use Dominion Lite for the controlled CPU preview path.
3. Preserve the detachable worker contract for a separate approved GPU-capable machine.
4. Do not enable paid GPU time, credits, or new GCP charges without a new explicit Human Overseer authorization.

## Required evidence before Law and Governance approval

- immutable upstream commit or release identifier for any third-party neural worker;
- code license text and checksum;
- each model/checkpoint source, revision, checksum, and license;
- complete dependency license inventory and container notice export;
- commercial-use conclusion with unresolved terms clearly listed;
- consent, retention, deletion, and access-control rules for likeness and voice media;
- no external publication or third-party cloning authorization.
