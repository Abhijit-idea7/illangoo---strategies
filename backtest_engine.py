# =============================================================================
# backtest_engine.py — Core candle-by-candle backtest engine + metrics
# =============================================================================
# Design:
#   Each strategy exposes a `generate_signals(df_day)` method that returns
#   a list of Signal namedtuples. The engine iterates the day candle-by-candle,
#   enters on signal, manages SL/Target, and force-exits at FORCE_EXIT_TIME.
#
# Trade lifecycle per day (intraday only — NO overnight positions):
#   1. Scan for entry signal on each bar
#   2. If signal: enter at next bar's Open (realistic fill)
#   3. Check each subsequent bar for SL hit, Target hit, or time exit
#   4. Record trade with all metadata
# =============================================================================

from __future__ import annotations

import os
import json
from collections import namedtuple
from dataclasses import dataclass, field
from datetime import datetime, time
from typing import List, Optional

import numpy as np
import pandas as pd
from tabulate import tabulate

from config import (
    CAPITAL,
    RISK_PER_TRADE_PCT,
    MAX_TRADES_PER_DAY,
    FORCE_EXIT_TIME,
    REPORTS_DIR,
)
from indicators import position_size

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

Signal = namedtuple(
    "Signal",
    [
        "bar_index",    # integer index in the day's DataFrame where signal fires
        "direction",    # "LONG" or "SHORT"
        "entry_price",  # suggested entry price (often current Close)
        "sl_price",     # stop-loss level
        "target_price", # profit target (or None to trail)
        "strategy",     # strategy code string e.g. "S1"
    ],
)


@dataclass
class Trade:
    symbol: str
    strategy: str
    direction: str
    entry_time: pd.Timestamp
    entry_price: float
    sl_price: float
    target_price: Optional[float]
    qty: int
    exit_time: Optional[pd.Timestamp] = None
    exit_price: Optional[float] = None
    exit_reason: Optional[str] = None   # "TARGET", "SL", "TIME_EXIT", "EOD"
    pnl: float = 0.0
    pnl_pct: float = 0.0

    @property
    def is_open(self) -> bool:
        return self.exit_time is None

    def close(self, exit_time, exit_price, reason):
        self.exit_time  = exit_time
        self.exit_price = exit_price
        self.exit_reason = reason
        if self.direction == "LONG":
            self.pnl = (exit_price - self.entry_price) * self.qty
        else:
            self.pnl = (self.entry_price - exit_price) * self.qty
        self.pnl_pct = self.pnl / (self.entry_price * self.qty) * 100


# ---------------------------------------------------------------------------
# Core engine
# ---------------------------------------------------------------------------

