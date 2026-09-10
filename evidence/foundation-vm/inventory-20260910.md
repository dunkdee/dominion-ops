# foundation-vm runtime inventory — 2026-09-10

Source: workflow `foundation-vm-inventory.yml`, run **34448533182**, job
**102778639794**, conclusion `success`. Dispatched with `confirm: INVENTORY
FOUNDATION VM`.

- Collected at merged SHA `9e29367efc5bdd0efc30c7d83122bff0a785d52a`.
- Artifact `foundation-vm-inventory`, ID **10140582146**, 3056 bytes.
  Uploaded-zip SHA-256 `77c1fbc09b4b01e72ff3de800e4ceab856f7b46448dd7e77b16ea22ba6e2ca68`.
- `collected_at=2026-09-10T07:09:14Z`, `hostname=foundation-vm`,
  `uptime=up 13 weeks, 3 days, 17 hours, 24 minutes`.
- Gate `INVENTORY_SCRIPT_READONLY=VERIFIED` passed before connection.
- Script reported **`MUTATIONS_PERFORMED=0`**.

The VM username is redacted by GitHub throughout (`/home/***/`). No secret
value was read: env files were reduced to key names only.

## What this inventory can and cannot prove

`ss` was run **without `-p`**, deliberately, so no process-to-port mapping was
captured. Therefore:

- Unit state and container state are **VERIFIED** — read directly.
- Published container ports are **VERIFIED** — read from `docker ps`.
- Every systemd service's port is **INFERRED** at best: the repository declares
  it and the port is listening, but nothing here proves that unit holds it.
- The health-probe labels below were chosen by the inventory script in advance.
  A probe proves *something answers on that port*, never *which unit answers*.

## Findings that require a decision

### 1. Containment breach on TCP 11435

`governance/system_integrity_agent.json` declares `absent_listeners: [11435]`,
and `scripts/system_integrity_agent.py:152` fails `hold:port:11435` whenever a
listener is present. The 2026-08-15 containment record accepted "no listener on
TCP 11435" as the acceptance evidence that Nemotron was contained.

**`127.0.0.1:11435` is listening.** `dominion-nemotron.service` does not appear
in the unit list at all, so the listener is running outside the unit that was
disabled, and its identity is UNKNOWN. No work order re-enabled it.

### 2. The agent that enforces containment is failed

`dominion-system-integrity.service` is `load=loaded active=failed sub=failed`.
That is the process that checks active units, containment holds and
`absent_listeners`. While it is down, none of those invariants are enforced —
which is why finding 1 went unreported.

### 3. Port 8200 is occupied — Council Node would collide

`0.0.0.0:8200` is listening, owner unidentified.
`deploy/council-node/docker-compose.yml` sets `COUNCIL_BIND_PORT: "8200"` and
both `deploy/council-node/scripts/deploy.sh` and `verify.sh` health-check
`127.0.0.1:8200/health`. A Council Node deploy to foundation-vm collides today.

### 4. Caddy forwards to a dead upstream

`/etc/caddy/Caddyfile` carries `reverse_proxy 127.0.0.1:5120`. Port 5120 is not
in the listening set. Traffic on that route gets a gateway error.

### 5. Two storefronts, neither from a governed release path

`ascendant-store.service` and `dominion-store.service` are both active (5090
and 5080). The probe on 5090 returned **200**, so a storefront is already
serving — yet `~/.dominion/ascendant-store/runtime/release` and
`~/.dominion/ascendant-store/runtime.env` are both **ABSENT**. The running
code's deployment source is unproven and is not the governed release path.

### 6. Two active units claim port 5055

`PORT_MANIFEST[5055]` reads `juris`, annotated "gemini-server removed", and
`dominion-juris.service` is active. But `gemini-server.service` is **also
active**, and `SERVICES['gemini-server']` still claims 5055 as critical.

### 7. All-interface binds behind cloud-firewall-only protection

`auric_edge` (9380), the ops dashboard (5100) and the Twilio router (5102) bind
`0.0.0.0`. The containment record closed raw ingress by deleting GCP firewall
rules, and states the Twilio router "remains reachable only locally". The host
still binds all interfaces, so that property rests on the cloud firewall alone.

