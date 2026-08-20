#!/usr/bin/env python3
# ============================================================
# agents/markov_paper_trade.py — DOMINION MARKOV PAPER TRADER
# Runs daily on VM via systemd timer. Logs all decisions.
# Sends weekly performance email.
#
# Best config from backtest:
#   Memory=4, Train=70%, Risk=10%, MinProb=0.52, BTC-USD only
#   Sharpe=2.25, WR=66.7%, MaxDD=0.0%
#
# Usage:
#   python markov_paper_trade.py run       # One daily iteration
#   python markov_paper_trade.py status    # Print current state
#   python markov_paper_trade.py report    # Print full report
#   python markov_paper_trade.py email     # Send weekly email
# ============================================================

import os
import sys
import json
import logging
import smtplib
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv(dotenv_path=Path.home() / "buddy_core" / ".env")
load_dotenv(dotenv_path=Path.home() / ".env")
load_dotenv(override=True)

try:
    from phi_constants import PHI, INV_PHI, INV_PHI2
except ImportError:
    PHI = 1.618033988749895
    INV_PHI = 1 / PHI
    INV_PHI2 = INV_PHI ** 2

log = logging.getLogger("paper_trade")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | PAPER_TRADE | %(levelname)s | %(message)s",
)

# ── Config ────────────────────────────────────────────────────

DATA_DIR = Path.home() / "trading_data"
DATA_DIR.mkdir(exist_ok=True)

STATE_FILE = DATA_DIR / "markov_paper_state.json"
JOURNAL_FILE = DATA_DIR / "markov_paper_journal.json"
LOG_FILE = DATA_DIR / "markov_paper.log"

# Add file handler
fh = logging.FileHandler(LOG_FILE, encoding="utf-8")
fh.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))
log.addHandler(fh)

SYMBOL = "BTC-USD"
CONFIG = {
    "memory": 4,
    "train_ratio": 0.70,
    "risk_per_trade_pct": 10.0,
    "min_probability": 0.65,
    "initial_capital": 10000.0,
    "max_daily_loss_pct": 3.0,
    "max_drawdown_pct": 50.0,
    "buy_fee": 0.001,
    "sell_fee": 0.001,
}

EMAIL_TO = os.getenv("DIGEST_EMAIL", "founder-personal@example.invalid")
EMAIL_FROM = os.getenv("EMAIL_ADDRESS", "founder-business@example.invalid")
EMAIL_PASS = os.getenv("EMAIL_PASSWORD", "")


# ── Markov Engine (same as strategy file) ─────────────────────

class MarkovEngine:
    def __init__(self, memory=4):
        self.memory = memory
        self.chains = {}

    def train(self, prices, symbol="BTC-USD"):
        if len(prices) < self.memory + 10:
            return
        states = 2
        occ = np.zeros((states,) * (2 + self.memory))
        for i in range(2 + self.memory, len(prices)):
            jumps = [int(prices[i - j] <= prices[i - j - 1]) for j in range(self.memory + 2)]
            jumps = list(reversed(jumps[2:])) + jumps[:2]
            occ[tuple(jumps)] += 1
        chain = occ.copy()
        dim = len(np.shape(occ))
        axis = dim - 2
        for index in np.ndindex(np.shape(occ)):
            slicer = [index[i] if i != axis else slice(None) for i in range(len(index))]
            total = sum(occ[tuple(slicer)])
            chain[index] = chain[index] / total if total > 0 else 0.5
        self.chains[symbol] = chain

    def predict(self, recent, symbol="BTC-USD", holding=False):
        if symbol not in self.chains or len(recent) < self.memory + 2:
            return 0.5
        chain = self.chains[symbol]
        priors = list(reversed([
            int(recent[-(j + 1)] <= recent[-(j + 2)])
            for j in range(self.memory + 1)
        ]))
        flag = 1 if holding else 0
        key = tuple(priors[:-1]) + (flag,) + (priors[-1],)
        try:
            return float(chain[key])
        except (IndexError, KeyError):
            return 0.5

    def regime(self, prices, window=20):
        if len(prices) < window + 5:
            return "UNKNOWN"
        recent = prices[-window:]
        up = sum(1 for i in range(1, len(recent)) if recent[i] > recent[i - 1])
        ratio = up / (len(recent) - 1)
        if ratio > 0.618:
            return "TRENDING_UP"
        elif ratio < 0.382:
            return "TRENDING_DOWN"
        return "RANGING"


