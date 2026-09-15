# ORION / Dominion Binary Qualification Standard

## Mandatory operational gates

- Owner-only Telegram authorization.
- Paper/manual execution only.
- OTC blocked without a matching fresh broker feed.
- Minimum score, positive expected value, regime confidence, stale-signal, confirmed-bar, cooldown, hourly-cap, open-position-cap, loss-streak, daily-loss, operator-pause, and news-blackout gates.
- Fresh entry reference captured at acceptance.
- Model result and broker result stored separately.
- Only broker-confirmed outcomes train the production learner.
- Persistent state survives restart.
- All deterministic tests and dependency audit must pass.

## Performance gates before real funds

- Minimum 200 broker-confirmed demo trades.
- Win rate above payout-adjusted break-even with a 95% confidence interval whose lower bound is above break-even.
- Positive net expectancy after actual payouts.
- Maximum drawdown and loss streak remain within configured limits.
- No single asset, timeframe, or regime contributes more than 35% of total trades.
- Results separated by asset class, timeframe, session, regime, and strategy version.

Passing software qualification does not establish trading profitability.
