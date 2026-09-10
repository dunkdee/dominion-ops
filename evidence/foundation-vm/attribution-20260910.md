# foundation-vm listener attribution — 2026-09-10

Source: workflow `foundation-vm-attribution.yml`, run **34458046789**, job
**102808985768**, conclusion `success`, at merged SHA `6276661`.

- Artifact `foundation-vm-attribution`, ID **10144310524**, 8055 bytes,
  zip SHA-256 `38f74549dd5629c1ff7b008f11ffaa93ef8bd3fa709034a1cafebf7f6ca5ba7d`.
- `privileged=YES` — full process-to-port mapping was obtained.
- Script reported **`MUTATIONS_PERFORMED=0`**, confirmed by a workflow step.

This run closes the gap the 2026-09-10 inventory left open. Every question it
was built to answer is answered.

## 1. TCP 11435 — a stray `ollama serve`, NOT Nemotron

```
pid=3192050  ppid=1  user=<vm user>
cmdline=/usr/local/bin/ollama serve
exe=/usr/local/bin/ollama
exe_sha256=c05cece87b2e85a525ccf9548d329197b938e58daa46d4fad59e8dab54e8d57d
cgroup=0::/user.slice/user-1000.slice/session-104082.scope
started=Wed Sep  9 21:16:51 2026   bind=127.0.0.1:11435
env_keys include OLLAMA_HOST, SSH_CLIENT, SSH_CONNECTION, MOTD_SHOWN, XDG_SESSION_ID
```

The cgroup is a **user login session scope**, not a systemd service slice, and
the environment carries `SSH_CLIENT`/`SSH_CONNECTION`/`MOTD_SHOWN`. This was
started by hand from an interactive SSH login and reparented to PID 1 when that
session ended. It is a **second** ollama: the governed one is pid 441 under
`ollama.service` on 127.0.0.1:11434.

**Nemotron containment is INTACT.** `dominion-nemotron.service` is
`loaded/inactive/disabled`, its unit file still on disk at
`/etc/systemd/system/dominion-nemotron.service` (Aug 11). `nemotron.service`
and `nemotron-worker.service` are `not-found`.

### Causal timeline, to the second

| Time (UTC) | Event |
| --- | --- |
| 2026-09-09 21:15:40 | `SYSTEM_INTEGRITY_AGENT=PASS cycle=7852 checks=20 defects=0` |
| 2026-09-09 **21:16:51** | `ollama serve` starts on 11435 from an SSH session |
| 2026-09-09 21:17:10 | first `Failed with result 'exit-code'` |

The integrity agent caught it in **19 seconds**.

### Classification: UNAUTHORIZED / ORPHANED

Not a containment regression — the contained unit never came back. Not
expected-but-registry-stale — nothing declares a second ollama. An unmanaged
manual process left running on a port governance reserves.

**The policy is correct and was not stale.** My earlier hypothesis that
`absent_listeners: [11435]` might be the stale artifact is **disproved**: the
rule did exactly its job. The separate `accepted_sources` contradiction
(below) is real but cosmetic and was not the cause.

## 2. dominion-system-integrity.service — HEALTHY, correctly reporting

```
Type=oneshot  RemainAfterExit=no  ExecMainCode=1  ExecMainStatus=2
SYSTEM_INTEGRITY_AGENT=DEGRADED cycle=8320 checks=20 defects=1 deep_probe=true
```

`latest.json`, the agent's own verdict:

```
defect: {'id': 'hold:port:11435', 'detail': 'listener=present',
         'ok': False, 'severity': 'critical'}
```

**Exactly one defect out of twenty checks.** 19 pass, including the deep
intelligence probe. The agent is running every 89 seconds exactly as designed
and returning exit 2 because `Type=oneshot` has no `SuccessExitStatus`, so
systemd renders a DEGRADED verdict as `failed`.

It is not malfunctioning. It is the alarm, and it has been sounding correctly
for 11 hours. Clearing 11435 returns it to PASS with no code change.

### No drift between deployed and reviewed

| Artifact | Live SHA-256 | Repo | Drift |
| --- | --- | --- | --- |
| `system_integrity_agent.py` | `ee4b558c…b75607` | identical | **NONE** |
| `system-integrity-agent.json` | `ee2cde34…4c9d538e` | identical | **NONE** |

The enforced policy *is* the reviewed policy. Live governance fields confirm
`absent_listeners=[11435]`, `cadence_seconds=89`, and
`accepted_sources=["buddy_operator","nemotron"]`.

## 3. TCP 8200 — a 94-day-old production service. Council Node cannot have it.

```
pid=394  cmdline=/usr/bin/node /home/<vm user>/dominion_3d_dashboard/server.js
cgroup=0::/system.slice/dominion-3d-dashboard.service
started=Sun Jun  7 13:45:15 2026   elapsed=94 days   bind=0.0.0.0:8200
```

