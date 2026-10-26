# MT5 Quantitative Trading Workstation — Comprehensive System Documentation

## 1. System Overview & Mission

The **MT5 Quantitative Trading Workstation** is a standalone, institutional-grade desktop application engineered for algorithmic traders operating on MetaTrader 5 (MT5). It bridges the MetaTrader 5 C++ IPC API directly to an asynchronous Python engine and a professional light-themed graphical interface.

### Core Design Principles
- **Direct Terminal Integration**: Bypasses slow third-party REST wrappers by interfacing directly with the installed MT5 desktop terminal via `MetaTrader5` binary bindings.
- **Deterministic & Rule-Based (No AI Hype)**: Every signal, backtest, and metric is derived strictly from quantitative mathematics, statistical finance, and deterministic indicator logic.
- **Asynchronous & Non-Blocking**: UI rendering, terminal IPC communication, and heavy backtesting computations run on decoupled background threads. The user interface never stutters, blocks, or shows "Not Responding".
- **Institutional Light Theme**: Clean, distraction-free fintech terminal interface built with custom Tkinter styling and Windows High-DPI hardware font rendering.
- **Security & Privacy by Default**: Credentials are stored locally in `.env`, masked in the GUI with toggleable visibility, and protected from git version control via `.gitignore`.

---

## 2. Architecture & File Hierarchy

```text
f:\Bot Retry\
│
├── .env                          # Local credentials & terminal path (gitignored)
├── .gitignore                    # Prevents leaking credentials, caches, and logs
├── config.py                     # Environment variables manager & .env serializer
├── main.py                       # High-DPI bootstrapper and application entry point
│
├── core/
│   ├── __init__.py               # Public API exports for core engine
│   ├── mt5_connection.py         # Thread-safe MT5 terminal connector & telemetry
│   └── backtester.py             # Bar-by-bar backtesting engine & strategy math
│
├── gui/
│   ├── __init__.py               # GUI package exports
│   ├── app.py                    # Main station layout, header, footer, & Tab 1 (Telemetry)
│   ├── data_tab.py               # Tab 2: Historical Market Data Downloader
│   └── backtest_tab.py           # Tab 3: Quantitative Backtester & Trade Ledger
│
└── docs/
    └── SYSTEM_DOCUMENTATION.md   # Complete technical specifications (this document)
```

---

## 3. Detailed Component Specifications

### 3.1. Bootstrapper (`main.py`)
- **High-DPI Awareness**: Invokes `SetProcessDpiAwareness(1)` via Windows `shcore.dll` / `user32.dll`. This ensures UI elements, fonts, borders, and treeviews render with native 4K/retina sharpness instead of blurry Windows OS scaling.
- **Application Lifecycle**: Initializes the root `tk.Tk` container, binds window destroy events for graceful terminal shutdown, and starts the Tkinter event loop.

---

### 3.2. Configuration Subsystem (`config.py`)
- **Auto-Discovery**: Locates `.env` relative to the project root directory.
- **Safe Persistence**: `Config.save_credentials(...)` utilizes `dotenv.set_key` to update credentials dynamically without destroying or altering existing keys.
- **Managed Variables**:
  - `MT5_ACCOUNT` / `MT5_LOGIN`: Account numeric identifier.
  - `MT5_PASSWORD`: Account trading password.
  - `MT5_SERVER`: Broker server name (e.g., `MetaQuotes-Demo`).
  - `MT5_PATH`: Path to the 64-bit MT5 executable (`terminal64.exe`).

---

### 3.3. MT5 Connection Engine (`core/mt5_connection.py`)
The `MT5Connector` class manages thread-safe IPC communication with the MetaTrader 5 terminal.

#### Methods & Responsibilities
| Method | Description | Return Type |
| :--- | :--- | :--- |
| `connect(login, password, server, path, timeout)` | Initializes MT5 terminal, authenticates account, measures latency. | `Tuple[bool, str]` |
| `disconnect()` | Safely calls `mt5.shutdown()` and resets state. | `Tuple[bool, str]` |
| `get_account_data()` | Queries live account metrics (Balance, Equity, Margin, Free Margin, Profit, Leverage). | `Optional[Dict[str, Any]]` |
| `get_terminal_data()` | Queries terminal build, ping latency, and connected state. | `Optional[Dict[str, Any]]` |
| `test_connection_state()` | Lightweight ping test to verify whether the terminal is responsive. | `bool` |
| `get_available_symbols()` | Discovers all active trading symbols from the broker terminal. | `List[str]` |
| `get_symbol_info(symbol)` | Retrieves point size, digits, pip multiplier, and contract size. | `Dict[str, Any]` |
| `fetch_historical_data(symbol, tf, date_from, date_to)` | Fetches real historical rates via `mt5.copy_rates_range`. | `Tuple[Optional[DataFrame], str]` |

