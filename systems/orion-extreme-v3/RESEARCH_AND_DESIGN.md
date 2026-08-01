# Research and design decisions

## TradingView

TradingView webhooks accept public HTTP ports 80 and 443, require valid JSON for JSON content type, and cancel slow requests. ORION therefore terminates TLS at Caddy, limits the request body, validates an unguessable path token, writes to a durable queue, and answers with HTTP 202 before analysis runs. The Pine bridge uses confirmed bars and `alert()` once per bar close.

## Telegram

The Telegram Bot API supports either long polling or webhooks for update delivery, not both simultaneously. ORION uses owner-only long polling so no additional public Telegram callback endpoint is required. It applies exponential backoff and checks the numeric owner user ID before executing commands.

## Public crypto data

The optional scanner uses Binance's public market-data-only REST endpoint. It excludes the currently forming candle and sends closed bars only. It has no API key, account, trade, or withdrawal permission. It is not a broker-feed substitute and is blocked for OTC.

## Pocket Option quote boundary

Pocket Option's terms state that its terminal uses its own quotation flow and that other companies' quotes are not controlling for disputes. ORION therefore treats external data as signal context only. OTC requires an explicit fresh matching broker feed, and every accepted paper trade captures the actual broker entry and payout.

## Statistical qualification

A raw historical win rate is not sufficient. ORION uses payout-adjusted break-even, realized expectancy, a Wilson 95% lower confidence bound, drawdown, loss streak, and concentration. Only broker-confirmed demo outcomes are eligible for learning and qualification.
