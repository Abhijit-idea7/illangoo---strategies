# =============================================================================
# config.py — Central configuration for Ilango Backtest Suite
# =============================================================================

# ---------------------------------------------------------------------------
# Stocks to backtest (NSE symbols — .NS suffix added automatically)
# Add / remove symbols as needed
# ---------------------------------------------------------------------------
SYMBOLS = [
    "RELIANCE",
    "TCS",
    "HDFCBANK",
    "INFY",
    "ICICIBANK",
    "SBIN",
    "AXISBANK",
    "KOTAKBANK",
    "LT",
    "WIPRO",
]

# ---------------------------------------------------------------------------
# Data settings
# ---------------------------------------------------------------------------
INTERVAL        = "2m"          # yFinance interval: "1m" (7d max) | "2m" (60d max)
PERIOD          = "60d"         # History window — keep within yFinance limits
TIMEZONE        = "Asia/Kolkata"

MARKET_OPEN     = "09:15"       # IST
MARKET_CLOSE    = "15:20"       # Forced exit before 15:30 close
FORCE_EXIT_TIME = "15:20"       # Any open position exited at this time

# ---------------------------------------------------------------------------
# Risk & position sizing
# ---------------------------------------------------------------------------
CAPITAL             = 500_000   # Total capital (INR) per backtest run
RISK_PER_TRADE_PCT  = 0.02      # 2% of capital risked per trade
MAX_TRADES_PER_DAY  = 2         # Hard limit per symbol per day

# ---------------------------------------------------------------------------
# Strategy selector (used by run_backtest.py)
# "ALL" runs every strategy; or specify e.g. ["S1", "S3"]
# ---------------------------------------------------------------------------
RUN_STRATEGIES = "ALL"

# Strategy codes:
#   S1  → Price Action HH/HL Trend-Following
#   S2  → Fibonacci Retracement Entry
#   S3  → 200 EMA + EMA Crossover
#   S4  → Channel Breakout / Breakdown
#   S5  → JNSAR (Stop-and-Reverse on Hourly)
#   S6  → Retracement Re-Entry (Fading bounces in trend direction)
#   S9  → MACD / RSI Divergence Reversal

# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------
REPORTS_DIR = "reports"
