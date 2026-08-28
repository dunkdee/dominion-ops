# Alpaca PAPER Read-Only Bridge

Additive, governed, server-side bridge that reads **Alpaca paper account** state
and serves it through an authenticated, phone-safe Dominion endpoint.

It stops before any live-trading capability. There is no order-execution code
path anywhere in the bridge, and `live_trading` remains a blocked capability in
`governance/runtime_activation_gates.json`.

---

## What it exposes

All routes are `GET`, all under `/api/trading/paper`, all require the
`X-Dominion-Key` header.

| Route | Content |
|---|---|
| `/health` | Bridge config, ledger state, activation state. No broker call. |
| `/summary` | Consolidated phone view: equity, buying power, P&L, positions, order counts, win/loss, drawdown, strategy performance, bot health. |
| `/account` | Equity, buying power, cash, portfolio value, day-trade count, session P&L. |
| `/positions` | Open positions with unrealized P&L. |
| `/orders` | Open and closed orders. |
| `/fills` | Fill activities. |
| `/history` | Closed round trips (FIFO-matched from fills). |
| `/performance` | Realized/unrealized P&L, win/loss metrics, drawdown, per-symbol performance. |
| `/evidence` | Verification state of the append-only observation chain. |

The unauthenticated `/health` probe gained one field, `trading_bridge`, which
reports mount and governance state only — never account data.

---

## Safety properties

| Property | How it is enforced |
|---|---|
| Paper only | Base-URL host allow-list. `api.alpaca.markets` is refused by name. |
| HTTPS only | Non-`https` schemes rejected. |
| Read only | Every call is `GET` against a fixed five-endpoint allow-list. No `POST`/`PUT`/`PATCH`/`DELETE` string exists in the bridge modules; CI greps for them. |
| No order execution | No submit, cancel, replace, or liquidate code path exists. |
| Credentials server-side | Read from the process environment, sent only in outbound Alpaca headers, never serialized into a response. Every payload is scanned before it is emitted. |
| Authenticated | `X-Dominion-Key`, constant-time compare, minimum 24 characters. |
| Fails closed | Missing or weak server key returns `503`, not open access. Missing credentials return a truthful "not connected" envelope with nulls, never fabricated zeros. |
| Tamper-evident | Every observation is appended to the canonical hash-chained ledger. |
| Live service preserved | The router is additive and its import is guarded, so a bridge fault cannot stop the Command Center from serving its existing surfaces. |

---

## Evidence

Each observation appends one record to the existing append-only, hash-chained
evidence ledger, using `control_plane.ledger.AppendOnlyLedger` directly — the
chain implementation is reused, not reimplemented.

- Default path: `/runtime/ledger/alpaca-paper-observations.jsonl`
- Event type: `alpaca_paper_readonly_observation`
- Payload: governance flags, aggregate figures, and `snapshot_sha256` binding
  the record to the exact snapshot served. No credentials, no raw broker bodies.

Verify with the same tool as every other Dominion record:

```bash
python3 -m control_plane.cli verify-ledger \
  --ledger /home/malachisingleton8/.dominion/ledger/alpaca-paper-observations.jsonl
```

---

## Metric parity with the live engine

The Dominion Alpha paper engine already computes win rate, profit factor, and
expectancy for its dashboard. `tests/test_alpaca_bridge_live_parity.py` loads
`alpha_engine/dominion_alpha/performance.py` as shipped and runs both
implementations over identical closed trades, so the phone cannot drift from
the dashboard.

Two divergences are deliberate and pinned by test:

1. **Breakeven trades.** The live engine folds a zero-P&L trade into losses
   (`pnl <= 0`). The bridge reports `breakeven` separately so the loss count is
   not inflated.
2. **Undefeated profit factor.** The live engine emits the sentinel `999.0` when
   there are no losses. The bridge emits `null`, so the phone never shows a
   sentinel as if it were a measured ratio.

With no trades at all, the live engine reports `0.0` rates; the bridge reports
`null`, so a `0%` win rate is never displayed as a measured result.

---

## Deployment

The Command Center build context is `apps/command-center`, so the shared
`control_plane` package is supplied by a read-only mount — the same pattern
already used for `governance/lane_access_policy.json`.

`docker-compose.command-center.yml` adds:

```yaml
volumes:
  - ./control_plane:/app/control_plane:ro
  - ${COMMAND_CENTER_LEDGER_DIR:-/home/malachisingleton8/.dominion/ledger}:/runtime/ledger
```

If that mount is missing, the bridge does not mount and `/health` reports
`trading_bridge.mounted: false` with the reason. The verification script treats
that as a failure, so a silent no-op deployment cannot pass.

---

## Verification

Safe to run before and after deployment; issues only `GET` requests.

```bash
COMMAND_CENTER_API_KEY='<phone key>' \
  ./scripts/verify_alpaca_paper_bridge.sh http://127.0.0.1:8091
```

Exits non-zero unless every governed assertion holds.

---

## Rollback

The change is additive. Three levels, least disruptive first.

### 1. Disable the surface without redeploying (seconds)

Unset the phone key and restart the container. Every trading route returns
`503`; nothing else is affected.

```bash
# in ~/.config/dominion/command-center.env
COMMAND_CENTER_API_KEY=
```

```bash
docker compose -f docker-compose.command-center.yml up -d dominion-command-center
./scripts/verify_alpaca_paper_bridge.sh http://127.0.0.1:8091   # [1] must still pass
```

### 2. Revoke broker access (seconds)

Clear the paper credentials and, in the Alpaca dashboard, regenerate the paper
API key. The surface then serves a truthful "not connected" envelope.

```bash
ALPACA_PAPER_KEY_ID=
ALPACA_PAPER_SECRET_KEY=
```

### 3. Full code rollback (one deploy)

```bash
git revert <merge-or-commit-sha>
docker compose -f docker-compose.command-center.yml build dominion-command-center
docker compose -f docker-compose.command-center.yml up -d dominion-command-center
curl -fsS http://127.0.0.1:8091/health | python3 -m json.tool
```

Nothing pre-existing was modified beyond three additive edits — the guarded
router import, the `include_router` call, and the `trading_bridge` health field
— so reverting restores the prior Command Center exactly.

The observation ledger is append-only and is **not** removed by rollback.
Retain it as evidence. Deleting it would break the chain's continuity.

### What rollback does not need to touch

- The Dominion Alpha engine: never modified, never restarted by this change.
- The trading lane's governance gates: `live_trading` was blocked before this
  change and is blocked after it.

---

## Remaining activation step

The bridge is built, tested, and mounted, but serves no broker data until the
Founder supplies credentials server-side. **No code change is required to
activate, and no configuration can enable live trading.**

On the Foundation VM, in `~/.config/dominion/command-center.env` (mode `600`):

```bash
COMMAND_CENTER_API_KEY=<32+ random chars, kept on the phone only>
ALPACA_PAPER_KEY_ID=<Alpaca PAPER key id>
ALPACA_PAPER_SECRET_KEY=<Alpaca PAPER secret>
```

Then:

```bash
docker compose -f docker-compose.command-center.yml up -d dominion-command-center
COMMAND_CENTER_API_KEY='<phone key>' ./scripts/verify_alpaca_paper_bridge.sh
```

Expect `activation_state: ready` and `RESULT: OK`.

Use a **paper** key pair. A live key pair would still be refused by the host
allow-list, but it must not be placed on the VM at all.
