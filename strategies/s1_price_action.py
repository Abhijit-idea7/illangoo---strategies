# =============================================================================
# S1 — Price Action Trend-Following (HH/HL & LH/LL)
# =============================================================================
# Rules (from VanIlango book):
#   Trend classification: last 2 swing highs + last 2 swing lows
#   Long  : Trend = UP   → enter on bar that CLOSES above the last LH (breakout)
#   Short : Trend = DOWN → enter on bar that CLOSES below the last HL (breakdown)
#   Filter: price must be on correct side of 200 EMA
#   SL    : Long → last Higher Low;  Short → last Lower High
#   Target: 2× risk (Risk:Reward 1:2 as conservative minimum)
# =============================================================================

from __future__ import annotations
from typing import List
import pandas as pd

from backtest_engine import Signal
from indicators import ema, find_swing_highs, find_swing_lows, classify_trend

SWING_LOOKBACK  = 5     # bars each side for swing detection
EMA_PERIOD      = 200
MIN_BARS        = 30    # minimum bars before generating signals
RR_RATIO        = 2.0   # risk-reward ratio for target


class S1PriceAction:
    code = "S1"
    name = "Price Action HH/HL Trend-Following"

    def generate_signals(self, df_day: pd.DataFrame) -> List[Signal]:
        signals = []
        close = df_day["Close"]
        high  = df_day["High"]
        low   = df_day["Low"]

        if len(df_day) < MIN_BARS:
            return signals

        ema200 = ema(close, EMA_PERIOD)

        # Pre-compute swing masks for full day
        sh_mask = find_swing_highs(df_day, SWING_LOOKBACK)
        sl_mask = find_swing_lows(df_day, SWING_LOOKBACK)

        # Rolling signal generation: for each bar i, look at history up to i
        signal_fired_today = False

        for i in range(MIN_BARS, len(df_day) - 1):
            if signal_fired_today:
                break   # one signal per day

            sub_sh = df_day.loc[sh_mask & (df_day.index <= i), "High"].values
            sub_sl = df_day.loc[sl_mask & (df_day.index <= i), "Low"].values

            if len(sub_sh) < 2 or len(sub_sl) < 2:
                continue

            trend = classify_trend(list(sub_sh), list(sub_sl))
            cur_close = close.iloc[i]
            cur_ema   = ema200.iloc[i]

            if trend == "UP" and cur_close > cur_ema:
                # Identify last LH for SL (last swing high before trend turned up)
                sl_price  = sub_sl[-1]    # last Higher Low is our stop
                risk      = cur_close - sl_price
                if risk <= 0 or risk > cur_close * 0.03:   # skip if SL > 3%
                    continue
                target = cur_close + RR_RATIO * risk
                signals.append(Signal(
                    bar_index   = i,
                    direction   = "LONG",
                    entry_price = cur_close,
                    sl_price    = round(sl_price * 0.998, 2),   # tiny buffer
                    target_price= round(target, 2),
                    strategy    = self.code,
                ))
                signal_fired_today = True

            elif trend == "DOWN" and cur_close < cur_ema:
                sl_price = sub_sh[-1]   # last Lower High is our stop
                risk     = sl_price - cur_close
                if risk <= 0 or risk > cur_close * 0.03:
                    continue
                target = cur_close - RR_RATIO * risk
                signals.append(Signal(
                    bar_index   = i,
                    direction   = "SHORT",
                    entry_price = cur_close,
                    sl_price    = round(sl_price * 1.002, 2),
                    target_price= round(target, 2),
                    strategy    = self.code,
                ))
                signal_fired_today = True

        return signals
