"""Alpaca optional adapter for the universal MarketDataProvider interface.

Loaded dynamically by get_market_data_provider() only.
Nothing in operator.py imports this file directly.

Alpaca-specific validity semantics (active status, tradable is True) live here —
not in the MarketDataProvider contract.
"""

from __future__ import annotations

try:
    from core.market_data_provider import MarketDataProvider
    from core.alpaca_market_data import AlpacaMarketData
except ImportError:
    from buddy_core.core.market_data_provider import MarketDataProvider
    from buddy_core.core.alpaca_market_data import AlpacaMarketData


class AlpacaProvider(MarketDataProvider):
    """Thin wrapper adapting AlpacaMarketData to the universal provider interface.

    All HTTP logic, endpoint allow-lists, credential handling, and
    credential-scan enforcement remain in AlpacaMarketData unchanged.
    This adapter only bridges the interface.

    No order functionality. No account mutation. No position access.
    No credential exposure. No duplicated HTTP code.
    """

    def __init__(self) -> None:
        self._client = AlpacaMarketData()

    @property
    def provider_name(self) -> str:
        return "ALPACA"

    def available(self) -> bool:
        """True only when Alpaca credentials are present and client is ready."""
        try:
            return self._client.connected()
        except Exception:
            return False

    def validate_symbol(self, symbol: str) -> dict:
        """Delegate to AlpacaMarketData.validate_symbol.

        Alpaca-specific validity: status == active AND tradable is True.
        Returns normalized envelope:
          {"valid": bool, "symbol": str, "status": str, "asset_class": str}
        Fails closed: valid=False on any error or missing credentials.
        """
        return self._client.validate_symbol(symbol)

    def latest_quote(self, symbol: str) -> dict:
        return self._client.latest_quote(symbol)

    def latest_trade(self, symbol: str) -> dict:
        return self._client.latest_trade(symbol)

    def bars(self, symbol: str, **kwargs) -> dict:
        return self._client.bars(symbol, **kwargs)

    def snapshot(self, symbol: str) -> dict:
        return self._client.snapshot(symbol)

    def clock(self) -> dict:
        return self._client.clock()
