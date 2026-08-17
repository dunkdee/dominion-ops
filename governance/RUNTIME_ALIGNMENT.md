> [!WARNING]
> **Superseded as an active runtime declaration on 2026-08-15.** This historical Stage-2 narrative is not authorization to run deployments or to re-enable any service. The verified recovery checkpoint is [2026-08-15-containment-record.md](runtime/2026-08-15-containment-record.md). Live state must be re-proven before action.

# Dominion Production Runtime Alignment

**Initial snapshot:** 2026-07-21 19:32 UTC  
**Initial source:** `Production Ecosystem Audit` run `29861920503`  
**Stage-1 verification:** run `29862504700`  
**Stage-2 ownership map:** run `29863614231`  
**Stage-2A verification:** run `29864120927`  
**Stage-2B reconciliation map:** run `29864574740`  
**Stage-2C preparation:** run `29866812526`  
**Stage-2D preflight veto:** run `29867278124`  
**Stage-2D-R trace:** runs `29868756275`, `29869539712`  
**Stage-2D-R3 persistent retirement:** run `29874133137`  
**Stage-2D-R4 final preflight:** run `29879295855`  
**Stage-2E exact cutover map:** run `29880455592`  
**Stage-2F failed cutover:** run `29883264403`  
**Stage-2F-R1 Baby recovery:** run `29885228305`  
**Operating order:** Cash flow → Systems → Scale

## Executive determination

The systemd control plane remains stable and governed. Retired Alchemist, Conductor, and Juris API units and the obsolete port healer remain persistently masked. Approval-gated publishing timers remain disabled.

Stage 2F failed closed when the canonical Wix Agent did not pass `/ready`. The rollback restored Wix data and the original Wix and Dominion Web services. The original Baby API could not recover because its `/app` bind mount referenced the vanished `/home/malachisingleton8/desktop-tutorial/api` source path.

Stage 2F-R1 successfully restored Baby API using the already-tested canonical image and release mount. Baby API now runs under Compose project `dominion-ops`, is healthy on port 8080, has zero restarts, and uses the approved canonical release source. The failed original container remains preserved locally for diagnosis.

No full-stack cutover retry is authorized. The next action is an isolated Wix reproduction and correction that cannot modify the healthy production Wix container or its live volumes.

## Current production status

| Component | Current evidence | Mode |
|---|---|---|
| Baby API | HTTP 200 on port 8080; canonical `dominion-ops` ownership; approved image; zero restarts | Production support |
| Wix Agent | HTTP 200 on `127.0.0.1:8082/ready`; original manually managed image | Record-only |
| Dominion Web | HTTP 200 on port 8090; original `desktop-tutorial` ownership | Production |
| n8n | HTTP 200 on `127.0.0.1:5678/healthz` | Approved automation only |
| Alpha Engine | HTTP 200 on `127.0.0.1:8787/health` | Paper-only |
| Conductor | HTTP 200 on `127.0.0.1:5060/health` | Observe and route |
| Caddy, Gatekeeper, Store, Guardian, Sentinel, Juris, Alchemist, Gemini | Active under existing controls | Protected |

## Durable containment

- `alchemist-api.service`, `conductor-api.service`, `juris-api.service`, and `dominion-port-healer.service` remain persistently masked and inactive.
- Root-only unit recovery copies remain at `/var/lib/dominion/unit-retirement/stage2d-r3-29874133137`.
- Approval-gated publisher timers remain inactive and disabled.
- The surplus scraper remains quarantined.
- Browser Agents and Obsidian remain inactive.

## Canonical release and recovery assets