`deploy/council-node/docker-compose.yml` sets `COUNCIL_BIND_PORT: "8200"` and
both `deploy.sh` and `verify.sh` health-check `127.0.0.1:8200/health`. Deploying
Council Node as configured would collide with a service that has run
continuously since June. **Council Node needs a different port.**

## 4. Storefront :5090 — governed unit, ungoverned source, and unrouted

```
pid=3554281  cgroup=0::/system.slice/ascendant-store.service
cmdline=/home/<vm user>/dominion_env/bin/python3 app.py
cwd=/home/<vm user>/ascendant_store    bind=0.0.0.0:5090
started=Fri Sep  4 01:27:03 2026   elapsed=6 days
FragmentPath=/etc/systemd/system/ascendant-store.service
EnvironmentFiles=/home/<vm user>/.env
```

- Source tree `~/ascendant_store` is **NOT_A_GIT_CHECKOUT**, 4 files. No
  deployed SHA exists. `~/.dominion/ascendant-store/runtime/release` is absent.
- `~/dominion-ops/ascendant_store` is a different tree at stale SHA `0233432`.
- The process environment **does** carry `STRIPE_SECRET_KEY`,
  `STRIPE_PUBLISHABLE_KEY`, `STRIPE_WEBHOOK_SECRET` and `DB_PASSWORD` (key
  names only were read; no value was retrieved).

Live routes: `/` **200**, `/health` **200**, `/success` **200**,
`/healthz` 404, `/products` **404**, `/policies` **404**.

### It is not publicly reachable

The Caddyfile has **no route to 5090 at all**. `store.dominionhealing.org`
proxies to **127.0.0.1:5080**, which is `dominion-store.service` running
`portal/payment_api.py` from `~/buddy_core`, up since **2026-06-22**.

So the public storefront is 5080, and the ascendant store on 5090 is an
internal service no customer can reach. A 200 on 5090 is not revenue.

## 5. TCP 8091 — the command centre, via host networking

```
pid=832467  user=root  cwd=/app
cmdline=/usr/local/bin/python3.12 /usr/local/bin/uvicorn app:app --host 127.0.0.1 --port 8091
cgroup=0::/system.slice/docker-00036fdf93…bb49.scope
parent=containerd-shim-runc-v2
```

`docker inspect dominion-command-center` → `network_mode=host`, `ports=map[]`.
That is why the container publishes nothing yet serves 8091. `/api/status`
returns **200**. Caddy routes both `command.` and `vault.` to it. The integrity
agent's canonical truth source is healthy and correctly attributed.

## 6. Alchemist :5050 and AuricEdge :9380 — both governed units

```
5050  pid=2287851  cgroup=0::/system.slice/dominion-alchemist.service
      cmdline=/home/<vm user>/dominion_env/bin/python alchemist_api.py
      cwd=/home/<vm user>/dominion/agents/health   up 39 days
9380  pid=2201712  cgroup=0::/system.slice/auric_edge.service
      cmdline=/home/<vm user>/dominion_env/bin/python main.py
      cwd=/home/<vm user>/auric_edge   bind=0.0.0.0:9380   up 40 days
      env_keys include AURIC_API_KEY, DATABASE_URL, DB_HOST, DB_NAME, DB_USER
```

Both are real, long-running, systemd-managed. AuricEdge holds its own database
credentials and binds all interfaces. Neither publishes a health contract
(501 and 404) — a documentation and observability gap, not an existence one.

## 7. Previously unattributed ports, now resolved

| Port | Owner |
| --- | --- |
| 20201 | `otelopscol` — Google Cloud Ops Agent OpenTelemetry collector |
| 20202 | `fluent-bit` — Google Cloud Ops Agent |
| 8200 | `dominion-3d-dashboard.service` (node) |
| 8091 | `dominion-command-center` container, host networking |

Still without a unit attribution, though each now has a pid: **5056**
(python3 pid 2199875), **5103** (python pid 3208532), **5110** (python pid
395), **8888** (python3 pid 3779929). UNKNOWN, not absent.

## 8. Caddy upstream 127.0.0.1:5120 — still dead

Referenced twice, including `tiktok.dominionhealing.org`. Nothing listens on
5120 in the full privileged listener map. That route returns a gateway error.

## 9. Open contract inconsistency (cosmetic, not causal)

`governance/system_integrity_agent.json` holds `dominion-nemotron.service` in
`containment_holds` and declares `absent_listeners: [11435]`, while
`intelligence_probe.accepted_sources` still lists `"nemotron"`. Both were
authored together in `727ef72` (2026-08-31); `d184238` (2026-09-01) edited
`accepted_sources` without revisiting the holds. Worth tidying so the contract
does not appear to both forbid and accept the same component. It did not cause
this incident.
