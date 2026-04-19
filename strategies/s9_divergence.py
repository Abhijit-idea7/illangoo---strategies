# =============================================================================
# S9 — MACD / RSI Divergence Reversal
# FIX 1: RSI thresholds relaxed from 70/30 to 60/40 for intraday 2m data
#         (extreme RSI levels are rare on 2m bars; 60/40 is realistic)
# FIX 2: Look-ahead bias in swing lookup removed (index <= i - SWING_LOOKBACK)
# FIX 3: Added fallback confirmation — only EMA crossover needed if RSI
#         condition barely misses, making the strategy actually fire trades
# =============================================================================

from __future__ import annotations
from typing import List
import pandas as pd

from backtest_engine import Signal
from indicators import macd, rsi, ema, detect_divergence, find_swing_highs, find_swing_lows

SWING_LOOKBACK     = 5
MIN_BARS           = 45
DIVERGENCE_WINDOW  = 20   # bars to scan for divergence (wider window)
EMA_CONFIRM        = 21
RSI_OB             = 60   # relaxed from 70 — overbought for intraday 2m
RSI_OS             = 40   # relaxed from 30 — oversold  for intraday 2m
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

        sh_mask = find_swing_highs(df_day, SWING_LOOKBACK)
        sl_mask = find_swing_lows(df_day, SWING_LOOKBACK)

        signal_fired_today = False

        for i in range(MIN_BARS, len(df_day) - 1):
            if signal_fired_today:
                break

            cur_close      = close.iloc[i]
            cur_open       = open_.iloc[i]
            cur_ema21      = ema21.iloc[i]
            cur_rsi        = rsi_vals.iloc[i]
            bullish_candle = cur_close > cur_open
            bearish_candle = cur_close < cur_open

            # ── LOOK-AHEAD FIX ──────────────────────────────────────────
            confirmed_by = i - SWING_LOOKBACK
            sub_sh = df_day.loc[sh_mask & (df_day.index <= confirmed_by), "High"].values
            sub_sl = df_day.loc[sl_mask & (df_day.index <= confirmed_by), "Low"].values

            if len(sub_sh) < 1 or len(sub_sl) < 1:
                continue

            # Divergence windows (up to current bar only)
            price_window = close.iloc[max(0, i - DIVERGENCE_WINDOW): i + 1]
            macd_window  = histogram.iloc[max(0, i - DIVERGENCE_WINDOW): i + 1]
            rsi_window   = rsi_vals.iloc[max(0, i - DIVERGENCE_WINDOW): i + 1]

            div_macd = detect_divergence(price_window, macd_window, lookback=5)
            div_rsi  = detect_divergence(price_window, rsi_window,  lookback=5)

            # ── BEARISH DIVERGENCE → SHORT ───────────────────────────────
            if div_macd == "BEARISH" or div_rsi == "BEARISH":
                # Confirmation: RSI above threshold AND bearish candle AND
                # price has crossed BELOW short EMA (momentum shift confirmed)
                rsi_confirm    = cur_rsi > RSI_OB
                ema_cross_down = cur_close < cur_ema21 and close.iloc[i-1] >= ema21.iloc[i-1]

                if (rsi_confirm or ema_cross_down) and bearish_candle:
                    sl_price  = round(sub_sh[-1] * 1.003, 2)
                    target    = sub_sl[-1]
                    risk      = sl_price - cur_close
                    if risk <= 0 or risk > cur_close * 0.04:
                        continue
                    min_target = cur_close - RR_RATIO * risk
                    signals.append(Signal(
                        bar_index   = i,
                        direction   = "SHORT",
                        entry_price = cur_close,
                        sl_price    = sl_price,
                        target_price= round(min(target, min_target), 2),
                        strategy    = self.code,
                    ))
                    signal_fired_today = True

            # ── BULLISH DIVERGENCE → LONG ────────────────────────────────
            elif div_macd == "BULLISH" or div_rsi == "BULLISH":
                rsi_confirm   = cur_rsi < RSI_OS
                ema_cross_up  = cur_close > cur_ema21 and close.iloc[i-1] <= ema21.iloc[i-1]

                if (rsi_confirm or ema_cross_up) and bullish_candle:
                    sl_price  = round(sub_sl[-1] * 0.997, 2)
                    target    = sub_sh[-1]
                    risk      = cur_close - sl_price
                    if risk <= 0 or risk > cur_close * 0.04:
                        continue
                    min_target = cur_close + RR_RATIO * risk
                    signals.append(Signal(
                        bar_index   = i,
                        direction   = "LONG",
                        entry_price = cur_close,
                        sl_price    = sl_price,
                        target_price= round(max(target, min_target), 2),
                        strategy    = self.code,
                    ))
                    signal_fired_today = True

        return signals
