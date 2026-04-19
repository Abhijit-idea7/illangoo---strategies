# =============================================================================
# S2 — Fibonacci Retracement Entry (LRHR — Low Risk High Reward)
# =============================================================================
# Rules (from VanIlango book):
#   1. Identify trend via HH/HL (UP) or LH/LL (DOWN) on the day.
#   2. Identify the most recent swing move (last swing low → swing high for UP;
#      last swing high → swing low for DOWN).
#   3. Calculate Fib retracement levels (38.2, 50, 61.8, 78.6).
#   4. Long  : Price pulls back into 50%–61.8% Fib zone + bullish reversal candle
#              (Close > Open) + price above 200 EMA → entry signal.
#   5. Short : Price bounces into 50%–61.8% Fib zone + bearish reversal candle
#              (Close < Open) + price below 200 EMA → entry signal.
#   SL    : Long  → 78.6% Fib level (one step deeper)
#            Short → 78.6% Fib level above
#   Target: 0.0% Fib (prior swing high/low) = R:R ~2:1 naturally
# =============================================================================

from __future__ import annotations
from typing import List
import pandas as pd

from backtest_engine import Signal
from indicators import (
    ema, find_swing_highs, find_swing_lows, classify_trend,
    fib_retracement, fib_retracement_up,
)

SWING_LOOKBACK = 5
EMA_PERIOD     = 200
MIN_BARS       = 30
FIB_ENTRY_LOW  = 0.50    # enter if price is between 50% and 61.8%
FIB_ENTRY_HIGH = 0.618
FIB_SL         = 0.786


class S2FibRetracement:
    code = "S2"
    name = "Fibonacci Retracement Entry (LRHR)"

    def generate_signals(self, df_day: pd.DataFrame) -> List[Signal]:
        signals = []
        close = df_day["Close"]
        open_ = df_day["Open"]

        if len(df_day) < MIN_BARS:
            return signals

        ema200  = ema(close, EMA_PERIOD)
        sh_mask = find_swing_highs(df_day, SWING_LOOKBACK)
        sl_mask = find_swing_lows(df_day, SWING_LOOKBACK)

        signal_fired_today = False

        for i in range(MIN_BARS, len(df_day) - 1):
            if signal_fired_today:
                break

            sub_sh = df_day.loc[sh_mask & (df_day.index <= i), "High"].values
            sub_sl = df_day.loc[sl_mask & (df_day.index <= i), "Low"].values

            if len(sub_sh) < 2 or len(sub_sl) < 2:
                continue

            trend     = classify_trend(list(sub_sh), list(sub_sl))
            cur_close = close.iloc[i]
            cur_open  = open_.iloc[i]
            cur_ema   = ema200.iloc[i]
            bullish_candle = cur_close > cur_open
            bearish_candle = cur_close < cur_open

            if trend == "UP" and cur_close > cur_ema:
                # Most recent swing move: last swing low → last swing high
                swing_low  = sub_sl[-1]
                swing_high = sub_sh[-1]
                if swing_high <= swing_low:
                    continue
                fibs = fib_retracement(swing_low, swing_high)
                # Entry zone: price pulled back to 50%–61.8%
                entry_zone_hi = fibs[FIB_ENTRY_LOW]
                entry_zone_lo = fibs[FIB_ENTRY_HIGH]
                sl_level      = fibs[FIB_SL]
                target_level  = swing_high    # return to prior high

                if entry_zone_lo <= cur_close <= entry_zone_hi and bullish_candle:
                    risk = cur_close - sl_level
                    if risk > 0 and risk < cur_close * 0.03:
                        signals.append(Signal(
                            bar_index   = i,
                            direction   = "LONG",
                            entry_price = cur_close,
                            sl_price    = round(sl_level * 0.998, 2),
                            target_price= round(target_level, 2),
                            strategy    = self.code,
                        ))
                        signal_fired_today = True

            elif trend == "DOWN" and cur_close < cur_ema:
                # Downtrend: bounce from recent low back toward prior high
                swing_high = sub_sh[-1]
                swing_low  = sub_sl[-1]
                if swing_low >= swing_high:
                    continue
                fibs = fib_retracement_up(swing_high, swing_low)
                entry_zone_lo = fibs[FIB_ENTRY_LOW]
                entry_zone_hi = fibs[FIB_ENTRY_HIGH]
                sl_level      = fibs[FIB_SL]
                target_level  = swing_low     # return to prior low

                if entry_zone_lo <= cur_close <= entry_zone_hi and bearish_candle:
                    risk = sl_level - cur_close
                    if risk > 0 and risk < cur_close * 0.03:
                        signals.append(Signal(
                            bar_index   = i,
                            direction   = "SHORT",
                            entry_price = cur_close,
                            sl_price    = round(sl_level * 1.002, 2),
                            target_price= round(target_level, 2),
                            strategy    = self.code,
                        ))
                        signal_fired_today = True

        return signals
