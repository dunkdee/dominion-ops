"""Tests for Buddy market-data routing, feed classification, and safety invariants.

Proves before LIVE_MARKET_DATA_ACCESS=YES is declared:

Routing:
  WRONG_COMMON_WORD_AS_SYMBOL=BLOCKED
  MARKET_CLOCK_SYMBOL_EXTRACTION=NONE
  NO_ARBITRARY_LOWERCASE_TICKER_GUESSING=YES
  NO_STATIC_TICKER_LIST=YES

Feed classification:
  IEX_REALTIME=YES
  IEX_NOT_LABELED_DELAYED=YES
  DELAYED_SIP_LABELED_DELAYED=YES
  UNKNOWN_FEED_LABELED_UNKNOWN=YES

Timestamp envelope:
  DATA_TIMESTAMP_IS_OBSERVATION_TIME=YES
  RETRIEVED_AT_SEPARATE=YES
  FRESHNESS_FROM_TIMESTAMP=YES
  HISTORICAL_BARS_FRESHNESS_UNKNOWN=YES

Safety:
  MARKET_QUERY_AUTO_LEARNING=NO
  EPHEMERAL_PRICE_PERSISTED_TO_LEARNING=NO
  ORDER_EXECUTION_PATH_PRESENT=NO
  WEB_PRICE_FALLBACK_PRESENT=NO
  AUTHORITATIVE_SYMBOL_VALIDATION=YES

Clock:
  CLOCK_CORRECT_HOST=YES
  CLOCK_GET_ONLY=YES
  CLOCK_NOT_FETCHED_FOR_QUOTES=YES
"""
from __future__ import annotations

import inspect
import re
import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

try:
    from core.alpaca_market_data import (
        AlpacaMarketData, MarketDataError,
        _feed_class, _extract_observation_ts, _data_freshness,
        _BROKER_HOST, _CLOCK_PATH, _ASSET_PATH_PREFIX,
    )
    from core.operator import _parse_market_request, BuddyOperator
except ImportError:
    from buddy_core.core.alpaca_market_data import (
        AlpacaMarketData, MarketDataError,
        _feed_class, _extract_observation_ts, _data_freshness,
        _BROKER_HOST, _CLOCK_PATH, _ASSET_PATH_PREFIX,
    )
    from buddy_core.core.operator import _parse_market_request, BuddyOperator


# ---------------------------------------------------------------------------
# Feed classification
# ---------------------------------------------------------------------------

class TestFeedClassification(unittest.TestCase):

    def test_iex_is_realtime(self):
        """IEX_REALTIME=YES"""
        self.assertEqual(_feed_class("iex"), "REALTIME")

    def test_iex_not_labeled_delayed(self):
        """IEX_NOT_LABELED_DELAYED=YES"""
        self.assertNotEqual(_feed_class("iex"), "DELAYED_15MIN")

    def test_sip_is_realtime(self):
        self.assertEqual(_feed_class("sip"), "REALTIME")

    def test_delayed_sip_is_delayed(self):
        """DELAYED_SIP_LABELED_DELAYED=YES"""
        self.assertEqual(_feed_class("delayed_sip"), "DELAYED_15MIN")

    def test_unknown_feed_is_unknown(self):
        """UNKNOWN_FEED_LABELED_UNKNOWN=YES"""
        self.assertEqual(_feed_class("something_else"), "UNKNOWN")
        self.assertEqual(_feed_class(""), "UNKNOWN")

    def test_feed_case_normalization(self):
        self.assertEqual(_feed_class("IEX"), "REALTIME")
        self.assertEqual(_feed_class("SIP"), "REALTIME")
        self.assertEqual(_feed_class("DELAYED_SIP"), "DELAYED_15MIN")


# ---------------------------------------------------------------------------
# Observation timestamp extraction
# ---------------------------------------------------------------------------

