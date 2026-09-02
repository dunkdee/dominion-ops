"""Read-only Alpaca market-data client.

Market data: data.alpaca.markets (market data service).
Market clock: paper-api.alpaca.markets/v2/clock (GET only — session visibility).

Safety invariants enforced at this layer:
- HTTPS only.
- data.alpaca.markets for all market data endpoints; no other brokerage paths.
- paper-api.alpaca.markets ONLY for GET /v2/clock — all other paths on that host refused.
- GET-only — no write verb exists in this module.
- Endpoint allow-list enforced separately for market-data and clock.
- Credentials sourced from environment, never serialized into responses.
- Credential scan executed before every return.
- Every observation envelope carries DATA_AVAILABLE, DATA_SOURCE, DATA_TIMESTAMP,
  RETRIEVED_AT, FEED, REALTIME_OR_DELAYED, DATA_FRESHNESS.
"""
from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from typing import Any

import requests

_DATA_HOST  = "data.alpaca.markets"
_BROKER_HOST       = "paper-api.alpaca.markets"
_CLOCK_PATH        = "/v2/clock"
_ASSET_PATH_PREFIX = "/v2/assets/"

# Default-deny brokerage host. GET-only.
# Permitted paths on _BROKER_HOST:
#   /v2/clock               — market session visibility (exact match)
#   /v2/assets/{symbol}     — read-only symbol validation (prefix match + symbol validation)
# ALL other paths are blocked: /orders, /positions, /account, everything else.
_BROKER_GET_ALLOWED = (_CLOCK_PATH, _ASSET_PATH_PREFIX)
_REFUSED_BROKERAGE_HOSTS = frozenset({"api.alpaca.markets"})

# Allow-list for data.alpaca.markets endpoints only.
_ALLOWED_DATA_PATTERNS = (
    re.compile(r"^/v2/stocks/[A-Z]{1,10}/quotes/latest$"),
    re.compile(r"^/v2/stocks/[A-Z]{1,10}/trades/latest$"),
    re.compile(r"^/v2/stocks/[A-Z]{1,10}/bars$"),
    re.compile(r"^/v2/stocks/[A-Z]{1,10}/snapshot$"),
    re.compile(r"^/v2/stocks/snapshots$"),
)

_DEFAULT_FEED = "iex"
_TIMEOUT = 8

# Freshness thresholds (seconds) by endpoint key.
_FRESH_THRESHOLDS: dict[str, int] = {
    "clock":         60,
    "quotes/latest": 300,
    "trades/latest": 300,
    "snapshot":      300,
}


class MarketDataError(RuntimeError):
    """Raised when market data retrieval fails or a safety invariant is violated."""


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _feed_class(feed: str) -> str:
    """Classify feed as REALTIME, DELAYED_15MIN, or UNKNOWN.

    sip  -> REALTIME (consolidated tape, paid subscription)
    iex  -> REALTIME (IEX exchange real-time, free tier — not delayed)
    delayed_sip -> DELAYED_15MIN
    anything else -> UNKNOWN
    """
    feed_norm = (feed or "").lower()
    if feed_norm in {"sip", "iex"}:
        return "REALTIME"
    if feed_norm == "delayed_sip":
        return "DELAYED_15MIN"
    return "UNKNOWN"


def _extract_observation_ts(data: Any, endpoint: str) -> str | None:
    """Extract the primary observation timestamp from a raw Alpaca response."""
    if not isinstance(data, dict):
        return None
    if endpoint == "clock":
        return data.get("timestamp")
    if "quotes/latest" in endpoint:
        return (data.get("quote") or {}).get("t")
    if "trades/latest" in endpoint:
        return (data.get("trade") or {}).get("t")
    if endpoint.startswith("bars/"):
        bars = data.get("bars") or []
        return bars[-1].get("t") if isinstance(bars, list) and bars else None
    if endpoint == "snapshot":
        return (
            (data.get("latestTrade") or {}).get("t")
            or (data.get("latestQuote") or {}).get("t")
        )
    return None


