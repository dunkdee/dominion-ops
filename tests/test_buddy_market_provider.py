"""Architecture tests for Dominion's universal market-data provider layer.

These tests prove provider neutrality, fail-closed behavior, optional vendor
adapters, and Buddy startup without Alpaca credentials.

They DO NOT claim that live market data is available when no real provider
is configured.
"""

from __future__ import annotations

import inspect
import os
import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

try:
    from core.market_data_provider import (
        MarketDataProvider,
        NullProvider,
        get_market_data_provider,
    )
    from core.operator import BuddyOperator
    from core.providers.alpaca_provider import AlpacaProvider
    import core.operator as op_mod
    import core.market_data_provider as mdp_mod
except ImportError:
    from buddy_core.core.market_data_provider import (
        MarketDataProvider,
        NullProvider,
        get_market_data_provider,
    )
    from buddy_core.core.operator import BuddyOperator
    from buddy_core.core.providers.alpaca_provider import AlpacaProvider
    import buddy_core.core.operator as op_mod
    import buddy_core.core.market_data_provider as mdp_mod


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _fake_envelope(endpoint: str, symbol: str | None = None) -> dict:
    return {
        "DATA_AVAILABLE": "YES",
        "DATA_SOURCE": "FAKE",
        "DATA_TIMESTAMP": _now(),
        "RETRIEVED_AT": _now(),
        "FEED": "fake",
        "REALTIME_OR_DELAYED": "REALTIME",
        "DATA_FRESHNESS": "FRESH",
        "endpoint": endpoint,
        "symbol": symbol,
        "data": {},
    }


class FakeProvider(MarketDataProvider):
    """Credential-free in-process provider used only for architecture tests."""

    @property
    def provider_name(self) -> str:
        return "FAKE"

    def available(self) -> bool:
        return True

    def validate_symbol(self, symbol: str) -> dict:
        return {
            "valid": True,
            "symbol": symbol.upper(),
            "status": "active",
            "asset_class": "us_equity",
        }

    def latest_quote(self, symbol: str) -> dict:
        return _fake_envelope("quotes/latest", symbol)

    def latest_trade(self, symbol: str) -> dict:
        return _fake_envelope("trades/latest", symbol)

    def bars(self, symbol: str, **kwargs) -> dict:
        timeframe = kwargs.get("timeframe", "1Day")
        return _fake_envelope(f"bars/{timeframe}", symbol)

    def snapshot(self, symbol: str) -> dict:
        return _fake_envelope("snapshot", symbol)

    def clock(self) -> dict:
        return _fake_envelope("clock")


class TestUniversalProviderInterface(unittest.TestCase):

    def test_market_data_provider_is_abstract(self):
        with self.assertRaises(TypeError):
            MarketDataProvider()  # type: ignore[abstract]

    def test_provider_has_required_interface(self):
        required = {
            "provider_name",
            "available",
            "validate_symbol",
            "latest_quote",
            "latest_trade",
            "bars",
            "snapshot",
            "clock",
        }
        members = {name for name, _ in inspect.getmembers(MarketDataProvider)}
        self.assertTrue(required.issubset(members))

    def test_base_contract_has_no_alpaca_semantics(self):
        src = inspect.getsource(MarketDataProvider)
        self.assertNotIn("Alpaca", src)
        self.assertNotIn("ALPACA", src)
        self.assertNotIn("tradable", src)

    def test_fake_provider_satisfies_interface(self):
        self.assertIsInstance(FakeProvider(), MarketDataProvider)

    def test_null_provider_satisfies_interface(self):
        self.assertIsInstance(NullProvider(), MarketDataProvider)


class TestNullProvider(unittest.TestCase):

    def setUp(self):
        self.provider = NullProvider()

    def test_identity_and_availability(self):
        self.assertEqual(self.provider.provider_name, "NONE")
        self.assertFalse(self.provider.available())

    def _assert_failed_envelope(self, result: dict):
        self.assertEqual(result["DATA_AVAILABLE"], "NO")
        self.assertEqual(result["DATA_SOURCE"], "NONE")
        self.assertIsNone(result["DATA_TIMESTAMP"])
        self.assertIn("RETRIEVED_AT", result)
        self.assertEqual(result["FEED"], "NONE")
        self.assertEqual(result["REALTIME_OR_DELAYED"], "UNKNOWN")
        self.assertEqual(result["DATA_FRESHNESS"], "UNKNOWN")
        self.assertIn("endpoint", result)
        self.assertIn("symbol", result)
        self.assertEqual(result["ERROR"], "NO_MARKET_DATA_PROVIDER")

    def test_quote_fails_closed(self):
        self._assert_failed_envelope(self.provider.latest_quote("AAPL"))

    def test_trade_fails_closed(self):
        self._assert_failed_envelope(self.provider.latest_trade("AAPL"))

    def test_bars_fails_closed(self):
        self._assert_failed_envelope(self.provider.bars("AAPL"))

    def test_snapshot_fails_closed(self):
        self._assert_failed_envelope(self.provider.snapshot("AAPL"))

    def test_clock_fails_closed(self):
        self._assert_failed_envelope(self.provider.clock())

    def test_validation_fails_closed(self):
        result = self.provider.validate_symbol("AAPL")
        self.assertFalse(result["valid"])
        self.assertEqual(result["status"], "no_provider")