## Corrections to earlier claims in this session

| Earlier claim | Evidence |
| --- | --- |
| Alchemist :5050 has no repository reference; owner UNKNOWN | **Wrong.** `buddy_core/sentinel.py` declares `PORT_MANIFEST[5050]="alchemist"` and `SERVICES["alchemist-api"]` with `critical: True`; `dominion-alchemist.service` is active/running. |
| AuricEdge :9380 has no repository reference; owner UNKNOWN | **Wrong.** `buddy_core/sentinel.py` declares `PORT_MANIFEST[9380]="auric-edge"`; `auric_edge.service` is active/running. |
| Storefront Stripe credentials are missing | **Wrong.** `~/.env` is mode 600 with 71 keys including `STRIPE_SECRET_KEY`, `STRIPE_PUBLISHABLE_KEY`, `STRIPE_WEBHOOK_SECRET` and `DB_PASSWORD`. |
| dominion-web serves port 3000 | **Wrong.** The container publishes `0.0.0.0:8090->80`. Host `127.0.0.1:3000` is `dominion-dashboard` per `PORT_MANIFEST[3000]`. |
| wix-agent serves port 8090 | **Wrong.** The container publishes `127.0.0.1:8082->8000`. |
| nemotron-worker is PRODUCTION/VERIFIED on 11435 | **Inverted.** 11435 is under a containment hold that is currently violated. |
| The registry needed 7 → 22 services | **Understated.** The reconciled count is 62. |

## Containers (11 running)

| Container | Image | Uptime | Published ports |
| --- | --- | --- | --- |
| dominion-db | postgres:15 | 2 weeks | 127.0.0.1:5432→5432 |
| dominion-n8n | n8nio/n8n:latest | 2 weeks | 0.0.0.0:5678→5678 |
| dominion-seo | dominion-seo:latest | 2 weeks | none |
| movie-generator | movie-generator | 2 weeks | 0.0.0.0:8001→8000 |
| dominion-command-center | dominion-ops-dominion-command-center | 4 days (healthy) | none |
| obsidian-remote | lscr.io/linuxserver/obsidian:latest | 4 days (healthy) | 127.0.0.1:8083→3000 |
| dominion-web | dominion-ops-dominion-web | 3 days | 0.0.0.0:8090→80 |
| wix-agent | dominion/wix-agent:local | 3 days (healthy) | 127.0.0.1:8082→8000 |
| browser-agents | dominion-ops-browser-agents | 3 days (healthy) | 0.0.0.0:8081→8000 |
| baby-api | dominion-ops-baby-api | 3 days (healthy) | 0.0.0.0:8080→8080 |
| baby-logger | alpine:latest | 3 days | none |

## Dominion systemd units — active/running (33)

ascendant-store, auric_edge, buddy-bridge, conductor-scheduler,
conductor-worker, covenant-watchdog, dominion-3d-dashboard,
dominion-alchemist, dominion-alpha, dominion-buddy-web,
dominion-command-deck, dominion-conductor, dominion-dashboard,
dominion-email-drip, dominion-gatekeeper, dominion-guardian, dominion-juris,
dominion-mcp-cli, dominion-monitor, dominion-n8n-watchdog,
dominion-ops-dashboard, dominion-proposal-queue, dominion-publisher,
dominion-report, dominion-revenue-runtime, dominion-review-queue,
dominion-sentinel, dominion-store, dominion-surplus-dashboard,
dominion-twilio-router, gemini-server, ollama, syncthing@\*\*\*.

## Dominion systemd units — failed (1)

`dominion-system-integrity.service` — `active=failed sub=failed`. See finding 2.

## Dominion systemd units — inactive/dead, timer-driven (12)

dominion-backup, dominion-command-center-state, dominion-executor,
dominion-healthcheck, dominion-intel, dominion-mission-runner,
dominion-overseer, dominion-paper-trade, dominion-radah-autopilot,
dominion-revenue-evaluator, dominion-trade-report, dominion-watchdog.