#### Thread Safety Mechanism
MT5 API calls are wrapped in Python's `threading.Lock()` (`self._lock`) to ensure concurrent telemetry polling and background backtest queries never collide in the underlying MT5 C-bindings.

---

### 3.4. Quantitative Backtesting & Strategy Engine (`core/backtester.py`)

#### Strategy Math & Indicator Calculations (`StrategyEngine`)
All indicators are computed using deterministic vector math via `pandas` and `numpy`:

1. **HTF Market Structure & M15 Fibonacci 0.77–0.78 Retracement (`HTF Bias + Fib 0.77-0.78 OTE`)**:
   - **Higher Timeframe Bias (1H / 4H)**: Evaluates Pure Market Structure on the higher timeframe. A **Bullish Break of Structure (BOS)** occurs when a candle closes above the prior Swing High; a **Bearish BOS** occurs when a candle closes below the prior Swing Low.
   - **M15 Fibonacci Deep Retracement**:
     - When M15 structure breaks in the direction of the HTF bias, an impulse leg between Swing Low $L$ and Swing High $H$ is mapped.
     - Fibonacci 0.77–0.78 level: $\text{Fib}_{77} = H - 0.77 \times (H - L)$ for longs (or $L + 0.77 \times (H - L)$ for shorts).
     - **Entry Trigger**: Price retraces down/up into the $0.77 - 0.78$ zone and **closes back out of the zone in the direction of the bias**.
     - **Dynamic Structural Stop Loss**: Placed strictly below/above the swing anchor point ($L - \text{buffer}$ or $H + \text{buffer}$).
     - **Dynamic Structural Take Profit**: Target 1.0 (the broken swing point).

2. **EMA Trend Crossover (`EMA Crossover`)**:
   $$\text{EMA}_t = \text{Close}_t \times \alpha + \text{EMA}_{t-1} \times (1 - \alpha), \quad \alpha = \frac{2}{N + 1}$$
   - **Buy Signal (1)**: Fast EMA crosses strictly above Slow EMA ($\text{EMA}_{\text{fast}, t} > \text{EMA}_{\text{slow}, t}$ and $\text{EMA}_{\text{fast}, t-1} \le \text{EMA}_{\text{slow}, t-1}$).
   - **Sell Signal (-1)**: Fast EMA crosses strictly below Slow EMA.

2. **RSI Mean Reversion (`RSI Mean Reversion`)**:
   $$\text{RS} = \frac{\text{Average Gain}_n}{\text{Average Loss}_n}, \quad \text{RSI} = 100 - \left(\frac{100}{1 + \text{RS}}\right)$$
   - **Buy Signal (1)**: RSI rises from oversold territory and crosses above the threshold (e.g., 30).
   - **Sell Signal (-1)**: RSI falls from overbought territory and crosses below the threshold (e.g., 70).

3. **MACD Momentum Trend (`MACD Momentum`)**:
   $$\text{MACD Line} = \text{EMA}_{12}(\text{Close}) - \text{EMA}_{26}(\text{Close})$$
   $$\text{Signal Line} = \text{EMA}_{9}(\text{MACD Line})$$
   - **Buy Signal (1)**: MACD line crosses above Signal line.
   - **Sell Signal (-1)**: MACD line crosses below Signal line.

4. **Bollinger Bands Breakout (`Bollinger Breakout`)**:
   $$\text{Middle Band} = \text{SMA}_{20}(\text{Close})$$
   $$\text{Upper/Lower Band} = \text{Middle Band} \pm (k \times \sigma)$$
   - **Buy Signal (1)**: Close crosses above Upper Band.
   - **Sell Signal (-1)**: Close crosses below Lower Band.

#### Simulation Engine (`Backtester`)
- **Bar-by-Bar Processing**: Evaluates bars sequentially. Signals generated on bar $i-1$ are executed at the Open of bar $i$ to prevent lookahead bias.
- **Intra-Bar SL/TP Triggering**: Evaluates whether High or Low penetrated Stop Loss or Take Profit levels during the bar:
  - For BUY: Exit at Stop Loss if $\text{Low} \le \text{SL}$; exit at Take Profit if $\text{High} \ge \text{TP}$.
  - For SELL: Exit at Stop Loss if $\text{High} \ge \text{SL}$; exit at Take Profit if $\text{Low} \le \text{TP}$.
- **Spread & Transaction Costs**: Deducts the configured broker spread (in points/pips) from gross trade proceeds.
- **Contract & Dollar PnL Math**:
  $$\text{PnL} = (\Delta \text{Price} - \text{Spread}) \times \text{Lot Size} \times \text{Contract Size}$$
- **Drawdown Tracking**: Tracks equity peak and records maximum dollar and percentage peak-to-trough decline.

---

## 4. User Interface Architecture (`gui/`)

