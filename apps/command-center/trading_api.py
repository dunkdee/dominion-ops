"""Authenticated, phone-safe, read-only trading surface for the Command Center.

Every route here is a GET. The router exposes no order-placing, order-cancelling,
position-closing, or configuration-mutating operation, and the underlying bridge
holds no code path that could perform one.

Authentication fails closed: if ``COMMAND_CENTER_API_KEY`` is not set on the
server, the surface returns 503 rather than serving account data openly.
"""

from __future__ import annotations

import os
import secrets
import threading
import time
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException

import alpaca_bridge
import trading_evidence

API_KEY_ENV = "COMMAND_CENTER_API_KEY"
CACHE_TTL_ENV = "TRADING_SNAPSHOT_TTL_SECONDS"
DEFAULT_CACHE_TTL_SECONDS = 15.0
MIN_API_KEY_LENGTH = 24

router = APIRouter(prefix="/api/trading/paper", tags=["trading-paper-readonly"])


def require_phone_key(x_dominion_key: str | None = Header(default=None)) -> None:
    """Authenticate the phone-facing surface. Fails closed when unconfigured."""
    expected = (os.getenv(API_KEY_ENV) or "").strip()
    if not expected:
        raise HTTPException(
            status_code=503,
            detail="trading surface unconfigured: COMMAND_CENTER_API_KEY is not set",
        )
    if len(expected) < MIN_API_KEY_LENGTH:
        raise HTTPException(
            status_code=503,
            detail=f"trading surface refused: {API_KEY_ENV} must be at least {MIN_API_KEY_LENGTH} characters",
        )
    if not x_dominion_key or not secrets.compare_digest(x_dominion_key, expected):
        raise HTTPException(status_code=401, detail="Unauthorized")


class _SnapshotCache:
    """Short-TTL cache so phone polling does not hammer the broker API."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._value: dict[str, Any] | None = None
        self._receipt: dict[str, Any] | None = None
        self._expires_at = 0.0

    @staticmethod
    def _ttl() -> float:
        try:
            return max(0.0, float(os.getenv(CACHE_TTL_ENV) or DEFAULT_CACHE_TTL_SECONDS))
        except (TypeError, ValueError):
            return DEFAULT_CACHE_TTL_SECONDS

    def get(self) -> tuple[dict[str, Any], dict[str, Any] | None, bool]:
        """Return ``(snapshot, ledger_receipt, cached)``."""
        with self._lock:
            now = time.monotonic()
            if self._value is not None and now < self._expires_at:
                return self._value, self._receipt, True

            snapshot, receipt = _observe()
            self._value = snapshot
            self._receipt = receipt
            self._expires_at = now + self._ttl()
            return snapshot, receipt, False

    def invalidate(self) -> None:
        with self._lock:
            self._value = None
            self._receipt = None
            self._expires_at = 0.0


_cache = _SnapshotCache()


def _observe() -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Fetch a fresh snapshot and write one ledger record for it."""
    try:
        client = alpaca_bridge.AlpacaPaperReadOnlyClient()
        snapshot = alpaca_bridge.build_snapshot(client)
        snapshot["connected"] = True
    except alpaca_bridge.BridgeError as exc:
        snapshot = alpaca_bridge.unavailable_snapshot(str(exc))

    # Never emit credential material, even if a broker payload echoed it back.
    alpaca_bridge.assert_no_credentials(snapshot)

    receipt: dict[str, Any] | None
    try:
        receipt = trading_evidence.record_observation(snapshot)
    except (OSError, ValueError, RuntimeError) as exc:
        # An evidence-write failure is reported, never hidden behind good data.
        receipt = {"recorded": False, "error": str(exc)}
    return snapshot, receipt


