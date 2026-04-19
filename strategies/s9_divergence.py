# =============================================================================
# S9 — MACD / RSI Divergence Reversal
# =============================================================================
# Rules (from VanIlango book):
#   Bearish Divergence (SHORT):
#     Price makes new HH but MACD histogram / RSI makes a Lower High.
#     Wait for confirmation: bearish candle + price closes below short EMA.
#     SL    : Above the divergence HH
#     Target: Previous swing low (1.5× risk minimum)
#
#   Bullish Divergence (LONG):
#     Price makes new LL but MACD histogram / RSI makes a Higher Low.
#     Confirmation: bullish candle + price closes above short EMA.
#     SL    : Below the divergence LL
#     Target: Previous swing high (1.5× risk minimum)
#
#   Filter: RSI must be in overbought (>70) for Bearish, oversold (<30) for Bullish.
#   Lookback window for divergence: DIVERGENCE_WINDOW bars.
# =============================================================================

from __future__ import annotations
from typing import List
import pandas as pd
import numpy as np

from backtest_engine import Signal
from indicators import macd, rsi, ema, detect_divergence, find_swing_highs, find_swing_lows

MIN_BARS           = 40
DIVERGENCE_WINDOW  = 15   # bars to scan for divergence
EMA_CONFIRM        = 21   # short EMA for confirmation
RSI_OB             = 70
RSI_OS             = 30
RR_RATIO           = 1.5


class S9Divergence:
    code = "S9"
    name = "MACD / RSI Divergence Reversal"

    def generate_signals(self, df_day: pd.DataFrame) -> List[Signal]:
        signals = []
        close = df_day["Close"]
        open_ = df_day["Open"]

        if len(df_day) < MIN_BARS:
            return signals

        macd_line, signal_line, histogram = macd(close)
        rsi_vals = rsi(close, period=14)
        ema21    = ema(close, EMA_CONFIRM)

        sh_mask = find_swing_highs(df_day, lookback=5)
        sl_mask = find_swing_lows(df_day, lookback=5)

        signal_fired_today = False

        for i in range(MIN_BARS, len(df_day) - 1):
            if signal_fired_today:
                break

            cur_close  = close.iloc[i]
            cur_open   = open_.iloc[i]
            cur_ema21  = ema21.iloc[i]
            cur_rsi    = rsi_vals.iloc[i]

            bullish_candle = cur_close > cur_open
            bearish_candle = cur_close < cur_open

            # Divergence on MACD histogram over window
            price_window = close.iloc[max(0, i-DIVERGENCE_WINDOW): i+1]
            macd_window  = histogram.iloc[max(0, i-DIVERGENCE_WINDOW): i+1]
            rsi_window   = rsi_vals.iloc[max(0, i-DIVERGENCE_WINDOW): i+1]

            div_macd = detect_divergence(price_window, macd_window, lookback=5)
            div_rsi  = detect_divergence(price_window, rsi_window,  lookback=5)

            # Use the stronger signal (both MACD and RSI agree = HCT)
            if div_macd == "BEARISH" or div_rsi == "BEARISH":
                # Confirm: RSI overbought AND bearish candle AND close below ema21
                if cur_rsi > RSI_OB and bearish_candle and cur_close < cur_ema21:
                    sub_sh = df_day.loc[sh_mask & (df_day.index <= i), "High"].values
                    sub_sl = df_day.loc[sl_mask & (df_day.index <= i), "Low"].values
                    if len(sub_sh) < 1 or len(sub_sl) < 1:
                        continue
                    sl_price  = sub_sh[-1] * 1.003   # SL above recent HH
                    target    = sub_sl[-1]            # prior swing low
                    risk      = sl_price - cur_close
                    if risk <= 0 or risk > cur_close * 0.04:
                        continue
                    min_target = cur_close - RR_RATIO * risk
                    signals.append(Signal(
                        bar_index   = i,
                        direction   = "SHORT",
                        entry_price = cur_close,
                        sl_price    = round(sl_price, 2),
                        target_price= round(min(target, min_target), 2),
                        strategy    = self.code,
                    ))
                    signal_fired_today = True

            elif div_macd == "BULLISH" or div_rsi == "BULLISH":
                if cur_rsi < RSI_OS and bullish_candle and cur_close > cur_ema21:
                    sub_sh = df_day.loc[sh_mask & (df_day.index <= i), "High"].values
                    sub_sl = df_day.loc[sl_mask & (df_day.index <= i), "Low"].values
                    if len(sub_sh) < 1 or len(sub_sl) < 1:
                        continue
                    sl_price  = sub_sl[-1] * 0.997   # SL below recent LL
                    target    = sub_sh[-1]            # prior swing high
                    risk      = cur_close - sl_price
                    if risk <= 0 or risk > cur_close * 0.04:
                        continue
                    min_target = cur_close + RR_RATIO * risk
                    signals.append(Signal(
                        bar_index   = i,
                        direction   = "LONG",
                        entry_price = cur_close,
                        sl_price    = round(sl_price, 2),
                        target_price= round(max(target, min_target), 2),
                        strategy    = self.code,
                    ))
                    signal_fired_today = True

        return signals