### 4.1. Visual Style & Color System
The GUI uses a custom light theme built on the `clam` ttk engine:
- **Canvas / Background**: `#F3F4F6` (Neutral Slate-100)
- **Cards / Containers**: `#FFFFFF` (Pure White) with 1px border `#E5E7EB`
- **Primary Text**: `#111827` (Slate-900)
- **Secondary Text**: `#6B7280` (Muted Slate-500)
- **Primary Accent**: `#2563EB` (Tailwind Royal Blue)
- **Status Green**: `#16A34A` / Badge `#DCFCE7`
- **Status Red**: `#DC2626` / Badge `#FEE2E2`
- **Status Amber**: `#D97706` / Badge `#FEF3C7`

---

### 4.2. Workstation Navigation & Tabs

```
+---------------------------------------------------------------------------------------+
|  MT5 ALGO TRADING WORKSTATION                   [ ⏱ 24 ms ]  [ ● CONNECTED ]         |
+---------------------------------------------------------------------------------------+
|  [ 📊 Live Terminal & Telemetry ]  [ 📥 Historical Data Fetcher ]  [ 🧪 Backtester ]  |
+---------------------------------------------------------------------------------------+
|                                                                                       |
|  (Dynamic Tab Contents Displayed Here)                                               |
|                                                                                       |
+---------------------------------------------------------------------------------------+
|  MetaTrader 5: Build 5410 (MetaQuotes) | Broker: MetaQuotes Ltd    Local: 13:30:00   |
+---------------------------------------------------------------------------------------+
```

#### Tab 1: Live Terminal & Telemetry
- **Left Panel (Credentials & Controls)**:
  - Account / Login input with numerical validation.
  - Password field with show/hide toggle (`👁`/`🔒`).
  - Server selection with history dropdown.
  - Terminal path with native file dialog (`Browse...`).
  - Save to `.env` toggle.
  - Action buttons: "CONNECT TO MT5", "DISCONNECT", "Ping / Verify", "Save to .env".
- **Right Panel - Live Telemetry Grid**:
  - Balance, Equity, Floating P&L (color-coded).
  - Free Margin, Margin Level (%).
  - Leverage & EA Algo Trading permissions flag (`EA: ALLOWED` / `EA: DISABLED`).
- **Right Panel - System & Audit Log**:
  - Real-time logging terminal with timestamped entries (`[HH:MM:SS] [INFO/SUCCESS/ERROR]`).
  - "Copy All" to clipboard and "Clear" buttons.
- **Background Telemetry Polling**: Every 2,500 ms, queries account balance and margin metrics smoothly without freezing the GUI.

#### Tab 2: Historical Market Data Downloader
- **Controls**:
  - Symbol selector (dynamically loads symbols available on your broker).
  - Timeframe selector (`M1`, `M5`, `M15`, `M30`, `H1`, `H4`, `D1`, `W1`).
  - Target Year selector (`2026`, `2025`, `2024`, `2023`, `2022`, `2021`, `2020`, etc.) or custom date range.
  - "FETCH DATA" button (executes asynchronously).
  - "Export CSV" button.
- **Telemetry Cards**:
  - Total Bars Fetched.
  - Date Range (`YYYY-MM-DD → YYYY-MM-DD`).
  - Period High & Period Low.
  - Average Spread in points.
- **Real Market Rates Table**:
  - Multi-column Treeview showing Date & Time (UTC), Open, High, Low, Close, Volume, and Spread.

#### Tab 3: Quantitative Backtester
- **Controls**:
  - Target Symbol, Timeframe, and Year.
  - Strategy selector (EMA Crossover, RSI Reversion, MACD Momentum, Bollinger Breakout).
  - Dynamic parameter inputs matching the chosen strategy.
  - Capital controls: Initial Capital ($), Lot Size, Stop Loss (pips), Take Profit (pips), Spread (pips).
  - "RUN QUANTITATIVE BACKTEST" button.
  - "Export Trade Ledger (CSV)" button.
- **Performance Scorecard**:
  - **Net Profit ($)** and **ROI (%)**.
  - **Win Rate (%)** and Wins vs Losses count.
  - **Profit Factor** and Trade Expectancy ($).
  - **Max Drawdown ($ and %)**.
  - **Total Trades**.
  - **Average Win vs. Average Loss** (Risk-to-Reward ratio achieved).
- **Trade Execution Ledger**:
  - Row-by-row table of each simulated trade with entry/exit times, prices, pips, dollar P&L (green for win, red for loss), and exit reason.

---

## 5. Security & Risk Management Features

1. **Local Secrets Isolation**: `.env` is omitted from version control via `.gitignore`.
2. **Terminal Disconnect Hook**: Closing the application window immediately triggers `mt5.shutdown()` and stops background polling loops to prevent orphan terminal sessions or socket leaks.
3. **Execution Safety**: Trade simulation includes bid/ask spread and realistic pip values, avoiding overly optimistic backtest results.
