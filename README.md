# MT5 Algorithmic Trading Station & Quantitative Backtester

A high-performance, institutional-grade desktop trading workstation for **MetaTrader 5 (MT5)** built in Python and Tkinter with a clean light theme, real historical market data downloader, and an algorithmic backtesting engine.

---

## Key Modules & Features

### 1. 📊 Live Terminal & Telemetry
- **Secure MT5 Authentication**: Connects to any MT5 broker server (Demo or Live) using credentials from `.env` or in-app input.
- **Asynchronous Execution**: All network and polling requests run on background threads — UI never freezes.
- **Live Account Overview**:
  - Live Balance, Equity, and Free Margin.
  - Floating Profit & Loss (PnL) with dynamic green/red status.
  - Margin Level, Account Leverage, and EA (Algo Trading) permissions.
  - Real-time terminal latency / ping monitoring (ms).
- **System Audit Log**: Real-time timestamped event logs with colored levels (`INFO`, `SUCCESS`, `WARNING`, `ERROR`).

### 2. 📥 Real Historical Market Data Downloader
- **Real Broker Data**: Fetches actual historical OHLCV bars directly from your MT5 terminal for any selected year (e.g. 2026, 2025, 2024, 2023, 2022, 2021, 2020) or custom date range.
- **Full Timeframe Support**: M1, M5, M15, M30, H1, H4, D1, W1.
- **Data Telemetry Cards**: Total Bars Fetched, Date Range, Period High, Period Low, and Average Spread.
- **Real Market Rates Preview Table**: Interactive Treeview showing timestamp, Open, High, Low, Close, Volume, and Spread.
- **Export to CSV**: Export the fetched historical dataset to CSV for external quantitative analysis.

### 3. 🧪 Quantitative Backtesting Engine (Rule-Based, Non-AI)
- **Real-World Simulation**: Evaluates orders bar-by-bar using actual MT5 historical market data.
- **Realistic Execution**: Incorporates broker bid/ask spread, pip distances, contract sizing, Take Profit (TP), and Stop Loss (SL).
- **Algorithmic Strategies Included**:
  - **HTF Bias + Fib 0.77-0.78 OTE**: Multi-timeframe institutional strategy checking Higher Timeframe (1H or 4H) Market Structure bias, calculating 15M Fibonacci retracement on broken structure, entering when price tests the 0.77–0.78 deep discount/premium zone and closes out in the bias direction, with dynamic structural SL and Target 1.0 TP.
  - **EMA Crossover**: Dual Exponential Moving Average trend following with customizable fast/slow periods.
  - **RSI Mean Reversion**: Momentum exhaustion with customizable RSI period and oversold/overbought thresholds.
  - **MACD Momentum**: Moving Average Convergence Divergence line crossovers with signal line confirmation.
  - **Bollinger Breakout**: Volatility band expansion breakout strategy.
- **Performance Scorecard**:
  - Net Profit ($) and Return on Investment (ROI %).
  - Win Rate % (Winning vs. Losing Trades count).
  - Profit Factor (Gross Wins / Gross Losses).
  - Maximum Peak Drawdown ($ and %).
  - Average Win vs Average Loss (Risk-to-Reward ratio achieved).
  - Trade Expectancy ($ per trade).
- **Detailed Trade Execution Ledger**:
  - Every trade logged with ID, Type (BUY/SELL), Entry Time/Price, Exit Time/Price, Pips won/lost, Net P&L ($), and Exit Reason (Take Profit, Stop Loss, Reverse Signal).
  - One-click export of complete trade history to CSV.

---

## Quick Start

1. **Install Requirements**:
   ```bash
   pip install MetaTrader5 pandas python-dotenv
   ```

2. **Run Application**:
   ```bash
   python main.py
   ```

---

## Project Structure

```text
├── .env                  # Local credentials & terminal configuration (gitignored)
├── .gitignore            # Protects credentials and python cache files
├── config.py             # Configuration loader and .env updater
├── main.py               # Main application entry point with high-DPI awareness
├── core/
│   ├── __init__.py
│   ├── mt5_connection.py # MT5Connector (auth, telemetry, historical rates fetching)
│   └── backtester.py     # Quantitative Backtester & Strategy Indicator Engine
└── gui/
    ├── __init__.py
    ├── app.py            # Main Station GUI & Tabbed Notebook Container
    ├── data_tab.py       # Real Historical Data Downloader View
    └── backtest_tab.py   # Quantitative Backtesting & Telemetry View
```
