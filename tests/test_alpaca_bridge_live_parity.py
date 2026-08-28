"""Side-by-side parity between the new bridge and the live Alpha engine.

The Dominion Alpha paper engine already computes win rate, profit factor and
expectancy for the running dashboard. If the phone surface used different
definitions it would show different numbers for the same trades, so this suite
runs both implementations over identical closed trades and compares them.

The live ``alpha_engine/dominion_alpha/performance.py`` is loaded as-is against
a stubbed data layer, so the comparison is against the real shipped code rather
than a restatement of it.
"""

from __future__ import annotations

import importlib.util
import sqlite3
import sys
import tempfile
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CC_DIR = ROOT / "apps" / "command-center"
ALPHA_PERF = ROOT / "alpha_engine" / "dominion_alpha" / "performance.py"

sys.path.insert(0, str(CC_DIR))
spec = importlib.util.spec_from_file_location("alpaca_bridge_parity", CC_DIR / "alpaca_bridge.py")
assert spec and spec.loader
bridge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)


def load_live_performance(db_path: Path):
    """Load the live engine's performance module against a stub data layer.

    Avoids the engine's runtime dependencies (dotenv, live DB path) while still
    executing its real code.
    """
    package = types.ModuleType("dominion_alpha")
    package.__path__ = [str(ALPHA_PERF.parent)]
    memory = types.ModuleType("dominion_alpha.memory")

    def get_conn():
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        return conn

    memory.get_conn = get_conn
    saved = {name: sys.modules.get(name) for name in ("dominion_alpha", "dominion_alpha.memory")}
    sys.modules["dominion_alpha"] = package
    sys.modules["dominion_alpha.memory"] = memory
    try:
        perf_spec = importlib.util.spec_from_file_location("dominion_alpha.performance", ALPHA_PERF)
        assert perf_spec and perf_spec.loader
        module = importlib.util.module_from_spec(perf_spec)
        perf_spec.loader.exec_module(module)
        return module
    finally:
        for name, value in saved.items():
            if value is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = value