class TestObservationTs(unittest.TestCase):

    def _now_iso(self, delta_seconds: int = 0) -> str:
        dt = datetime.now(timezone.utc) - timedelta(seconds=delta_seconds)
        return dt.isoformat()

    def test_clock_timestamp_extracted(self):
        ts = self._now_iso(10)
        self.assertEqual(_extract_observation_ts({"timestamp": ts, "is_open": True}, "clock"), ts)

    def test_quote_timestamp_extracted(self):
        ts = self._now_iso(5)
        self.assertEqual(_extract_observation_ts({"quote": {"t": ts, "bp": 100.0}}, "quotes/latest"), ts)

    def test_trade_timestamp_extracted(self):
        ts = self._now_iso(3)
        self.assertEqual(_extract_observation_ts({"trade": {"t": ts, "p": 150.0}}, "trades/latest"), ts)

    def test_bars_last_bar_timestamp(self):
        ts = self._now_iso(3600)
        data = {"bars": [{"t": self._now_iso(7200)}, {"t": ts}]}
        self.assertEqual(_extract_observation_ts(data, "bars/1Day"), ts)

    def test_bars_empty_returns_none(self):
        self.assertIsNone(_extract_observation_ts({"bars": []}, "bars/1Day"))

    def test_snapshot_trade_timestamp_preferred(self):
        ts_trade = self._now_iso(2)
        ts_quote = self._now_iso(1)
        data = {"latestTrade": {"t": ts_trade}, "latestQuote": {"t": ts_quote}}
        self.assertEqual(_extract_observation_ts(data, "snapshot"), ts_trade)

    def test_missing_timestamp_returns_none(self):
        self.assertIsNone(_extract_observation_ts({}, "quotes/latest"))
        self.assertIsNone(_extract_observation_ts({}, "clock"))


# ---------------------------------------------------------------------------
# DATA_FRESHNESS
# ---------------------------------------------------------------------------

class TestDataFreshness(unittest.TestCase):

    def _ts(self, seconds_ago: int) -> str:
        return (datetime.now(timezone.utc) - timedelta(seconds=seconds_ago)).isoformat()

    def test_fresh_clock(self):
        """FRESHNESS_FROM_TIMESTAMP=YES"""
        self.assertEqual(_data_freshness({"timestamp": self._ts(30)}, "clock"), "FRESH")

    def test_stale_clock(self):
        self.assertEqual(_data_freshness({"timestamp": self._ts(120)}, "clock"), "STALE")

    def test_fresh_quote(self):
        self.assertEqual(_data_freshness({"quote": {"t": self._ts(60)}}, "quotes/latest"), "FRESH")

    def test_stale_quote(self):
        self.assertEqual(_data_freshness({"quote": {"t": self._ts(400)}}, "quotes/latest"), "STALE")

    def test_historical_bars_always_unknown(self):
        """HISTORICAL_BARS_FRESHNESS_UNKNOWN=YES"""
        self.assertEqual(_data_freshness({"bars": [{"t": self._ts(1)}]}, "bars/1Day"), "UNKNOWN")

    def test_missing_timestamp_is_unknown(self):
        self.assertEqual(_data_freshness({}, "quotes/latest"), "UNKNOWN")

    def test_unparsable_timestamp_is_unknown(self):
        self.assertEqual(_data_freshness({"quote": {"t": "not-a-timestamp"}}, "quotes/latest"), "UNKNOWN")


# ---------------------------------------------------------------------------
# Envelope: DATA_TIMESTAMP vs RETRIEVED_AT independence
# ---------------------------------------------------------------------------

class TestEnvelope(unittest.TestCase):

    def _client(self, feed="iex"):
        return AlpacaMarketData(key_id="TESTKEY123", secret="TESTSECRET123", feed=feed)

    def test_data_timestamp_is_observation_time_not_retrieval(self):
        """DATA_TIMESTAMP_IS_OBSERVATION_TIME=YES, RETRIEVED_AT_SEPARATE=YES"""
        obs_ts = (datetime.now(timezone.utc) - timedelta(seconds=5)).isoformat()
        data = {"quote": {"t": obs_ts, "bp": 100.0}}
        env = self._client()._envelope(data, symbol="AAPL", endpoint="quotes/latest")
        self.assertEqual(env["DATA_TIMESTAMP"], obs_ts)
        self.assertIn("RETRIEVED_AT", env)
        self.assertNotEqual(env["DATA_TIMESTAMP"], env["RETRIEVED_AT"])

    def test_iex_labeled_realtime_not_delayed(self):
        """IEX_NOT_LABELED_DELAYED=YES"""
        env = self._client(feed="iex")._envelope({}, symbol=None, endpoint="clock")
        self.assertEqual(env["REALTIME_OR_DELAYED"], "REALTIME")
        self.assertNotEqual(env["REALTIME_OR_DELAYED"], "DELAYED_15MIN")

    def test_delayed_sip_labeled_correctly(self):
        env = self._client(feed="delayed_sip")._envelope(
            {"quote": {"t": datetime.now(timezone.utc).isoformat()}},
            symbol="TSLA", endpoint="quotes/latest"
        )
        self.assertEqual(env["REALTIME_OR_DELAYED"], "DELAYED_15MIN")

    def test_bars_freshness_always_unknown(self):
        """HISTORICAL_BARS_FRESHNESS_UNKNOWN=YES"""
        ts = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
        env = self._client()._envelope({"bars": [{"t": ts}]}, symbol="AAPL", endpoint="bars/1Day")
        self.assertEqual(env["DATA_FRESHNESS"], "UNKNOWN")

    def test_null_timestamp_when_absent(self):
        env = self._client()._envelope({}, symbol=None, endpoint="clock")
        self.assertIsNone(env["DATA_TIMESTAMP"])
        self.assertEqual(env["DATA_FRESHNESS"], "UNKNOWN")

    def test_data_available_yes_on_success(self):
        env = self._client()._envelope({}, symbol=None, endpoint="clock")
        self.assertEqual(env["DATA_AVAILABLE"], "YES")
        self.assertEqual(env["DATA_SOURCE"], "ALPACA")


