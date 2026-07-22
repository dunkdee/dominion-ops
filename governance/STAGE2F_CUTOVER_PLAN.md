# Stage 2F — Guarded Canonical Compose Cutover

**Authority:** Dewayne Singleton — human final decision-maker  
**Change class:** Controlled production ownership migration  
**Required authorization:** `CUTOVER_STAGE_2F`  
**Canonical release:** `/home/malachisingleton8/dominion-releases/dominion-ops-10646094aa3a`  
**New Compose project:** `dominion-ops`

## Objective

Move Baby API, Baby Logger, Dominion Web, and Wix Agent from split/orphaned ownership into the canonical `dominion-ops` Compose project without deleting the current containers, changing secrets, creating new Wix data volumes, or altering unrelated production services.

## Verified source evidence

- Stage-2D-R4 run `29879295855` passed runtime, secrets, deployment, rollback, governance, agent-runtime, isolated-build, and post-build-stability gates.
- Stage-2E run `29880455592` captured the exact current image IDs, container IDs, ports, mounts, restart policies, Compose labels, production network, and Wix volume names.
- The live `desktop-tutorial` Compose manifest path no longer exists.
- Baby API, Baby Logger, and Dominion Web retain `desktop-tutorial` labels.
- Wix Agent is manually managed but uses the same production network.

## Approved new images

| Service | Approved image | Image ID |
|---|---|---|
| Baby API | `dominion-stage2d-r4-baby-api:latest` | `sha256:089445475d96ca3630fd4821af3c0304d38de5ece89a529b3782a398e38c3c82` |
| Dominion Web | `dominion-stage2d-r4-dominion-web:latest` | `sha256:77583ed35a7537206aeae97e97fa015f21d9d3b112a3885ca50e6cdd1cc03847` |
| Wix Agent | `dominion/wix-agent:stage2d-r4-10646094aa3a` | `sha256:ef792a2ac99184cd51192becb7ead9d0ef3b5347a57b5f41eba6ce5bd834292e` |
| Baby Logger | `alpine:latest` | Existing verified image ID retained |

## Preserved production resources

- Network: `desktop-tutorial_default`
- Wix data volume: `wix_agent_data_a33ce2044d95-29785123140-1`
- Wix logs volume: `wix_agent_logs_a33ce2044d95-29785123140-1`
- Baby API vault mount: `/home/malachisingleton8/vault`
- Release `.env`: local, regular file, mode `0600`, hash-gated

No environment value, secret content, customer data, or volume content is included in GitHub reports.

## Execution sequence

For each target service:

1. Verify the exact current container ID and image ID from Stage 2E.
2. Verify the exact approved replacement image ID.
3. Stop the current container.
4. For Wix Agent, create root-only quiescent archives of the data and log volumes.
5. Rename the current container to a run-specific rollback name.
6. Set its restart policy to `no` and disconnect it from the production network.
7. Create the new container through the canonical `dominion-ops` Compose project using the existing network and Wix volumes.
8. Verify image ID, Compose ownership, port contract, mounts, network, security settings, and health before proceeding.

Expected interruption is limited to the service-by-service stop, rename, and replacement interval. Parallel host-port binding is impossible because ports 8080, 8082, and 8090 are already occupied.

## Automatic rollback

Any failed gate triggers rollback:

1. Remove newly created target containers.
2. Rename the preserved originals back to their production names.
3. Restore the Wix data volume from the quiescent local archive when Wix was migrated.
4. Reconnect exact production-network aliases.
5. Restore original restart policies.
6. Start the original containers.
7. Re-run all protected HTTP health checks.

Original containers are never deleted during Stage 2F. Full original `docker inspect` records and Wix volume archives remain in a root-only VM cutover directory and are not uploaded.

## Acceptance gates

Stage 2F succeeds only when:

- All four target containers run under Compose project `dominion-ops`.
- Exact approved image IDs are active.
- Baby API remains publicly bound on port 8080.
- Dominion Web remains publicly bound on port 8090.
- Wix remains loopback-only on `127.0.0.1:8082`.
- Wix reuses the exact existing data and log volumes.
- Baby API mounts the canonical release source and existing vault.
- Wix remains read-only, capped at 512 MB and 1 CPU, PID-limited, capability-dropped, and `no-new-privileges` protected.
- Baby API, Wix, Dominion Web, n8n, Alpha Engine, and Conductor return HTTP 200.
- Canonical systemd services record zero new restarts during the post-cutover hold.
- Retired units remain persistently masked.
- Publishing timers remain inactive and disabled.
- Unrelated containers retain the same IDs, images, and states.
- No rollback occurs.

## Explicit exclusions

Stage 2F does not:

- Start Browser Agents or Obsidian.
- Migrate n8n, PostgreSQL, SEO, or Movie Generator.
- Delete the old VM checkout.
- Change DNS or Caddy.
- Enable publishing.
- Enable live trading.
- Contact surplus claimants or file documents.
- Delete preserved rollback containers.

## Post-cutover hold

After successful verification, preserved rollback containers and local volume archives remain in place until a separate cleanup authorization is recorded. Stage 2G will reconcile remaining unmanaged containers, harden resource limits, and perform a non-production restore proof.