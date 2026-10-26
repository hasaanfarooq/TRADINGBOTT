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

1. **CRT Range + CISD/FVG Institutional Model (`CRT Range + CISD/FVG (A++ Institutional)`)**:
   - **Market Narrative / DOL (Draw on Liquidity)**:
     - Multi-timeframe trend alignment across **Daily (D1)**, **4-Hour (H4)**, and **1-Hour (H1)**.
     - D1 Macro Order Flow: Evaluated via 50 EMA and structural swing highs/lows.
     - H4 Intermediate Flow: Evaluated via 50 EMA and directional momentum.
     - **A++ Confluence Requirement**: Setup MUST have **$>2$ timeframes in agreement** ($\ge 3$ timeframes aligned in the direction of the trade). If fewer than 3 timeframes align, the setup is rejected.
   - **Candle Range Theory (CRT) Range Anchor**:
     - On the Higher Timeframe (e.g., H1 or H4), a key swing candle establishes the trading range: $[\text{CRT}_{\text{Low}}, \text{CRT}_{\text{High}}]$.
     - **Liquidity Sweep**: Price sweeps outside the CRT candle range:
       - Bullish Setup: Sweeps below $\text{CRT}_{\text{Low}}$ (sell-side liquidity grab), but immediately rejects and closes back inside the range.
       - Bearish Setup: Sweeps above $\text{CRT}_{\text{High}}$ (buy-side liquidity grab / turtle soup), but immediately rejects and closes back inside the range.
   - **Execution Timeframe Confirmation (CISD + FVG/IFVG)**:
     - On the Lower Timeframe (M15), price must print a confirmed **Change In State of Delivery (CISD)**:
       - Bullish: Strong displacement candle closing above the highest open/body of the down-close delivery sequence into the low.
       - Bearish: Strong displacement candle closing below the lowest open/body of the up-close delivery sequence into the high.
     - Formed with a 3-candle **Fair Value Gap (FVG)** imbalance ($\text{Low}_{i} > \text{High}_{i-2}$ for buy, $\text{High}_{i} < \text{Low}_{i-2}$ for sell) or tap into an Inverted FVG (IFVG).
   - **Stop Loss**: Placed strictly on top/bottom of the CISD candle anchor with ATR volatility cushioning ($\text{CISD} \pm \text{buffer}$).
   - **Take Profit Target**: Targets the opposite side of the CRT candle range:
     - Bullish Target: $\text{CRT}_{\text{High}}$ (the other high of the CRT range).
     - Bearish Target: $\text{CRT}_{\text{Low}}$ (the other low of the CRT range).
   - **Position Sizing & Risk Management**:
     - Strict 1.0% equity risk per trade: $\text{Lot} = \frac{\text{Capital} \times 0.01}{\text{Risk Distance} \times \text{Contract Size}}$.
     - Automatic Break-Even trailing when price reaches $+1.0\text{R}$ in profit.

2. **HTF Market Structure & M15 Fibonacci 0.77–0.78 Retracement (`HTF Bias + Fib 0.77-0.78 OTE`)**:
   - **Higher Timeframe Bias (1H / 4H)**: Evaluates Pure Market Structure on the higher timeframe. A **Bullish Break of Structure (BOS)** occurs when a candle closes above the prior Swing High; a **Bearish BOS** occurs when a candle closes below the prior Swing Low.
   - **M15 Fibonacci Deep Retracement**:
     - When M15 structure breaks in the direction of the HTF bias, an impulse leg between Swing Low $L$ and Swing High $H$ is mapped.
     - Fibonacci 0.77–0.78 level: $\text{Fib}_{77} = H - 0.77 \times (H - L)$ for longs (or $L + 0.77 \times (H - L)$ for shorts).
     - **Entry Trigger**: Price retraces down/up into the $0.77 - 0.78$ zone and **closes back out of the zone in the direction of the bias**.
     - **Dynamic Structural Stop Loss**: Placed strictly below/above the swing anchor point ($L - \text{buffer}$ or $H + \text{buffer}$).
     - **Dynamic Take Profit (1:2 Risk/Reward)**: Goal targeted at exactly twice the structural risk distance: $\text{TP} = \text{Entry} \pm (2.0 \times |\text{Entry} - \text{SL}|)$.

3. **EMA Trend Crossover (`EMA Crossover`)**:
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

### 3.5. Quantitative Trade Reasoning & Confluence Engine (`core/reasoning_engine.py`)

Before any candidate trade signal is executed, the `TradeReasoningEngine` evaluates the setup across **4 quantitative pillars** and assigns a holistic Confluence Score from **0 to 100 points**:

