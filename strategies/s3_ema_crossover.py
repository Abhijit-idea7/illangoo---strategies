# =============================================================================
# S3 — 200 EMA Bias + EMA Crossover
# =============================================================================
# Rules (from VanIlango book):
#   Bias filter : price above 200 EMA → Long signals only
#                 price below 200 EMA → Short signals only
#   Signal      : 8 EMA crosses above 21 EMA → LONG
#                 8 EMA crosses below 21 EMA → SHORT
#   Confirmation: at least 2 consecutive closes on the correct side of 200 EMA
#   SL          : Long  → 1 point below 200 EMA (or last swing low)
#                 Short → 1 point above 200 EMA (or last swing high)
#   Target      : 2× risk (R:R 1:2)
# =============================================================================

from __future__ import annotations
from typing import List
import pandas as pd
import numpy as np

from backtest_engine import Signal
from indicators import ema, find_swing_lows, find_swing_highs

EMA_BIAS   = 200
EMA_FAST   = 8
EMA_SLOW   = 21
MIN_BARS   = 25
RR_RATIO   = 2.0
CONFIRM_BARS = 2   # consecutive closes on correct side of 200 EMA


class S3EMACrossover:
    code = "S3"
    name = "200 EMA Bias + EMA Crossover"

    def generate_signals(self, df_day: pd.DataFrame) -> List[Signal]:
        signals = []
        close = df_day["Close"]

        if len(df_day) < MIN_BARS:
            return signals

        ema200 = ema(close, EMA_BIAS)
        ema8   = ema(close, EMA_FAST)
        ema21  = ema(close, EMA_SLOW)

        sh_mask = find_swing_highs(df_day, lookback=5)
        sl_mask = find_swing_lows(df_day, lookback=5)

        signal_fired_today = False

        for i in range(MIN_BARS, len(df_day) - 1):
            if signal_fired_today:
                break

            # Crossover at bar i: fast crosses slow
            cross_up   = (ema8.iloc[i] > ema21.iloc[i]) and (ema8.iloc[i-1] <= ema21.iloc[i-1])
            cross_down = (ema8.iloc[i] < ema21.iloc[i]) and (ema8.iloc[i-1] >= ema21.iloc[i-1])

            cur_close  = close.iloc[i]
            cur_ema200 = ema200.iloc[i]

            # Confirm consecutive closes above/below 200 EMA
            above_200 = all(close.iloc[i-j] > ema200.iloc[i-j] for j in range(CONFIRM_BARS))
            below_200 = all(close.iloc[i-j] < ema200.iloc[i-j] for j in range(CONFIRM_BARS))

            if cross_up and above_200:
                # SL = max(200 EMA, last swing low)
                sub_sl = df_day.loc[sl_mask & (df_day.index <= i), "Low"].values
                sl_from_swing = sub_sl[-1] if len(sub_sl) > 0 else cur_ema200 * 0.995
                sl_price = min(cur_ema200 - 1, sl_from_swing) * 0.999
                risk     = cur_close - sl_price
                if risk <= 0 or risk > cur_close * 0.03:
                    continue
                target = cur_close + RR_RATIO * risk
                signals.append(Signal(
                    bar_index   = i,
                    direction   = "LONG",
                    entry_price = cur_close,
                    sl_price    = round(sl_price, 2),
                    target_price= round(target, 2),
                    strategy    = self.code,
                ))
                signal_fired_today = True

            elif cross_down and below_200:
                sub_sh = df_day.loc[sh_mask & (df_day.index <= i), "High"].values
                sl_from_swing = sub_sh[-1] if len(sub_sh) > 0 else cur_ema200 * 1.005
                sl_price = max(cur_ema200 + 1, sl_from_swing) * 1.001
                risk     = sl_price - cur_close
                if risk <= 0 or risk > cur_close * 0.03:
                    continue
                target = cur_close - RR_RATIO * risk
                signals.append(Signal(
                    bar_index   = i,
                    direction   = "SHORT",
                    entry_price = cur_close,
                    sl_price    = round(sl_price, 2),
                    target_price= round(target, 2),
                    strategy    = self.code,
                ))
                signal_fired_today = True

        return signals