class BacktestEngine:
    def __init__(self, strategy, symbol: str, df: pd.DataFrame):
        """
        strategy : strategy instance with generate_signals(df_day) method
        symbol   : NSE symbol string
        df       : full OHLCV DataFrame (multi-day, IST index)
        """
        self.strategy = strategy
        self.symbol   = symbol
        self.df       = df
        self.trades: List[Trade] = []

    def run(self) -> List[Trade]:
        """Run backtest day by day. Returns list of completed Trade objects."""
        trading_days = sorted(self.df.index.normalize().unique())

        for day in trading_days:
            df_day = self.df[self.df.index.normalize() == day].copy()
            df_day = df_day.reset_index(drop=False)  # keep timestamp column
            if len(df_day) < 10:
                continue
            self._run_day(df_day, day)

        return self.trades

    def _run_day(self, df_day: pd.DataFrame, day):
        """Simulate a single trading day candle-by-candle."""
        trades_today = 0
        open_trade: Optional[Trade] = None
        force_exit_t = time(*[int(x) for x in FORCE_EXIT_TIME.split(":")])

        # Let the strategy generate all signals for this day up-front
        # (signals fired at bar i are entered at bar i+1 open)
        try:
            signals: List[Signal] = self.strategy.generate_signals(df_day)
        except Exception as e:
            print(f"  [ERROR] {self.strategy.code} on {day}: {e}")
            return

        signal_map = {s.bar_index: s for s in signals}

        for i, row in df_day.iterrows():
            ts    = row["index"]
            open_ = row["Open"]
            high  = row["High"]
            low   = row["Low"]
            close = row["Close"]

            current_time = ts.time() if hasattr(ts, "time") else ts

            # ── Manage open trade ──────────────────────────────────────────
            if open_trade is not None and open_trade.is_open:
                # Force exit at FORCE_EXIT_TIME
                if current_time >= force_exit_t:
                    open_trade.close(ts, close, "TIME_EXIT")
                    self.trades.append(open_trade)
                    open_trade = None
                    continue

                if open_trade.direction == "LONG":
                    # Check SL hit (intra-bar Low)
                    if low <= open_trade.sl_price:
                        exit_p = open_trade.sl_price
                        open_trade.close(ts, exit_p, "SL")
                        self.trades.append(open_trade)
                        open_trade = None
                    # Check Target hit
                    elif open_trade.target_price and high >= open_trade.target_price:
                        exit_p = open_trade.target_price
                        open_trade.close(ts, exit_p, "TARGET")
                        self.trades.append(open_trade)
                        open_trade = None
                else:  # SHORT
                    if high >= open_trade.sl_price:
                        exit_p = open_trade.sl_price
                        open_trade.close(ts, exit_p, "SL")
                        self.trades.append(open_trade)
                        open_trade = None
                    elif open_trade.target_price and low <= open_trade.target_price:
                        exit_p = open_trade.target_price
                        open_trade.close(ts, exit_p, "TARGET")
                        self.trades.append(open_trade)
                        open_trade = None

            # ── Check for new entry signal at bar i ────────────────────────
            # Enter at the NEXT bar's open (i+1), so look ahead by 1
            entry_bar = i - 1   # signals from bar i-1 enter at bar i open
            if (
                open_trade is None
                and trades_today < MAX_TRADES_PER_DAY
                and entry_bar in signal_map
                and current_time < force_exit_t
            ):
                sig = signal_map[entry_bar]
                entry_price = open_  # fill at this bar's open

                # Validate signal still makes sense at entry
                if sig.direction == "LONG" and entry_price < sig.sl_price:
                    pass  # price already below SL — skip
                elif sig.direction == "SHORT" and entry_price > sig.sl_price:
                    pass  # price already above SL — skip
                else:
                    qty = position_size(CAPITAL, RISK_PER_TRADE_PCT, entry_price, sig.sl_price)
                    if qty > 0:
                        open_trade = Trade(
                            symbol       = self.symbol,
                            strategy     = sig.strategy,
                            direction    = sig.direction,
                            entry_time   = ts,
                            entry_price  = entry_price,
                            sl_price     = sig.sl_price,
                            target_price = sig.target_price,
                            qty          = qty,
                        )
                        trades_today += 1

        # End of day — close any still-open trade at last bar's close
        if open_trade is not None and open_trade.is_open:
            last_row = df_day.iloc[-1]
            open_trade.close(last_row["index"], last_row["Close"], "EOD")
            self.trades.append(open_trade)


# ---------------------------------------------------------------------------
# Performance Metrics
# ---------------------------------------------------------------------------

