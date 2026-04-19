# =============================================================================
# S6 — Retracement Re-Entry (Fading bounces / pullbacks in trend direction)
# FIX: Look-ahead bias removed — swings only used after SWING_LOOKBACK
#      confirmation bars have passed (i.e. index <= i - SWING_LOOKBACK)
# =============================================================================

from __future__ import annotations
from typing import List
import pandas as pd

from backtest_engine import Signal
from indicators import (
    ema, find_swing_highs, find_swing_lows, classify_trend,
    fib_retracement, fib_retracement_up,
)

SWING_LOOKBACK  = 5
EMA_PERIOD      = 200
MIN_BARS        = 35
FIB_ZONE_LOW    = 0.50
FIB_ZONE_HIGH   = 0.618
FIB_SL          = 0.786
MAX_SIGNALS     = 2


class S6RetracementReentry:
    code = "S6"
    name = "Retracement Re-Entry (Trend-Direction Fade)"

    def generate_signals(self, df_day: pd.DataFrame) -> List[Signal]:
        signals = []
        close = df_day["Close"]
        open_ = df_day["Open"]

        if len(df_day) < MIN_BARS:
            return signals

        ema200  = ema(close, EMA_PERIOD)
        sh_mask = find_swing_highs(df_day, SWING_LOOKBACK)
        sl_mask = find_swing_lows(df_day, SWING_LOOKBACK)

        signals_fired = 0

        for i in range(MIN_BARS, len(df_day) - 1):
            if signals_fired >= MAX_SIGNALS:
                break

            # ── LOOK-AHEAD FIX ──────────────────────────────────────────────
            confirmed_by = i - SWING_LOOKBACK
            sub_sh = df_day.loc[sh_mask & (df_day.index <= confirmed_by), "High"].values
            sub_sl = df_day.loc[sl_mask & (df_day.index <= confirmed_by), "Low"].values

            if len(sub_sh) < 2 or len(sub_sl) < 2:
                continue

            trend          = classify_trend(list(sub_sh), list(sub_sl))
            cur_close      = close.iloc[i]
            cur_open       = open_.iloc[i]
            cur_ema        = ema200.iloc[i]
            bullish_candle = cur_close > cur_open
            bearish_candle = cur_close < cur_open

            # ── DOWNTREND: Short re-entry on bounce ──────────────────────
            if trend == "DOWN" and cur_close < cur_ema:
                sh = sub_sh[-1]
                sl = sub_sl[-1]
                if sh <= sl:
                    continue
                fibs    = fib_retracement_up(sh, sl)
                zone_lo = fibs[FIB_ZONE_LOW]
                zone_hi = fibs[FIB_ZONE_HIGH]
                sl_fib  = fibs[FIB_SL]
                target  = sl

                if zone_lo <= cur_close <= zone_hi and bearish_candle:
                    risk = sl_fib - cur_close
                    if risk > 0 and risk < cur_close * 0.03:
                        signals.append(Signal(
                            bar_index   = i,
                            direction   = "SHORT",
                            entry_price = cur_close,
                            sl_price    = round(sl_fib * 1.002, 2),
                            target_price= round(target * 0.998, 2),
                            strategy    = self.code,
                        ))
                        signals_fired += 1

            # ── UPTREND: Long re-entry on dip ─────────────────────────────
            elif trend == "UP" and cur_close > cur_ema:
                sh = sub_sh[-1]
                sl = sub_sl[-1]
                if sh <= sl:
                    continue
                fibs    = fib_retracement(sl, sh)
                zone_hi = fibs[FIB_ZONE_LOW]
                zone_lo = fibs[FIB_ZONE_HIGH]
                sl_fib  = fibs[FIB_SL]
                target  = sh

                if zone_lo <= cur_close <= zone_hi and bullish_candle:
                    risk = cur_close - sl_fib
                    if risk > 0 and risk < cur_close * 0.03:
                        signals.append(Signal(
                            bar_index   = i,
                            direction   = "LONG",
                            entry_price = cur_close,
                            sl_price    = round(sl_fib * 0.998, 2),
                            target_price= round(target * 1.002, 2),
                            strategy    = self.code,
                        ))
                        signals_fired += 1

        return signals
