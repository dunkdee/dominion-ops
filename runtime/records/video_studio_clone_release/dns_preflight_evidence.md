# Dominion Video Studio DNS Preflight Evidence

**Release docket:** `video_studio_clone_release_20260724`  
**Evidence date:** `2026-07-25`  
**Source workflow:** `Dominion Video Studio DNS Preflight`  
**Result:** `PASS — READ-ONLY DNS PLACEMENT CHECK`

```text
release_sha=6c3564232ae646d4de310c392c584fef784f91ce
result=passed
inspection_only=true
studio_dns_present=false
studio_resolves_to_vm=false
tools_dns_present=true
tools_resolves_to_vm=true
root_dns_present=true
vm_resolution_available=true
studio_address_count=0
tools_address_count=1
root_address_count=1
raw_addresses_exported=false
dns_modified=false
```

## Placement decision

- `studio.dominionhealing.org` cannot be used immediately because it currently has no DNS record.
- `tools.dominionhealing.org` already resolves to `foundation-vm` and is present in the validated live Caddy configuration.
- The no-new-DNS candidate is therefore a protected path under the existing tools host, such as `/video-studio/`.
- This decision avoids changing DNS and does not expose or modify the live service.

## Remaining route gate

Before live activation, a candidate must prove:

- path-scoped authentication;
- unauthorized request rejection;
- authorized reverse-proxy success;
- live Caddyfile backup and hash binding;
- candidate config validation;
- graceful reload;
- automatic rollback;
- no plaintext credential in Git, logs, workflow summaries, or ordinary artifacts.
