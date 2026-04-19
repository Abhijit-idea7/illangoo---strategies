#!/usr/bin/env python3
# =============================================================================
# run_backtest.py — Main CLI runner for Ilango Backtest Suite
# =============================================================================
# Usage:
#   python run_backtest.py                          # all strategies, all symbols
#   python run_backtest.py --strategy S3            # single strategy
#   python run_backtest.py --symbols RELIANCE TCS   # specific symbols
#   python run_backtest.py --strategy S3 --symbols INFY WIPRO
#   python run_backtest.py --summary                # print combined summary table
# =============================================================================

import argparse
import sys
import time
from collections import defaultdict

import pandas as pd
from colorama import Fore, Style, init as colorama_init

from config import SYMBOLS, RUN_STRATEGIES, CAPITAL, REPORTS_DIR
from data_fetcher import fetch_ohlcv, fetch_hourly
from backtest_engine import BacktestEngine, compute_metrics, print_summary, save_report
from strategies import ALL_STRATEGIES

colorama_init(autoreset=True)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def banner():
    print(f"\n{Fore.CYAN}{'='*65}")
    print(f"  Ilango / JustNifty — Intraday Strategy Backtest Suite")
    print(f"  Capital: ₹{CAPITAL:,.0f}  |  Data: yFinance 2m (last 60d)")
    print(f"{'='*65}{Style.RESET_ALL}\n")


def run_strategy_on_symbol(strategy_cls, symbol: str, verbose: bool = True) -> dict:
    """Download data, run backtest, compute metrics, save report."""
    strat = strategy_cls()
    is_hourly = strategy_cls.code == "S5"

    print(f"  {Fore.YELLOW}[{strat.code}] {symbol}{Style.RESET_ALL} — fetching {'hourly' if is_hourly else '2m'} data …", end=" ", flush=True)

    try:
        if is_hourly:
            df = fetch_hourly(symbol)
        else:
            df = fetch_ohlcv(symbol)
    except Exception as e:
        print(f"{Fore.RED}FAILED ({e}){Style.RESET_ALL}")
        return {}

    if df.empty or len(df) < 20:
        print(f"{Fore.RED}Insufficient data{Style.RESET_ALL}")
        return {}

    print(f"{Fore.GREEN}{len(df)} bars{Style.RESET_ALL}")

    engine = BacktestEngine(strat, symbol, df)
    trades = engine.run()
    metrics = compute_metrics(trades, CAPITAL)

    if verbose:
        print_summary(symbol, metrics, trades)

    save_report(symbol, strat.code, metrics, trades)
    return metrics


def print_combined_table(all_results: dict):
    """Print a cross-symbol, cross-strategy summary table."""
    from tabulate import tabulate

    rows = []
    for (sym, code), m in all_results.items():
        if not m:
            continue
        rows.append([
            sym, code,
            m.get("total_trades", 0),
            f"{m.get('win_rate_pct', 0):.1f}%",
            f"₹{m.get('total_pnl', 0):,.0f}",
            f"{m.get('return_pct', 0):.2f}%",
            f"{m.get('profit_factor', 0):.2f}",
            f"{m.get('max_drawdown_pct', 0):.2f}%",
        ])

    # Sort by return descending
    rows.sort(key=lambda r: float(r[5].rstrip("%")), reverse=True)

    print(f"\n{Fore.CYAN}{'='*65}")
    print("  COMBINED RESULTS SUMMARY")
    print(f"{'='*65}{Style.RESET_ALL}")
    print(tabulate(
        rows,
        headers=["Symbol", "Strategy", "Trades", "Win%", "P&L", "Return%", "PF", "MaxDD%"],
        tablefmt="rounded_outline",
    ))

    # Aggregate by strategy
    by_strat = defaultdict(lambda: {"trades": 0, "pnl": 0.0, "wins": 0})
    for (sym, code), m in all_results.items():
        if m:
            by_strat[code]["trades"] += m.get("total_trades", 0)
            by_strat[code]["pnl"]    += m.get("total_pnl", 0)
            wins = m.get("win_count", 0)
            by_strat[code]["wins"]   += wins

    strat_rows = []
    for code, agg in sorted(by_strat.items()):
        t = agg["trades"]
        wr = (agg["wins"] / t * 100) if t > 0 else 0
        strat_rows.append([code, ALL_STRATEGIES[code].name, t, f"{wr:.1f}%", f"₹{agg['pnl']:,.0f}"])

    print(f"\n{Fore.CYAN}Strategy Aggregate:{Style.RESET_ALL}")
    print(tabulate(strat_rows, headers=["Code", "Strategy", "Trades", "Win%", "Total P&L"], tablefmt="rounded_outline"))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Ilango Intraday Backtest Suite")
    parser.add_argument("--strategy", "-s", nargs="+", default=None,
                        help="Strategy code(s): S1 S2 S3 S4 S5 S6 S9. Default: all.")
    parser.add_argument("--symbols", "-sym", nargs="+", default=None,
                        help="NSE symbols (no .NS suffix). Default: from config.py.")
    parser.add_argument("--summary", action="store_true",
                        help="Print combined cross-strategy summary table at the end.")
    parser.add_argument("--quiet", "-q", action="store_true",
                        help="Suppress per-trade output.")
    args = parser.parse_args()

    banner()

    # Determine which strategies to run
    if args.strategy:
        codes = [c.upper() for c in args.strategy]
        invalid = [c for c in codes if c not in ALL_STRATEGIES]
        if invalid:
            print(f"{Fore.RED}Unknown strategy codes: {invalid}. Choose from {list(ALL_STRATEGIES.keys())}{Style.RESET_ALL}")
            sys.exit(1)
        strategies_to_run = {c: ALL_STRATEGIES[c] for c in codes}
    elif RUN_STRATEGIES == "ALL":
        strategies_to_run = ALL_STRATEGIES
    else:
        strategies_to_run = {c: ALL_STRATEGIES[c] for c in RUN_STRATEGIES if c in ALL_STRATEGIES}

    # Determine which symbols to run
    symbols = args.symbols if args.symbols else SYMBOLS

    print(f"  Strategies : {list(strategies_to_run.keys())}")
    print(f"  Symbols    : {symbols}")
    print(f"  Reports    : {REPORTS_DIR}/\n")

    all_results = {}
    t0 = time.time()

    for sym in symbols:
        print(f"\n{Fore.CYAN}── {sym} {'─'*50}{Style.RESET_ALL}")
        for code, strat_cls in strategies_to_run.items():
            try:
                metrics = run_strategy_on_symbol(strat_cls, sym, verbose=not args.quiet)
                all_results[(sym, code)] = metrics
            except Exception as e:
                print(f"  {Fore.RED}[ERROR] {sym}/{code}: {e}{Style.RESET_ALL}")
                all_results[(sym, code)] = {}

    elapsed = time.time() - t0
    print(f"\n{Fore.GREEN}Backtest complete in {elapsed:.1f}s{Style.RESET_ALL}")

    if args.summary or True:   # always show summary
        print_combined_table(all_results)


if __name__ == "__main__":
    main()
