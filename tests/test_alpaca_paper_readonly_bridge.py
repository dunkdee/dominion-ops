"""Governed acceptance tests for the read-only Alpaca PAPER bridge.

Every test runs offline. The Alpaca transport is injected, so nothing here
touches a real brokerage account.
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CC_DIR = ROOT / "apps" / "command-center"
sys.path.insert(0, str(CC_DIR))
sys.path.insert(0, str(ROOT))

spec = importlib.util.spec_from_file_location("alpaca_bridge", CC_DIR / "alpaca_bridge.py")
assert spec and spec.loader
bridge = importlib.util.module_from_spec(spec)
sys.modules["alpaca_bridge"] = bridge
spec.loader.exec_module(bridge)

from control_plane.ledger import AppendOnlyLedger  # noqa: E402

spec_ev = importlib.util.spec_from_file_location("trading_evidence", CC_DIR / "trading_evidence.py")
assert spec_ev and spec_ev.loader
evidence = importlib.util.module_from_spec(spec_ev)
sys.modules["trading_evidence"] = evidence
spec_ev.loader.exec_module(evidence)

try:
    from fastapi.testclient import TestClient

    HTTP_DEPS = True
except Exception:  # pragma: no cover - exercised only on minimal runners
    HTTP_DEPS = False

PAPER_ENV = {
    "ALPACA_PAPER_KEY_ID": "PKTESTKEYID000000000",
    "ALPACA_PAPER_SECRET_KEY": "sk-test-secret-value-must-never-leak",
}

ACCOUNT = {
    "account_number": "PA123456", "status": "ACTIVE", "currency": "USD",
    "equity": "104250.75", "last_equity": "103900.25", "cash": "52000.00",
    "buying_power": "208501.50", "regt_buying_power": "104250.75",
    "daytrading_buying_power": "417003.00", "portfolio_value": "104250.75",
    "long_market_value": "52250.75", "short_market_value": "0",
    "daytrade_count": 1, "pattern_day_trader": False,
    "trading_blocked": False, "account_blocked": False, "is_paper": True,
}

POSITIONS = [
    {"symbol": "AAPL", "side": "long", "qty": "50", "avg_entry_price": "180.00",
     "current_price": "190.00", "market_value": "9500.00", "cost_basis": "9000.00",
     "unrealized_pl": "500.00", "unrealized_plpc": "0.0555", "unrealized_intraday_pl": "120.00",
     "asset_class": "us_equity", "exchange": "NASDAQ"},
    {"symbol": "MSFT", "side": "long", "qty": "10", "avg_entry_price": "400.00",
     "current_price": "390.00", "market_value": "3900.00", "cost_basis": "4000.00",
     "unrealized_pl": "-100.00", "unrealized_plpc": "-0.025", "unrealized_intraday_pl": "-30.00",
     "asset_class": "us_equity", "exchange": "NASDAQ"},
]

OPEN_ORDERS = [{
    "id": "o-open-1", "client_order_id": "dominion-alpha-1", "symbol": "NVDA",
    "side": "buy", "type": "limit", "time_in_force": "day", "qty": "5",
    "filled_qty": "0", "filled_avg_price": None, "limit_price": "800.00",
    "status": "new", "submitted_at": "2026-08-28T13:00:00Z",
}]

CLOSED_ORDERS = [{
    "id": "o-closed-1", "client_order_id": "dominion-alpha-0", "symbol": "AAPL",
    "side": "buy", "type": "market", "time_in_force": "day", "qty": "50",
    "filled_qty": "50", "filled_avg_price": "180.00", "status": "filled",
    "submitted_at": "2026-08-20T13:30:00Z", "filled_at": "2026-08-20T13:30:01Z",
}]

# TSLA: 10 @ 100 in, 10 @ 130 out  -> +300 realized (win)
# SPY:  20 @ 500 in, 20 @ 495 out  -> -100 realized (loss)
# GOOG: short 5 @ 200, cover 5 @ 180 -> +100 realized (short win)
FILLS = [
    {"id": "f1", "symbol": "TSLA", "side": "buy", "qty": "10", "price": "100",
     "type": "fill", "order_id": "ord-1", "transaction_time": "2026-08-21T14:00:00Z"},
    {"id": "f2", "symbol": "TSLA", "side": "sell", "qty": "10", "price": "130",
     "type": "fill", "order_id": "ord-2", "transaction_time": "2026-08-22T14:00:00Z"},
    {"id": "f3", "symbol": "SPY", "side": "buy", "qty": "20", "price": "500",
     "type": "fill", "order_id": "ord-3", "transaction_time": "2026-08-23T14:00:00Z"},
    {"id": "f4", "symbol": "SPY", "side": "sell", "qty": "20", "price": "495",
     "type": "fill", "order_id": "ord-4", "transaction_time": "2026-08-24T14:00:00Z"},
    {"id": "f5", "symbol": "GOOG", "side": "sell_short", "qty": "5", "price": "200",
     "type": "fill", "order_id": "ord-5", "transaction_time": "2026-08-25T14:00:00Z"},
    {"id": "f6", "symbol": "GOOG", "side": "buy", "qty": "5", "price": "180",
     "type": "fill", "order_id": "ord-6", "transaction_time": "2026-08-26T14:00:00Z"},
]

HISTORY = {
    "timestamp": [1, 2, 3, 4, 5],
    "equity": [100000.0, 106000.0, 98000.0, 101000.0, 104250.75],
}

ALPHA_STATUS = {
    "version": "2.0", "kill_switch": False, "confidence_threshold": 0.82,
    "cycles_run": 42, "last_scan_count": 120,
    "last_cycle_ts": "2026-08-28T14:00:00+00:00",
    "capital": 1000.0, "open_positions": 2, "errors": [], "live_trading": False,
}


class FakeAlpaca:
    """Records every outbound call so read-only behaviour is provable."""

    def __init__(self, *, account=None, status_code=200):
        self.calls: list[tuple[str, str, dict]] = []
        self.account = ACCOUNT if account is None else account
        self.status_code = status_code

    def __call__(self, method, url, headers, timeout):
        self.calls.append((method, url, dict(headers)))
        if self.status_code != 200:
            return self.status_code, b'{"message":"forced"}'
        path = url.split("?", 1)[0]
        query = url.split("?", 1)[1] if "?" in url else ""
        if path.endswith("/v2/account"):
            body = self.account
        elif path.endswith("/v2/positions"):
            body = POSITIONS
        elif path.endswith("/v2/orders"):
            body = OPEN_ORDERS if "status=open" in query else CLOSED_ORDERS
        elif path.endswith("/v2/account/activities/FILL"):
            body = FILLS
        elif path.endswith("/v2/account/portfolio/history"):
            body = HISTORY
        elif path.endswith("/status"):
            body = ALPHA_STATUS
        else:  # pragma: no cover - guarded by the allow-list
            return 404, b'{"message":"not found"}'
        return 200, json.dumps(body).encode("utf-8")

    @property
    def methods(self) -> set[str]:
        return {call[0] for call in self.calls}


def make_client(transport, env=None):
    return bridge.AlpacaPaperReadOnlyClient(env=dict(env or PAPER_ENV), transport=transport)


def full_snapshot(transport=None):
    fake = transport or FakeAlpaca()
    client = make_client(fake)
    snapshot = bridge.build_snapshot(
        client, env=dict(PAPER_ENV), bot_transport=fake,
        now=datetime(2026, 8, 28, 14, 5, tzinfo=timezone.utc),
    )
    snapshot["connected"] = True
    return snapshot, fake


class PaperOnlyEnforcementTests(unittest.TestCase):
    def test_live_alpaca_host_is_refused(self):
        with self.assertRaises(bridge.LiveTradingRefused) as ctx:
            bridge.resolve_base_url({"ALPACA_PAPER_BASE_URL": "https://api.alpaca.markets"})
        self.assertIn("live", str(ctx.exception).lower())

    def test_paper_host_is_accepted(self):
        self.assertEqual(
            bridge.resolve_base_url({"ALPACA_PAPER_BASE_URL": "https://paper-api.alpaca.markets/"}),
            "https://paper-api.alpaca.markets",
        )

    def test_default_base_url_is_paper(self):
        self.assertEqual(bridge.resolve_base_url({}), bridge.DEFAULT_BASE_URL)
        self.assertIn("paper", bridge.DEFAULT_BASE_URL)

    def test_non_https_and_unknown_hosts_are_refused(self):
        for url in ("http://paper-api.alpaca.markets", "https://evil.example.com", "https://api.alpaca.markets"):
            with self.subTest(url=url), self.assertRaises(bridge.LiveTradingRefused):
                bridge.resolve_base_url({"ALPACA_PAPER_BASE_URL": url})

    def test_missing_credentials_fail_closed(self):
        with self.assertRaises(bridge.BridgeNotConfigured):
            bridge.AlpacaPaperReadOnlyClient(env={}, transport=FakeAlpaca())

    def test_path_allow_list_is_enforced(self):
        client = make_client(FakeAlpaca())
        for path in ("/v2/orders/o-1", "/v2/positions/AAPL", "/v2/account/configurations"):
            with self.subTest(path=path), self.assertRaises(bridge.BridgeError):
                client.get(path)

    def test_every_outbound_call_is_a_get(self):
        _, fake = full_snapshot()
        self.assertEqual(fake.methods, {"GET"})
        self.assertGreaterEqual(len(fake.calls), 6)

    def test_no_write_verb_or_order_execution_code_path_exists(self):
        for name in ("alpaca_bridge.py", "trading_api.py", "trading_evidence.py"):
            source = (CC_DIR / name).read_text(encoding="utf-8")
            # Strip the module docstring/comments is unnecessary: assert on the
            # concrete call shapes that could ever mutate a brokerage account.
            for forbidden in ('"POST"', "'POST'", '"DELETE"', "'DELETE'", '"PATCH"', "'PATCH'",
                              '"PUT"', "'PUT'", "router.post", "router.delete", "router.patch", "router.put"):
                with self.subTest(module=name, token=forbidden):
                    self.assertNotIn(forbidden, source)

    def test_bridge_config_reports_read_only_and_hides_credentials(self):
        config = bridge.bridge_config(dict(PAPER_ENV))
        self.assertTrue(config["read_only"])
        self.assertFalse(config["live_trading_enabled"])
        self.assertFalse(config["order_execution_enabled"])
        self.assertTrue(config["credentials_present"])
        self.assertNotIn(PAPER_ENV["ALPACA_PAPER_SECRET_KEY"], json.dumps(config))
        self.assertNotIn(PAPER_ENV["ALPACA_PAPER_KEY_ID"], json.dumps(config))


class CredentialContainmentTests(unittest.TestCase):
    def test_credentials_are_sent_only_in_outbound_headers(self):
        _, fake = full_snapshot()
        header_values = {v for _, _, headers in fake.calls for v in headers.values()}
        self.assertIn(PAPER_ENV["ALPACA_PAPER_SECRET_KEY"], header_values)
        for _, url, _ in fake.calls:
            self.assertNotIn(PAPER_ENV["ALPACA_PAPER_SECRET_KEY"], url)
            self.assertNotIn(PAPER_ENV["ALPACA_PAPER_KEY_ID"], url)

    def test_snapshot_never_contains_credential_material(self):
        snapshot, _ = full_snapshot()
        encoded = json.dumps(snapshot)
        self.assertNotIn(PAPER_ENV["ALPACA_PAPER_SECRET_KEY"], encoded)
        self.assertNotIn(PAPER_ENV["ALPACA_PAPER_KEY_ID"], encoded)
        self.assertNotIn("PA123456", encoded)
        self.assertTrue(snapshot["account"]["account_number_present"])

    def test_credential_scan_raises_when_a_secret_would_be_emitted(self):
        leaking = {"oops": PAPER_ENV["ALPACA_PAPER_SECRET_KEY"]}
        with self.assertRaises(bridge.BridgeError):
            bridge.assert_no_credentials(leaking, dict(PAPER_ENV))
        bridge.assert_no_credentials({"safe": True}, dict(PAPER_ENV))


class DerivedMetricTests(unittest.TestCase):
    def test_fifo_round_trips_cover_long_short_and_direction(self):
        trips = bridge.compute_round_trips(FILLS)
        self.assertEqual(len(trips), 3)
        by_symbol = {t["symbol"]: t for t in trips}
        self.assertEqual(by_symbol["TSLA"]["realized_pnl"], 300.0)
        self.assertEqual(by_symbol["TSLA"]["direction"], "long")
        self.assertEqual(by_symbol["SPY"]["realized_pnl"], -100.0)
        self.assertEqual(by_symbol["GOOG"]["realized_pnl"], 100.0)
        self.assertEqual(by_symbol["GOOG"]["direction"], "short")

    def test_partial_fills_match_fifo_oldest_lot_first(self):
        fills = [
            {"id": "a", "symbol": "X", "side": "buy", "qty": "10", "price": "100",
             "transaction_time": "2026-08-01T00:00:00Z"},
            {"id": "b", "symbol": "X", "side": "buy", "qty": "10", "price": "120",
             "transaction_time": "2026-08-02T00:00:00Z"},
            {"id": "c", "symbol": "X", "side": "sell", "qty": "15", "price": "130",
             "transaction_time": "2026-08-03T00:00:00Z"},
        ]
        trips = bridge.compute_round_trips(fills)
        self.assertEqual(len(trips), 2)
        # Oldest lot (100) closes first for its full 10, then 5 from the 120 lot.
        self.assertEqual((trips[0]["qty"], trips[0]["realized_pnl"]), (10.0, 300.0))
        self.assertEqual((trips[1]["qty"], trips[1]["realized_pnl"]), (5.0, 50.0))

    def test_open_position_produces_no_realized_pnl(self):
        fills = [{"id": "a", "symbol": "X", "side": "buy", "qty": "10", "price": "100",
                  "transaction_time": "2026-08-01T00:00:00Z"}]
        self.assertEqual(bridge.compute_round_trips(fills), [])

    def test_win_loss_metrics(self):
        stats = bridge.compute_win_loss(bridge.compute_round_trips(FILLS))
        self.assertEqual(stats["closed_trades"], 3)
        self.assertEqual((stats["wins"], stats["losses"]), (2, 1))
        self.assertAlmostEqual(stats["win_rate"], 2 / 3, places=4)
        self.assertEqual(stats["realized_pnl"], 300.0)
        self.assertEqual(stats["profit_factor"], 4.0)  # 400 gross profit / 100 gross loss
        self.assertEqual(stats["largest_win"], 300.0)
        self.assertEqual(stats["largest_loss"], -100.0)

    def test_no_trades_reports_unavailable_not_fabricated_zero_rates(self):
        stats = bridge.compute_win_loss([])
        self.assertEqual(stats["closed_trades"], 0)
        self.assertIsNone(stats["win_rate"])
        self.assertIsNone(stats["profit_factor"])
        self.assertIsNone(stats["expectancy"])

    def test_profit_factor_is_null_rather_than_a_sentinel_when_no_losses(self):
        trips = [{"symbol": "X", "realized_pnl": 50.0}, {"symbol": "X", "realized_pnl": 25.0}]
        self.assertIsNone(bridge.compute_win_loss(trips)["profit_factor"])

    def test_drawdown_is_peak_to_trough(self):
        dd = bridge.compute_drawdown(HISTORY["equity"], HISTORY["timestamp"])
        self.assertEqual(dd["peak_equity"], 106000.0)
        self.assertEqual(dd["trough_equity"], 98000.0)
        self.assertEqual(dd["max_drawdown_usd"], 8000.0)
        self.assertAlmostEqual(dd["max_drawdown_pct"], 7.5472, places=3)
        self.assertEqual(dd["peak_at"], 2)
        self.assertEqual(dd["trough_at"], 3)

    def test_drawdown_on_empty_series_is_unavailable(self):
        dd = bridge.compute_drawdown([], [])
        self.assertEqual(dd["points"], 0)
        self.assertIsNone(dd["max_drawdown_usd"])
        self.assertIsNone(dd["max_drawdown_pct"])

    def test_strategy_performance_merges_realized_and_unrealized(self):
        rows = bridge.compute_strategy_performance(bridge.compute_round_trips(FILLS), POSITIONS)
        by_symbol = {r["symbol"]: r for r in rows}
        self.assertEqual(by_symbol["TSLA"]["realized_pnl"], 300.0)
        self.assertEqual(by_symbol["AAPL"]["unrealized_pnl"], 500.0)
        self.assertEqual(by_symbol["AAPL"]["closed_trades"], 0)
        self.assertIsNone(by_symbol["AAPL"]["win_rate"])
        self.assertEqual(by_symbol["MSFT"]["total_pnl"], -100.0)
        self.assertEqual(rows, sorted(rows, key=lambda r: r["total_pnl"], reverse=True))

    def test_snapshot_reports_every_requested_dimension(self):
        snapshot, _ = full_snapshot()
        self.assertEqual(snapshot["account"]["equity"], 104250.75)
        self.assertEqual(snapshot["account"]["buying_power"], 208501.5)
        self.assertEqual(snapshot["positions"]["count"], 2)
        self.assertEqual(snapshot["positions"]["unrealized_pnl"], 400.0)
        self.assertEqual(snapshot["orders"]["open_count"], 1)
        self.assertEqual(snapshot["orders"]["closed_count"], 1)
        self.assertEqual(snapshot["fills"]["count"], 6)
        self.assertEqual(snapshot["trade_history"]["closed_round_trips"], 3)
        self.assertEqual(snapshot["pnl"]["realized"], 300.0)
        self.assertEqual(snapshot["pnl"]["unrealized"], 400.0)
        self.assertEqual(snapshot["pnl"]["total"], 700.0)
        self.assertEqual(snapshot["pnl"]["session"], 350.5)
        self.assertEqual(snapshot["win_loss"]["closed_trades"], 3)
        self.assertEqual(snapshot["drawdown"]["max_drawdown_usd"], 8000.0)
        self.assertTrue(snapshot["strategy_performance"])
        self.assertEqual(snapshot["mode"], "paper")
        self.assertTrue(snapshot["read_only"])
        self.assertFalse(snapshot["live_trading_enabled"])

    def test_bot_health_observes_engine_and_flags_staleness(self):
        fake = FakeAlpaca()
        fresh = bridge.bot_health(env={}, transport=fake,
                                  now=datetime(2026, 8, 28, 14, 5, tzinfo=timezone.utc))
        self.assertTrue(fresh["connected"])
        self.assertFalse(fresh["live_trading"])
        self.assertFalse(fresh["stale"])
        self.assertEqual(fresh["cycles_run"], 42)

        stale = bridge.bot_health(env={}, transport=fake,
                                  now=datetime(2026, 8, 29, 14, 5, tzinfo=timezone.utc))
        self.assertTrue(stale["stale"])

    def test_bot_health_unreachable_is_reported_not_faked(self):
        state = bridge.bot_health(env={}, transport=FakeAlpaca(status_code=502))
        self.assertFalse(state["connected"])
        self.assertIn("502", state["reason"])

    def test_rejected_credentials_surface_as_a_bridge_error(self):
        client = make_client(FakeAlpaca(status_code=401))
        with self.assertRaises(bridge.BridgeError) as ctx:
            client.get("/v2/account")
        self.assertIn("credentials rejected", str(ctx.exception))

    def test_unavailable_snapshot_is_truthful(self):
        snap = bridge.unavailable_snapshot("no credentials")
        self.assertFalse(snap["connected"])
        self.assertIsNone(snap["account"])
        self.assertIsNone(snap["win_loss"])
        self.assertFalse(snap["live_trading_enabled"])
        self.assertTrue(snap["read_only"])


class LedgerEvidenceTests(unittest.TestCase):
    def test_observation_appends_a_record_the_control_plane_can_verify(self):
        snapshot, _ = full_snapshot()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "alpaca-paper-observations.jsonl"
            first = evidence.record_observation(snapshot, path=path)
            second = evidence.record_observation(snapshot, path=path)
            self.assertEqual((first["sequence"], second["sequence"]), (1, 2))
            # Verified by the canonical control-plane implementation, not a copy.
            result = AppendOnlyLedger(path).verify()
            self.assertTrue(result["valid"])
            self.assertEqual(result["record_count"], 2)
            self.assertEqual(evidence.verify(path)["record_count"], 2)

    def test_ledger_detects_tampering_with_a_trading_observation(self):
        snapshot, _ = full_snapshot()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ledger.jsonl"
            evidence.record_observation(snapshot, path=path)
            record = json.loads(path.read_text(encoding="utf-8").strip())
            record["payload"]["account"]["equity"] = 999999.99
            path.write_text(json.dumps(record) + "\n", encoding="utf-8")
            verified = evidence.verify(path)
            self.assertFalse(verified["valid"])

    def test_evidence_payload_carries_governance_flags_and_no_secrets(self):
        snapshot, _ = full_snapshot()
        payload = evidence.build_evidence_payload(snapshot)
        encoded = json.dumps(payload)
        self.assertNotIn(PAPER_ENV["ALPACA_PAPER_SECRET_KEY"], encoded)
        self.assertNotIn(PAPER_ENV["ALPACA_PAPER_KEY_ID"], encoded)
        self.assertNotIn("PA123456", encoded)
        self.assertTrue(payload["governance"]["read_only"])
        self.assertFalse(payload["governance"]["live_trading_enabled"])
        self.assertFalse(payload["governance"]["order_execution_enabled"])
        self.assertEqual(payload["counts"]["closed_round_trips"], 3)
        self.assertEqual(len(payload["snapshot_sha256"]), 64)

    def test_evidence_payload_omits_raw_order_and_fill_bodies(self):
        snapshot, _ = full_snapshot()
        payload = evidence.build_evidence_payload(snapshot)
        self.assertNotIn("items", json.dumps(payload))
        self.assertNotIn("o-open-1", json.dumps(payload))

    def test_missing_ledger_is_reported_as_absent_not_invalid(self):
        result = evidence.verify(Path("/definitely/not/a/ledger.jsonl"))
        self.assertTrue(result["valid"])
        self.assertFalse(result["present"])
        self.assertEqual(result["record_count"], 0)

    def test_unavailable_snapshot_is_still_recorded_as_evidence(self):
        snap = bridge.unavailable_snapshot("credentials absent")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ledger.jsonl"
            evidence.record_observation(snap, path=path)
            payload = json.loads(path.read_text(encoding="utf-8").strip())["payload"]
            self.assertFalse(payload["connected"])
            self.assertEqual(payload["reason"], "credentials absent")
            self.assertTrue(AppendOnlyLedger(path).verify()["valid"])


class GovernanceContractTests(unittest.TestCase):
    def setUp(self):
        self.policy = json.loads(
            (ROOT / "governance" / "alpaca_paper_readonly_bridge_policy.json").read_text(encoding="utf-8")
        )

    def test_live_trading_remains_blocked_in_activation_gates(self):
        gates = json.loads((ROOT / "governance" / "runtime_activation_gates.json").read_text(encoding="utf-8"))
        self.assertIn("live_trading", gates["blocked_capabilities"])
        self.assertIn("live_financial_execution", gates["blocked_capabilities"])
        self.assertFalse(gates["external_execution_enabled"])

    def test_policy_blocks_every_execution_capability(self):
        for capability in ("live_trading", "order_submission", "order_cancellation",
                           "position_liquidation", "fund_transfer"):
            self.assertIn(capability, self.policy["blocked_capabilities"])
        self.assertEqual(self.policy["mode"], "paper")
        self.assertIn("live_trading", self.policy["founder_holds_preserved"])

    def test_policy_routes_match_the_implemented_router(self):
        source = (CC_DIR / "trading_api.py").read_text(encoding="utf-8")
        for route in self.policy["surface"]["routes"]:
            suffix = route.split("/api/trading/paper", 1)[1]
            self.assertIn(f'@router.get("{suffix}"', source)
        self.assertEqual(self.policy["surface"]["methods"], ["GET"])

    def test_policy_states_the_remaining_activation_step(self):
        step = self.policy["remaining_activation_step"]
        self.assertIn("ALPACA_PAPER_KEY_ID", step)
        self.assertIn("COMMAND_CENTER_API_KEY", step)
        self.assertEqual(self.policy["status"], "built_pending_founder_activation")


class PackagingTests(unittest.TestCase):
    def test_docker_image_packages_every_new_module(self):
        dockerfile = (CC_DIR / "Dockerfile").read_text(encoding="utf-8")
        for name in ("alpaca_bridge.py", "trading_api.py", "trading_evidence.py"):
            self.assertIn(name, dockerfile)

    def test_compose_supplies_server_side_credentials_and_ledger_mount(self):
        compose = (ROOT / "docker-compose.command-center.yml").read_text(encoding="utf-8")
        for key in ("ALPACA_PAPER_KEY_ID", "ALPACA_PAPER_SECRET_KEY", "COMMAND_CENTER_API_KEY",
                    "TRADING_LEDGER_PATH", "ALPACA_PAPER_BASE_URL"):
            self.assertIn(key, compose)
        self.assertIn("/app/control_plane:ro", compose)

    def test_compose_never_hardcodes_a_credential_value(self):
        compose = (ROOT / "docker-compose.command-center.yml").read_text(encoding="utf-8")
        for line in compose.splitlines():
            if "ALPACA_PAPER_KEY_ID:" in line or "ALPACA_PAPER_SECRET_KEY:" in line:
                self.assertIn("${", line)

    def test_bridge_adds_no_new_python_dependency(self):
        requirements = (CC_DIR / "requirements.txt").read_text(encoding="utf-8")
        self.assertNotIn("alpaca", requirements.lower())
        self.assertNotIn("requests", requirements.lower())
        source = (CC_DIR / "alpaca_bridge.py").read_text(encoding="utf-8")
        self.assertNotIn("import httpx", source)
        self.assertNotIn("import requests", source)


@unittest.skipUnless(HTTP_DEPS, "fastapi/httpx not installed on this runner")
class AuthenticatedSurfaceTests(unittest.TestCase):
    KEY = "dominion-phone-key-abcdefghijklmnop"

    def setUp(self):
        for module in ("trading_api", "app"):
            sys.modules.pop(module, None)
        self._saved = {k: os.environ.get(k) for k in
                       ("COMMAND_CENTER_API_KEY", "TRADING_LEDGER_PATH",
                        "ALPACA_PAPER_KEY_ID", "ALPACA_PAPER_SECRET_KEY",
                        "TRADING_SNAPSHOT_TTL_SECONDS")}
        self._tmp = tempfile.TemporaryDirectory()
        os.environ["COMMAND_CENTER_API_KEY"] = self.KEY
        os.environ["TRADING_LEDGER_PATH"] = str(Path(self._tmp.name) / "ledger.jsonl")
        os.environ["TRADING_SNAPSHOT_TTL_SECONDS"] = "0"
        os.environ.update(PAPER_ENV)

        import trading_api
        self.trading_api = trading_api
        trading_api._cache.invalidate()
        from fastapi import FastAPI
        api = FastAPI()
        api.include_router(trading_api.router)
        self.client = TestClient(api)

    def tearDown(self):
        self._tmp.cleanup()
        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        sys.modules.pop("trading_api", None)

    def auth(self):
        return {"X-Dominion-Key": self.KEY}

    def test_every_route_rejects_unauthenticated_access(self):
        for route in ("health", "summary", "account", "positions", "orders",
                      "fills", "history", "performance", "evidence"):
            with self.subTest(route=route):
                self.assertEqual(self.client.get(f"/api/trading/paper/{route}").status_code, 401)

    def test_wrong_key_is_rejected(self):
        response = self.client.get("/api/trading/paper/summary",
                                   headers={"X-Dominion-Key": "wrong-key-wrong-key-wrong-key"})
        self.assertEqual(response.status_code, 401)

    def test_surface_fails_closed_when_no_server_key_is_configured(self):
        os.environ.pop("COMMAND_CENTER_API_KEY")
        response = self.client.get("/api/trading/paper/summary", headers=self.auth())
        self.assertEqual(response.status_code, 503)
        self.assertIn("unconfigured", response.json()["detail"])

    def test_surface_refuses_a_weak_server_key(self):
        os.environ["COMMAND_CENTER_API_KEY"] = "short"
        response = self.client.get("/api/trading/paper/summary",
                                   headers={"X-Dominion-Key": "short"})
        self.assertEqual(response.status_code, 503)

    def test_write_methods_are_not_routed(self):
        for method in ("post", "put", "patch", "delete"):
            with self.subTest(method=method):
                response = getattr(self.client, method)("/api/trading/paper/summary", headers=self.auth())
                self.assertEqual(response.status_code, 405)

    def test_health_reports_read_only_configuration(self):
        body = self.client.get("/api/trading/paper/health", headers=self.auth()).json()
        self.assertEqual(body["config"]["mode"], "paper")
        self.assertTrue(body["config"]["read_only"])
        self.assertFalse(body["config"]["live_trading_enabled"])
        self.assertTrue(body["config"]["credentials_present"])
        self.assertEqual(body["activation_state"], "ready")
        self.assertNotIn(PAPER_ENV["ALPACA_PAPER_SECRET_KEY"], json.dumps(body))

    def test_summary_serves_governed_data_and_writes_evidence(self):
        fake = FakeAlpaca()
        self.trading_api.alpaca_bridge._default_transport = fake
        original = self.trading_api.alpaca_bridge.build_snapshot

        def patched(client, **kwargs):
            kwargs["bot_transport"] = fake
            return original(client, **kwargs)

        self.trading_api.alpaca_bridge.build_snapshot = patched
        try:
            body = self.client.get("/api/trading/paper/summary", headers=self.auth()).json()
        finally:
            self.trading_api.alpaca_bridge.build_snapshot = original

        self.assertTrue(body["connected"])
        self.assertFalse(body["live_trading_enabled"])
        self.assertTrue(body["read_only"])
        self.assertEqual(body["account"]["equity"], 104250.75)
        self.assertEqual(body["pnl"]["realized"], 300.0)
        self.assertEqual(body["win_loss"]["closed_trades"], 3)
        self.assertEqual(body["drawdown"]["max_drawdown_usd"], 8000.0)
        self.assertEqual(body["evidence"]["sequence"], 1)
        ledger = Path(os.environ["TRADING_LEDGER_PATH"])
        self.assertTrue(AppendOnlyLedger(ledger).verify()["valid"])
        self.assertNotIn(PAPER_ENV["ALPACA_PAPER_SECRET_KEY"], json.dumps(body))

    def test_unreachable_broker_returns_a_truthful_disconnected_envelope(self):
        os.environ.pop("ALPACA_PAPER_KEY_ID")
        body = self.client.get("/api/trading/paper/summary", headers=self.auth()).json()
        self.assertFalse(body["connected"])
        self.assertIn("ALPACA_PAPER_KEY_ID", body["reason"])
        self.assertIsNone(body["account"])
        self.assertFalse(body["live_trading_enabled"])


@unittest.skipUnless(HTTP_DEPS, "fastapi/httpx not installed on this runner")

def _route_paths(routes) -> set:
    """Every route path an app serves, including routes behind include_router.

    Newer FastAPI keeps included routers as `_IncludedRouter` objects in
    `app.routes` instead of flattening their routes into it. Those objects
    carry no `.path`, so reading paths off the top level alone silently misses
    every mounted sub-router — which would make these preservation assertions
    pass while checking nothing.
    """
    found = set()
    for route in routes:
        inner = getattr(route, "original_router", None)
        if inner is not None:
            found |= _route_paths(getattr(inner, "routes", []))
        path = getattr(route, "path", None)
        if path:
            found.add(path)
    return found


class LiveServicePreservationTests(unittest.TestCase):
    """The pre-existing Command Center surface must be unchanged."""

    def setUp(self):
        for module in ("app", "trading_api"):
            sys.modules.pop(module, None)
        # Other subprojects in this repository also provide a top-level `app`
        # and put their own root on sys.path. Claim command-center's `app.py`
        # here so a repository-wide run imports the module under test rather
        # than whichever `app` was resolved last.
        cc_entry = str(CC_DIR)
        if cc_entry in sys.path:
            sys.path.remove(cc_entry)
        sys.path.insert(0, cc_entry)
        os.environ.setdefault("COMMAND_CENTER_API_KEY", "dominion-phone-key-abcdefghijklmnop")
        import app as command_center
        self.app = command_center
        self.client = TestClient(command_center.app)

    def test_pre_existing_routes_all_still_exist(self):
        paths = _route_paths(self.app.app.routes)
        for path in ("/", "/health", "/api/status", "/api/chat",
                     "/api/revenue", "/api/revenue/events"):
            self.assertIn(path, paths)

    def test_trading_routes_are_additive_and_namespaced(self):
        paths = _route_paths(self.app.app.routes)
        trading = {p for p in paths if p.startswith("/api/trading/")}
        self.assertEqual(len(trading), 9)
        self.assertTrue(all(p.startswith("/api/trading/paper/") for p in trading))

    def test_health_still_serves_and_now_reports_bridge_state(self):
        body = self.client.get("/health").json()
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["service"], "dominion-command-center")
        # Pre-existing keys must survive.
        for key in ("truth_source_connected", "open_lane_count", "revenue_constraint",
                    "buddy_voice_surface", "lane_policy_connected"):
            self.assertIn(key, body)
        self.assertTrue(body["trading_bridge"]["mounted"])
        self.assertFalse(body["trading_bridge"]["live_trading_enabled"])
        self.assertTrue(body["trading_bridge"]["read_only"])

    def test_unauthenticated_health_leaks_no_account_data(self):
        body = json.dumps(self.client.get("/health").json())
        for token in ("equity", "buying_power", "PA123456", "positions"):
            self.assertNotIn(token, body)


if __name__ == "__main__":
    unittest.main(verbosity=2)
