# ORION Ready-Now Procedure

This release starts the qualified signal bot on `foundation-vm` with:

- owner-only Telegram long polling;
- live public crypto market scanning;
- TradingView webhook intake;
- 82/100 score, expected-value, higher-timeframe, stale-data, spread, liquidity, cooldown, loss-streak, and daily-loss gates;
- persistent SQLite audit and qualification state;
- no broker login, withdrawal access, or automated clicking.

## One command on the VM

```bash
cd /path/to/ORION_READY_NOW_V3_3
sudo bash scripts/ready_now.sh
```

The setup validates the BotFather token, waits for the owner to send `/start`, discovers the numeric Telegram chat/owner IDs, writes them to `/opt/orion-extreme/.env` with mode `0600`, starts the core service and scanner, and runs health checks.

## First Telegram commands

```text
/status
/mode paper
/capital 1000
/payout 85
/arm
```

Use the bot's signal manually while the 200 broker-confirmed sample is accumulated. Record each accepted trade and result through `/accept` and `/result` so qualification uses actual broker-confirmed outcomes.