- Approved source: `10646094aa3a5a1e0d4d18dc5508a33d2f5ec2a3`.
- Release root: `/home/malachisingleton8/dominion-releases/dominion-ops-10646094aa3a`.
- Compose SHA-256: `42e2e90c41e9c154bf96f3ba2dc277811f873626af41b747474fcea6a494c8eb`.
- Release `.env` remains local with mode `0600`; values were not uploaded or reported.
- Stage-2C recovery root: `/home/malachisingleton8/.dominion-recovery/stage2c-29866812526`.
- Stage-2F local cutover root: `/var/lib/dominion/cutovers/stage2f-29883264403-1`.
- Quiescent Wix data and log archives exist locally with mode `0600`; Wix data was restored during rollback.
- Baby recovery root: `/var/lib/dominion/cutovers/stage2f-baby-recovery-29885228305-1`.
- Failed original Baby API preserved as `baby-api-failed-stage2f-29885228305-1`.

## Stage-2F failure evidence

- Canonical Baby API and Dominion Web passed service-level migration checks before Wix migration.
- Canonical Wix Agent failed its `/ready` health gate.
- The new Baby API, Dominion Web, and Wix containers were removed by rollback.
- Original Dominion Web and Wix Agent returned HTTP 200 after rollback.
- Original Baby API entered a restart loop because the old bind source path was missing.
- Unaffected container identities remained unchanged.
- No databases, DNS, network definitions, volume definitions, repository checkout, secret values, or customer data were changed or collected.

## Stage-2F-R1 verified recovery

- Original failing Baby API container was preserved, not deleted.
- Canonical image ID: `sha256:089445475d96ca3630fd4821af3c0304d38de5ece89a529b3782a398e38c3c82`.
- Compose ownership: project `dominion-ops`, service `baby-api`.
- `/app` bind source: `/home/malachisingleton8/dominion-releases/dominion-ops-10646094aa3a/api`.
- `/vault` bind source: `/home/malachisingleton8/vault`.
- Production network ID matched the Stage-2E map.
- Port 8080 was restored on IPv4 and IPv6 public bindings.
- Container health is healthy, restart count is zero, and the 60-second stability check passed.
- Wix, Dominion Web, n8n, Alpha Engine, and Conductor remained HTTP 200.
- Retired units remained masked and publishing timers remained disabled.
- The one-time Baby recovery workflow was removed after verification.

## Current engineering action

### Stage 2F-W1 — Isolated Wix diagnosis

The next diagnostic must:

1. Reproduce the approved Wix image under an isolated Compose project and loopback test port.
2. Use temporary copied Wix data and log volumes; never attach production volumes read/write.
3. Use the local release environment without reporting values.
4. Classify bounded startup and health failure signals without publishing raw logs.
5. Remove all isolated containers, networks, and temporary volumes after the test.
6. Verify production Wix, Baby API, Dominion Web, n8n, Alpha, and Conductor remain HTTP 200.
7. Keep the full cutover disabled until the canonical Wix image passes isolated `/ready` and stability verification.

## Blocked operations

Until Wix diagnosis and correction pass:

- No full-stack cutover retry.
- No deletion of failed, rollback, recovery containers, or local Wix archives.
- No reset or deletion of the old VM checkout.
- No Browser Agents or Obsidian activation.
- No n8n, PostgreSQL, SEO, or Movie Generator migration.
- No production publishing, live trading, or surplus claimant contact.

## Stage sequence

### Stage 1 — Stabilize — COMPLETE

### Stage 2 — Unify control — ACTIVE

- Supervisor containment — complete.
- Approval-timer enforcement — complete.
- Boot persistence — complete.
- Deployment reconciliation map — complete.
- Parallel immutable release preparation — complete.
- Persistent retirement — complete.
- Independent gate and isolated-build preflight — complete.
- Exact cutover and rollback map — complete.
- Guarded full cutover — failed closed.
- Baby API emergency recovery — complete.
- Isolated Wix diagnosis and correction — active.

### Stage 3 — Prove vertical duties

Blocked until Stage 2 returns to a stable, verified state.

### Stage 4 — Scale

Scale remains prohibited until relevant Stage-3 exit gates are evidenced and recorded.