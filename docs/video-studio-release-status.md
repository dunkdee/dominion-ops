# Dominion Video Studio Release Status

Release branch: `agent/video-studio-five-council-release`

## Implemented

- rollback-safe immutable VM deployment script
- persistent worker-token and data-volume handling
- localhost-only service binding
- automatic restoration of the previous container when readiness fails
- release identity labels and post-deployment verification
- protected manual production deployment workflow using existing VM secrets
- CI compilation, API tests, shell validation, Compose validation, and container build

## Still gated

- authenticated Caddy route verification
- commercially usable neural worker license record
- neural worker installation and hardware compatibility test
- first authorized neural MP4 and quality review
- five independent Council review records
- final release evaluator approval

The production workflow intentionally deploys only the control plane. It does not claim that facial animation or neural cloning is operational.
