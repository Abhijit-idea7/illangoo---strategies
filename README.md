# Ilango / JustNifty — Intraday Strategy Backtest Suite

Backtest engine for **7 intraday trading strategies** derived from *"Practical Guide to Trading and Investing"* by VanIlango (JustNifty).

---

## Strategies Included

| Code | Strategy | Direction |
|------|----------|-----------|
| **S1** | Price Action HH/HL Trend-Following | Long & Short |
| **S2** | Fibonacci Retracement Entry (LRHR) | Long & Short |
| **S3** | 200 EMA Bias + EMA Crossover | Long & Short |
| **S4** | Channel Breakout / Breakdown | Long & Short |
| **S5** | JNSAR Stop-and-Reverse (Hourly) | Long & Short |
| **S6** | Retracement Re-Entry (Fade bounces in trend) | Long & Short |
| **S9** | MACD / RSI Divergence Reversal | Long & Short |

---

## Setup

```bash
# 1. Clone the repo
git clone https://github.com/YOUR_USERNAME/ilango-backtest.git
cd ilango-backtest

# 2. Install dependencies
pip install -r requirements.txt

# 3. (Optional) Configure symbols and capital
#    Edit config.py
```

---

## Running Locally

```bash
# Run ALL strategies on ALL symbols from config.py
python run_backtest.py

# Run a single strategy
python run_backtest.py --strategy S3

# Run multiple strategies
python run_backtest.py --strategy S1 S2 S3

# Run on specific symbols
python run_backtest.py --symbols RELIANCE TCS INFY

# Combine filters
python run_backtest.py --strategy S3 --symbols RELIANCE HDFCBANK

# Quiet mode (suppress per-trade tables)
python run_backtest.py --quiet
```

---

## GitHub Actions

The workflow in `.github/workflows/backtest.yml` runs:
- **Manually**: Go to Actions → "Ilango Intraday Backtest" → Run workflow.  
  You can optionally pass a specific strategy code and/or symbol list.
- **Automatically**: Every Monday at 7:30 AM IST.

Reports are uploaded as **artifacts** (retained 30 days).

---

## Configuration (`config.py`)

| Parameter | Default | Description |
|-----------|---------|-------------|
| `SYMBOLS` | 10 NSE stocks | Stocks to backtest |
| `INTERVAL` | `"2m"` | yFinance bar size |
| `PERIOD` | `"60d"` | History window |
| `CAPITAL` | `500,000` | Backtest capital (INR) |
| `RISK_PER_TRADE_PCT` | `0.02` | 2% risk per trade |
| `MAX_TRADES_PER_DAY` | `2` | Max trades per symbol per day |
| `FORCE_EXIT_TIME` | `"15:20"` | All positions exited by this time |

---

## Data Source

- **Provider**: [yFinance](https://github.com/ranaroussi/yfinance)
- **Exchange**: NSE India (`.NS` suffix added automatically)
- **Interval**: 2-minute bars
- **History**: Last 60 calendar days (yFinance limit for 2m data)
- **Timezone**: All times in IST (Asia/Kolkata)

---

## Output

Each run produces:
- **Console**: Per-symbol trade tables + combined summary table sorted by Return%
- **`reports/`**: One JSON file per (symbol × strategy) with full trade log + metrics

### Metrics reported
- Total trades, Win count, Loss count
- Win rate %
- Total P&L (INR)
- Return % on capital
- Profit Factor
- Max Drawdown %
- Exit breakdown (TARGET / SL / TIME_EXIT / EOD)

---

## Roadmap

- [x] Backtest engines (this repo)
- [ ] Live trading engine with Stocksdeveloper API → Zerodha
- [ ] Paper trading mode
- [ ] Walk-forward optimization
- [ ] Telegram/email alerts

---

## Disclaimer

For educational and research purposes only. Past backtest results do not guarantee future performance. Always paper-trade before going live.
