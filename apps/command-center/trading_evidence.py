"""Ledger evidence for read-only Alpaca paper observations.

Observations are appended to the existing Dominion append-only, hash-chained
evidence ledger (``control_plane.ledger.AppendOnlyLedger``). The chain
implementation is reused rather than reimplemented, so records written here
verify with the same ``control-plane verify-ledger`` command as every other
Dominion evidence record.

Per ``runtime/ledger/README.md`` the ledger holds no secret values. Each record
carries governance flags, aggregate figures, and a digest of the full snapshot
so the observation is tamper-evident without storing raw broker payloads.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from control_plane.canonical import sha256_json
from control_plane.ledger import AppendOnlyLedger, LedgerError

LEDGER_PATH_ENV = "TRADING_LEDGER_PATH"
DEFAULT_LEDGER_PATH = "/ledger/alpaca-paper-observations.jsonl"

EVENT_TYPE = "alpaca_paper_readonly_observation"
DEFAULT_ACTOR = "command-center-alpaca-bridge"


def ledger_path(env: dict[str, str] | None = None) -> Path:
    source = os.environ if env is None else env
    return Path(source.get(LEDGER_PATH_ENV) or DEFAULT_LEDGER_PATH)


def build_evidence_payload(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Reduce a snapshot to a non-secret, ledger-safe evidence payload."""
    account = snapshot.get("account") or {}
    positions = snapshot.get("positions") or {}
    orders = snapshot.get("orders") or {}
    fills = snapshot.get("fills") or {}
    pnl = snapshot.get("pnl") or {}
    win_loss = snapshot.get("win_loss") or {}
    drawdown = snapshot.get("drawdown") or {}
    bot = snapshot.get("bot_health") or {}

    return {
        "schema": "dominion-alpaca-paper-evidence-v1",
        "observed_at": snapshot.get("observed_at"),
        "mode": snapshot.get("mode"),
        "connected": snapshot.get("connected", True),
        "reason": snapshot.get("reason"),
        # Governance flags are recorded on every observation so the ledger
        # itself proves the bridge stayed read-only for the whole run.
        "governance": {
            "read_only": bool(snapshot.get("read_only")),
            "live_trading_enabled": bool(snapshot.get("live_trading_enabled")),
            "order_execution_enabled": bool(snapshot.get("order_execution_enabled")),
        },
        "account": {
            "status": account.get("status"),
            "currency": account.get("currency"),
            "equity": account.get("equity"),
            "buying_power": account.get("buying_power"),
            "cash": account.get("cash"),
            "portfolio_value": account.get("portfolio_value"),
        },
        "counts": {
            "positions": positions.get("count"),
            "open_orders": orders.get("open_count"),
            "closed_orders": orders.get("closed_count"),
            "fills": fills.get("count"),
            "closed_round_trips": (snapshot.get("trade_history") or {}).get("closed_round_trips"),
        },
        "pnl": {
            "realized": pnl.get("realized"),
            "unrealized": pnl.get("unrealized"),
            "total": pnl.get("total"),
        },
        "win_loss": {
            "closed_trades": win_loss.get("closed_trades"),
            "wins": win_loss.get("wins"),
            "losses": win_loss.get("losses"),
            "win_rate": win_loss.get("win_rate"),
            "profit_factor": win_loss.get("profit_factor"),
            "expectancy": win_loss.get("expectancy"),
        },
        "drawdown": {
            "max_drawdown_usd": drawdown.get("max_drawdown_usd"),
            "max_drawdown_pct": drawdown.get("max_drawdown_pct"),
            "current_drawdown_pct": drawdown.get("current_drawdown_pct"),
        },
        "bot_health": {
            "connected": bot.get("connected"),
            "live_trading": bot.get("live_trading"),
            "kill_switch": bot.get("kill_switch"),
            "stale": bot.get("stale"),
        },
        # Binds the ledger record to the exact snapshot that was served.
        "snapshot_sha256": sha256_json(snapshot),
    }


def record_observation(
    snapshot: dict[str, Any],
    *,
    path: str | Path | None = None,
    actor: str = DEFAULT_ACTOR,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Append one observation to the hash-chained ledger.

    Returns a small, non-secret receipt. Ledger failure is surfaced to the
    caller rather than silently swallowed.
    """
    target = Path(path) if path is not None else ledger_path(env)
    payload = build_evidence_payload(snapshot)
    record = AppendOnlyLedger(target).append(
        event_type=EVENT_TYPE,
        actor=actor,
        payload=payload,
    )
    return {
        "ledger_path": str(target),
        "sequence": record["sequence"],
        "record_hash": record["record_hash"],
        "timestamp": record["timestamp"],
        "event_type": record["event_type"],
    }


def verify(path: str | Path | None = None, env: dict[str, str] | None = None) -> dict[str, Any]:
    """Verify the trading evidence chain."""
    target = Path(path) if path is not None else ledger_path(env)
    if not Path(target).exists():
        return {"valid": True, "record_count": 0, "head_hash": None, "present": False}
    try:
        result = dict(AppendOnlyLedger(target).verify())
    except LedgerError as exc:
        return {"valid": False, "present": True, "error": str(exc)}
    result["present"] = True
    return result