class TestFakeProvider(unittest.TestCase):

    def setUp(self):
        self.provider = FakeProvider()

    def test_available(self):
        self.assertTrue(self.provider.available())

    def test_symbol_validation(self):
        result = self.provider.validate_symbol("aapl")
        self.assertTrue(result["valid"])
        self.assertEqual(result["symbol"], "AAPL")

    def test_quote(self):
        result = self.provider.latest_quote("AAPL")
        self.assertEqual(result["DATA_AVAILABLE"], "YES")
        self.assertEqual(result["endpoint"], "quotes/latest")

    def test_trade(self):
        result = self.provider.latest_trade("AAPL")
        self.assertEqual(result["DATA_AVAILABLE"], "YES")
        self.assertEqual(result["endpoint"], "trades/latest")

    def test_bars(self):
        result = self.provider.bars("AAPL")
        self.assertEqual(result["DATA_AVAILABLE"], "YES")
        self.assertEqual(result["endpoint"], "bars/1Day")

    def test_snapshot(self):
        result = self.provider.snapshot("AAPL")
        self.assertEqual(result["DATA_AVAILABLE"], "YES")
        self.assertEqual(result["endpoint"], "snapshot")

    def test_clock(self):
        result = self.provider.clock()
        self.assertEqual(result["DATA_AVAILABLE"], "YES")
        self.assertEqual(result["endpoint"], "clock")


class TestProviderSelection(unittest.TestCase):

    def test_router_lives_in_provider_module(self):
        self.assertTrue(hasattr(mdp_mod, "get_market_data_provider"))

    def test_explicit_none_returns_null_provider(self):
        with patch.dict(
            os.environ,
            {"MARKET_DATA_PROVIDER": "none"},
            clear=False,
        ):
            provider = get_market_data_provider()

        self.assertIsInstance(provider, NullProvider)

    def test_alpaca_without_credentials_returns_null_provider(self):
        with patch.dict(
            os.environ,
            {
                "MARKET_DATA_PROVIDER": "alpaca",
                "ALPACA_PAPER_KEY_ID": "",
                "ALPACA_PAPER_SECRET_KEY": "",
            },
            clear=False,
        ):
            provider = get_market_data_provider()

        self.assertIsInstance(provider, NullProvider)

    def test_unknown_provider_setting_fails_closed(self):
        with patch.dict(
            os.environ,
            {"MARKET_DATA_PROVIDER": "__unsupported_test_provider__"},
            clear=False,
        ):
            provider = get_market_data_provider()

        self.assertIsInstance(provider, NullProvider)

    def test_operator_contains_no_adapter_selection_logic(self):
        src = inspect.getsource(op_mod.BuddyOperator._market_data)
        self.assertNotIn("AlpacaProvider", src)
        self.assertNotIn("NullProvider", src)
        self.assertNotIn('getenv("MARKET_DATA_PROVIDER"', src)


class TestAlpacaOptionalAdapter(unittest.TestCase):

    def test_alpaca_adapter_is_market_data_provider(self):
        with patch.dict(
            os.environ,
            {
                "ALPACA_PAPER_KEY_ID": "",
                "ALPACA_PAPER_SECRET_KEY": "",
            },
            clear=False,
        ):
            provider = AlpacaProvider()

        self.assertIsInstance(provider, MarketDataProvider)

    def test_missing_alpaca_credentials_is_unavailable_not_exception(self):
        with patch.dict(
            os.environ,
            {
                "ALPACA_PAPER_KEY_ID": "",
                "ALPACA_PAPER_SECRET_KEY": "",
            },
            clear=False,
        ):
            provider = AlpacaProvider()
            self.assertFalse(provider.available())


