# Dominion Video Studio — Neural Worker License Review

**Review date:** 2026-07-24  
**Release ID:** `video_studio_clone_release_20260724`  
**Status:** `CANDIDATE REVIEW — NOT FINAL LEGAL APPROVAL`

## Scope

This record identifies upstream self-hosted neural-video candidates for the first authorized Dominion clone test. It does not install model code or weights, authorize public release, or declare a candidate commercially cleared. Every selected dependency and checkpoint must be recorded by immutable source, version, checksum, and license before production use.

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

## Excluded default

- Original Wav2Lip releases are not accepted as the commercial default without a separate current license determination.
- Unofficial forks, repackaged checkpoints, model mirrors, and community containers are excluded unless their complete provenance and licenses are verified against upstream sources.
- Internet test media from upstream repositories must not be used commercially.

## Hardware decision gate

1. Run the isolated `foundation-vm` preflight and record whether a supported NVIDIA GPU and CUDA runtime are present.
2. If compatible owned hardware is present, run a no-personal-media installation smoke test for the preferred candidate.
3. If `foundation-vm` has no compatible GPU, keep the control plane there and attach a separate approved worker on already-owned hardware.
4. Do not enable paid GPU time, credits, or new GCP charges without a new explicit Human Overseer authorization.

## Required evidence before Law and Governance approval

- immutable upstream commit or release identifier;
- code license text and checksum;
- each model/checkpoint source, revision, checksum, and license;
- complete dependency license inventory;
- commercial-use conclusion with unresolved terms clearly listed;
- consent, retention, deletion, and access-control rules for likeness and voice media;
- no external publication or third-party cloning authorization.
