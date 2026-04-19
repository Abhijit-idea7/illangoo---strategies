# =============================================================================
# indicators.py — All technical indicator computations
# Used by every strategy. Pure functions; no side-effects.
# =============================================================================

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Moving Averages
# ---------------------------------------------------------------------------

def ema(series: pd.Series, period: int) -> pd.Series:
    """Exponential Moving Average."""
    return series.ewm(span=period, adjust=False).mean()


def sma(series: pd.Series, period: int) -> pd.Series:
    """Simple Moving Average."""
    return series.rolling(window=period).mean()


# ---------------------------------------------------------------------------
# Swing High / Low Detection
# ---------------------------------------------------------------------------

def find_swing_highs(df: pd.DataFrame, lookback: int = 5) -> pd.Series:
    """
    Returns a boolean Series; True where a swing high exists.
    A swing high: High[i] is the highest among the surrounding `lookback` bars on each side.
    """
    highs = df["High"]
    is_swing = pd.Series(False, index=df.index)
    for i in range(lookback, len(df) - lookback):
        window = highs.iloc[i - lookback: i + lookback + 1]
        if highs.iloc[i] == window.max():
            is_swing.iloc[i] = True
    return is_swing


def find_swing_lows(df: pd.DataFrame, lookback: int = 5) -> pd.Series:
    """
    Returns a boolean Series; True where a swing low exists.
    """
    lows = df["Low"]
    is_swing = pd.Series(False, index=df.index)
    for i in range(lookback, len(df) - lookback):
        window = lows.iloc[i - lookback: i + lookback + 1]
        if lows.iloc[i] == window.min():
            is_swing.iloc[i] = True
    return is_swing


def get_recent_swing_highs(df: pd.DataFrame, lookback: int = 5, n: int = 3) -> list:
    """Return the last `n` swing high price values (most recent last)."""
    mask = find_swing_highs(df, lookback)
    return df.loc[mask, "High"].iloc[-n:].tolist()


def get_recent_swing_lows(df: pd.DataFrame, lookback: int = 5, n: int = 3) -> list:
    """Return the last `n` swing low price values (most recent last)."""
    mask = find_swing_lows(df, lookback)
    return df.loc[mask, "Low"].iloc[-n:].tolist()


# ---------------------------------------------------------------------------
# Trend Classification (HH/HL vs LH/LL)
# ---------------------------------------------------------------------------

def classify_trend(swing_highs: list, swing_lows: list) -> str:
    """
    Classify trend from last 2 swing highs and 2 swing lows.
    Returns: "UP", "DOWN", or "SIDEWAYS"
    """
    if len(swing_highs) < 2 or len(swing_lows) < 2:
        return "SIDEWAYS"

    hh = swing_highs[-1] > swing_highs[-2]   # Higher High
    hl = swing_lows[-1] > swing_lows[-2]     # Higher Low
    lh = swing_highs[-1] < swing_highs[-2]   # Lower High
    ll = swing_lows[-1] < swing_lows[-2]     # Lower Low

    if hh and hl:
        return "UP"
    if lh and ll:
        return "DOWN"
    return "SIDEWAYS"


# ---------------------------------------------------------------------------
# Fibonacci Retracement Levels
# ---------------------------------------------------------------------------

FIB_LEVELS = [0.0, 0.236, 0.382, 0.5, 0.618, 0.786, 1.0]


def fib_retracement(swing_low: float, swing_high: float) -> dict:
    """
    Calculate Fibonacci retracement levels for an upswing (low → high).
    Retracement levels measure pullbacks FROM the high back toward the low.
    """
    diff = swing_high - swing_low
    return {
        level: round(swing_high - diff * level, 4)
        for level in FIB_LEVELS
    }


def fib_retracement_up(swing_high: float, swing_low: float) -> dict:
    """
    Calculate Fibonacci retracement levels for a downswing (high → low).
    Retracement levels measure bounces FROM the low back toward the high.
    """
    diff = swing_high - swing_low
    return {
        level: round(swing_low + diff * level, 4)
        for level in FIB_LEVELS
    }


# ---------------------------------------------------------------------------
# MACD
# ---------------------------------------------------------------------------

def macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
    """
    Returns (macd_line, signal_line, histogram) as pd.Series.
    """
    ema_fast = ema(close, fast)
    ema_slow = ema(close, slow)
    macd_line = ema_fast - ema_slow
    signal_line = ema(macd_line, signal)
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


# ---------------------------------------------------------------------------
# RSI
# ---------------------------------------------------------------------------

def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """Wilder's RSI."""
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


# ---------------------------------------------------------------------------
# Parabolic SAR  (used by JNSAR strategy on Hourly data)
# ---------------------------------------------------------------------------

