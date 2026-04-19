# =============================================================================
# S5 — JNSAR (Stop-and-Reverse on Hourly Bars)
# =============================================================================
# Rules (from VanIlango book):
#   1. Work on HOURLY bars (resampled from 2m data via data_fetcher).
#   2. Compute Parabolic SAR on hourly OHLCV.
#   3. LONG  : SAR flips from above price to below price (uptrend SAR).
#   4. SHORT : SAR flips from below price to above price (downtrend SAR).
#   5. SL    : The SAR value itself at entry bar.
#   6. Target: 100–150 points (stocks) or 1.5× risk, whichever comes first.
#   7. Downtrend filter: only take SHORT signals when price below 21-period hourly EMA.
#      Uptrend filter  : only take LONG  signals when price above 21-period hourly EMA.
#
# NOTE: This strategy receives HOURLY data (not 2m). The runner passes hourly
#       data when it detects S5.
# =============================================================================

from __future__ import annotations
from typing import List
import pandas as pd

from backtest_engine import Signal
from indicators import parabolic_sar, ema

EMA_PERIOD = 21
RR_RATIO   = 1.5
MIN_BARS   = 5      # minimum hourly bars before signal
FIXED_TARGET_PCT = 0.015   # 1.5% price move as target cap


class S5JNSAR:
    code = "S5"
    name = "JNSAR Stop-and-Reverse (Hourly)"

    def generate_signals(self, df_day: pd.DataFrame) -> List[Signal]:
        """
        df_day here is the FULL hourly DataFrame (all days), not one day.
        The engine iterates by day, but JNSAR needs multi-day hourly context.
        We still return signals keyed by bar_index within df_day.
        """
        signals = []

        if len(df_day) < MIN_BARS + 2:
            return signals

        sar_series, trend_series = parabolic_sar(df_day)
        ema21 = ema(df_day["Close"], EMA_PERIOD)

        signal_fired = False

        for i in range(1, len(df_day) - 1):
            if signal_fired:
                break

            prev_trend = trend_series.iloc[i - 1]
            cur_trend  = trend_series.iloc[i]
            cur_sar    = sar_series.iloc[i]
            cur_close  = df_day["Close"].iloc[i]
            cur_ema    = ema21.iloc[i]

            # SAR flip to uptrend (was -1, now +1) → LONG
            if prev_trend == -1 and cur_trend == 1 and cur_close > cur_ema:
                sl_price = cur_sar
                risk     = cur_close - sl_price
                if risk <= 0 or risk > cur_close * 0.05:
                    continue
                target = cur_close + max(RR_RATIO * risk, cur_close * FIXED_TARGET_PCT)
                signals.append(Signal(
                    bar_index   = i,
                    direction   = "LONG",
                    entry_price = cur_close,
                    sl_price    = round(sl_price * 0.999, 2),
                    target_price= round(target, 2),
                    strategy    = self.code,
                ))
                signal_fired = True

            # SAR flip to downtrend (was +1, now -1) → SHORT
            elif prev_trend == 1 and cur_trend == -1 and cur_close < cur_ema:
                sl_price = cur_sar
                risk     = sl_price - cur_close
                if risk <= 0 or risk > cur_close * 0.05:
                    continue
                target = cur_close - max(RR_RATIO * risk, cur_close * FIXED_TARGET_PCT)
                signals.append(Signal(
                    bar_index   = i,
                    direction   = "SHORT",
                    entry_price = cur_close,
                    sl_price    = round(sl_price * 1.001, 2),
                    target_price= round(target, 2),
                    strategy    = self.code,
                ))
                signal_fired = True

        return signals