# ── State Management ──────────────────────────────────────────

def load_state():
    if STATE_FILE.exists():
        with open(STATE_FILE) as f:
            return json.load(f)
    return {
        "balance": CONFIG["initial_capital"],
        "peak_balance": CONFIG["initial_capital"],
        "holding": False,
        "buy_price": 0,
        "shares": 0,
        "daily_loss": 0,
        "kill_switch": False,
        "start_date": datetime.now().isoformat(),
        "last_run": None,
        "trade_count": 0,
        "win_count": 0,
        "loss_count": 0,
        "total_pnl": 0,
    }


def save_state(state):
    tmp = str(STATE_FILE) + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state, f, indent=2)
    os.replace(tmp, str(STATE_FILE))


def load_journal():
    if JOURNAL_FILE.exists():
        with open(JOURNAL_FILE) as f:
            return json.load(f)
    return []


def save_journal(journal):
    tmp = str(JOURNAL_FILE) + ".tmp"
    with open(tmp, "w") as f:
        json.dump(journal[-500:], f, indent=2)
    os.replace(tmp, str(JOURNAL_FILE))


# ── Position Sizing ───────────────────────────────────────────

def position_size(balance, price, regime):
    risk = balance * (CONFIG["risk_per_trade_pct"] / 100)
    if regime == "TRENDING_UP":
        scale = 1.0
    elif regime == "TRENDING_DOWN":
        scale = INV_PHI2
    else:
        scale = INV_PHI
    dollar = risk * scale
    if price <= 0 or not np.isfinite(price):
        return 0
    return max(0.0001, round(dollar / price, 6))


# ── Daily Iteration ──────────────────────────────────────────