def _envelope(snapshot: dict[str, Any], receipt: dict[str, Any] | None, cached: bool) -> dict[str, Any]:
    return {
        "observed_at": snapshot.get("observed_at"),
        "cached": cached,
        "connected": bool(snapshot.get("connected")),
        "reason": snapshot.get("reason"),
        "mode": alpaca_bridge.MODE,
        "read_only": True,
        "live_trading_enabled": False,
        "order_execution_enabled": False,
        "evidence": receipt,
    }


@router.get("/health", dependencies=[Depends(require_phone_key)])
def paper_health() -> dict[str, Any]:
    """Bridge configuration and evidence-chain state. No broker call."""
    config = alpaca_bridge.bridge_config()
    return {
        "status": "ok",
        "service": "dominion-command-center-trading-bridge",
        "time": alpaca_bridge.utc_now(),
        "config": config,
        "ledger": trading_evidence.verify(),
        "activation_state": (
            "ready" if config["credentials_present"] and config["base_url"] else "awaiting_paper_credentials"
        ),
    }


@router.get("/summary", dependencies=[Depends(require_phone_key)])
def paper_summary() -> dict[str, Any]:
    """Consolidated phone view: equity, P&L, positions, orders, health, risk."""
    snapshot, receipt, cached = _cache.get()
    envelope = _envelope(snapshot, receipt, cached)
    envelope.update({
        "account": snapshot.get("account"),
        "pnl": snapshot.get("pnl"),
        "positions": snapshot.get("positions"),
        "orders": {
            "open_count": (snapshot.get("orders") or {}).get("open_count"),
            "closed_count": (snapshot.get("orders") or {}).get("closed_count"),
        } if snapshot.get("orders") else None,
        "fills_count": (snapshot.get("fills") or {}).get("count") if snapshot.get("fills") else None,
        "win_loss": snapshot.get("win_loss"),
        "drawdown": snapshot.get("drawdown"),
        "strategy_performance": snapshot.get("strategy_performance"),
        "bot_health": snapshot.get("bot_health"),
    })
    return envelope


@router.get("/account", dependencies=[Depends(require_phone_key)])
def paper_account() -> dict[str, Any]:
    snapshot, receipt, cached = _cache.get()
    return {**_envelope(snapshot, receipt, cached), "account": snapshot.get("account")}


@router.get("/positions", dependencies=[Depends(require_phone_key)])
def paper_positions() -> dict[str, Any]:
    snapshot, receipt, cached = _cache.get()
    return {**_envelope(snapshot, receipt, cached), "positions": snapshot.get("positions")}


@router.get("/orders", dependencies=[Depends(require_phone_key)])
def paper_orders() -> dict[str, Any]:
    snapshot, receipt, cached = _cache.get()
    return {**_envelope(snapshot, receipt, cached), "orders": snapshot.get("orders")}


@router.get("/fills", dependencies=[Depends(require_phone_key)])
def paper_fills() -> dict[str, Any]:
    snapshot, receipt, cached = _cache.get()
    return {**_envelope(snapshot, receipt, cached), "fills": snapshot.get("fills")}


@router.get("/history", dependencies=[Depends(require_phone_key)])
def paper_history() -> dict[str, Any]:
    snapshot, receipt, cached = _cache.get()
    return {**_envelope(snapshot, receipt, cached), "trade_history": snapshot.get("trade_history")}


@router.get("/performance", dependencies=[Depends(require_phone_key)])
def paper_performance() -> dict[str, Any]:
    snapshot, receipt, cached = _cache.get()
    return {
        **_envelope(snapshot, receipt, cached),
        "pnl": snapshot.get("pnl"),
        "win_loss": snapshot.get("win_loss"),
        "drawdown": snapshot.get("drawdown"),
        "strategy_performance": snapshot.get("strategy_performance"),
    }


@router.get("/evidence", dependencies=[Depends(require_phone_key)])
def paper_evidence() -> dict[str, Any]:
    """Verification state of the append-only observation chain."""
    return {"time": alpaca_bridge.utc_now(), "ledger": trading_evidence.verify()}
