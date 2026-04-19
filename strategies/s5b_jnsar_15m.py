# =============================================================================
# S5b — JNSAR on 15-Minute Bars  (Pullback-Entry variant)
# =============================================================================
# SAR flip detection is identical to S5 (just at 15min resolution).
# The key difference from the immediate-entry version: instead of entering
# as soon as the 15min flip bar closes, we WAIT for price to retrace
# ~38.2% of that bar's range back toward the SAR level before entering.
#
# Why pullback entry?
#   Entering right after a SAR flip bar means chasing a move that already
#   happened. The bar's entire range is already "spent." A 38% pullback
#   gives a better price, tighter effective risk, and naturally filters
#   out weak SAR flips that immediately reverse (those would pull all the
#   way through and hit SL before we enter).
#
# Entry flow:
#   1. 15min bar closes at time T+15min; SAR has flipped to LONG.
#      flip_close = P, SAR = S, bar_risk = P − S
#   2. pullback_target = P − bar_risk × 0.382   (Fibonacci 38.2%)
#      Hard floor:  pullback_target ≥ S × 1.003  (stay above SL buffer)
#   3. Scan 2m bars from T+15min onward:
#      find first bar where Low ≤ pullback_target  → signal fires there
#   4. Engine enters at the NEXT bar's Open (realistic fill)
#   5. SL = SAR × 0.999;  Target = entry + max(1.5× risk, 1.0% of price)
#   (Mirror logic for SHORT)
#
# Filters:
#   - EMA 21 (on 15min bars) as trend-direction gate
#   - SAR distance cap: risk ≤ 3% of price
#   - Flip bar must close before 14:00 IST so the pullback can form in time
#   - Max 2 valid flips per day
# =============================================================================

from __future__ import annotations
from typing import List, Dict, Optional
import pandas as pd
from datetime import date, time as dtime

from backtest_engine import Signal
from indicators import parabolic_sar, ema

EMA_PERIOD        = 21
RR_RATIO          = 1.5
FIXED_TARGET_PCT  = 0.010   # 1.0% minimum target (slightly wider than immediate entry)
RESAMPLE_FREQ     = "15min"
PULLBACK_RATIO    = 0.382   # Fibonacci: retrace 38.2% of flip-bar range
PULLBACK_FLOOR    = 1.003   # pullback_target must be ≥ SAR × this (LONG)
PULLBACK_CEIL     = 0.997   # pullback_target must be ≤ SAR × this (SHORT)
MAX_FLIP_CLOSE_H  = 14      # skip flips whose bar closes at or after 14:00 IST
MAX_DAILY_SIGNALS = 2