def compute_metrics(trades: List[Trade], capital: float = CAPITAL) -> dict:
    """Compute standard backtest performance metrics from a list of trades."""
    if not trades:
        return {"total_trades": 0}

    pnls  = [t.pnl for t in trades]
    wins  = [p for p in pnls if p > 0]
    losses= [p for p in pnls if p <= 0]

    total_pnl    = sum(pnls)
    win_rate     = len(wins) / len(pnls) * 100 if pnls else 0
    avg_win      = np.mean(wins)  if wins   else 0
    avg_loss     = np.mean(losses) if losses else 0
    profit_factor= (sum(wins) / abs(sum(losses))) if losses else float("inf")

    # Running equity for drawdown
    equity = np.cumsum([0] + pnls) + capital
    peak   = np.maximum.accumulate(equity)
    dd     = (equity - peak) / peak * 100
    max_dd = dd.min()

    # Exit reason breakdown
    reasons = {}
    for t in trades:
        reasons[t.exit_reason] = reasons.get(t.exit_reason, 0) + 1

    # Per-strategy breakdown
    strategies = {}
    for t in trades:
        if t.strategy not in strategies:
            strategies[t.strategy] = {"trades": 0, "pnl": 0, "wins": 0}
        strategies[t.strategy]["trades"] += 1
        strategies[t.strategy]["pnl"]    += t.pnl
        if t.pnl > 0:
            strategies[t.strategy]["wins"] += 1

    return {
        "total_trades"  : len(trades),
        "win_count"     : len(wins),
        "loss_count"    : len(losses),
        "win_rate_pct"  : round(win_rate, 2),
        "total_pnl"     : round(total_pnl, 2),
        "avg_win"       : round(avg_win, 2),
        "avg_loss"      : round(avg_loss, 2),
        "profit_factor" : round(profit_factor, 3),
        "max_drawdown_pct": round(max_dd, 2),
        "return_pct"    : round(total_pnl / capital * 100, 2),
        "exit_reasons"  : reasons,
        "by_strategy"   : strategies,
    }


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def print_summary(symbol: str, metrics: dict, trades: List[Trade]):
    """Pretty-print a strategy summary to console."""
    print(f"\n{'='*60}")
    print(f"  Symbol : {symbol}")
    print(f"  Trades : {metrics.get('total_trades', 0)}")
    print(f"  Win %  : {metrics.get('win_rate_pct', 0):.1f}%")
    print(f"  P&L    : ₹{metrics.get('total_pnl', 0):,.0f}")
    print(f"  Return : {metrics.get('return_pct', 0):.2f}%")
    print(f"  PF     : {metrics.get('profit_factor', 0):.2f}")
    print(f"  MaxDD  : {metrics.get('max_drawdown_pct', 0):.2f}%")
    print(f"  Exits  : {metrics.get('exit_reasons', {})}")
    print(f"{'='*60}")

    if trades:
        rows = [
            [
                t.entry_time.strftime("%d-%b %H:%M"),
                t.direction,
                f"{t.entry_price:.2f}",
                f"{t.exit_price:.2f}" if t.exit_price else "-",
                t.exit_reason,
                f"₹{t.pnl:,.0f}",
            ]
            for t in trades[-10:]   # show last 10
        ]
        print(tabulate(rows, headers=["Entry", "Dir", "Entry₹", "Exit₹", "Reason", "PnL"], tablefmt="rounded_outline"))


def save_report(symbol: str, strategy_code: str, metrics: dict, trades: List[Trade]):
    """Save trade log and metrics to JSON in reports/ directory."""
    os.makedirs(REPORTS_DIR, exist_ok=True)
    report = {
        "symbol"   : symbol,
        "strategy" : strategy_code,
        "metrics"  : metrics,
        "trades"   : [
            {
                "entry_time"  : str(t.entry_time),
                "exit_time"   : str(t.exit_time),
                "direction"   : t.direction,
                "entry_price" : t.entry_price,
                "exit_price"  : t.exit_price,
                "sl_price"    : t.sl_price,
                "target_price": t.target_price,
                "qty"         : t.qty,
                "pnl"         : t.pnl,
                "exit_reason" : t.exit_reason,
            }
            for t in trades
        ],
    }
    fname = os.path.join(REPORTS_DIR, f"{symbol}_{strategy_code}.json")
    with open(fname, "w") as f:
        json.dump(report, f, indent=2)
    print(f"  Report saved → {fname}")