def run_iteration():
    """Execute one paper trading iteration."""
    import yfinance as yf

    state = load_state()
    journal = load_journal()

    # Reset daily counters
    today = datetime.now().strftime("%Y-%m-%d")
    if state.get("last_run_date") != today:
        state["daily_loss"] = 0
        if state.get("kill_switch") and state["balance"] > state["peak_balance"] * 0.5:
            state["kill_switch"] = False
        state["last_run_date"] = today

    # Kill switch check
    if state["kill_switch"]:
        log.warning("KILL SWITCH ACTIVE — skipping")
        state["last_run"] = datetime.now().isoformat()
        save_state(state)
        return state

    # Drawdown check
    dd = (1 - state["balance"] / state["peak_balance"]) * 100 if state["peak_balance"] > 0 else 0
    if dd >= CONFIG["max_drawdown_pct"]:
        state["kill_switch"] = True
        log.error(f"MAX DRAWDOWN {dd:.1f}% — KILL SWITCH ENGAGED")
        save_state(state)
        return state

    # Fetch BTC data
    ticker = yf.Ticker(SYMBOL)
    hist = ticker.history(period="1y")
    if hist.empty or len(hist) < 50:
        log.error("Insufficient BTC data from yfinance")
        return state

    prices = hist["Close"].values
    current_price = float(prices[-1])

    # Train Markov chain on 70% of data
    train_size = int(len(prices) * CONFIG["train_ratio"])
    engine = MarkovEngine(memory=CONFIG["memory"])
    engine.train(prices[:train_size], SYMBOL)

    recent = list(prices[-CONFIG["memory"] - 3:])
    regime = engine.regime(prices)

    log.info(f"BTC=${current_price:,.2f} | Balance=${state['balance']:,.2f} | "
             f"Regime={regime} | Holding={state['holding']}")

    entry = {
        "ts": datetime.now().isoformat(),
        "price": round(current_price, 2),
        "regime": regime,
        "balance": round(state["balance"], 2),
    }

    if not state["holding"]:
        prob = engine.predict(recent, SYMBOL, holding=False)
        entry["buy_prob"] = round(prob, 4)

        if regime == "TRENDING_DOWN":
            entry["action"] = "SKIP_DOWNTREND"
            log.info(f"Hold cash -- regime=TRENDING_DOWN, no buys in downtrend")
        elif prob > CONFIG["min_probability"]:
            size = position_size(state["balance"], current_price, regime)
            cost = size * current_price * (1 + CONFIG["buy_fee"])

            if cost <= state["balance"]:
                state["holding"] = True
                state["buy_price"] = current_price
                state["shares"] = size
                entry["action"] = "BUY"
                entry["size"] = size
                entry["cost"] = round(cost, 2)
                log.info(f"BUY {size:.6f} BTC @ ${current_price:,.2f} (prob={prob:.3f}, regime={regime})")
            else:
                entry["action"] = "SKIP_INSUFFICIENT_FUNDS"
                log.info(f"Skip buy — cost ${cost:.2f} > balance ${state['balance']:.2f}")
        else:
            entry["action"] = "HOLD_CASH"
            log.info(f"Hold cash — prob={prob:.3f} < {CONFIG['min_probability']}")
    else:
        prob = engine.predict(recent, SYMBOL, holding=True)
        entry["sell_prob"] = round(prob, 4)

        unrealized_pct = (current_price - state["buy_price"]) / state["buy_price"] * 100 if state["buy_price"] > 0 else 0
        stop_loss_hit = unrealized_pct <= -2.0

        if stop_loss_hit:
            log.info(f"STOP LOSS HIT -- {unrealized_pct:.2f}% -- forcing sell")
            prob = 1.0  # force sell path

        if prob > CONFIG["min_probability"]:
            sell_value = state["shares"] * current_price * (1 - CONFIG["sell_fee"])
            buy_cost = state["shares"] * state["buy_price"]
            pnl = sell_value - buy_cost

            state["holding"] = False
            state["trade_count"] += 1
            state["total_pnl"] += pnl
            state["balance"] += pnl

            if pnl >= 0:
                state["win_count"] += 1
            else:
                state["loss_count"] += 1
                state["daily_loss"] += abs(pnl)

            if state["balance"] > state["peak_balance"]:
                state["peak_balance"] = state["balance"]

            # Daily loss check
            daily_limit = state["balance"] * (CONFIG["max_daily_loss_pct"] / 100)
            if state["daily_loss"] >= daily_limit:
                state["kill_switch"] = True

            entry["action"] = "SELL"
            entry["pnl"] = round(pnl, 2)
            entry["size"] = state["shares"]
            log.info(f"SELL {state['shares']:.6f} BTC @ ${current_price:,.2f} | "
                     f"PnL=${pnl:+,.2f} | Balance=${state['balance']:,.2f}")

            state["shares"] = 0
            state["buy_price"] = 0
        else:
            # Track unrealized PnL
            unrealized = (current_price - state["buy_price"]) * state["shares"]
            entry["action"] = "HOLD_POSITION"
            entry["unrealized_pnl"] = round(unrealized, 2)
            log.info(f"Hold position — prob={prob:.3f} | Unrealized=${unrealized:+,.2f}")

    state["last_run"] = datetime.now().isoformat()
    journal.append(entry)
    save_state(state)
    save_journal(journal)
    return state


# ── Reporting ─────────────────────────────────────────────────

def get_report(state=None):
    if state is None:
        state = load_state()
    journal = load_journal()

    days_active = 0
    if state.get("start_date"):
        start = datetime.fromisoformat(state["start_date"])
        days_active = (datetime.now() - start).days

    wr = (state["win_count"] / state["trade_count"] * 100) if state["trade_count"] > 0 else 0
    dd = (1 - state["balance"] / state["peak_balance"]) * 100 if state["peak_balance"] > 0 else 0
    ret = (state["balance"] / CONFIG["initial_capital"] - 1) * 100

    # Recent trades
    recent_trades = [e for e in journal[-20:] if e.get("action") in ("BUY", "SELL")]

    return {
        "days_active": days_active,
        "balance": round(state["balance"], 2),
        "initial_capital": CONFIG["initial_capital"],
        "total_return_pct": round(ret, 2),
        "total_pnl": round(state["total_pnl"], 2),
        "peak_balance": round(state["peak_balance"], 2),
        "max_drawdown_pct": round(dd, 2),
        "trade_count": state["trade_count"],
        "win_count": state["win_count"],
        "loss_count": state["loss_count"],
        "win_rate": round(wr, 2),
        "holding": state["holding"],
        "kill_switch": state["kill_switch"],
        "config": CONFIG,
        "recent_trades": recent_trades,
    }