`dominion-growth-engine.timer` is registered, but no
`dominion-growth-engine.service` appears in the unit listing — UNKNOWN.

## Health probes (loopback)

Labels are the script's own; a result proves only that something answers.

| Port | Label probed | Result |
| --- | --- | --- |
| 5060 | conductor | 200 |
| 5050 | alchemist | **501** |
| 9380 | auricedge | **404** |
| 5000 | gatekeeper | 200 |
| 5052 | buddy_bridge | 200 |
| 5090 | ascendant_store | 200 |
| 5112 | dominion_publisher | 200 |
| 8790 | revenue_runtime | 200 |
| 5678 | n8n | 200 |
| 3000 | dominion_web | 302 |
| 8001 | baby_api | **404** |
| 8090 | wix_agent | 200 |

501 on 5050 and 404 on 9380 mean the process is alive but publishes no health
contract. The 8090 probe was labelled `wix_agent` but 8090 is `dominion-web`.

## Listening TCP ports

Public (`0.0.0.0` / `*`): 22, 80, 443, 5000, 5052, 5055, 5070, 5080, 5090,
5095, 5100, 5101, 5102, 5103, 5110, 5355, 5678, 8001, 8080, 8081, 8090, 8100,
8200, 8787, 8888, 9380, 20201, 20202, 22000.

Loopback: 25, 2019, 3000, 5050, 5056, 5060, 5112, 5432, 8082, 8083, 8091,
8099, 8384, 8390, 8790, 11434, 11435. Plus `127.0.0.53%lo:53`,
`127.0.0.54:53`, `[::1]:25`, `[::]:22`.

**No owner identified for:** 5056, 5103, 5110, 8200, 8390, 8888, 20201, 20202.

## Deployed revisions

| Path | Revision |
| --- | --- |
| `~/.dominion/publisher/runtime/release` | NOT_A_GIT_CHECKOUT |
| `~/.dominion/ascendant-store/runtime/release` | **ABSENT** |
| `~/.dominion/revenue-runtime/runtime/release` | **ABSENT** |
| `~/dominion` | NOT_A_GIT_CHECKOUT |
| `~/dominion-ops` | `02334320b73366336a8ac9173df164481c84c37a` (stale) |

## Configuration presence (key names only; no value was read)

- `~/.dominion/publisher/runtime.env` — mode 600, 3 keys:
  `DOMINION_PUBLISHER_OPERATOR_TOKEN`, `DOMINION_PUBLISHER_DB`,
  `DOMINION_PUBLISHER_VAULT`.
- `~/.dominion/ascendant-store/runtime.env` — **ABSENT**.
- `~/.dominion/revenue-runtime/runtime.env` — **ABSENT**.
- `~/.env` — mode 600, **71 keys**, including `STRIPE_SECRET_KEY`,
  `STRIPE_PUBLISHABLE_KEY`, `STRIPE_WEBHOOK_SECRET` and `DB_PASSWORD`.

## Reverse proxy

`/etc/caddy/Caddyfile` serves 16 sites under `dominionhealing.org`: apex, dash,
api, n8n, agent, store, tools, buddy, shop, report, surplus, empire, hub,
tiktok, vault, command.

Numeric upstreams: 3000, 5000, 5055, 5070, 5080 (×2), 5095, 5101 (×2), 5120,
5678, 8100. Matcher-based routes: `@dominion_publisher_meta_callback`,
`@dominion_revenue_public`, `@buddy`, `@store_api`, `@lead`, `@api`,
`@vault_path`, `@not_acme`.

## PostgreSQL

`psql` is **NOT INSTALLED on the host**. The server runs inside the
`dominion-db` container, published at `127.0.0.1:5432`. Any host-side script
that shells out to `psql` fails on this VM as it stands.

## Systemd timers registered

dominion-system-integrity, dominion-executor, dominion-mission-runner,
dominion-command-center-state, dominion-watchdog, dominion-healthcheck,
dominion-revenue-evaluator, dominion-radah-autopilot, dominion-intel,
dominion-paper-trade, dominion-backup, dominion-trade-report,
dominion-growth-engine, dominion-overseer.
