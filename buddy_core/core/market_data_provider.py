"""Universal market-data provider contract and router.

Operator code calls get_market_data_provider() only.
No trading vendor is imported at module load time.
Provider adapters are loaded dynamically.
Buddy starts normally with no market-data credentials.

Fail-closed guarantee:
  If no configured provider is available -> NullProvider is returned.
  NullProvider returns DATA_AVAILABLE=NO, ERROR=NO_MARKET_DATA_PROVIDER.
  No crash. No fake data. No fabricated prices.

Environment:
  MARKET_DATA_PROVIDER=auto   discover first available adapter
  MARKET_DATA_PROVIDER=alpaca try Alpaca adapter only
  MARKET_DATA_PROVIDER=none   disable market data and return NullProvider
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from datetime import datetime, timezone


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _null_envelope(
    *,
    error: str,
    endpoint: str = "unknown",
    symbol: str | None = None,
) -> dict:
    return {
        "DATA_AVAILABLE": "NO",
        "DATA_SOURCE": "NONE",
        "DATA_TIMESTAMP": None,
        "RETRIEVED_AT": _utc(),
        "FEED": "NONE",
        "REALTIME_OR_DELAYED": "UNKNOWN",
        "DATA_FRESHNESS": "UNKNOWN",
        "endpoint": endpoint,
        "symbol": symbol,
        "ERROR": error,
    }


class MarketDataProvider(ABC):
    """Provider-neutral, read-only market-data contract.

    Provider-specific rules belong inside adapters, not this interface.
    Adapters normalize their responses into Dominion's shared evidence envelope.
    """

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Short provider identifier."""

    @abstractmethod
    def available(self) -> bool:
        """Return True only when the provider can currently be used."""

    @abstractmethod
    def validate_symbol(self, symbol: str) -> dict:
        """Authoritative provider-specific symbol validation.

        Normalized return:

        {
            "valid": bool,
            "symbol": str,
            "status": str,
            "asset_class": str
        }

        Each adapter determines validity using its own authoritative source.
        Errors fail closed with valid=False.
        """

    @abstractmethod
    def latest_quote(self, symbol: str) -> dict:
        """Latest quote using the shared market-data envelope."""

    @abstractmethod
    def latest_trade(self, symbol: str) -> dict:
        """Latest trade using the shared market-data envelope."""

    @abstractmethod
    def bars(self, symbol: str, **kwargs) -> dict:
        """OHLCV bars using the shared market-data envelope."""

    @abstractmethod
    def snapshot(self, symbol: str) -> dict:
        """Market snapshot using the shared market-data envelope."""

    @abstractmethod
    def clock(self) -> dict:
        """Market/session clock using the shared market-data envelope."""


class NullProvider(MarketDataProvider):
    """Fail-closed provider used when no real provider is available."""

    @property
    def provider_name(self) -> str:
        return "NONE"

    def available(self) -> bool:
        return False

    def validate_symbol(self, symbol: str) -> dict:
        return {
            "valid": False,
            "symbol": symbol,
            "status": "no_provider",
            "asset_class": "",
        }

    def latest_quote(self, symbol: str) -> dict:
        return _null_envelope(
            error="NO_MARKET_DATA_PROVIDER",
            endpoint="quotes/latest",
            symbol=symbol,
        )

    def latest_trade(self, symbol: str) -> dict:
        return _null_envelope(
            error="NO_MARKET_DATA_PROVIDER",
            endpoint="trades/latest",
            symbol=symbol,
        )

    def bars(self, symbol: str, **kwargs) -> dict:
        return _null_envelope(
            error="NO_MARKET_DATA_PROVIDER",
            endpoint="bars",
            symbol=symbol,
        )

    def snapshot(self, symbol: str) -> dict:
        return _null_envelope(
            error="NO_MARKET_DATA_PROVIDER",
            endpoint="snapshot",
            symbol=symbol,
        )

    def clock(self) -> dict:
        return _null_envelope(
            error="NO_MARKET_DATA_PROVIDER",
            endpoint="clock",
        )


def get_market_data_provider() -> MarketDataProvider:
    """Resolve active market-data provider without vendor coupling in operator.py."""

    setting = os.getenv("MARKET_DATA_PROVIDER", "auto").strip().lower()

    if setting == "none":
        return NullProvider()

    providers_to_try: list[MarketDataProvider] = []

    if setting in {"auto", "alpaca"}:
        alpaca_provider_cls = None

        try:
            from core.providers.alpaca_provider import AlpacaProvider
            alpaca_provider_cls = AlpacaProvider
        except ImportError:
            try:
                from buddy_core.core.providers.alpaca_provider import AlpacaProvider
                alpaca_provider_cls = AlpacaProvider
            except ImportError:
                pass

        if alpaca_provider_cls is not None:
            try:
                providers_to_try.append(alpaca_provider_cls())
            except Exception:
                pass

    for provider in providers_to_try:
        try:
            if provider.available():
                return provider
        except Exception:
            continue

    return NullProvider()
