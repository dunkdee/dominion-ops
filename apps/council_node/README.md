# Dominion Council Node

Governed orchestration under **RADAH MEMSHALAH**. A bounded subsystem inside
`dominion-ops` — it adds a control plane and changes no existing service.

> **Status: BUILT, NOT DEPLOYED.** Phases 1–5 are implemented and tested. No
> Oracle VM has been provisioned and nothing here runs in production. Treat
> every claim below as "the code does this", not "this is running".

---

## Inventory findings (required before code, work order §29)

The work order asked for an inventory of existing architecture first. Six
findings changed what got built.

### 1. The Council and authority model already exist

`governance/five_council_policy.json` and `governance/authority_matrix.json`
already define councils, veto domains, risk levels and approval thresholds —
and in more detail than the work order's §9 sketch. The names map cleanly:

| Work order §9 | Existing file |
| --- | --- |
| Truth Council | `truth_evidence` |
| Security Council | `security_risk` |
| Reliability Council | `engineering_reliability` |
| Business Council | `business_human_impact` |
| Governance Council | `law_governance` |

**Decision:** the Council Node *binds* to those files. It does not ship
`dominion_constitution.json` or `council_release_policy.json` as §6 lists,
because doing so would create the second source of truth rule 15 forbids.
`governance/council_node_policy.json` records the bindings explicitly.

### 2. A capability registry already exists

`buddy_core/config/capability_registry.json` (v2.1.0) already carries
`id`, `classification`, `auth_required` and `enabled` per capability. The
Council Node reads it rather than defining a rival registry.

### 3. Every deployed service uses SQLite, not PostgreSQL

Publisher, revenue-runtime, wix-agent and video-studio are all SQLite. The
only PostgreSQL consumer in the repo is `ascendant_store`, which is not
deployed anywhere.

**Decision, and a deliberate divergence:** memory uses SQLite behind a narrow
interface (`write` / `search` / `expire`). The work order specifies PostgreSQL
+ pgvector, and the interface is kept small precisely so that backend can
replace it without touching callers — but adopting Postgres now would make
this the first service in the estate to need it, for a subsystem with no data
yet. Compose still provisions Postgres for when semantic search is real.
**This is the one place the build knowingly departs from the spec.**

### 4. The Foundation VM is GCP, not Oracle

`watchdog.yml` targets the `dominion-ascendant` GCP project. The Oracle VM is
a *new, separate* host. Nothing here touches the existing Foundation VM or
the Publisher running on it.

### 5. Receipts already have a shape

`apps/dominion_publisher/models.py:PublishReceipt` uses
`receipt_id` / `status` / `observed_at` / evidence hashes. The Council Node
receipt is a superset with the same vocabulary, so the two read alike.

### 6. Deployment conventions exist and are followed

`deploy/systemd/*.service` uses `NoNewPrivileges`, `ProtectSystem=strict`,
`Restart=on-failure`. `deploy/Caddyfile` terminates TLS and reverse-proxies.
The Council Node unit and Caddyfile follow both.

---

## Dependency and regression impact note

**Files changed outside `apps/council_node/` and `deploy/council-node/`:**
three *new* files in `governance/`. No existing file is modified anywhere in
the repository.

| Risk | Assessment |
| --- | --- |
| Existing services | **None.** No shared module is edited. Publisher, revenue-runtime, command-center and buddy_core are untouched. |
| Governance files | **Read-only.** The Council Node reads `authority_matrix.json`, `five_council_policy.json` and the capability registry. It never writes them. |
| Test suite | Additive. 86 new tests; the existing suite is unchanged. |
| Runtime | Nothing starts. No systemd unit is installed, no container is built, no port is bound by this merge. |
| Rollback | Deleting the three new directories fully reverts the subsystem. |

**The one coupling to know about:** `app/deps.py` reads
`buddy_core/config/capability_registry.json` by relative path. If that file
moves, the Council Node fails to start — loudly, at construction, not
silently at request time.

---

## What Phases 1–5 actually deliver

| Phase | Delivered | Proven by |
| --- | --- | --- |
| 1 Foundation | compose, Caddyfile, systemd unit, idempotent Oracle bootstrap | `bash -n`, manual review |
| 2 Governance | constitution loader, capability gate, policy evaluator, Founder gate, release gate | `test_fail_closed.py`, `test_governance.py`, `test_founder_gate.py` |
| 3 Orchestrator | task intake, state machine, executor, agent registry, receipts | `test_executor.py`, `test_receipts.py` |
| 4 Memory | layered store, working-memory expiry, write-time secret rejection | `test_secret_redaction.py`, memory tests |
| 5 Scheduler | 3-hour sweep, stale detection, recovery proposals, sweep receipts | `test_scheduler_369.py` |

### Design decisions worth knowing

**UNKNOWN blocks.** An action with no declared risk level returns `UNKNOWN`,
not `low`. Something nobody classified has not been approved by anyone.

**Refusals get receipts too.** The executor writes a receipt on every outcome
including denials and crashes. A blocked action with no record would be an
action with no attribution.

**The router refuses rather than leaks.** Outbound prompts are redacted, then
re-scanned. If a secret shape survives, the call raises instead of sending.
Failing a task is recoverable; leaking a credential to a third party is not.

**The sweep cannot mutate.** It holds no handles that could publish, trade,
spend, or delete. `SweepResult.mutations` is always empty and asserted so.

**Advisory means advisory.** An agent registered as advisory never executes,
even when policy would allow the capability.

---

## Running the tests

```bash
python -m pytest apps/council_node/tests/ -q     # 86 tests
python -m pytest -q                              # full repository suite
```

## Deploying (not yet done)

```bash
sudo deploy/council-node/scripts/install_oracle_vm.sh   # idempotent bootstrap
# populate /etc/dominion/council-node/service.env
sudo systemctl enable --now dominion-council-node
deploy/council-node/scripts/verify.sh                   # Gate 8 exposure checks
```

`verify.sh` asserts Postgres, Redis and Ollama are **not** publicly reachable.
A deploy that published those ports fails verification rather than passing.

## Known gaps before Definition of Done (§33)

- Phases 6–9 are not built (external council adapters beyond the two model
  adapters, Dominion integrations, command centre, closure evidence).
- pgvector semantic retrieval is not implemented; search is lexical.
- No restore test has been run, so backups are not yet valid by §22.
- Lanes are seeded in-process; they are not yet persisted to the canonical DB.