# ---------------------------------------------------------------------------
# Clock host safety
# ---------------------------------------------------------------------------

class TestClockHost(unittest.TestCase):

    def test_clock_uses_broker_host(self):
        """CLOCK_CORRECT_HOST=YES"""
        self.assertEqual(_BROKER_HOST, "paper-api.alpaca.markets")

    def test_clock_path_correct(self):
        self.assertEqual(_CLOCK_PATH, "/v2/clock")

    def test_asset_path_prefix_correct(self):
        self.assertEqual(_ASSET_PATH_PREFIX, "/v2/assets/")

    def test_clock_get_only_no_write_verbs(self):
        """CLOCK_GET_ONLY=YES"""
        import buddy_core.core.alpaca_market_data as amd
        src = inspect.getsource(amd.AlpacaMarketData._clock_get)
        self.assertIn("requests.get", src)
        self.assertNotIn("requests.post", src)
        self.assertNotIn("requests.put", src)
        self.assertNotIn("requests.patch", src)
        self.assertNotIn("requests.delete", src)

    def test_asset_get_only_no_write_verbs(self):
        import buddy_core.core.alpaca_market_data as amd
        src = inspect.getsource(amd.AlpacaMarketData._asset_get)
        self.assertIn("requests.get", src)
        self.assertNotIn("requests.post", src)
        self.assertNotIn("requests.put", src)

    def test_data_get_uses_data_host_not_broker(self):
        import buddy_core.core.alpaca_market_data as amd
        src = inspect.getsource(amd.AlpacaMarketData._get)
        self.assertIn("_DATA_HOST", src)
        self.assertNotIn("_BROKER_HOST", src)
        self.assertNotIn("paper-api", src)


# ---------------------------------------------------------------------------
# Clock not auto-fetched for non-clock requests
# ---------------------------------------------------------------------------

class TestClockNotAutoFetched(unittest.TestCase):

    def test_quote_request_does_not_call_clock(self):
        """CLOCK_NOT_FETCHED_FOR_QUOTES=YES"""
        client = AlpacaMarketData(key_id="K1234567", secret="S1234567", feed="iex")
        fake_data = {"quote": {"t": datetime.now(timezone.utc).isoformat(), "bp": 100.0}}
        with patch.object(client, "_get", return_value=fake_data), \
             patch.object(client, "_clock_get") as mock_clock:
            client.latest_quote("AAPL")
            mock_clock.assert_not_called()


# ---------------------------------------------------------------------------
# validate_symbol fail-closed contract
# ---------------------------------------------------------------------------

