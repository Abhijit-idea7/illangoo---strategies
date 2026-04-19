# =============================================================================
# S4 — Channel Breakout / Breakdown
# =============================================================================
# Rules (from VanIlango book):
#   Identify a rolling linear-regression channel over the last CHANNEL_WINDOW bars.
#   Upper band = mid + 1 std of residuals;  Lower band = mid − 1 std
#
#   SHORT : Close breaches below Lower Channel band (supply > demand)
#           → SL above Upper band
#           → Target: Lower band − 1× channel width
#
#   LONG  : Close breaches above Upper Channel band
#           → SL below Lower band
#           → Target: Upper band + 1× channel width
#
#   Additional filter: 200 EMA confirms direction.
#   One signal per day; second breakout in same direction is higher conviction
#   (handled by signal_fired flag reset logic).
# =============================================================================

from __future__ import annotations
from typing import List
import numpy as np
import pandas as pd

from backtest_engine import Signal
from indicators import ema, linear_regression_channel

CHANNEL_WINDOW = 30
EMA_PERIOD     = 200
MIN_BARS       = CHANNEL_WINDOW + 5
RR_RATIO       = 1.5


class S4ChannelBreakout:
    code = "S4"
    name = "Channel Breakout / Breakdown"

    def generate_signals(self, df_day: pd.DataFrame) -> List[Signal]:
        signals = []
        close = df_day["Close"]

        if len(df_day) < MIN_BARS:
            return signals

        ema200 = ema(close, EMA_PERIOD)
        signal_fired_today = False
        inside_channel_prev = True   # track when price was last inside channel

        for i in range(MIN_BARS, len(df_day) - 1):
            if signal_fired_today:
                break

            upper, mid, lower = linear_regression_channel(close.iloc[:i+1], CHANNEL_WINDOW)
            if upper is None:
                continue

            channel_width = upper - lower
            if channel_width <= 0:
                continue

            cur_close = close.iloc[i]
            cur_ema   = ema200.iloc[i]
            prev_close = close.iloc[i-1]

            currently_inside = lower <= cur_close <= upper
            was_inside = lower <= prev_close <= upper

            # Breakdown: was inside, now below lower band, and below 200 EMA
            if was_inside and cur_close < lower and cur_close < cur_ema:
                sl_price = upper + channel_width * 0.1
                risk     = sl_price - cur_close
                if risk <= 0 or risk > cur_close * 0.04:
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

            # Breakout: was inside, now above upper band, and above 200 EMA
            elif was_inside and cur_close > upper and cur_close > cur_ema:
                sl_price = lower - channel_width * 0.1
                risk     = cur_close - sl_price
                if risk <= 0 or risk > cur_close * 0.04:
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

        return signals
