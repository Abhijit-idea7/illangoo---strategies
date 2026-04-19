# =============================================================================
# S5b — JNSAR on 15-Minute Bars (comparison variant vs S5 Hourly)
# =============================================================================
# Identical logic to S5 — only the resample frequency changes: "1h" → "15min"
#
# Purpose: compare signal frequency and quality vs the hourly SAR.
#   S5  → 1H  bars → 6–13 signals per stock per 60d → very clean, low whipsaw
#   S5b → 15m bars → ~25–40 signals per stock per 60d → more frequent, more noise
#
# Same filters apply:
#   - EMA 21 (on 15min bars) as directional filter
#   - Parabolic SAR flip = entry signal
#   - LONG only above 21-period 15min EMA; SHORT only below
#   - SL at SAR value; Target = max(1.5× risk, 0.8% of price)
# =============================================================================

from __future__ import annotations
from typing import List, Dict
import pandas as pd
from datetime import date

from backtest_engine import Signal
from indicators import parabolic_sar, ema

EMA_PERIOD       = 21
RR_RATIO         = 1.5
FIXED_TARGET_PCT = 0.008   # 0.8% — tighter than hourly (smaller moves expected)
RESAMPLE_FREQ    = "15min"


class S5bJNSAR15m:
    code = "S5b"
    name = "JNSAR Stop-and-Reverse (15-Min)"

    _flip_map: Dict[date, list] = {}

    # ------------------------------------------------------------------
    def precompute(self, df_2m: pd.DataFrame):
        """
        Resamples full 2m data to 15-minute bars, computes Parabolic SAR
        on the entire history (proper warmup), stores SAR flip events by date.
        """
        self._flip_map = {}

        hourly = df_2m.resample(RESAMPLE_FREQ).agg(
            Open  = ("Open",  "first"),
            High  = ("High",  "max"),
            Low   = ("Low",   "min"),
            Close = ("Close", "last"),
            Volume= ("Volume","sum"),
        ).dropna(subset=["Open", "High", "Low", "Close"])

        if len(hourly) < 15:
            return

        sar_s, trend_s = parabolic_sar(hourly)
        ema21          = ema(hourly["Close"], EMA_PERIOD)

        for i in range(1, len(hourly)):
            prev_trend = trend_s.iloc[i - 1]
            cur_trend  = trend_s.iloc[i]

            if prev_trend == cur_trend:
                continue

            direction  = "LONG" if cur_trend == 1 else "SHORT"
            sar_price  = sar_s.iloc[i]
            cur_close  = hourly["Close"].iloc[i]
            cur_ema    = ema21.iloc[i]
            flip_time  = hourly.index[i]

            # EMA directional filter
            if direction == "LONG"  and cur_close < cur_ema:
                continue
            if direction == "SHORT" and cur_close > cur_ema:
                continue

            # Risk guard — skip extreme SAR distances
            risk = abs(cur_close - sar_price)
            if risk <= 0 or risk > cur_close * 0.03:   # tighter cap vs hourly
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
        Returns up to MAX_TRADES_PER_DAY signals mapped to 2m bar indices.
        """
        signals = []

        if not self._flip_map:
            return signals

        first_ts = df_day["index"].iloc[0]
        day_key  = first_ts.date()

        if day_key not in self._flip_map:
            return signals

        # 15min may generate multiple flips per day — cap at 2 (per config)
        flips = self._flip_map[day_key][:2]

        for flip in flips:
            flip_time  = flip["flip_time"]
            direction  = flip["direction"]
            sar_price  = flip["sar_price"]
            flip_close = flip["flip_close"]

            # Find first 2m bar at or after the 15min flip bar
            future_bars = df_day[df_day["index"] >= flip_time]
            if future_bars.empty:
                continue

            bar_idx     = future_bars.index[0]
            entry_price = flip_close

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