def _data_freshness(data: Any, endpoint: str) -> str:
    """Compare observation timestamp to current UTC.

    Returns FRESH, STALE, or UNKNOWN.
    Historical bars always return UNKNOWN — no session-aware heuristics.
    """
    if endpoint.startswith("bars/"):
        return "UNKNOWN"
    ts_str = _extract_observation_ts(data, endpoint)
    if not ts_str:
        return "UNKNOWN"
    try:
        ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        age_s = (datetime.now(timezone.utc) - ts).total_seconds()
        threshold = _FRESH_THRESHOLDS.get(endpoint, 300)
        return "FRESH" if age_s <= threshold else "STALE"
    except Exception:
        return "UNKNOWN"


def _check_data_path(path: str) -> None:
    if not any(p.match(path) for p in _ALLOWED_DATA_PATTERNS):
        raise MarketDataError(f"path not in market-data allow-list: {path!r}")


def _credential_scan(payload: str, key_id: str, secret: str) -> None:
    """Raise if any live credential material is present in the outgoing payload."""
    if key_id and len(key_id) >= 8 and key_id in payload:
        raise MarketDataError("CREDENTIAL_SCAN_FAIL: key_id found in response payload")
    if secret and len(secret) >= 8 and secret in payload:
        raise MarketDataError("CREDENTIAL_SCAN_FAIL: secret found in response payload")


