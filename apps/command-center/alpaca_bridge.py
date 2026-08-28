"""Read-only Alpaca PAPER account bridge.

Design constraints enforced by this module:

* **Paper only.** The base URL host must be an Alpaca paper host. The live
  trading host is rejected outright, so a misconfigured environment fails
  closed instead of reaching a live brokerage account.
* **Read only.** Every outbound call is an HTTP ``GET`` against a fixed
  allow-list of Alpaca read endpoints. No order-submitting, order-cancelling,
  or position-closing code path exists in this module.
* **Credentials stay server-side.** Key material is read from the process
  environment, sent only in outbound Alpaca request headers, and never placed
  into any returned structure.

Only the Python standard library is used, so the Command Center image gains no
new dependency.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Callable, Iterable
from urllib.parse import urlencode, urlsplit

MODE = "paper"

# Alpaca paper trading hosts. Anything else is refused.
ALLOWED_HOSTS = frozenset({"paper-api.alpaca.markets"})

# The live trading host. Named explicitly so the refusal is unambiguous and
# testable rather than an incidental consequence of the allow-list.
LIVE_TRADING_HOSTS = frozenset({"api.alpaca.markets"})

DEFAULT_BASE_URL = "https://paper-api.alpaca.markets"

# Read-only Alpaca endpoints this bridge is permitted to call.
ALLOWED_PATHS = frozenset({
    "/v2/account",
    "/v2/positions",
    "/v2/orders",
    "/v2/account/activities/FILL",
    "/v2/account/portfolio/history",
})

KEY_ID_ENV = "ALPACA_PAPER_KEY_ID"
SECRET_ENV = "ALPACA_PAPER_SECRET_KEY"
BASE_URL_ENV = "ALPACA_PAPER_BASE_URL"
TIMEOUT_ENV = "ALPACA_TIMEOUT_SECONDS"

DEFAULT_TIMEOUT_SECONDS = 15.0


class BridgeError(RuntimeError):
    """Raised when the bridge cannot produce a truthful read-only observation."""


class BridgeNotConfigured(BridgeError):
    """Raised when paper credentials are absent. The bridge fails closed."""


class LiveTradingRefused(BridgeError):
    """Raised when configuration points at a live-trading endpoint."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _decimal(value: Any) -> Decimal:
    """Parse a broker numeric field without inventing a value on failure."""
    if value is None or value == "":
        return Decimal("0")
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return Decimal("0")


def _float(value: Any) -> float:
    return float(_decimal(value))


def _round(value: Decimal | float, places: int = 4) -> float:
    return round(float(value), places)


def resolve_base_url(env: dict[str, str] | None = None) -> str:
    """Return the validated paper base URL, refusing live-trading endpoints."""
    source = os.environ if env is None else env
    raw = (source.get(BASE_URL_ENV) or DEFAULT_BASE_URL).strip().rstrip("/")
    parts = urlsplit(raw)
    if parts.scheme != "https":
        raise LiveTradingRefused(f"alpaca base URL must use https, got {parts.scheme or 'none'!r}")
    host = parts.hostname or ""
    if host in LIVE_TRADING_HOSTS:
        raise LiveTradingRefused(
            "live Alpaca trading host is refused by this read-only paper bridge"
        )
    if host not in ALLOWED_HOSTS:
        raise LiveTradingRefused(f"alpaca host {host!r} is not an approved paper host")
    return raw


def bridge_config(env: dict[str, str] | None = None) -> dict[str, Any]:
    """Describe bridge configuration. Never contains credential material."""
    source = os.environ if env is None else env
    key_id = (source.get(KEY_ID_ENV) or "").strip()
    secret = (source.get(SECRET_ENV) or "").strip()
    try:
        base_url = resolve_base_url(source)
        base_url_error = None
    except LiveTradingRefused as exc:
        base_url = None
        base_url_error = str(exc)
    return {
        "mode": MODE,
        "read_only": True,
        "live_trading_enabled": False,
        "order_execution_enabled": False,
        "credentials_present": bool(key_id and secret),
        "base_url": base_url,
        "base_url_error": base_url_error,
        "allowed_paths": sorted(ALLOWED_PATHS),
    }