class TestValidateSymbol(unittest.TestCase):

    def _client(self):
        return AlpacaMarketData(key_id="K1234567", secret="S1234567")

    def test_active_tradable_is_valid(self):
        client = self._client()
        with patch.object(client, "_asset_get",
                          return_value={"status": "active", "tradable": True, "symbol": "AAPL", "class": "us_equity"}):
            r = client.validate_symbol("AAPL")
        self.assertTrue(r["valid"])
        self.assertEqual(r["symbol"], "AAPL")

    def test_tradable_false_is_invalid(self):
        """tradable=False → valid=False"""
        client = self._client()
        with patch.object(client, "_asset_get",
                          return_value={"status": "active", "tradable": False, "symbol": "XYZ", "class": "us_equity"}):
            r = client.validate_symbol("XYZ")
        self.assertFalse(r["valid"])

    def test_tradable_absent_is_invalid(self):
        """tradable key absent → None is True → False"""
        client = self._client()
        with patch.object(client, "_asset_get",
                          return_value={"status": "active", "symbol": "XYZ", "class": "us_equity"}):
            r = client.validate_symbol("XYZ")
        self.assertFalse(r["valid"])

    def test_tradable_integer_is_invalid(self):
        """tradable=1 → 1 is True → False in Python"""
        client = self._client()
        with patch.object(client, "_asset_get",
                          return_value={"status": "active", "tradable": 1, "symbol": "XYZ"}):
            r = client.validate_symbol("XYZ")
        self.assertFalse(r["valid"])

    def test_not_found_404_is_invalid(self):
        """404 → _asset_get returns {} → valid=False"""
        client = self._client()
        with patch.object(client, "_asset_get", return_value={}):
            r = client.validate_symbol("FAKE")
        self.assertFalse(r["valid"])
        self.assertEqual(r["status"], "not_found")

    def test_network_error_is_invalid(self):
        """Network failure → valid=False (fail closed)"""
        client = self._client()
        with patch.object(client, "_asset_get", side_effect=Exception("timeout")):
            r = client.validate_symbol("AAPL")
        self.assertFalse(r["valid"])
        self.assertEqual(r["status"], "network_error")

    def test_invalid_format_is_invalid(self):
        client = self._client()
        r = client.validate_symbol("INVALID!!")
        self.assertFalse(r["valid"])


# ---------------------------------------------------------------------------
# Routing: _parse_market_request
# ---------------------------------------------------------------------------

class TestMarketRouting(unittest.TestCase):

    def test_aapl_caps_price_confirmed(self):
        """AAPL price → confirmed symbol, no validation needed"""
        r = _parse_market_request("AAPL price")
        self.assertTrue(r["is_market"])
        self.assertEqual(r["symbol"], "AAPL")
        self.assertFalse(r["needs_symbol_validation"])

    def test_dollar_aapl_confirmed(self):
        """$aapl → confirmed AAPL, no validation"""
        r = _parse_market_request("$aapl price")
        self.assertTrue(r["is_market"])
        self.assertEqual(r["symbol"], "AAPL")
        self.assertFalse(r["needs_symbol_validation"])

    def test_aapl_lowercase_needs_validation(self):
        """aapl price → candidate, needs Alpaca validation"""
        r = _parse_market_request("aapl price")
        self.assertTrue(r["is_market"])
        self.assertIsNone(r["symbol"])
        self.assertEqual(r["symbol_candidate"], "AAPL")
        self.assertTrue(r["needs_symbol_validation"])

    def test_nvda_lowercase_quote_needs_validation(self):
        """nvda quote → candidate, needs validation"""
        r = _parse_market_request("nvda quote")
        self.assertTrue(r["is_market"])
        self.assertIsNone(r["symbol"])
        self.assertEqual(r["symbol_candidate"], "NVDA")
        self.assertTrue(r["needs_symbol_validation"])

    def test_ticker_nvda_needs_validation(self):
        """ticker nvda → candidate, needs validation"""
        r = _parse_market_request("ticker nvda")
        self.assertTrue(r["is_market"])
        self.assertEqual(r["symbol_candidate"], "NVDA")
        self.assertTrue(r["needs_symbol_validation"])

    def test_market_clock_no_symbol(self):
        """MARKET_CLOCK_SYMBOL_EXTRACTION=NONE"""
        r = _parse_market_request("market clock")
        self.assertTrue(r["is_market"])
        self.assertIsNone(r["symbol"])
        self.assertIsNone(r["symbol_candidate"])
        self.assertEqual(r["request_type"], "clock")

    def test_ups_shipping_quote_not_market(self):
        """WRONG_COMMON_WORD_AS_SYMBOL=BLOCKED — NON_MARKET_PROX blocks"""
        r = _parse_market_request("UPS shipping quote")
        self.assertFalse(r["is_market"])

    def test_ibm_consulting_quote_not_market(self):
        r = _parse_market_request("IBM consulting quote")
        self.assertFalse(r["is_market"])

    def test_wix_product_price_not_market(self):
        r = _parse_market_request("WIX product price")
        self.assertFalse(r["is_market"])

    def test_uber_ride_price_not_market(self):
        r = _parse_market_request("uber ride price")
        self.assertFalse(r["is_market"])

    def test_our_wix_revenue_chart_not_market(self):
        r = _parse_market_request("our Wix revenue chart")
        self.assertFalse(r["is_market"])

    def test_stock_price_for_ford_no_confirmed_symbol(self):
        """stock price for ford → MUST NOT produce confirmed symbol=FORD blindly"""
        r = _parse_market_request("stock price for ford")
        # If market, ford must be a candidate (needing validation), not confirmed
        if r["is_market"]:
            self.assertIsNone(r["symbol"], "FORD must not be a confirmed symbol")
            self.assertTrue(r["needs_symbol_validation"])

    def test_ford_price_no_confirmed_symbol(self):
        """ford price → MUST NOT blindly confirm FORD"""
        r = _parse_market_request("ford price")
        if r["is_market"]:
            self.assertIsNone(r["symbol"])
            self.assertTrue(r["needs_symbol_validation"])

    def test_apple_price_no_confirmed_symbol(self):
        """apple price → MUST NOT blindly confirm APPLE"""
        r = _parse_market_request("apple price")
        if r["is_market"]:
            self.assertIsNone(r["symbol"])
            self.assertTrue(r["needs_symbol_validation"])

    def test_task_not_quote_type(self):
        """task for AAPL stock — 'ask' inside 'task' must not trigger quote type"""
        r = _parse_market_request("task for AAPL stock")
        self.assertTrue(r["is_market"])
        self.assertNotEqual(r["request_type"], "quote")

    def test_no_static_ticker_list(self):
        """NO_STATIC_TICKER_LIST=YES — parser has no hardcoded ticker universe"""
        import buddy_core.core.operator as op_mod
        src = inspect.getsource(op_mod._parse_market_request)
        self.assertNotIn("AAPL", src)
        self.assertNotIn("TSLA", src)
        self.assertNotIn("MSFT", src)