class TestOperatorDecoupling(unittest.TestCase):

    def test_operator_has_no_direct_alpaca_dependency(self):
        src = inspect.getsource(op_mod.BuddyOperator._market_data)
        self.assertNotIn("alpaca_market_data", src)
        self.assertNotIn("AlpacaMarketData", src)
        self.assertNotIn("MarketDataError", src)

    def test_operator_uses_universal_router(self):
        src = inspect.getsource(op_mod.BuddyOperator._market_data)
        self.assertIn("get_market_data_provider", src)

    def test_operator_uses_existing_shared_parser(self):
        src = inspect.getsource(op_mod.BuddyOperator._market_data)
        self.assertIn("_parse_market_request", src)

    def test_operator_adds_no_order_or_position_paths(self):
        src = inspect.getsource(op_mod.BuddyOperator._market_data)
        for forbidden in (
            "/orders",
            "/positions",
            "requests.post",
            "requests.put",
            "requests.patch",
            "requests.delete",
        ):
            self.assertNotIn(forbidden, src)

    def test_operator_has_no_web_price_fallback(self):
        src = inspect.getsource(op_mod.BuddyOperator._market_data)
        self.assertNotIn("web_research", src)
        self.assertNotIn("researcher", src)


class TestBuddyWithoutAlpaca(unittest.TestCase):

    def test_buddy_operator_constructs_without_alpaca_credentials(self):
        with patch.dict(
            os.environ,
            {
                "MARKET_DATA_PROVIDER": "none",
                "ALPACA_PAPER_KEY_ID": "",
                "ALPACA_PAPER_SECRET_KEY": "",
            },
            clear=False,
        ):
            operator = BuddyOperator(
                researcher=MagicMock(),
                brain_call=MagicMock(),
            )

        self.assertIsNotNone(operator)

    def test_market_request_without_provider_fails_closed(self):
        with patch.dict(
            os.environ,
            {
                "MARKET_DATA_PROVIDER": "none",
                "ALPACA_PAPER_KEY_ID": "",
                "ALPACA_PAPER_SECRET_KEY": "",
            },
            clear=False,
        ):
            operator = BuddyOperator(
                researcher=MagicMock(),
                brain_call=MagicMock(),
            )

            context = {
                "objective": "AAPL price",
                "outputs": [],
                "sources": [],
                "conversation_context": "",
                "evidence_policy": None,
            }

            result, evidence = operator._market_data(
                "AAPL price",
                context,
            )

        self.assertEqual(result["DATA_AVAILABLE"], "NO")
        self.assertEqual(result["DATA_SOURCE"], "NONE")
        self.assertIsNone(result["DATA_TIMESTAMP"])
        self.assertIn("RETRIEVED_AT", result)
        self.assertEqual(result["FEED"], "NONE")
        self.assertEqual(result["REALTIME_OR_DELAYED"], "UNKNOWN")
        self.assertEqual(result["DATA_FRESHNESS"], "UNKNOWN")
        self.assertEqual(result["ERROR"], "NO_MARKET_DATA_PROVIDER")
        self.assertEqual(len(evidence), 1)
        self.assertEqual(evidence[0]["type"], "market_data")

    def test_fake_provider_quote_routes_through_operator(self):
        fake = FakeProvider()
        operator = BuddyOperator(
            researcher=MagicMock(),
            brain_call=MagicMock(),
        )

        context = {
            "objective": "AAPL price",
            "outputs": [],
            "sources": [],
            "conversation_context": "",
            "evidence_policy": None,
        }

        with patch.object(
            op_mod,
            "get_market_data_provider",
            return_value=fake,
        ):
            result, evidence = operator._market_data(
                "AAPL price",
                context,
            )

        self.assertEqual(result["DATA_AVAILABLE"], "YES")
        self.assertEqual(result["DATA_SOURCE"], "FAKE")
        self.assertEqual(len(evidence), 1)

    def test_fake_provider_clock_routes_through_operator(self):
        fake = FakeProvider()
        operator = BuddyOperator(
            researcher=MagicMock(),
            brain_call=MagicMock(),
        )

        context = {
            "objective": "market clock",
            "outputs": [],
            "sources": [],
            "conversation_context": "",
            "evidence_policy": None,
        }

        with patch.object(
            op_mod,
            "get_market_data_provider",
            return_value=fake,
        ):
            result, evidence = operator._market_data(
                "market clock",
                context,
            )

        self.assertEqual(result["DATA_AVAILABLE"], "YES")
        self.assertEqual(result["DATA_SOURCE"], "FAKE")
        self.assertEqual(result["endpoint"], "clock")
        self.assertEqual(len(evidence), 1)


if __name__ == "__main__":
    unittest.main()
