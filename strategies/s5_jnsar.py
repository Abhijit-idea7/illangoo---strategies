# =============================================================================
# S5 — JNSAR (Stop-and-Reverse on Hourly Bars)
# FIX: Complete redesign. Uses precompute() to compute SAR on the full
#      multi-day 2m dataset (resampled to hourly) ONCE before the day loop.
#      generate_signals() then simply looks up precomputed SAR flip events
#      for the current day and maps them to 2m bar indices for execution.
#
# How it works:
#   precompute(df_full_2m):
#     - Resample 2m → 1H
#     - Compute Parabolic SAR on full hourly history (proper warmup)
#     - Record every SAR trend flip with its timestamp, direction, SAR level
#
#   generate_signals(df_day):
#     - df_day is the reset-indexed 2m DataFrame for one trading day
#     - Look up any SAR flip that falls on this day
#     - Find the first 2m bar at or after the flip hour → entry bar
#     - Return Signal with that bar_index
# =============================================================================

from __future__ import annotations
from typing import List, Dict
import pandas as pd
from datetime import date

from backtest_engine import Signal
from indicators import parabolic_sar, ema

EMA_PERIOD       = 21
RR_RATIO         = 1.5
FIXED_TARGET_PCT = 0.015   # 1.5% minimum target


class S5JNSAR:
    code = "S1J"     # internal code; displayed as S5 in reports
    code = "S5"
    name = "JNSAR Stop-and-Reverse (Hourly)"

    # Populated by precompute() before the day loop starts
    _flip_map: Dict[date, list] = {}

    # ------------------------------------------------------------------
    def precompute(self, df_2m: pd.DataFrame):
        """
        Called once by BacktestEngine before iterating trading days.
        Resamples full 2m data to hourly, computes SAR, stores flip events.
        """
        self._flip_map = {}

        # Resample 2m → 1H, drop incomplete bars
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
                continue          # no flip

            direction  = "LONG" if cur_trend == 1 else "SHORT"
            sar_price  = sar_s.iloc[i]
            cur_close  = hourly["Close"].iloc[i]
            cur_ema    = ema21.iloc[i]
            flip_time  = hourly.index[i]

            # EMA filter: LONG only above 21H EMA, SHORT only below
            if direction == "LONG"  and cur_close < cur_ema:
                continue
            if direction == "SHORT" and cur_close > cur_ema:
                continue

            # Basic risk guard
            risk = abs(cur_close - sar_price)
            if risk <= 0 or risk > cur_close * 0.05:
                continue

            day_key = flip_time.date()
            if day_key not in self._flip_map:
                self._flip_map[day_key] = []

            self._flip_map[day_key].append({
                "flip_time" : flip_time,
                "direction" : direction,
                "sar_price" : sar_price,
                "flip_close": cur_close,
            })

    # ------------------------------------------------------------------
    def generate_signals(self, df_day: pd.DataFrame) -> List[Signal]:
        """
        df_day : reset-indexed 2m DataFrame for one trading day.
                 Must have columns ["index", "Open", "High", "Low", "Close"].
        """
        signals = []

        if not self._flip_map:
            return signals

        # Determine which calendar date this day represents
        first_ts = df_day["index"].iloc[0]
        day_key  = first_ts.date()

        if day_key not in self._flip_map:
            return signals

        flips = self._flip_map[day_key]

        for flip in flips[:1]:    # max 1 JNSAR signal per day
            flip_time = flip["flip_time"]
            direction = flip["direction"]
            sar_price = flip["sar_price"]
            flip_close= flip["flip_close"]

            # Find first 2m bar whose timestamp >= flip hour start
            future_bars = df_day[df_day["index"] >= flip_time]
            if future_bars.empty:
                continue

            bar_idx    = future_bars.index[0]
            entry_price= flip_close

            if direction == "LONG":
                sl_price = round(sar_price * 0.999, 2)
                risk     = entry_price - sl_price
                if risk <= 0:
                    continue
                target = round(entry_price + max(RR_RATIO * risk,
                                                 entry_price * FIXED_TARGET_PCT), 2)
            else:
                sl_price = round(sar_price * 1.001, 2)
                risk     = sl_price - entry_price
                if risk <= 0:
                    continue
                target = round(entry_price - max(RR_RATIO * risk,
                                                 entry_price * FIXED_TARGET_PCT), 2)

            signals.append(Signal(
                bar_index   = bar_idx,
                direction   = direction,
                entry_price = entry_price,
                sl_price    = sl_price,
                target_price= target,
                strategy    = self.code,
            ))

        return signals