# ---------------------------------------------------------------------------
# Safety invariants
# ---------------------------------------------------------------------------

class TestSafetyInvariants(unittest.TestCase):

    def test_market_plan_has_no_learn_record(self):
        """MARKET_QUERY_AUTO_LEARNING=NO, EPHEMERAL_PRICE_PERSISTED_TO_LEARNING=NO"""
        op = BuddyOperator(researcher=MagicMock(), brain_call=MagicMock())
        plan = op.plan("AAPL price")
        caps = [s["capability"] for s in plan["steps"]]
        self.assertNotIn("learn.record", caps)
        self.assertEqual(caps, ["market.data"])

    def test_market_data_no_order_paths(self):
        """ORDER_EXECUTION_PATH_PRESENT=NO"""
        import buddy_core.core.operator as op_mod
        src = inspect.getsource(op_mod.BuddyOperator._market_data)
        self.assertNotIn("/orders", src)
        self.assertNotIn("/positions", src)
        self.assertNotIn("requests.post", src)

    def test_market_data_no_web_fallback(self):
        """WEB_PRICE_FALLBACK_PRESENT=NO"""
        import buddy_core.core.operator as op_mod
        src = inspect.getsource(op_mod.BuddyOperator._market_data)
        self.assertNotIn("web_research", src)
        self.assertNotIn("researcher", src)

    def test_market_data_uses_shared_parser_only(self):
        """NO_ARBITRARY_LOWERCASE_TICKER_GUESSING=YES — single parser, no second extractor"""
        import buddy_core.core.operator as op_mod
        src = inspect.getsource(op_mod.BuddyOperator._market_data)
        self.assertIn("_parse_market_request", src)
        self.assertNotIn('re.findall(r"[A-Z]', src)
        self.assertNotIn("re.search(r'[A-Z]", src)

    def test_market_data_fails_closed_no_credentials(self):
        """Fail closed: DATA_AVAILABLE=NO when credentials absent"""
        op = BuddyOperator(researcher=MagicMock(), brain_call=MagicMock())
        ctx = {"objective": "AAPL price", "outputs": [], "sources": [],
               "conversation_context": "", "evidence_policy": None}
        result, evidence = op._market_data("AAPL price", ctx)
        self.assertEqual(result["DATA_AVAILABLE"], "NO")
        self.assertEqual(result["DATA_FRESHNESS"], "UNKNOWN")
        self.assertIsNone(result["DATA_TIMESTAMP"])
        self.assertIn("ERROR", result)

    def test_authoritative_validation_for_lowercase(self):
        """AUTHORITATIVE_SYMBOL_VALIDATION=YES — lowercase goes through validate_symbol"""
        import buddy_core.core.operator as op_mod
        src = inspect.getsource(op_mod.BuddyOperator._market_data)
        self.assertIn("validate_symbol", src)
        self.assertIn("needs_validation", src)


if __name__ == "__main__":
    unittest.main()
