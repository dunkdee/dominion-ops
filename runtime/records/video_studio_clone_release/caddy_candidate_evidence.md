# Dominion Video Studio Authenticated Caddy Candidate Evidence

**Release docket:** `video_studio_clone_release_20260724`  
**Evidence date:** `2026-07-25`  
**Source workflow:** `Dominion Video Studio Caddy Candidate`  
**Result:** `PASS — NON-PRODUCTION AUTHENTICATED ROUTE CANARY`

```text
release_sha=61ad6a7878feac4b046204dd03ab093b7476ac82
result=passed
candidate_only=true
placement=tools.dominionhealing.org/video-studio/
auth_directive=basicauth
live_config_hash_unchanged=true
route_insertion_count=1
merged_live_config_validation=passed
isolated_canary_config_validation=passed
unauthorized_status=401
wrong_password_status=401
authorized_status=200
authorized_upstream_marker=passed
live_caddy_active_after=true
plaintext_credential_exported=false
password_hash_exported=false
live_config_modified=false
public_route_activated=false
```

## Verified behavior

- The route was inserted into a private copy of the live `tools.dominionhealing.org` site block.
- The merged copy validated with the Caddy binary installed on `foundation-vm`.
- Runtime compatibility testing determined that this VM requires the `basicauth` directive.
- A temporary high-port Caddy canary rejected missing and incorrect credentials with HTTP `401`.
- Correct credentials reached a temporary localhost upstream and returned HTTP `200` with the expected marker.
- The active `/etc/caddy/Caddyfile` hash did not change, the live Caddy service remained active, and no public route was activated.
- The ephemeral plaintext password and password hash were not exported in Git, logs, workflow summaries, or artifacts.

## Release implication

The route architecture is technically valid for `https://tools.dominionhealing.org/video-studio/`. Live activation still requires:

- an approved persistent credential-creation and secure-delivery mechanism;
- backup, atomic config replacement, validation, graceful reload, unauthorized/authorized post-deploy probes, and rollback;
- the deployed Video Studio service listening on `127.0.0.1:8094`;
- unanimous independent Five Council approval and a final evaluator result of `FINAL_RELEASE_APPROVED`.
