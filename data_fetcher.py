# =============================================================================
# data_fetcher.py — yFinance data downloader with IST timezone handling
# =============================================================================

import yfinance as yf
import pandas as pd
from config import INTERVAL, PERIOD, TIMEZONE, MARKET_OPEN, MARKET_CLOSE


def fetch_ohlcv(symbol: str, interval: str = INTERVAL, period: str = PERIOD) -> pd.DataFrame:
    """
    Download OHLCV data for an NSE symbol via yFinance.

    Parameters
    ----------
    symbol  : NSE ticker without suffix, e.g. "RELIANCE"
    interval: yFinance interval string ("1m", "2m", "5m" …)
    period  : look-back period ("7d" for 1m, "60d" for 2m)

    Returns
    -------
    DataFrame with DatetimeIndex in IST, filtered to market hours.
    Columns: Open, High, Low, Close, Volume
    """
    ticker_sym = symbol + ".NS"
    ticker = yf.Ticker(ticker_sym)

    df = ticker.history(period=period, interval=interval, auto_adjust=True)

    if df.empty:
        print(f"  [WARNING] No data returned for {ticker_sym}")
        return df

    # Convert index to IST
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC").tz_convert(TIMEZONE)
    else:
        df.index = df.index.tz_convert(TIMEZONE)

    # Keep only OHLCV columns
    df = df[["Open", "High", "Low", "Close", "Volume"]].copy()

    # Drop rows with NaN OHLC (sometimes yFinance returns incomplete rows)
    df.dropna(subset=["Open", "High", "Low", "Close"], inplace=True)

    # Filter to regular market hours
    df = df.between_time(MARKET_OPEN, MARKET_CLOSE)

    return df


def fetch_hourly(symbol: str) -> pd.DataFrame:
    """
    Return OHLCV resampled to 1-Hour bars (used by JNSAR strategy).
    Builds from 2m data so we get 60 days of hourly history.
    """
    df_2m = fetch_ohlcv(symbol, interval="2m", period="60d")
    if df_2m.empty:
        return df_2m

    hourly = df_2m.resample("1h").agg(
        Open=("Open", "first"),
        High=("High", "max"),
        Low=("Low", "min"),
        Close=("Close", "last"),
        Volume=("Volume", "sum"),
    ).dropna(subset=["Open", "High", "Low", "Close"])

    # Keep only market hours rows (some hourly bars may fall outside)
    hourly = hourly.between_time(MARKET_OPEN, MARKET_CLOSE)
    return hourly


def get_trading_days(df: pd.DataFrame) -> list:
    """Return sorted list of unique trading dates present in the DataFrame."""
    return sorted(df.index.normalize().unique())
