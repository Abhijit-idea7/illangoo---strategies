# =============================================================================
# S5 — JNSAR (Stop-and-Reverse on Hourly Bars)
# =============================================================================
# Design: precompute() runs ONCE before the day loop, computing Parabolic SAR
# on the full 60-day hourly history.  generate_signals() looks up confirmed
# flip events for each trading day and maps them to 2m bar indices.
#
# Entry timing fix (look-ahead):
#   The 1H bar labeled T covers T → T+59min. It is only OBSERVABLE at T+1h.
#   We therefore look for the first 2m bar at or after  flip_time + 1h.
#   The engine then enters at THAT bar + 1 open (realistic fill).
#
# Time-of-day quality filter:
#   Hourly bars that close at or after 13:00 IST leave ≤ 2h 20min for the
#   trade to reach target before the 15:20 force-exit.  Those setups are
#   statistically weaker and are dropped.
#
# Filters:
#   - EMA 21 (hourly) — trend direction gate
#   - SAR distance cap: risk ≤ 5% of price
#   - Flip bar must close before 13:00 IST
#   - Max 1 JNSAR signal per day
# =============================================================================

from __future__ import annotations
from typing import List, Dict
import pandas as pd
from datetime import date, time as dtime

from backtest_engine import Signal
from indicators import parabolic_sar, ema

EMA_PERIOD        = 21
RR_RATIO          = 1.5
FIXED_TARGET_PCT  = 0.015   # 1.5% minimum target
MAX_FLIP_CLOSE_H  = 13      # hourly bar must close before 13:00 IST


class S5JNSAR:
    code = "S5"
    name = "JNSAR Stop-and-Reverse (Hourly)"

    _flip_map: Dict[date, list] = {}

    # ------------------------------------------------------------------
    def precompute(self, df_2m: pd.DataFrame):
        """
        Called once by BacktestEngine before iterating trading days.
        Resamples full 2m data to hourly, computes SAR on full history
        (proper warmup), stores qualifying flip events keyed by date.
        """
        self._flip_map = {}

        hourly = df_2m.resample("1h").agg(
            Open  = ("Open",  "first"),
            High  = ("High",  "max"),
            Low   = ("Low",   "min"),
            Close = ("Close", "last"),
            Volume= ("Volume","sum"),
        ).dropna(subset=["Open", "High", "Low", "Close"])

        if len(hourly) < 10:
            return

        sar_s, trend_s = parabolic_sar(hourly)
        ema21          = ema(hourly["Close"], EMA_PERIOD)

        for i in range(1, len(hourly)):
            prev_trend = trend_s.iloc[i - 1]
            cur_trend  = trend_s.iloc[i]

            if prev_trend == cur_trend:
                continue                          # no flip this bar

            direction  = "LONG" if cur_trend == 1 else "SHORT"
            sar_price  = sar_s.iloc[i]
            cur_close  = hourly["Close"].iloc[i]
            cur_ema    = ema21.iloc[i]
            flip_time  = hourly.index[i]          # label = bar START time

            # ── EMA directional filter ─────────────────────────────────
            if direction == "LONG"  and cur_close < cur_ema:
                continue
            if direction == "SHORT" and cur_close > cur_ema:
                continue

            # ── SAR distance cap ───────────────────────────────────────
            risk = abs(cur_close - sar_price)
            if risk <= 0 or risk > cur_close * 0.05:
                continue

            # ── Time filter: bar must CLOSE before 13:00 IST ──────────
            # Hourly bar labeled T closes at T+1h; skip if T+1h ≥ 13:00
            bar_close_time = (flip_time + pd.Timedelta("1h")).time()
            if bar_close_time >= dtime(MAX_FLIP_CLOSE_H, 0):
                continue

            day_key = flip_time.date()
            self._flip_map.setdefault(day_key, []).append({
                "flip_time" : flip_time,
                "direction" : direction,
                "sar_price" : sar_price,
                "flip_close": cur_close,
            })

    # ------------------------------------------------------------------
    def generate_signals(self, df_day: pd.DataFrame) -> List[Signal]:
        """
        df_day : reset-indexed 2m DataFrame for one trading day.
        Finds the first 2m bar AFTER the hourly flip bar closes and
        returns at most one Signal per day.
        """
        signals = []

        if not self._flip_map:
            return signals

        first_ts = df_day["index"].iloc[0]
        day_key  = first_ts.date()

        if day_key not in self._flip_map:
            return signals

        for flip in self._flip_map[day_key][:1]:    # max 1 per day
            flip_time  = flip["flip_time"]
            direction  = flip["direction"]
            sar_price  = flip["sar_price"]
            flip_close = flip["flip_close"]

            # First 2m bar at or after the hourly bar CLOSES (T + 1h)
            bar_end     = flip_time + pd.Timedelta("1h")
            future_bars = df_day[df_day["index"] >= bar_end]
            if future_bars.empty:
                continue

            bar_idx     = future_bars.index[0]
            entry_price = flip_close              # approx; engine fills at next open

            if direction == "LONG":
                sl_price = round(sar_price * 0.999, 2)
                risk     = entry_price - sl_price
                if risk <= 0:
                    continue
                target = round(
                    entry_price + max(RR_RATIO * risk, entry_price * FIXED_TARGET_PCT), 2
                )
            else:
                sl_price = round(sar_price * 1.001, 2)
                risk     = sl_price - entry_price
                if risk <= 0:
                    continue
                target = round(
                    entry_price - max(RR_RATIO * risk, entry_price * FIXED_TARGET_PCT), 2
                )

            signals.append(Signal(
                bar_index   = bar_idx,
                direction   = direction,
                entry_price = entry_price,
                sl_price    = sl_price,
                target_price= target,
                strategy    = self.code,
            ))

        return signals
