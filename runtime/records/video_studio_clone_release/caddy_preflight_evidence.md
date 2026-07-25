# Dominion Video Studio Caddy Preflight Evidence

**Release docket:** `video_studio_clone_release_20260724`  
**Evidence date:** `2026-07-25`  
**Source workflow:** `Dominion Video Studio Caddy Preflight`  
**Result:** `PASS — READ-ONLY CADDY INVENTORY`

## Verified live state

```text
release_sha=bdfd0ed60b48786350cfae8a7dffcd69b395fe45
result=passed
inspection_only=true
caddy_mode=systemd
caddy_active=true
config_source=/etc/caddy/Caddyfile
config_sha256=28b518797bc9240996f9f4f791cdf500bff5ea2da170af34c47cd48161b4c65d
config_validation=passed
basic_auth_directive_count=0
video_studio_route_present=false
plaintext_password_pattern_detected=false
http_listener=true
https_listener=true
video_studio_local_listener=false
production_modified=false
full_config_exported=false
```

## Sanitized structure

The active configuration contains 13 site labels, 19 reverse-proxy directives, and five handle directives. No password hash, certificate material, token, header secret, or full Caddy configuration was exported.

The observed site labels were:

- `agent.dominionhealing.org`
- `api.dominionhealing.org`
- `buddy.dominionhealing.org`
- `dash.dominionhealing.org`
- `empire.dominionhealing.org`
- `hub.dominionhealing.org`
- `n8n.dominionhealing.org`
- `report.dominionhealing.org`
- `shop.dominionhealing.org`
- `store.dominionhealing.org`
- `surplus.dominionhealing.org`
- `tiktok.dominionhealing.org`
- `tools.dominionhealing.org`

## Release implication

- Caddy is available and syntactically healthy for a rollback-safe protected route.
- No existing authentication convention can be reused directly from the current Caddyfile.
- No Video Studio route or local listener is active.
- A candidate route must therefore include an explicit authentication mechanism, private credential handling, config backup, validation, graceful reload, unauthorized/authorized probes, and automatic rollback.
- This evidence does not authorize adding the route or exposing Video Studio.