def parabolic_sar(
    df: pd.DataFrame,
    af_start: float = 0.02,
    af_step: float = 0.02,
    af_max: float = 0.20,
) -> pd.Series:
    """
    Classic Parabolic SAR.
    Returns a Series of SAR values aligned with df.index.
    Positive SAR value = below price (uptrend).
    Negative SAR value = above price (downtrend) — encoded as negative for clarity.
    We also attach a 'trend' attribute for convenience.
    """
    high = df["High"].values
    low  = df["Low"].values
    n    = len(df)

    sar    = np.zeros(n)
    trend  = np.zeros(n, dtype=int)   # +1 = up, -1 = down
    ep     = np.zeros(n)              # extreme point
    af     = np.zeros(n)

    # Initialise with first bar
    trend[0] = 1
    sar[0]   = low[0]
    ep[0]    = high[0]
    af[0]    = af_start

    for i in range(1, n):
        prev_trend = trend[i - 1]
        prev_sar   = sar[i - 1]
        prev_ep    = ep[i - 1]
        prev_af    = af[i - 1]

        if prev_trend == 1:  # uptrend
            new_sar = prev_sar + prev_af * (prev_ep - prev_sar)
            new_sar = min(new_sar, low[i - 1], low[max(0, i - 2)])
            if low[i] < new_sar:
                # Reversal to downtrend
                trend[i] = -1
                sar[i]   = prev_ep
                ep[i]    = low[i]
                af[i]    = af_start
            else:
                trend[i] = 1
                sar[i]   = new_sar
                if high[i] > prev_ep:
                    ep[i] = high[i]
                    af[i] = min(prev_af + af_step, af_max)
                else:
                    ep[i] = prev_ep
                    af[i] = prev_af
        else:  # downtrend
            new_sar = prev_sar + prev_af * (prev_ep - prev_sar)
            new_sar = max(new_sar, high[i - 1], high[max(0, i - 2)])
            if high[i] > new_sar:
                # Reversal to uptrend
                trend[i] = 1
                sar[i]   = prev_ep
                ep[i]    = high[i]
                af[i]    = af_start
            else:
                trend[i] = -1
                sar[i]   = new_sar
                if low[i] < prev_ep:
                    ep[i] = low[i]
                    af[i] = min(prev_af + af_step, af_max)
                else:
                    ep[i] = prev_ep
                    af[i] = prev_af

    sar_series = pd.Series(sar, index=df.index, name="SAR")
    trend_series = pd.Series(trend, index=df.index, name="trend")
    return sar_series, trend_series


# ---------------------------------------------------------------------------
# Channel Detection via Linear Regression
# ---------------------------------------------------------------------------

def linear_regression_channel(prices: pd.Series, window: int = 30):
    """
    Fit a linear regression line over `window` bars.
    Returns (upper_band, mid_line, lower_band) as floats for the last bar.
    Upper/lower bands use ±1 standard deviation of residuals.
    """
    if len(prices) < window:
        return None, None, None

    y = prices.iloc[-window:].values
    x = np.arange(window)

    coeffs = np.polyfit(x, y, 1)
    fitted = np.polyval(coeffs, x)
    residuals = y - fitted
    std = residuals.std()

    mid   = fitted[-1]
    upper = mid + std
    lower = mid - std
    return upper, mid, lower


# ---------------------------------------------------------------------------
# Divergence Detection
# ---------------------------------------------------------------------------

def detect_divergence(
    price: pd.Series,
    indicator: pd.Series,
    lookback: int = 5,
    n_swings: int = 2,
) -> str:
    """
    Detect MACD/RSI divergence over the recent `lookback` bars.
    Returns: "BULLISH", "BEARISH", or "NONE"

    Bearish: price makes HH but indicator makes LH → hidden weakness.
    Bullish: price makes LL but indicator makes HL → hidden strength.
    """
    if len(price) < lookback * 3:
        return "NONE"

    p = price.iloc[-lookback * 3:]
    ind = indicator.iloc[-lookback * 3:]

    # Find last two swing highs
    sh_idx = [i for i in range(lookback, len(p) - lookback)
              if p.iloc[i] == p.iloc[i - lookback: i + lookback + 1].max()]
    sl_idx = [i for i in range(lookback, len(p) - lookback)
              if p.iloc[i] == p.iloc[i - lookback: i + lookback + 1].min()]

    if len(sh_idx) >= 2:
        i1, i2 = sh_idx[-2], sh_idx[-1]
        if p.iloc[i2] > p.iloc[i1] and ind.iloc[i2] < ind.iloc[i1]:
            return "BEARISH"

    if len(sl_idx) >= 2:
        i1, i2 = sl_idx[-2], sl_idx[-1]
        if p.iloc[i2] < p.iloc[i1] and ind.iloc[i2] > ind.iloc[i1]:
            return "BULLISH"

    return "NONE"


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def position_size(capital: float, risk_pct: float, entry: float, sl: float) -> int:
    """
    Calculate number of shares to trade given risk parameters.
    risk_pct: e.g. 0.02 for 2%
    """
    risk_amount = capital * risk_pct
    risk_per_share = abs(entry - sl)
    if risk_per_share == 0:
        return 0
    qty = int(risk_amount / risk_per_share)
    return max(qty, 1)