def send_weekly_email():
    """Send weekly performance report via SMTP."""
    if not EMAIL_PASS:
        log.warning("No EMAIL_PASSWORD set — skipping email")
        return

    report = get_report()
    subject = f"Dominion Markov Paper Trade — Week Report ({datetime.now().strftime('%Y-%m-%d')})"

    body = f"""DOMINION MARKOV PAPER TRADE — WEEKLY REPORT
{'='*50}

Days Active:     {report['days_active']}
Balance:         ${report['balance']:,.2f}
Total Return:    {report['total_return_pct']}%
Total PnL:       ${report['total_pnl']:+,.2f}
Peak Balance:    ${report['peak_balance']:,.2f}
Max Drawdown:    {report['max_drawdown_pct']}%

Trades:          {report['trade_count']}
Win Rate:        {report['win_rate']}%
Wins/Losses:     {report['win_count']}/{report['loss_count']}

Currently Holding: {'YES' if report['holding'] else 'NO'}
Kill Switch:       {'ACTIVE' if report['kill_switch'] else 'OFF'}

Config:
  Memory:    {CONFIG['memory']}
  Risk/Trade: {CONFIG['risk_per_trade_pct']}%
  Min Prob:  {CONFIG['min_probability']}
  Train:     {CONFIG['train_ratio']*100:.0f}%
  Asset:     BTC-USD

{'='*50}
30-day paper trade requirement: {'MET' if report['days_active'] >= 30 else f'{30 - report["days_active"]} days remaining'}
Go-live criteria: WR>40%, Sharpe>1.0, DD<50%
{'='*50}
"""

    msg = MIMEMultipart()
    msg["From"] = EMAIL_FROM
    msg["To"] = EMAIL_TO
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    try:
        with smtplib.SMTP("mail.privateemail.com", 587, timeout=10) as server:
            server.starttls()
            server.login(EMAIL_FROM, EMAIL_PASS)
            server.send_message(msg)
        log.info(f"Weekly report sent to {EMAIL_TO}")
    except Exception as e:
        log.error(f"Email failed: {e}")
        # Try dominionhealing.org SMTP
        try:
            with smtplib.SMTP("mail.dominionhealing.org", 587, timeout=10) as server:
                server.starttls()
                server.login(EMAIL_FROM, EMAIL_PASS)
                server.send_message(msg)
            log.info(f"Weekly report sent via dominionhealing.org to {EMAIL_TO}")
        except Exception as e2:
            log.error(f"Fallback email also failed: {e2}")


# ── CLI ───────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Dominion Markov Paper Trader")
    parser.add_argument("command", choices=["run", "status", "report", "email", "reset"],
                        help="Command to execute")
    args = parser.parse_args()

    if args.command == "run":
        state = run_iteration()
        print(f"Balance: ${state['balance']:,.2f} | Trades: {state['trade_count']} | "
              f"Holding: {state['holding']}")

    elif args.command == "status":
        state = load_state()
        print(json.dumps(state, indent=2))

    elif args.command == "report":
        report = get_report()
        print(f"\nDOMINION MARKOV PAPER TRADE")
        print(f"{'='*40}")
        print(f"Days Active:  {report['days_active']}")
        print(f"Balance:      ${report['balance']:,.2f}")
        print(f"Return:       {report['total_return_pct']}%")
        print(f"Win Rate:     {report['win_rate']}%")
        print(f"Max DD:       {report['max_drawdown_pct']}%")
        print(f"Trades:       {report['trade_count']}")
        print(f"Holding:      {report['holding']}")
        print(f"Kill Switch:  {report['kill_switch']}")
        print(f"{'='*40}")

    elif args.command == "email":
        send_weekly_email()

    elif args.command == "reset":
        if STATE_FILE.exists():
            STATE_FILE.unlink()
        if JOURNAL_FILE.exists():
            JOURNAL_FILE.unlink()
        print("Paper trade state reset.")