def seed_live_trades(db_path: Path, closed: list[tuple[str, float]]) -> None:
    """Write SELL rows in the live engine's trades schema."""
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            token_address TEXT, symbol TEXT, action TEXT,
            price REAL, size_usd REAL, pnl REAL, capital_after REAL,
            timestamp TEXT, notes TEXT
        )
    """)
    capital = 1000.0
    for index, (symbol, pnl) in enumerate(closed, start=1):
        capital += pnl
        conn.execute(
            "INSERT INTO trades (token_address,symbol,action,price,size_usd,pnl,capital_after,timestamp,notes)"
            " VALUES (?,?,'SELL',?,?,?,?,?,?)",
            (f"0x{index}", symbol, 1.0, 100.0, pnl, capital, f"2026-08-{index:02d}T00:00:00", "exit"),
        )
    conn.commit()
    conn.close()


def bridge_trips(closed: list[tuple[str, float]]) -> list[dict]:
    """The same closed trades expressed as bridge round trips."""
    return [{"symbol": symbol, "realized_pnl": pnl} for symbol, pnl in closed]


# No breakeven trades, at least one loss: the domain where both engines share a
# definition. The two deliberate divergences are asserted separately below.
# The live engine rounds profit factor to 3 decimals; that rounding step is
# the only source of divergence, so it bounds the parity tolerance.
LIVE_PF_QUANTUM = 0.001

COMPARABLE = [
    ("TSLA", 300.0), ("SPY", -100.0), ("GOOG", 100.0),
    ("AAPL", 250.0), ("MSFT", -75.0), ("NVDA", -20.0), ("AMD", 40.0),
]


class LiveSystemParityTests(unittest.TestCase):
    def _both(self, closed):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "alpha.db"
            seed_live_trades(db, closed)
            live = load_live_performance(db).compute_performance()
        new = bridge.compute_win_loss(bridge_trips(closed))
        return live, new

    def test_trade_counts_and_classification_agree(self):
        live, new = self._both(COMPARABLE)
        self.assertEqual(live["total_trades"], new["closed_trades"])
        self.assertEqual(live["wins"], new["wins"])
        self.assertEqual(live["losses"], new["losses"])

    def test_win_rate_agrees_with_the_live_dashboard(self):
        live, new = self._both(COMPARABLE)
        self.assertAlmostEqual(live["win_rate"], new["win_rate"], places=4)

    def test_profit_factor_agrees_with_the_live_dashboard(self):
        live, new = self._both(COMPARABLE)
        # The live engine reports profit factor rounded to 3 decimals, the
        # bridge to 4, so parity is asserted to the live engine's precision.
        self.assertAlmostEqual(live["profit_factor"], new["profit_factor"], delta=LIVE_PF_QUANTUM)

    def test_expectancy_agrees_with_the_live_dashboard(self):
        live, new = self._both(COMPARABLE)
        self.assertAlmostEqual(live["expectancy"], new["expectancy"], places=3)

    def test_average_win_and_loss_agree(self):
        live, new = self._both(COMPARABLE)
        self.assertAlmostEqual(live["avg_win"], new["avg_win"], places=3)
        self.assertAlmostEqual(live["avg_loss"], new["avg_loss"], places=3)

    def test_total_realized_pnl_agrees(self):
        live, new = self._both(COMPARABLE)
        self.assertAlmostEqual(live["total_pnl"], new["realized_pnl"], places=3)

    def test_parity_holds_across_several_trade_mixes(self):
        mixes = [
            [("A", 10.0), ("B", -5.0)],
            [("A", 1.5), ("B", -0.25), ("C", 3.75), ("D", -2.0)],
            [("A", -10.0), ("B", -20.0), ("C", 5.0)],
        ]
        for mix in mixes:
            with self.subTest(mix=mix):
                live, new = self._both(mix)
                self.assertAlmostEqual(live["win_rate"], new["win_rate"], places=4)
                self.assertAlmostEqual(live["profit_factor"], new["profit_factor"], delta=LIVE_PF_QUANTUM)
                self.assertAlmostEqual(live["expectancy"], new["expectancy"], places=3)

    def test_empty_history_agrees_that_there_are_no_trades(self):
        live, new = self._both([])
        self.assertEqual(live["total_trades"], 0)
        self.assertEqual(new["closed_trades"], 0)
        # The live engine reports 0.0 rates; the bridge reports null. Both mean
        # "no trades", and the bridge avoids showing a 0% win rate on the phone
        # as if it were a measured result.
        self.assertEqual(live["win_rate"], 0.0)
        self.assertIsNone(new["win_rate"])


class DocumentedDivergenceTests(unittest.TestCase):
    """Two intentional differences, pinned so they cannot drift silently."""

    def test_breakeven_trades_are_classified_separately_by_the_bridge(self):
        closed = [("A", 100.0), ("B", 0.0), ("C", -50.0)]
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "alpha.db"
            seed_live_trades(db, closed)
            live = load_live_performance(db).compute_performance()
        new = bridge.compute_win_loss(bridge_trips(closed))
        # The live engine folds a breakeven trade into losses (pnl <= 0).
        self.assertEqual(live["losses"], 2)
        # The bridge reports it as breakeven so the loss count is not inflated.
        self.assertEqual(new["losses"], 1)
        self.assertEqual(new["breakeven"], 1)
        self.assertEqual(live["wins"], new["wins"])

    def test_bridge_reports_null_profit_factor_where_the_engine_uses_999(self):
        closed = [("A", 100.0), ("B", 50.0)]
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "alpha.db"
            seed_live_trades(db, closed)
            live = load_live_performance(db).compute_performance()
        new = bridge.compute_win_loss(bridge_trips(closed))
        self.assertEqual(live["profit_factor"], 999.0)
        self.assertIsNone(new["profit_factor"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
