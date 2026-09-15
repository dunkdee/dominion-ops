# ORION Extreme v3.1 Validation Report

Validation date: 2026-08-01

## Passed

- Python syntax compilation: `orion_engine.py`, `orion_production.py`, and `orion_market_scanner.py`.
- Deterministic automated tests: **23/23 passed**.
- TradingView webhook token rejection and authenticated HTTP 202 acceptance.
- Generic market webhook authentication and durable enqueue.
- Private API bearer-token rejection/acceptance.
- Public health endpoint and SQLite integrity check.
- Confirmed-bar gate.
- High-impact-news and operator-pause gates.
- Minimum score, confidence, expected value, regime confidence, freshness, cooldown, hourly cap, open-position cap, loss-streak, daily-loss, and engine-veto gates.
- OTC rejection without a fresh matching broker feed.
- Fresh acceptance price, slippage, actual-payout, and 2% risk cap.
- 75% partial / 25% runner exit tracking.
- Broker outcome separation from model decision.
- Only broker-confirmed outcomes create learning samples.
- Durable queue deduplication and restart recovery.
- Owner-only Telegram command authorization logic.
- SQLite consistent backup and queue statistics.
- Qualification calculations: payout-adjusted break-even, Wilson 95% lower bound, realized expectancy, drawdown, loss streak, and concentration.
- Doctor and deterministic demo JSON output.
- Shell syntax checks for install, backup, doctor, and verify scripts.
- Architecture visualization rendered successfully.

## Not externally validated in this environment

- TradingView Pine compilation inside the user's TradingView account.
- A real TradingView webhook reaching the public Dominion HTTPS endpoint.
- Telegram Bot API connection using the user's BotFather token, chat ID, and owner ID.
- Live Binance scanner request. The execution environment had DNS/network access disabled; unit tests used deterministic mocked official-response shapes.
- Dependency vulnerability audit. `pip-audit` was unavailable and the isolated environment could not reach a package index. Run `pip install -r requirements-dev.txt && pip-audit -r requirements.txt` on the VM.
- Foundation VM service start, Caddy validation, and firewall path.
- Broker-screen price/payout matching.
- Performance or profitability. No such claim is made.

## Operating classification

The software is acceptable for **paper/demo signal collection and manual tracking after account-specific integration tests**. It is not qualified for autonomous real-money execution. The minimum real-funds evidence gate remains 200 broker-confirmed demo outcomes plus all statistical and risk gates.