class S5bJNSAR15m:
    code = "S5b"
    name = "JNSAR 15-Min (Pullback Entry)"

    _flip_map: Dict[date, list] = {}

    # ------------------------------------------------------------------
    def precompute(self, df_2m: pd.DataFrame):
        """
        Resamples full 2m data to 15-minute bars, computes Parabolic SAR
        on the full history (proper warmup), then stores qualifying SAR
        flip events keyed by calendar date.
        """
        self._flip_map = {}

        bars = df_2m.resample(RESAMPLE_FREQ).agg(
            Open  = ("Open",  "first"),
            High  = ("High",  "max"),
            Low   = ("Low",   "min"),
            Close = ("Close", "last"),
            Volume= ("Volume","sum"),
        ).dropna(subset=["Open", "High", "Low", "Close"])

        if len(bars) < 15:
            return

        sar_s, trend_s = parabolic_sar(bars)
        ema21          = ema(bars["Close"], EMA_PERIOD)

        for i in range(1, len(bars)):
            prev_trend = trend_s.iloc[i - 1]
            cur_trend  = trend_s.iloc[i]

            if prev_trend == cur_trend:
                continue                          # no flip this bar

            direction  = "LONG" if cur_trend == 1 else "SHORT"
            sar_price  = sar_s.iloc[i]
            cur_close  = bars["Close"].iloc[i]
            cur_ema    = ema21.iloc[i]
            flip_time  = bars.index[i]            # label = bar START time

            # ── EMA directional filter ─────────────────────────────────
            if direction == "LONG"  and cur_close < cur_ema:
                continue
            if direction == "SHORT" and cur_close > cur_ema:
                continue

            # ── SAR distance cap (risk ≤ 3% of price) ─────────────────
            bar_risk = abs(cur_close - sar_price)
            if bar_risk <= 0 or bar_risk > cur_close * 0.03:
                continue

            # ── Time filter: bar must CLOSE before 14:00 IST ──────────
            # Bar labeled T closes at T+15min; skip if T+15min ≥ 14:00
            bar_close_time = (flip_time + pd.Timedelta(RESAMPLE_FREQ)).time()
            if bar_close_time >= dtime(MAX_FLIP_CLOSE_H, 0):
                continue

            day_key = flip_time.date()
            self._flip_map.setdefault(day_key, []).append({
                "flip_time" : flip_time,
                "direction" : direction,
                "sar_price" : sar_price,
                "flip_close": cur_close,
                "bar_risk"  : bar_risk,
            })

    # ------------------------------------------------------------------
    def generate_signals(self, df_day: pd.DataFrame) -> List[Signal]:
        """
        df_day : reset-indexed 2m DataFrame for one trading day.

        For each qualifying SAR flip today, scans 2m bars AFTER the flip
        bar closes and looks for a pullback to the 38.2% retracement level.
        Returns a Signal at the bar where the pullback touches; the engine
        enters at that bar +1 Open.
        """
        signals = []

        if not self._flip_map:
            return signals

        first_ts = df_day["index"].iloc[0]
        day_key  = first_ts.date()

        if day_key not in self._flip_map:
            return signals

        flips = self._flip_map[day_key][:MAX_DAILY_SIGNALS]

        for flip in flips:
            flip_time  = flip["flip_time"]
            direction  = flip["direction"]
            sar_price  = flip["sar_price"]
            flip_close = flip["flip_close"]
            bar_risk   = flip["bar_risk"]

            # ── Only look at bars AFTER the 15min bar closes ──────────
            bar_end     = flip_time + pd.Timedelta(RESAMPLE_FREQ)
            future_bars = df_day[df_day["index"] >= bar_end]
            if future_bars.empty:
                continue

            # ── Pullback target price ──────────────────────────────────
            if direction == "LONG":
                pb_target = round(flip_close - bar_risk * PULLBACK_RATIO, 2)
                # Must stay meaningfully above SAR (not breach the stop zone)
                pb_target = max(pb_target, round(sar_price * PULLBACK_FLOOR, 2))

                # Scan for first 2m bar whose Low touches the pullback level
                entry_bar_idx: Optional[int] = None
                for idx, row in future_bars.iterrows():
                    if row["Low"] <= pb_target:
                        entry_bar_idx = idx
                        break

                if entry_bar_idx is None:
                    continue                       # no pullback today → skip

                sl_price    = round(sar_price * 0.999, 2)
                entry_ref   = pb_target            # approx; engine fills at next open
                actual_risk = entry_ref - sl_price
                if actual_risk <= 0:
                    continue
                target = round(
                    entry_ref + max(RR_RATIO * actual_risk, entry_ref * FIXED_TARGET_PCT), 2
                )

            else:  # SHORT ─────────────────────────────────────────────
                pb_target = round(flip_close + bar_risk * PULLBACK_RATIO, 2)
                pb_target = min(pb_target, round(sar_price * PULLBACK_CEIL, 2))

                entry_bar_idx = None
                for idx, row in future_bars.iterrows():
                    if row["High"] >= pb_target:
                        entry_bar_idx = idx
                        break

                if entry_bar_idx is None:
                    continue

                sl_price    = round(sar_price * 1.001, 2)
                entry_ref   = pb_target
                actual_risk = sl_price - entry_ref
                if actual_risk <= 0:
                    continue
                target = round(
                    entry_ref - max(RR_RATIO * actual_risk, entry_ref * FIXED_TARGET_PCT), 2
                )

            signals.append(Signal(
                bar_index    = entry_bar_idx,
                direction    = direction,
                entry_price  = entry_ref,
                sl_price     = sl_price,
                target_price = target,
                strategy     = self.code,
            ))

        return signals
