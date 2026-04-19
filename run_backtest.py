#!/usr/bin/env python3
# =============================================================================
# run_backtest.py — Main CLI runner for Ilango Backtest Suite
# Strategies: S1, S2, S3, S5 (1H SAR), S5b (15min SAR), S6, S9
# =============================================================================
# Usage:
#   python run_backtest.py                            # all strategies, all symbols
#   python run_backtest.py --strategy S5 S5b          # compare SAR timeframes
#   python run_backtest.py --symbols HDFCBANK TCS LT AXISBANK ICICIBANK
#   python run_backtest.py --strategy S5 S5b --symbols HDFCBANK TCS LT AXISBANK ICICIBANK
# =============================================================================

import argparse
import sys
import time
from collections import defaultdict

from colorama import Fore, Style, init as colorama_init

from config import SYMBOLS, CAPITAL, REPORTS_DIR
from data_fetcher import fetch_ohlcv
from backtest_engine import BacktestEngine, compute_metrics, print_summary, save_report
from strategies import ALL_STRATEGIES

colorama_init(autoreset=True)

# Stocks selected for S5 live trading
SELECTED_5 = ["HDFCBANK", "TCS", "LT", "AXISBANK", "ICICIBANK"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def banner():
    print(f"\n{Fore.CYAN}{'='*65}")
    print(f"  Ilango / JustNifty — Intraday Strategy Backtest Suite v3")
    print(f"  Capital : ₹{CAPITAL:,.0f}  |  Data: yFinance 2m (last 60d)")
    print(f"  SAR variants: S5 = 1-Hour | S5b = 15-Minute")
    print(f"{'='*65}{Style.RESET_ALL}\n")


def run_strategy_on_symbol(strategy_cls, symbol: str, verbose: bool = True) -> dict:
    """Download 2m data, run backtest, compute metrics, save report."""
    strat = strategy_cls()

    print(
        f"  {Fore.YELLOW}[{strat.code}] {symbol}{Style.RESET_ALL}"
        f" — fetching 2m data …",
        end=" ", flush=True,
    )

    try:
        df = fetch_ohlcv(symbol)
    except Exception as e:
        print(f"{Fore.RED}FAILED ({e}){Style.RESET_ALL}")
        return {}

    if df.empty or len(df) < 20:
        print(f"{Fore.RED}Insufficient data{Style.RESET_ALL}")
        return {}

    print(f"{Fore.GREEN}{len(df)} bars{Style.RESET_ALL}")

    engine  = BacktestEngine(strat, symbol, df)
    trades  = engine.run()
    metrics = compute_metrics(trades, CAPITAL)

    if verbose:
        print_summary(symbol, metrics, trades)

    save_report(symbol, strat.code, metrics, trades)
    return metrics


def print_combined_table(all_results: dict):
    """Print cross-symbol, cross-strategy summary sorted by Return%."""
    from tabulate import tabulate

    rows = []
    for (sym, code), m in all_results.items():
        if not m or m.get("total_trades", 0) == 0:
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

    rows.sort(key=lambda r: float(r[5].rstrip("%")), reverse=True)

    print(f"\n{Fore.CYAN}{'='*65}")
    print("  COMBINED RESULTS (excluding zero-trade rows)")
    print(f"{'='*65}{Style.RESET_ALL}")
    print(tabulate(
        rows,
        headers=["Symbol", "Strat", "Trades", "Win%", "P&L", "Return%", "PF", "MaxDD%"],
        tablefmt="rounded_outline",
    ))

    # ── Strategy aggregate ───────────────────────────────────────────────
    by_strat = defaultdict(lambda: {"trades": 0, "pnl": 0.0, "wins": 0})
    for (sym, code), m in all_results.items():
        if m:
            by_strat[code]["trades"] += m.get("total_trades", 0)
            by_strat[code]["pnl"]    += m.get("total_pnl", 0)
            by_strat[code]["wins"]   += m.get("win_count", 0)

    strat_rows = []
    for code in sorted(by_strat):
        agg = by_strat[code]
        t   = agg["trades"]
        wr  = (agg["wins"] / t * 100) if t > 0 else 0
        strat_rows.append([
            code,
            ALL_STRATEGIES[code].name,
            t,
            f"{wr:.1f}%",
            f"₹{agg['pnl']:,.0f}",
        ])

    print(f"\n{Fore.CYAN}Strategy Aggregate:{Style.RESET_ALL}")
    print(tabulate(
        strat_rows,
        headers=["Code", "Strategy", "Trades", "Win%", "Total P&L"],
        tablefmt="rounded_outline",
    ))

    # ── S5 vs S5b head-to-head (if both present) ────────────────────────
    s5_codes = [c for c in by_strat if c in ("S5", "S5b")]
    if len(s5_codes) == 2:
        print(f"\n{Fore.CYAN}S5 (1-Hour) vs S5b (15-Min) — Head-to-Head:{Style.RESET_ALL}")
        h2h = []
        for code in ["S5", "S5b"]:
            agg = by_strat[code]
            t   = agg["trades"]
            wr  = (agg["wins"] / t * 100) if t > 0 else 0
            pct = agg["pnl"] / CAPITAL * 100
            h2h.append([
                code,
                ALL_STRATEGIES[code].name,
                t,
                f"{wr:.1f}%",
                f"₹{agg['pnl']:,.0f}",
                f"{pct:.2f}%",
                f"~{t // max(len([k for k in all_results if k[1]==code]), 1)} per stock",
            ])
        print(tabulate(
            h2h,
            headers=["Code", "Strategy", "Trades", "Win%", "Total P&L", "Return%", "Avg/Stock"],
            tablefmt="rounded_outline",
        ))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Ilango Intraday Backtest Suite")
    parser.add_argument(
        "--strategy", "-s", nargs="+", default=None,
        help=f"Strategy codes: {list(ALL_STRATEGIES.keys())}. Default: all.",
    )
    parser.add_argument(
        "--symbols", "-sym", nargs="+", default=None,
        help="NSE symbols (no .NS suffix). Default: from config.py.",
    )
    parser.add_argument(
        "--selected", action="store_true",
        help=f"Run on selected 5 stocks only: {SELECTED_5}",
    )
    parser.add_argument("--quiet", "-q", action="store_true",
                        help="Suppress per-trade output.")
    args = parser.parse_args()

    banner()

    # Strategies
    if args.strategy:
        codes = [c.upper() for c in args.strategy]
        # handle S5B → S5b
        codes = [c if c != "S5B" else "S5b" for c in codes]
        invalid = [c for c in codes if c not in ALL_STRATEGIES]
        if invalid:
            print(f"{Fore.RED}Unknown codes: {invalid}. Valid: {list(ALL_STRATEGIES.keys())}{Style.RESET_ALL}")
            sys.exit(1)
        strategies_to_run = {c: ALL_STRATEGIES[c] for c in codes}
    else:
        strategies_to_run = ALL_STRATEGIES

    # Symbols
    if args.selected:
        symbols = SELECTED_5
    elif args.symbols:
        symbols = args.symbols
    else:
        symbols = SYMBOLS

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
    print_combined_table(all_results)


if __name__ == "__main__":
    main()