def _default_transport(method: str, url: str, headers: dict[str, str], timeout: float) -> tuple[int, bytes]:
    request = urllib.request.Request(url, method=method, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return int(response.status), response.read()
    except urllib.error.HTTPError as exc:
        return int(exc.code), exc.read()
    except urllib.error.URLError as exc:
        raise BridgeError(f"alpaca paper endpoint unreachable: {exc.reason}") from exc
    except TimeoutError as exc:
        raise BridgeError("alpaca paper endpoint timed out") from exc


class AlpacaPaperReadOnlyClient:
    """Minimal read-only Alpaca paper client.

    ``transport`` is injectable so the bridge is fully testable without network
    access. It receives ``(method, url, headers, timeout)`` and returns
    ``(status_code, body_bytes)``.
    """

    def __init__(
        self,
        *,
        env: dict[str, str] | None = None,
        transport: Callable[[str, str, dict[str, str], float], tuple[int, bytes]] | None = None,
    ) -> None:
        source = os.environ if env is None else env
        self._key_id = (source.get(KEY_ID_ENV) or "").strip()
        self._secret = (source.get(SECRET_ENV) or "").strip()
        if not self._key_id or not self._secret:
            raise BridgeNotConfigured(
                f"{KEY_ID_ENV} and {SECRET_ENV} must be set server-side for the paper bridge"
            )
        self.base_url = resolve_base_url(source)
        try:
            self.timeout = float(source.get(TIMEOUT_ENV) or DEFAULT_TIMEOUT_SECONDS)
        except (TypeError, ValueError):
            self.timeout = DEFAULT_TIMEOUT_SECONDS
        self._transport = transport or _default_transport

    def _headers(self) -> dict[str, str]:
        return {
            "APCA-API-KEY-ID": self._key_id,
            "APCA-API-SECRET-KEY": self._secret,
            "Accept": "application/json",
        }

    def get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        """Perform an allow-listed read-only GET against the paper API."""
        if path not in ALLOWED_PATHS:
            raise BridgeError(f"path {path!r} is not in the read-only allow-list")
        url = f"{self.base_url}{path}"
        if params:
            url = f"{url}?{urlencode({k: v for k, v in params.items() if v is not None})}"
        status, body = self._transport("GET", url, self._headers(), self.timeout)
        if status == 401 or status == 403:
            raise BridgeError(f"alpaca paper credentials rejected (HTTP {status})")
        if status >= 400:
            raise BridgeError(f"alpaca paper read failed for {path} (HTTP {status})")
        if not body:
            return None
        try:
            return json.loads(body.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:
            raise BridgeError(f"alpaca paper returned unreadable JSON for {path}") from exc


# --------------------------------------------------------------------------
# Derived analytics
# --------------------------------------------------------------------------


def compute_round_trips(fills: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Match fills into closed round trips using per-symbol FIFO lot matching.

    Handles long and short sequences. A fill in the opposite direction of the
    currently open lots closes them oldest-first; any remainder opens new lots.
    Realized P&L is only recorded for the closed portion.
    """
    ordered = sorted(
        (f for f in fills if isinstance(f, dict)),
        key=lambda f: (str(f.get("transaction_time") or ""), str(f.get("id") or "")),
    )
    open_lots: dict[str, list[dict[str, Any]]] = {}
    round_trips: list[dict[str, Any]] = []

    for fill in ordered:
        symbol = str(fill.get("symbol") or "").upper()
        if not symbol:
            continue
        qty = _decimal(fill.get("qty"))
        price = _decimal(fill.get("price"))
        if qty <= 0:
            continue
        side = str(fill.get("side") or "").lower()
        # buy and buy_to_cover are +1; sell and sell_short are -1.
        direction = 1 if side.startswith("buy") else -1
        lots = open_lots.setdefault(symbol, [])
        remaining = qty

        while remaining > 0 and lots and lots[0]["direction"] != direction:
            lot = lots[0]
            matched = min(remaining, lot["qty"])
            if lot["direction"] == 1:
                # Closing a long lot: profit when the exit price is higher.
                pnl = (price - lot["price"]) * matched
            else:
                # Closing a short lot: profit when the exit price is lower.
                pnl = (lot["price"] - price) * matched
            round_trips.append({
                "symbol": symbol,
                "direction": "long" if lot["direction"] == 1 else "short",
                "qty": _round(matched, 8),
                "entry_price": _round(lot["price"], 8),
                "exit_price": _round(price, 8),
                "entry_time": lot["time"],
                "exit_time": fill.get("transaction_time"),
                "realized_pnl": _round(pnl),
                "entry_order_id": lot.get("order_id"),
                "exit_order_id": fill.get("order_id"),
            })
            remaining -= matched
            lot["qty"] -= matched
            if lot["qty"] <= 0:
                lots.pop(0)

        if remaining > 0:
            lots.append({
                "direction": direction,
                "qty": remaining,
                "price": price,
                "time": fill.get("transaction_time"),
                "order_id": fill.get("order_id"),
            })

    return round_trips


def compute_win_loss(round_trips: list[dict[str, Any]]) -> dict[str, Any]:
    """Win/loss statistics over closed round trips."""
    pnls = [float(rt["realized_pnl"]) for rt in round_trips]
    if not pnls:
        return {
            "closed_trades": 0,
            "wins": 0,
            "losses": 0,
            "breakeven": 0,
            "win_rate": None,
            "avg_win": None,
            "avg_loss": None,
            "profit_factor": None,
            "expectancy": None,
            "largest_win": None,
            "largest_loss": None,
            "realized_pnl": 0.0,
        }
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    breakeven = [p for p in pnls if p == 0]
    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    win_rate = len(wins) / len(pnls)
    avg_win = (gross_profit / len(wins)) if wins else 0.0
    avg_loss = (gross_loss / len(losses)) if losses else 0.0
    return {
        "closed_trades": len(pnls),
        "wins": len(wins),
        "losses": len(losses),
        "breakeven": len(breakeven),
        "win_rate": round(win_rate, 4),
        "avg_win": round(avg_win, 4),
        "avg_loss": round(avg_loss, 4),
        # An unbeaten record has no finite profit factor; report null, not a
        # sentinel that would read as a real ratio.
        "profit_factor": round(gross_profit / gross_loss, 4) if gross_loss > 0 else None,
        "expectancy": round((win_rate * avg_win) - ((1 - win_rate) * avg_loss), 4),
        "largest_win": round(max(pnls), 4),
        "largest_loss": round(min(pnls), 4),
        "realized_pnl": round(sum(pnls), 4),
    }


def compute_drawdown(equity_series: list[Any], timestamps: list[Any] | None = None) -> dict[str, Any]:
    """Maximum peak-to-trough decline over an equity series."""
    values = [_float(v) for v in equity_series if v is not None]
    if not values:
        return {
            "points": 0,
            "peak_equity": None,
            "trough_equity": None,
            "max_drawdown_usd": None,
            "max_drawdown_pct": None,
            "current_drawdown_usd": None,
            "current_drawdown_pct": None,
            "peak_at": None,
            "trough_at": None,
        }

    stamps = list(timestamps or [])
    peak = values[0]
    peak_index = 0
    best_peak_index = 0
    trough_index = 0
    max_dd = 0.0
    for index, value in enumerate(values):
        if value > peak:
            peak = value
            peak_index = index
        drawdown = peak - value
        if drawdown > max_dd:
            max_dd = drawdown
            best_peak_index = peak_index
            trough_index = index

    peak_value = values[best_peak_index]
    trough_value = values[trough_index]
    running_peak = max(values)
    current = values[-1]
    current_dd = max(running_peak - current, 0.0)

    def stamp_at(index: int) -> Any:
        return stamps[index] if index < len(stamps) else None

    return {
        "points": len(values),
        "peak_equity": round(peak_value, 4),
        "trough_equity": round(trough_value, 4),
        "max_drawdown_usd": round(max_dd, 4),
        "max_drawdown_pct": round((max_dd / peak_value) * 100, 4) if peak_value > 0 else None,
        "current_drawdown_usd": round(current_dd, 4),
        "current_drawdown_pct": round((current_dd / running_peak) * 100, 4) if running_peak > 0 else None,
        "peak_at": stamp_at(best_peak_index),
        "trough_at": stamp_at(trough_index),
    }


def compute_strategy_performance(
    round_trips: list[dict[str, Any]],
    positions: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Per-symbol performance.

    Symbol is the attribution granularity Alpaca fill activities actually
    support; fills carry no strategy tag, so nothing finer is claimed here.
    """
    buckets: dict[str, dict[str, Any]] = {}
    for trip in round_trips:
        symbol = str(trip["symbol"])
        bucket = buckets.setdefault(symbol, {
            "symbol": symbol,
            "closed_trades": 0,
            "wins": 0,
            "losses": 0,
            "realized_pnl": 0.0,
            "unrealized_pnl": 0.0,
            "open_qty": 0.0,
        })
        pnl = float(trip["realized_pnl"])
        bucket["closed_trades"] += 1
        bucket["realized_pnl"] += pnl
        if pnl > 0:
            bucket["wins"] += 1
        elif pnl < 0:
            bucket["losses"] += 1

    for position in positions or []:
        if not isinstance(position, dict):
            continue
        symbol = str(position.get("symbol") or "").upper()
        if not symbol:
            continue
        bucket = buckets.setdefault(symbol, {
            "symbol": symbol,
            "closed_trades": 0,
            "wins": 0,
            "losses": 0,
            "realized_pnl": 0.0,
            "unrealized_pnl": 0.0,
            "open_qty": 0.0,
        })
        bucket["unrealized_pnl"] += _float(position.get("unrealized_pl"))
        bucket["open_qty"] += _float(position.get("qty"))

    results = []
    for bucket in buckets.values():
        closed = bucket["closed_trades"]
        bucket["realized_pnl"] = round(bucket["realized_pnl"], 4)
        bucket["unrealized_pnl"] = round(bucket["unrealized_pnl"], 4)
        bucket["open_qty"] = round(bucket["open_qty"], 8)
        bucket["win_rate"] = round(bucket["wins"] / closed, 4) if closed else None
        bucket["total_pnl"] = round(bucket["realized_pnl"] + bucket["unrealized_pnl"], 4)
        results.append(bucket)
    results.sort(key=lambda item: item["total_pnl"], reverse=True)
    return results


def summarize_account(account: dict[str, Any] | None) -> dict[str, Any]:
    account = account or {}
    return {
        "account_number_present": bool(account.get("account_number")),
        "status": account.get("status"),
        "currency": account.get("currency"),
        "equity": _round(_decimal(account.get("equity")), 2),
        "last_equity": _round(_decimal(account.get("last_equity")), 2),
        "cash": _round(_decimal(account.get("cash")), 2),
        "buying_power": _round(_decimal(account.get("buying_power")), 2),
        "regt_buying_power": _round(_decimal(account.get("regt_buying_power")), 2),
        "daytrading_buying_power": _round(_decimal(account.get("daytrading_buying_power")), 2),
        "portfolio_value": _round(_decimal(account.get("portfolio_value")), 2),
        "long_market_value": _round(_decimal(account.get("long_market_value")), 2),
        "short_market_value": _round(_decimal(account.get("short_market_value")), 2),
        "daytrade_count": account.get("daytrade_count"),
        "pattern_day_trader": account.get("pattern_day_trader"),
        "trading_blocked": account.get("trading_blocked"),
        "account_blocked": account.get("account_blocked"),
        # Alpaca marks paper accounts; surface it so the phone can confirm mode.
        "reported_paper_flag": account.get("is_paper"),
        "session_pnl": _round(
            _decimal(account.get("equity")) - _decimal(account.get("last_equity")), 2
        ),
    }


def summarize_positions(positions: list[dict[str, Any]] | None) -> dict[str, Any]:
    items = [p for p in (positions or []) if isinstance(p, dict)]
    detailed = [{
        "symbol": p.get("symbol"),
        "side": p.get("side"),
        "qty": _round(_decimal(p.get("qty")), 8),
        "avg_entry_price": _round(_decimal(p.get("avg_entry_price")), 8),
        "current_price": _round(_decimal(p.get("current_price")), 8),
        "market_value": _round(_decimal(p.get("market_value")), 2),
        "cost_basis": _round(_decimal(p.get("cost_basis")), 2),
        "unrealized_pl": _round(_decimal(p.get("unrealized_pl")), 4),
        "unrealized_plpc": _round(_decimal(p.get("unrealized_plpc")), 6),
        "unrealized_intraday_pl": _round(_decimal(p.get("unrealized_intraday_pl")), 4),
        "asset_class": p.get("asset_class"),
        "exchange": p.get("exchange"),
    } for p in items]
    return {
        "count": len(detailed),
        "unrealized_pnl": round(sum(p["unrealized_pl"] for p in detailed), 4),
        "market_value": round(sum(p["market_value"] for p in detailed), 2),
        "items": detailed,
    }


def summarize_orders(orders: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    return [{
        "id": o.get("id"),
        "client_order_id": o.get("client_order_id"),
        "symbol": o.get("symbol"),
        "side": o.get("side"),
        "type": o.get("type"),
        "time_in_force": o.get("time_in_force"),
        "qty": _round(_decimal(o.get("qty")), 8),
        "filled_qty": _round(_decimal(o.get("filled_qty")), 8),
        "filled_avg_price": _round(_decimal(o.get("filled_avg_price")), 8),
        "limit_price": _round(_decimal(o.get("limit_price")), 8) if o.get("limit_price") else None,
        "status": o.get("status"),
        "submitted_at": o.get("submitted_at"),
        "filled_at": o.get("filled_at"),
        "canceled_at": o.get("canceled_at"),
    } for o in (orders or []) if isinstance(o, dict)]


def summarize_fills(fills: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    return [{
        "id": f.get("id"),
        "symbol": f.get("symbol"),
        "side": f.get("side"),
        "qty": _round(_decimal(f.get("qty")), 8),
        "price": _round(_decimal(f.get("price")), 8),
        "notional": _round(_decimal(f.get("qty")) * _decimal(f.get("price")), 4),
        "type": f.get("type"),
        "order_id": f.get("order_id"),
        "transaction_time": f.get("transaction_time"),
    } for f in (fills or []) if isinstance(f, dict)]


# --------------------------------------------------------------------------
# Bot health (existing Dominion Alpha paper engine)
# --------------------------------------------------------------------------

ALPHA_BASE_URL_ENV = "ALPHA_ENGINE_BASE_URL"
DEFAULT_ALPHA_BASE_URL = "http://127.0.0.1:8787"
BOT_STALE_AFTER_SECONDS = 900


def _parse_timestamp(value: Any) -> datetime | None:
    if not value:
        return None
    text = str(value).replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def bot_health(
    *,
    env: dict[str, str] | None = None,
    transport: Callable[[str, str, dict[str, str], float], tuple[int, bytes]] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Read the existing Dominion Alpha paper engine's own status endpoint.

    This observes the running bot; it never starts, stops, or reconfigures it.
    """
    source = os.environ if env is None else env
    base = (source.get(ALPHA_BASE_URL_ENV) or DEFAULT_ALPHA_BASE_URL).strip().rstrip("/")
    call = transport or _default_transport
    try:
        status_code, body = call("GET", f"{base}/status", {"Accept": "application/json"}, 10.0)
    except BridgeError as exc:
        return {"connected": False, "reason": str(exc), "base_url": base}
    if status_code >= 400:
        return {"connected": False, "reason": f"HTTP {status_code}", "base_url": base}
    try:
        payload = json.loads(body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return {"connected": False, "reason": "unreadable JSON", "base_url": base}
    if not isinstance(payload, dict):
        return {"connected": False, "reason": "unexpected payload", "base_url": base}

    reference = now or datetime.now(timezone.utc)
    last_cycle = _parse_timestamp(payload.get("last_cycle_ts"))
    age_seconds = (reference - last_cycle).total_seconds() if last_cycle else None
    return {
        "connected": True,
        "base_url": base,
        "engine": "dominion-alpha",
        "version": payload.get("version"),
        "live_trading": bool(payload.get("live_trading", False)),
        "kill_switch": bool(payload.get("kill_switch", False)),
        "cycles_run": payload.get("cycles_run"),
        "last_cycle_ts": payload.get("last_cycle_ts"),
        "last_cycle_age_seconds": round(age_seconds, 1) if age_seconds is not None else None,
        "stale": bool(age_seconds is not None and age_seconds > BOT_STALE_AFTER_SECONDS),
        "capital": payload.get("capital"),
        "open_positions": payload.get("open_positions"),
        "errors": payload.get("errors") or [],
    }


# --------------------------------------------------------------------------
# Snapshot assembly
# --------------------------------------------------------------------------

MAX_ORDERS = 200
MAX_FILLS = 500


def build_snapshot(
    client: AlpacaPaperReadOnlyClient,
    *,
    include_bot_health: bool = True,
    env: dict[str, str] | None = None,
    bot_transport: Callable[[str, str, dict[str, str], float], tuple[int, bytes]] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Fetch every permitted read endpoint and derive the governed summary."""
    account = client.get("/v2/account")
    positions = client.get("/v2/positions") or []
    open_orders = client.get("/v2/orders", {"status": "open", "limit": MAX_ORDERS, "direction": "desc"}) or []
    closed_orders = client.get("/v2/orders", {"status": "closed", "limit": MAX_ORDERS, "direction": "desc"}) or []
    fills = client.get("/v2/account/activities/FILL", {"page_size": MAX_FILLS}) or []
    history = client.get("/v2/account/portfolio/history", {"period": "1M", "timeframe": "1D"}) or {}

    if not isinstance(positions, list):
        positions = []
    if not isinstance(fills, list):
        fills = []
    if not isinstance(history, dict):
        history = {}

    round_trips = compute_round_trips(fills)
    account_summary = summarize_account(account if isinstance(account, dict) else {})
    position_summary = summarize_positions(positions)
    win_loss = compute_win_loss(round_trips)
    drawdown = compute_drawdown(history.get("equity") or [], history.get("timestamp") or [])

    realized = win_loss["realized_pnl"]
    unrealized = position_summary["unrealized_pnl"]

    snapshot: dict[str, Any] = {
        "schema": "dominion-alpaca-paper-readonly-observation-v1",
        "observed_at": (now or datetime.now(timezone.utc)).isoformat(),
        "mode": MODE,
        "read_only": True,
        "live_trading_enabled": False,
        "order_execution_enabled": False,
        "source": "alpaca-paper-api",
        "account": account_summary,
        "positions": position_summary,
        "orders": {
            "open_count": len(open_orders) if isinstance(open_orders, list) else 0,
            "closed_count": len(closed_orders) if isinstance(closed_orders, list) else 0,
            "open": summarize_orders(open_orders if isinstance(open_orders, list) else []),
            "closed": summarize_orders(closed_orders if isinstance(closed_orders, list) else []),
        },
        "fills": {
            "count": len(fills),
            "items": summarize_fills(fills),
        },
        "trade_history": {
            "closed_round_trips": len(round_trips),
            "items": round_trips,
        },
        "pnl": {
            "realized": realized,
            "unrealized": unrealized,
            "total": round(realized + unrealized, 4),
            "session": account_summary["session_pnl"],
        },
        "win_loss": win_loss,
        "drawdown": drawdown,
        "strategy_performance": compute_strategy_performance(round_trips, positions),
    }
    if include_bot_health:
        snapshot["bot_health"] = bot_health(env=env, transport=bot_transport, now=now)
    return snapshot


def unavailable_snapshot(reason: str, *, now: datetime | None = None) -> dict[str, Any]:
    """A truthful 'not observed' snapshot.

    Absent data is reported as unavailable rather than as zero, matching the
    Command Center's existing runtime-truth contract.
    """
    return {
        "schema": "dominion-alpaca-paper-readonly-observation-v1",
        "observed_at": (now or datetime.now(timezone.utc)).isoformat(),
        "mode": MODE,
        "read_only": True,
        "live_trading_enabled": False,
        "order_execution_enabled": False,
        "connected": False,
        "reason": reason,
        "account": None,
        "positions": None,
        "orders": None,
        "fills": None,
        "trade_history": None,
        "pnl": None,
        "win_loss": None,
        "drawdown": None,
        "strategy_performance": None,
    }


SECRET_ENV_NAMES = (KEY_ID_ENV, SECRET_ENV)


def assert_no_credentials(payload: Any, env: dict[str, str] | None = None) -> None:
    """Fail closed if credential material ever appears in an outbound payload."""
    source = os.environ if env is None else env
    secrets_in_use = [
        (source.get(name) or "").strip() for name in SECRET_ENV_NAMES
    ]
    encoded = json.dumps(payload, default=str)
    for value in secrets_in_use:
        if value and value in encoded:
            raise BridgeError("refusing to emit a payload containing credential material")
