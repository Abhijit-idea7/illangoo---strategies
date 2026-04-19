# =============================================================================
# S1 — Price Action Trend-Following (HH/HL & LH/LL)
# FIX: Look-ahead bias removed — swings only used after SWING_LOOKBACK
#      confirmation bars have passed (i.e. index <= i - SWING_LOOKBACK)
# =============================================================================

from __future__ import annotations
from typing import List
import pandas as pd

from backtest_engine import Signal
from indicators import ema, find_swing_highs, find_swing_lows, classify_trend

SWING_LOOKBACK  = 5
EMA_PERIOD      = 200
MIN_BARS        = 35    # enough bars for EMA + swing confirmation
RR_RATIO        = 2.0


class S1PriceAction:
    code = "S1"
    name = "Price Action HH/HL Trend-Following"

    def generate_signals(self, df_day: pd.DataFrame) -> List[Signal]:
        signals = []
        close = df_day["Close"]

        if len(df_day) < MIN_BARS:
            return signals

        ema200  = ema(close, EMA_PERIOD)
        sh_mask = find_swing_highs(df_day, SWING_LOOKBACK)
        sl_mask = find_swing_lows(df_day, SWING_LOOKBACK)

        signal_fired_today = False

        for i in range(MIN_BARS, len(df_day) - 1):
            if signal_fired_today:
                break

            # ── LOOK-AHEAD FIX ──────────────────────────────────────────────
            # Only use swings at index <= i - SWING_LOOKBACK so all their
            # confirmation bars (up to swing_idx + SWING_LOOKBACK) are in the past
            confirmed_by = i - SWING_LOOKBACK
            sub_sh = df_day.loc[sh_mask & (df_day.index <= confirmed_by), "High"].values
            sub_sl = df_day.loc[sl_mask & (df_day.index <= confirmed_by), "Low"].values

            if len(sub_sh) < 2 or len(sub_sl) < 2:
                continue

            trend     = classify_trend(list(sub_sh), list(sub_sl))
            cur_close = close.iloc[i]
            cur_ema   = ema200.iloc[i]

            if trend == "UP" and cur_close > cur_ema:
                sl_price = sub_sl[-1]
                risk     = cur_close - sl_price
                if risk <= 0 or risk > cur_close * 0.03:
                    continue
                target = cur_close + RR_RATIO * risk
                signals.append(Signal(
                    bar_index   = i,
                    direction   = "LONG",
                    entry_price = cur_close,
                    sl_price    = round(sl_price * 0.998, 2),
                    target_price= round(target, 2),
                    strategy    = self.code,
                ))
                signal_fired_today = True

            elif trend == "DOWN" and cur_close < cur_ema:
                sl_price = sub_sh[-1]
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