```text
Trade Signal Triggered
         │
         ▼
┌────────────────────────────────────────────────────────┐
│  PILLAR 1: Multi-Timeframe Alignment (Max 30 pts)     │
│  - Daily 50 EMA Macro Trend (+10 pts)                  │
│  - 4-Hour 50 EMA Intermediate Flow (+10 pts)           │
│  - 1-Hour 20 EMA Momentum Direction (+10 pts)          │
├────────────────────────────────────────────────────────┤
│  PILLAR 2: Candle Anatomy & Rejection (Max 25 pts)    │
│  - Long Rejection Wick (>= 35% of total bar) (+15 pts) │
│  - Strong Displacement Close in Bias Direction (+10)  │
├────────────────────────────────────────────────────────┤
│  PILLAR 3: Liquidity Sweep / Fakeout Grab (Max 25 pts)│
│  - Turtle Soup Liquidity Sweep (+25 pts)               │
│  - Tested Established Support/Resistance (+15 pts)     │
├────────────────────────────────────────────────────────┤
│  PILLAR 4: Volatility & ATR Regime (Max 20 pts)        │
│  - ATR Expansion (not in dead chop regime) (+10 pts)   │
│  - Orderly Bar Range vs. ATR (+10 pts)                 │
└────────────────────────────────────────────────────────┘
         │
         ▼
Score >= Min Threshold (e.g., 65/100)?
├── YES ──> TRADE APPROVED (Executed with full trade thesis)
└── NO  ──> TRADE REJECTED (Filtered out to protect capital)
```

- **Thesis Audit Trail**: Every trade stores its exact decision breakdown and score (e.g. `Score: 85/100 | [+] D1 Trend | [+] Strong Rejection Wick | [+] Liquidity Sweep`).
- **Filtered Trades Telemetry**: The UI scorecard tracks the exact count of low-quality trades filtered out by the reasoning engine.

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
  - Target Symbol, Timeframe, and **Historical Period** (`Last 1 Day`, `Last 3 Days`, `Last 1 Week`, `Last 2 Weeks`, `Last 1 Month`, `Last 3 Months`, `Last 6 Months`, `Year 2025`, `Year 2024`, `Year 2023`, `Custom Date Range` with start and end date entry fields).
  - **Strategy Selector**:
    - **Tick Momentum Scalper** (Sub-second high-frequency tick burst momentum scalper on raw millisecond broker ticks).
    - **CRT Range + CISD/FVG (A++ Institutional)** (Multi-timeframe market structure narrative, candle range sweeps, CISD displacement, and FVG imbalance).
    - **HTF Bias + Fib 0.77-0.78 OTE** (Higher timeframe market structure + 15M OTE retracement).
    - **Classic Technicals**: EMA Crossover, RSI Reversion, MACD Momentum, Bollinger Breakout.
  - **Tick Momentum Scalper Architecture**:
    - **Raw Tick Ingestion**: Automatically streams and chunks real millisecond broker ticks directly from the MT5 terminal.
    - **Burst Detection**: Evaluates rolling 10-tick windows for $\ge 70\%$ agreement and net directional displacement.
    - **Trend Filter**: 1-minute 50 EMA (buys only above, sells only below).
    - **Scaling In**: Concurrently holds up to 20 positions with 500ms cooldown.
    - **Micro Dollar Exits**: Fixed dollar take profit ($1-$2), hard stop loss ($2-$3), and stall decay exit (30-60 seconds).
    - **Circuit Breakers**: Basket stop loss ($15.00 limit) closes all positions and pauses; 5 consecutive loss cooldown; daily loss cap; session filter (London Open & London/NY overlap 07:00-17:00 UTC); rollover avoidance (21:00-23:00 UTC).
  - **Capital Allocation (Single User Parameter)**: Editable `Initial Trading Capital ($)` entry with one-click quick preset buttons (`$1k`, `$5k`, `$10k`, `$25k`, `$50k`).
  - **Autonomous Reasoning Execution Model**:
    - **Position Sizing**: Autonomous Risk-Parity (risks exactly 1.0% of equity per trade).
    - **Stop Loss**: Dynamic structural swing anchor + ATR volatility shield.
    - **Take Profit**: Strict 1:2 Risk-to-Reward ratio target (+2.0% profit).
    - **Capital Preservation**: Automatic Break-Even trailing when price reaches +1.0R in profit.
    - **Broker Spread**: Auto-detected live from MetaTrader 5 broker terminal specs.
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