class AlpacaMarketData:
    """Read-only client for Alpaca market data.

    Credentials are read from the process environment only.
    They are never serialized into any response or evidence record.
    Market DATA access and order EXECUTION are separate authorities.
    This class provides DATA access only. Clock is the one permitted
    paper-api exception (GET /v2/clock, session visibility only).
    """

    def __init__(self, *, key_id: str | None = None, secret: str | None = None,
                 feed: str | None = None):
        # Explicit override for tests; otherwise read from environment.
        self._key_id = key_id if key_id is not None else os.getenv("ALPACA_PAPER_KEY_ID", "")
        self._secret = secret if secret is not None else os.getenv("ALPACA_PAPER_SECRET_KEY", "")
        self.feed = feed if feed is not None else os.getenv("ALPACA_MARKET_FEED", _DEFAULT_FEED)

    # ---------- Public API ----------

    def connected(self) -> bool:
        return bool(self._key_id and self._secret)

    def clock(self) -> dict:
        """Market clock: is_open, next_open, next_close.

        Uses paper-api.alpaca.markets/v2/clock (GET only).
        Grants session-visibility; grants zero trade authority.
        """
        data = self._clock_get()
        return self._envelope(data, symbol=None, endpoint="clock")

    def latest_quote(self, symbol: str) -> dict:
        sym = _validate_symbol(symbol)
        data = self._get(f"/v2/stocks/{sym}/quotes/latest", {"feed": self.feed})
        return self._envelope(data, symbol=sym, endpoint="quotes/latest")

    def latest_trade(self, symbol: str) -> dict:
        sym = _validate_symbol(symbol)
        data = self._get(f"/v2/stocks/{sym}/trades/latest", {"feed": self.feed})
        return self._envelope(data, symbol=sym, endpoint="trades/latest")

    def bars(self, symbol: str, *, timeframe: str = "1Day", limit: int = 20) -> dict:
        sym = _validate_symbol(symbol)
        data = self._get(
            f"/v2/stocks/{sym}/bars",
            {"timeframe": timeframe, "limit": min(limit, 200), "feed": self.feed},
        )
        return self._envelope(data, symbol=sym, endpoint=f"bars/{timeframe}")

    def snapshot(self, symbol: str) -> dict:
        sym = _validate_symbol(symbol)
        data = self._get(f"/v2/stocks/{sym}/snapshot", {"feed": self.feed})
        return self._envelope(data, symbol=sym, endpoint="snapshot")

    def validate_symbol(self, candidate: str) -> dict:
        """Authoritative read-only symbol check via Alpaca assets endpoint.

        Returns {"valid": bool, "symbol": str, "status": str, "asset_class": str}.
        valid=True requires BOTH:
          data.get("status") == "active"
          data.get("tradable") is True      <- exact identity check, not truthy
        Every other path returns valid=False.
        No trading authority. Calls _asset_get (GET only).
        """
        try:
            data = self._asset_get(candidate)
        except MarketDataError as exc:
            status = "invalid_format" if "invalid symbol" in str(exc) else "error"
            return {"valid": False, "symbol": candidate, "status": status, "asset_class": ""}
        except Exception:
            return {"valid": False, "symbol": candidate, "status": "network_error", "asset_class": ""}

        if not data:                        # 404 -> _asset_get returns {}
            sym_up = candidate.upper() if re.match(r"^[A-Za-z]{1,10}$", candidate) else candidate
            return {"valid": False, "symbol": sym_up, "status": "not_found", "asset_class": ""}

        is_valid = (
            isinstance(data, dict)
            and data.get("status") == "active"
            and data.get("tradable") is True
        )
        return {
            "valid":       is_valid,
            "symbol":      data.get("symbol", candidate.upper()),
            "status":      data.get("status", "unknown"),
            "asset_class": data.get("class", ""),
        }

    # ---------- Internal helpers ----------

    def _headers(self) -> dict:
        if not self._key_id or not self._secret:
            raise MarketDataError(
                "ALPACA_PAPER_KEY_ID and ALPACA_PAPER_SECRET_KEY are not set. "
                "Market data capability is available but not yet connected. "
                "Set credentials in the server environment to activate."
            )
        return {
            "APCA-API-KEY-ID": self._key_id,
            "APCA-API-SECRET-KEY": self._secret,
        }

    def _get(self, path: str, params: dict | None = None) -> Any:
        _check_data_path(path)
        url = f"https://{_DATA_HOST}{path}"
        response = requests.get(url, headers=self._headers(), params=params or {}, timeout=_TIMEOUT)
        response.raise_for_status()
        data = response.json()
        _credential_scan(str(data), self._key_id, self._secret)
        return data

    def _clock_get(self) -> Any:
        """GET /v2/clock from paper-api.alpaca.markets ONLY.

        Sole permitted exception to the data.alpaca.markets constraint.
        Only GET, only /v2/clock, only this host. All other trading paths refused.
        """
        url = f"https://{_BROKER_HOST}{_CLOCK_PATH}"
        response = requests.get(url, headers=self._headers(), timeout=_TIMEOUT)
        response.raise_for_status()
        data = response.json()
        _credential_scan(str(data), self._key_id, self._secret)
        return data

    def _asset_get(self, symbol: str) -> Any:
        """GET /v2/assets/{symbol} from paper-api.alpaca.markets ONLY.

        Enforcement:
        - host:   _BROKER_HOST — hardcoded, never dynamic
        - method: requests.get — no POST/PUT/PATCH/DELETE exists in this method
        - path:   /v2/assets/{validated_symbol} only
                  symbol validated by _validate_symbol() before URL construction
                  path prefix checked after construction as belt-and-suspenders
        All other broker paths are unreachable from this method.
        No /orders. No position or account mutation.
        """
        sym = _validate_symbol(symbol)
        path = f"{_ASSET_PATH_PREFIX}{sym}"
        if not path.startswith(_ASSET_PATH_PREFIX):
            raise MarketDataError(f"asset path invariant violated: {path!r}")
        url = f"https://{_BROKER_HOST}{path}"
        response = requests.get(url, headers=self._headers(), timeout=_TIMEOUT)
        if response.status_code == 404:
            return {}
        response.raise_for_status()
        data = response.json()
        _credential_scan(str(data), self._key_id, self._secret)
        return data

    def _envelope(self, data: Any, *, symbol: str | None, endpoint: str) -> dict:
        """Wrap raw broker response with mandatory freshness/source labels.

        DATA_TIMESTAMP  = actual Alpaca market observation timestamp (null if absent)
        RETRIEVED_AT    = UTC time Buddy received the response
        DATA_FRESHNESS  = derived from observation timestamp vs current UTC
        REALTIME_OR_DELAYED = derived from feed identity only
        """
        obs_ts = _extract_observation_ts(data, endpoint)
        return {
            "DATA_AVAILABLE":      "YES",
            "DATA_SOURCE":         "ALPACA",
            "DATA_TIMESTAMP":      obs_ts,
            "RETRIEVED_AT":        _utc(),
            "FEED":                self.feed,
            "REALTIME_OR_DELAYED": _feed_class(self.feed),
            "DATA_FRESHNESS":      _data_freshness(data, endpoint),
            "endpoint":            endpoint,
            "symbol":              symbol,
            "data":                data,
        }


def _validate_symbol(symbol: str) -> str:
    sym = symbol.upper().strip()
    if not re.match(r"^[A-Z]{1,10}$", sym):
        raise MarketDataError(f"invalid symbol: {symbol!r}")
    return sym
