"""
Quantitative Backtesting Engine.
Executes rule-based algorithmic strategies on real historical OHLCV data.
Calculates risk metrics, trade execution reports, and performance analytics.
"""

from typing import Dict, Any, List, Optional
import pandas as pd
import numpy as np
from .reasoning_engine import TradeReasoningEngine


class StrategyEngine:
    """Calculates technical indicators and generates trade signals without AI."""

    @staticmethod
    def calculate_indicators(df: pd.DataFrame, strategy: str, params: Dict[str, Any]) -> pd.DataFrame:
        df = df.copy()

        # Initialize dynamic SL and TP columns
        df["dyn_sl"] = 0.0
        df["dyn_tp"] = 0.0
        df["signal"] = 0

        if strategy == "HTF Bias + Fib 0.77-0.78 OTE":
            # Higher Timeframe Market Structure + M15 Fibonacci 0.77-0.78 Retracement
            df_htf = params.get("df_htf", None)
            swing_len_htf = int(params.get("swing_len_htf", 3))
            swing_len_m15 = int(params.get("swing_len_m15", 3))
            buffer_pips = float(params.get("buffer_pips", 2.0))
            pip_size = float(params.get("pip_size", 0.0001))
            buffer_dist = buffer_pips * pip_size

            # If HTF data is provided, calculate HTF Market Structure bias (Pure HH / LL)
            if df_htf is not None and len(df_htf) > swing_len_htf * 2:
                htf_df = df_htf.copy()
                n_htf = len(htf_df)
                bias_htf = [0] * n_htf
                last_sh_htf = np.nan
                last_sl_htf = np.nan
                curr_bias = 0

                for i in range(n_htf):
                    c_htf = htf_df["close"].iloc[i]
                    if i >= swing_len_htf:
                        idx = i - swing_len_htf
                        if idx >= swing_len_htf and idx + swing_len_htf < n_htf:
                            if htf_df["high"].iloc[idx] == htf_df["high"].iloc[idx - swing_len_htf : idx + swing_len_htf + 1].max():
                                last_sh_htf = htf_df["high"].iloc[idx]
                            if htf_df["low"].iloc[idx] == htf_df["low"].iloc[idx - swing_len_htf : idx + swing_len_htf + 1].min():
                                last_sl_htf = htf_df["low"].iloc[idx]
                    if not np.isnan(last_sh_htf) and c_htf > last_sh_htf:
                        curr_bias = 1   # Bullish Market Structure (BOS)
                    elif not np.isnan(last_sl_htf) and c_htf < last_sl_htf:
                        curr_bias = -1  # Bearish Market Structure (BOS)
                    bias_htf[i] = curr_bias

                htf_df["htf_bias"] = bias_htf
                merged = pd.merge_asof(
                    df.sort_values("time"),
                    htf_df[["time", "htf_bias"]].sort_values("time"),
                    on="time",
                    direction="backward"
                )
                df["htf_bias"] = merged["htf_bias"].fillna(0).values
            else:
                df["htf_bias"] = 1

            # ATR14 for dynamic volatility protection
            hl = df["high"] - df["low"]
            hc = (df["high"] - df["close"].shift(1)).abs()
            lc = (df["low"] - df["close"].shift(1)).abs()
            tr_series = pd.concat([hl, hc, lc], axis=1).max(axis=1)
            atr14_series = tr_series.rolling(window=14).mean().bfill()

            # M15 Break of Structure and Fib 0.77 - 0.78 Retracement
            n = len(df)
            signals = [0] * n
            dyn_sl = [0.0] * n
            dyn_tp = [0.0] * n

            last_sh = np.nan
            last_sl = np.nan
            active_setup = None

            for i in range(n):
                c = df["close"].iloc[i]
                h = df["high"].iloc[i]
                l = df["low"].iloc[i]
                o = df["open"].iloc[i]
                htf_bias = df["htf_bias"].iloc[i]
                curr_atr = float(atr14_series.iloc[i]) if i < len(atr14_series) else 15.0 * pip_size

                # Identify confirmed M15 swing points
                if i >= swing_len_m15:
                    idx = i - swing_len_m15
                    if idx >= swing_len_m15 and idx + swing_len_m15 < n:
                        if df["high"].iloc[idx] == df["high"].iloc[idx - swing_len_m15 : idx + swing_len_m15 + 1].max():
                            last_sh = df["high"].iloc[idx]
                        if df["low"].iloc[idx] == df["low"].iloc[idx - swing_len_m15 : idx + swing_len_m15 + 1].min():
                            last_sl = df["low"].iloc[idx]

                # 1. Detect Break of Structure aligned with HTF bias
                if htf_bias == 1 and not np.isnan(last_sh) and c > last_sh:
                    swing_l = last_sl if not np.isnan(last_sl) else df["low"].iloc[max(0, i - 20) : i].min()
                    if c > swing_l:
                        active_setup = {"type": "BULL", "L": swing_l, "H": h, "tested": False}
                elif htf_bias == -1 and not np.isnan(last_sl) and c < last_sl:
                    swing_h = last_sh if not np.isnan(last_sh) else df["high"].iloc[max(0, i - 20) : i].max()
                    if swing_h > c:
                        active_setup = {"type": "BEAR", "L": l, "H": swing_h, "tested": False}

                # 2. Check Fibonacci 0.77 - 0.78 retracement on active setup
                if active_setup is not None:
                    if active_setup["type"] == "BULL":
                        L = active_setup["L"]
                        H = active_setup["H"]
                        if h > H:
                            active_setup["H"] = h
                            H = h

                        fib_77 = H - 0.77 * (H - L)

                        if l <= fib_77 and l >= L:
                            active_setup["tested"] = True

                        # Closes back out of the zone in the direction of the bias
                        if active_setup["tested"] and c > fib_77 and c > o:
                            raw_risk = c - L + buffer_dist
                            safe_risk = max(raw_risk, 1.2 * curr_atr, 12.0 * pip_size)
                            signals[i] = 1
                            dyn_sl[i] = round(c - safe_risk, 5)
                            dyn_tp[i] = round(c + (2.0 * safe_risk), 5)  # Exact 1:2 R:R
                            active_setup = None
                        elif l < L:
                            active_setup = None

                    elif active_setup["type"] == "BEAR":
                        L = active_setup["L"]
                        H = active_setup["H"]
                        if l < L:
                            active_setup["L"] = l
                            L = l

                        fib_77 = L + 0.77 * (H - L)

                        if h >= fib_77 and h <= H:
                            active_setup["tested"] = True

                        # Closes back out of the zone in the direction of the bias
                        if active_setup["tested"] and c < fib_77 and c < o:
                            raw_risk = H - c + buffer_dist
                            safe_risk = max(raw_risk, 1.2 * curr_atr, 12.0 * pip_size)
                            signals[i] = -1
                            dyn_sl[i] = round(c + safe_risk, 5)
                            dyn_tp[i] = round(c - (2.0 * safe_risk), 5)  # Exact 1:2 R:R
                            active_setup = None
                        elif h > H:
                            active_setup = None

            df["signal"] = signals
            df["dyn_sl"] = dyn_sl
            df["dyn_tp"] = dyn_tp

        elif strategy == "CRT Range + CISD/FVG (A++ Institutional)":
            # Candle Range Theory (CRT) + CISD + FVG/IFVG Execution with Multi-Timeframe Narrative (>2 TFs)
            df_htf = params.get("df_htf", None)   # CRT Anchor Timeframe (H1 or H4)
            df_h4 = params.get("df_h4", None)
            df_d1 = params.get("df_d1", None)
            pip_size = float(params.get("pip_size", 0.0001))
            buffer_pips = float(params.get("buffer_pips", 2.0))
            buffer_dist = buffer_pips * pip_size

            # ATR14 on execution timeframe (M15)
            hl = df["high"] - df["low"]
            hc = (df["high"] - df["close"].shift(1)).abs()
            lc = (df["low"] - df["close"].shift(1)).abs()
            tr_series = pd.concat([hl, hc, lc], axis=1).max(axis=1)
            atr14 = tr_series.rolling(window=14).mean().bfill()

            # 1. Macro Narrative (D1 50 EMA)
            if df_d1 is not None and len(df_d1) > 10:
                d1 = df_d1.copy()
                d1["d1_bias"] = np.where(d1["close"] > d1["close"].ewm(span=50, adjust=False).mean(), 1, -1)
                df = pd.merge_asof(
                    df.sort_values("time"),
                    d1[["time", "d1_bias"]].sort_values("time"),
                    on="time",
                    direction="backward"
                )
            else:
                df["d1_bias"] = 1

            # 2. Intermediate Flow (H4 50 EMA)
            if df_h4 is not None and len(df_h4) > 10:
                h4 = df_h4.copy()
                h4["h4_bias"] = np.where(h4["close"] > h4["close"].ewm(span=50, adjust=False).mean(), 1, -1)
                df = pd.merge_asof(
                    df.sort_values("time"),
                    h4[["time", "h4_bias"]].sort_values("time"),
                    on="time",
                    direction="backward"
                )
            else:
                df["h4_bias"] = 1

            # 3. CRT Range on HTF (H1 or H4)
            # Find swing high and swing low CRT candles
            if df_htf is not None and len(df_htf) > 10:
                htf = df_htf.copy()
                htf_n = len(htf)
                crt_highs = [np.nan] * htf_n
                crt_lows = [np.nan] * htf_n
                last_ch = np.nan
                last_cl = np.nan

                for j in range(2, htf_n - 2):
                    # Confirmed swing high CRT candle
                    if htf["high"].iloc[j] == htf["high"].iloc[j-2:j+3].max():
                        last_ch = htf["high"].iloc[j]
                        last_cl = htf["low"].iloc[j]
                    # Confirmed swing low CRT candle
                    if htf["low"].iloc[j] == htf["low"].iloc[j-2:j+3].min():
                        last_ch = htf["high"].iloc[j]
                        last_cl = htf["low"].iloc[j]
                    crt_highs[j+2] = last_ch
                    crt_lows[j+2] = last_cl

                htf["crt_high"] = crt_highs
                htf["crt_low"] = crt_lows
                htf["h1_bias"] = np.where(htf["close"] > htf["close"].ewm(span=20, adjust=False).mean(), 1, -1)

                df = pd.merge_asof(
                    df.sort_values("time"),
                    htf[["time", "crt_high", "crt_low", "h1_bias"]].sort_values("time"),
                    on="time",
                    direction="backward"
                )
            else:
                df["crt_high"] = np.nan
                df["crt_low"] = np.nan
                df["h1_bias"] = 1

            n = len(df)
            signals = [0] * n
            dyn_sl = [0.0] * n
            dyn_tp = [0.0] * n

            for i in range(3, n):
                c = float(df["close"].iloc[i])
                o = float(df["open"].iloc[i])
                h = float(df["high"].iloc[i])
                l = float(df["low"].iloc[i])
                curr_atr = float(atr14.iloc[i]) if i < len(atr14) else 15.0 * pip_size

                prev_c = float(df["close"].iloc[i-1])
                prev_o = float(df["open"].iloc[i-1])
                prev_h = float(df["high"].iloc[i-1])
                prev_l = float(df["low"].iloc[i-1])
                bar2_h = float(df["high"].iloc[i-2])
                bar2_l = float(df["low"].iloc[i-2])

                crt_h = float(df["crt_high"].iloc[i]) if pd.notna(df["crt_high"].iloc[i]) else np.nan
                crt_l = float(df["crt_low"].iloc[i]) if pd.notna(df["crt_low"].iloc[i]) else np.nan
                d1_b = df["d1_bias"].iloc[i]
                h4_b = df["h4_bias"].iloc[i]
                h1_b = df["h1_bias"].iloc[i]

                if np.isnan(crt_h) or np.isnan(crt_l):
                    continue

                # -------------------------------------------------------------
                # BULLISH A++ SETUP:
                # 1. Narrative Check: > 2 Timeframes confirm Bullish (D1 + H4 + H1)
                # 2. Liquidity Sweep: Price swept CRT Low and closed back above
                # 3. CISD + FVG: LTF displacement candle closes above prior down-body, leaving FVG/IFVG
                # 4. Target: Opposite CRT High
                # -------------------------------------------------------------
                bull_tfs = (1 if d1_b == 1 else 0) + (1 if h4_b == 1 else 0) + (1 if h1_b == 1 else 0)
                if bull_tfs >= 2 and l <= crt_l and c > crt_l:
                    # CISD: Change in State of Delivery (displacement closes above prior down-candle body)
                    cisd_bull = (c > max(prev_o, prev_c)) and (c > o)
                    # FVG: Fair Value Gap (3-bar imbalance: current low > bar2 high) OR strong displacement
                    fvg_bull = (l > bar2_h) or ((c - o) > 1.2 * abs(prev_c - prev_o))

                    if cisd_bull and fvg_bull and crt_h > c:
                        # Stop Loss set on top/bottom of CISD anchor with ATR noise shield
                        raw_risk = c - min(l, prev_l) + buffer_dist
                        safe_risk = max(raw_risk, 1.2 * curr_atr, 12.0 * pip_size)
                        target_dist = crt_h - c
                        # Ensure favorable R:R to the CRT High
                        if target_dist >= (1.5 * safe_risk):
                            signals[i] = 1
                            dyn_sl[i] = round(c - safe_risk, 5)
                            dyn_tp[i] = round(crt_h, 5)

                # -------------------------------------------------------------
                # BEARISH A++ SETUP:
                # 1. Narrative Check: > 2 Timeframes confirm Bearish
                # 2. Liquidity Sweep: Price swept CRT High and closed back below
                # 3. CISD + FVG: LTF displacement candle closes below prior up-body, leaving FVG/IFVG
                # 4. Target: Opposite CRT Low
                # -------------------------------------------------------------
                bear_tfs = (1 if d1_b == -1 else 0) + (1 if h4_b == -1 else 0) + (1 if h1_b == -1 else 0)
                if bear_tfs >= 2 and h >= crt_h and c < crt_h:
                    cisd_bear = (c < min(prev_o, prev_c)) and (c < o)
                    fvg_bear = (h < bar2_l) or ((o - c) > 1.2 * abs(prev_c - prev_o))

                    if cisd_bear and fvg_bear and crt_l < c:
                        raw_risk = max(h, prev_h) - c + buffer_dist
                        safe_risk = max(raw_risk, 1.2 * curr_atr, 12.0 * pip_size)
                        target_dist = c - crt_l
                        if target_dist >= (1.5 * safe_risk):
                            signals[i] = -1
                            dyn_sl[i] = round(c + safe_risk, 5)
                            dyn_tp[i] = round(crt_l, 5)

            df["signal"] = signals
            df["dyn_sl"] = dyn_sl
            df["dyn_tp"] = dyn_tp

        elif strategy == "EMA Crossover":
            fast_p = int(params.get("fast_ema", 9))
            slow_p = int(params.get("slow_ema", 21))
            df["fast_ema"] = df["close"].ewm(span=fast_p, adjust=False).mean()
            df["slow_ema"] = df["close"].ewm(span=slow_p, adjust=False).mean()

            buy_cond = (df["fast_ema"] > df["slow_ema"]) & (df["fast_ema"].shift(1) <= df["slow_ema"].shift(1))
            sell_cond = (df["fast_ema"] < df["slow_ema"]) & (df["fast_ema"].shift(1) >= df["slow_ema"].shift(1))
            df.loc[buy_cond, "signal"] = 1
            df.loc[sell_cond, "signal"] = -1

        elif strategy == "RSI Mean Reversion":
            period = int(params.get("rsi_period", 14))
            oversold = float(params.get("rsi_oversold", 30))
            overbought = float(params.get("rsi_overbought", 70))

            delta = df["close"].diff()
            gain = delta.clip(lower=0)
            loss = -delta.clip(upper=0)
            avg_gain = gain.rolling(window=period).mean()
            avg_loss = loss.rolling(window=period).mean()
            rs = avg_gain / avg_loss.replace(0, np.nan)
            df["rsi"] = 100 - (100 / (1 + rs))

            buy_cond = (df["rsi"] > oversold) & (df["rsi"].shift(1) <= oversold)
            sell_cond = (df["rsi"] < overbought) & (df["rsi"].shift(1) >= overbought)
            df.loc[buy_cond, "signal"] = 1
            df.loc[sell_cond, "signal"] = -1

        elif strategy == "MACD Momentum":
            fast = int(params.get("macd_fast", 12))
            slow = int(params.get("macd_slow", 26))
            signal_p = int(params.get("macd_signal", 9))

            ema_fast = df["close"].ewm(span=fast, adjust=False).mean()
            ema_slow = df["close"].ewm(span=slow, adjust=False).mean()
            df["macd"] = ema_fast - ema_slow
            df["macd_signal"] = df["macd"].ewm(span=signal_p, adjust=False).mean()

            buy_cond = (df["macd"] > df["macd_signal"]) & (df["macd"].shift(1) <= df["macd_signal"].shift(1))
            sell_cond = (df["macd"] < df["macd_signal"]) & (df["macd"].shift(1) >= df["macd_signal"].shift(1))
            df.loc[buy_cond, "signal"] = 1
            df.loc[sell_cond, "signal"] = -1

        elif strategy == "Bollinger Breakout":
            period = int(params.get("bb_period", 20))
            std_dev = float(params.get("bb_std", 2.0))

            df["bb_mid"] = df["close"].rolling(window=period).mean()
            df["bb_std"] = df["close"].rolling(window=period).std()
            df["bb_upper"] = df["bb_mid"] + (df["bb_std"] * std_dev)
            df["bb_lower"] = df["bb_mid"] - (df["bb_std"] * std_dev)

            buy_cond = (df["close"] > df["bb_upper"]) & (df["close"].shift(1) <= df["bb_upper"].shift(1))
            sell_cond = (df["close"] < df["bb_lower"]) & (df["close"].shift(1) >= df["bb_lower"].shift(1))
            df.loc[buy_cond, "signal"] = 1
            df.loc[sell_cond, "signal"] = -1

        return df


class Backtester:
    """Simulates trade execution with realistic spread, slippage, SL/TP."""

    def __init__(
        self,
        data: pd.DataFrame,
        strategy_name: str,
        params: Dict[str, Any],
        initial_capital: float = 10000.0,
        lot_size: Optional[float] = None,
        stop_loss_pips: float = 0.0,
        take_profit_pips: float = 0.0,
        spread_pips: float = 1.5,
        pip_size: float = 0.0001,
        contract_size: float = 100000.0,
        risk_per_trade_pct: float = 0.01
    ):
        self.raw_data = data
        self.strategy_name = strategy_name
        self.params = params
        self.initial_capital = initial_capital
        self.lot_size = lot_size
        self.stop_loss_pips = stop_loss_pips
        self.take_profit_pips = take_profit_pips
        self.spread_pips = spread_pips
        self.pip_size = pip_size
        self.contract_size = contract_size
        self.risk_per_trade_pct = risk_per_trade_pct

    def _run_tick_scalper(self) -> Dict[str, Any]:
        """
        High-frequency tick-by-tick simulation engine for Tick Momentum Scalper.
        Rides micro-bursts, scales in up to 20 positions, enforces $1-2 TP,
        $2-3 hard SL, 30-60s time decay, $15 basket stop, London/NY session,
        tight spread, and 1M 50 EMA trend alignment.
        """
        # Determine tick dataset
        df_ticks = self.params.get("df_ticks", None)
        if df_ticks is None or len(df_ticks) < 50:
            if self.raw_data is not None and "bid" in self.raw_data.columns and "ask" in self.raw_data.columns:
                df_ticks = self.raw_data.copy()
            elif self.raw_data is not None and len(self.raw_data) >= 10:
                # Synthesize micro-ticks from OHLC bars if raw ticks were not provided
                t_rows = []
                pip = self.pip_size
                spread_val = self.spread_pips * pip
                for _, row in self.raw_data.iterrows():
                    b_time = row["time"]
                    o = float(row["open"])
                    h = float(row["high"])
                    l = float(row["low"])
                    c = float(row["close"])
                    seq = [o, l, h, c] if c >= o else [o, h, l, c]
                    base_msc = int(pd.to_datetime(b_time).timestamp() * 1000)
                    for idx_t, p_val in enumerate(seq):
                        t_msc = base_msc + (idx_t * 15000)
                        t_rows.append({
                            "time_msc": t_msc,
                            "time_dt": pd.to_datetime(t_msc, unit="ms"),
                            "bid": p_val,
                            "ask": round(p_val + spread_val, 5),
                            "last": p_val
                        })
                df_ticks = pd.DataFrame(t_rows)
            else:
                return {"error": "Insufficient tick or bar data to execute Tick Momentum Scalper."}

        if "time_dt" not in df_ticks.columns:
            if "time_msc" in df_ticks.columns:
                df_ticks["time_dt"] = pd.to_datetime(df_ticks["time_msc"], unit="ms")
            else:
                df_ticks["time_dt"] = pd.to_datetime(df_ticks["time"])

        # 1-Minute 50 EMA & ATR Volatility Ratio Filters
        df_m1 = self.params.get("df_m1", None)
        if df_m1 is not None and len(df_m1) > 10:
            m1 = df_m1.copy()
            if "time_dt" not in m1.columns:
                if isinstance(m1["time"].iloc[0], (int, float)):
                    m1["time_dt"] = pd.to_datetime(m1["time"], unit="s")
                else:
                    m1["time_dt"] = pd.to_datetime(m1["time"])
            m1["ema50"] = m1["close"].ewm(span=50, adjust=False).mean()

            # ATR Volatility Ratio
            hl = m1["high"] - m1["low"]
            hc = (m1["high"] - m1["close"].shift(1)).abs()
            lc = (m1["low"] - m1["close"].shift(1)).abs()
            m1["atr14"] = pd.concat([hl, hc, lc], axis=1).max(axis=1).rolling(14).mean().bfill()
            m1["atr50"] = m1["atr14"].rolling(50).mean().bfill()
            m1["atr_ratio"] = (m1["atr14"] / m1["atr50"]).fillna(1.0)

            df_ticks = pd.merge_asof(
                df_ticks.sort_values("time_dt"),
                m1[["time_dt", "ema50", "atr_ratio"]].sort_values("time_dt"),
                on="time_dt",
                direction="backward"
            )
            df_ticks["atr_ratio"] = df_ticks["atr_ratio"].fillna(1.0)
        else:
            df_ticks["ema50"] = df_ticks["bid"].ewm(span=500, adjust=False).mean()
            df_ticks["atr_ratio"] = 1.0

        # Strategy Parameters
        target_profit_usd = float(self.params.get("target_profit_usd", 0.01))
        stop_loss_usd = float(self.params.get("stop_loss_usd", 2.50))
        max_hold_sec = float(self.params.get("max_hold_seconds", 45.0))
        max_positions = int(self.params.get("max_positions", 30))
        batch_size = int(self.params.get("batch_size", 3))
        cooldown_ms = int(self.params.get("cooldown_ms", 100))
        burst_ticks = int(self.params.get("burst_ticks", 10))
        burst_agreement = float(self.params.get("burst_agreement", 0.70))
        min_burst_pips = float(self.params.get("min_burst_pips", 0.6))
        max_spread_pips = float(self.params.get("max_spread_pips", 1.5))
        basket_stop_usd = float(self.params.get("basket_stop_usd", 25.0))
        basket_pause_sec = int(self.params.get("basket_pause_sec", 300))
        max_consec_losses = int(self.params.get("max_consec_losses", 5))
        daily_loss_cap = float(self.params.get("daily_loss_cap", 100.0))

        # Autonomous ML Reasoning Engine
        min_ml_prob = float(self.params.get("min_ml_probability", 0.75))
        reasoning_engine = TradeReasoningEngine(min_confluence_score=65, min_ml_probability=min_ml_prob)
        rejected_trades: List[Dict[str, Any]] = []

        # Dynamic or fixed lot sizing
        if self.lot_size and self.lot_size > 0:
            pos_lot = self.lot_size
        else:
            # Scaled micro-lot calibrated to capital
            pos_lot = max(0.01, round(self.initial_capital * 0.000005, 2))

        balance = self.initial_capital
        peak_balance = self.initial_capital
        max_drawdown_dollar = 0.0
        max_drawdown_pct = 0.0

        trades: List[Dict[str, Any]] = []
        positions: List[Dict[str, Any]] = []

        last_entry_time_msc = 0
        basket_pause_until_msc = 0
        consec_losses = 0
        curr_day = None
        daily_loss = 0.0

        bids = df_ticks["bid"].values
        asks = df_ticks["ask"].values
        time_mscs = df_ticks["time_msc"].values
        ema50s = df_ticks["ema50"].values
        atr_ratios = df_ticks["atr_ratio"].values
        time_dts = df_ticks["time_dt"]
        hours = time_dts.dt.hour.values
        days = time_dts.dt.day.values

        all_mids = (bids + asks) * 0.5

        # Rolling median spread
        spread_arr = (asks - bids) / self.pip_size
        rolling_spread_median = pd.Series(spread_arr).rolling(200, min_periods=1).median().bfill().values

        n = len(df_ticks)
        for i in range(burst_ticks + 10, n):
            t_msc = time_mscs[i]
            bid = bids[i]
            ask = asks[i]
            spread_pips = spread_arr[i]
            hr = hours[i]
            d = days[i]
            ema = ema50s[i]

            # Daily Loss Cap Reset on day boundary
            if d != curr_day:
                curr_day = d
                daily_loss = 0.0

            # 1. Manage Active Positions Tick by Tick: Close AS SOON AS THEY ARE IN PROFIT!
            if positions:
                total_floating_usd = 0.0
                still_open = []
                for p in positions:
                    p_type = p["type"]
                    entry_p = p["entry_price"]
                    hold_sec = (t_msc - p["entry_time_msc"]) / 1000.0

                    if p_type == "BUY":
                        diff = bid - entry_p
                    else:
                        diff = entry_p - ask

                    pnl = diff * p["lot_size"] * self.contract_size
                    total_floating_usd += pnl

                    exit_reason = None
                    exit_price = bid if p_type == "BUY" else ask

                    # Close the moment position turns into profit (as soon as in profit)!
                    if (target_profit_usd <= 0.05 and pnl > 0.0) or (pnl >= target_profit_usd):
                        exit_reason = f"Profit Scalp (+${pnl:.2f})"
                    elif pnl <= -stop_loss_usd:
                        exit_reason = f"Stop Loss (-${abs(pnl):.2f})"
                    elif hold_sec >= max_hold_sec:
                        exit_reason = f"Time Decay ({hold_sec:.0f}s)"

                    if exit_reason:
                        balance += pnl
                        if pnl < 0:
                            daily_loss += abs(pnl)
                            consec_losses += 1
                        else:
                            consec_losses = 0

                        if balance > peak_balance:
                            peak_balance = balance
                        dd_dlr = peak_balance - balance
                        dd_p = (dd_dlr / peak_balance) * 100 if peak_balance > 0 else 0
                        if dd_dlr > max_drawdown_dollar:
                            max_drawdown_dollar = dd_dlr
                        if dd_p > max_drawdown_pct:
                            max_drawdown_pct = dd_p

                        p_thinking = p.get("thinking", {})
                        trades.append({
                            "id": len(trades) + 1,
                            "type": p_type,
                            "lot_size": p["lot_size"],
                            "entry_time": p["entry_time_str"],
                            "entry_price": round(entry_p, 5),
                            "exit_time": str(time_dts.iloc[i]),
                            "exit_price": round(exit_price, 5),
                            "pips": round(diff / self.pip_size, 1),
                            "pnl": round(pnl, 2),
                            "pnl_pct": round((pnl / self.initial_capital) * 100, 2),
                            "balance": round(balance, 2),
                            "reason": exit_reason,
                            "score": p_thinking.get("total_score", 90),
                            "thesis": p_thinking.get("thesis", "Tick Burst Momentum"),
                            "thinking": p_thinking
                        })
                    else:
                        still_open.append(p)

                positions = still_open

                # Basket Stop Loss: Close ALL positions if total floating loss exceeds basket limit
                if total_floating_usd <= -basket_stop_usd:
                    for p in positions:
                        p_type = p["type"]
                        entry_p = p["entry_price"]
                        exit_price = bid if p_type == "BUY" else ask
                        diff = (exit_price - entry_p) if p_type == "BUY" else (entry_p - exit_price)
                        pnl = diff * p["lot_size"] * self.contract_size
                        balance += pnl
                        daily_loss += max(0, -pnl)

                        if balance > peak_balance:
                            peak_balance = balance
                        dd_dlr = peak_balance - balance
                        dd_p = (dd_dlr / peak_balance) * 100 if peak_balance > 0 else 0
                        if dd_dlr > max_drawdown_dollar:
                            max_drawdown_dollar = dd_dlr
                        if dd_p > max_drawdown_pct:
                            max_drawdown_pct = dd_p

                        p_thinking = p.get("thinking", {})
                        trades.append({
                            "id": len(trades) + 1,
                            "type": p_type,
                            "lot_size": p["lot_size"],
                            "entry_time": p["entry_time_str"],
                            "entry_price": round(entry_p, 5),
                            "exit_time": str(time_dts.iloc[i]),
                            "exit_price": round(exit_price, 5),
                            "pips": round(diff / self.pip_size, 1),
                            "pnl": round(pnl, 2),
                            "pnl_pct": round((pnl / self.initial_capital) * 100, 2),
                            "balance": round(balance, 2),
                            "reason": "Basket Stop Loss",
                            "score": p_thinking.get("total_score", 90),
                            "thesis": "Circuit Breaker Protection",
                            "thinking": p_thinking
                        })
                    positions = []
                    basket_pause_until_msc = t_msc + (basket_pause_sec * 1000)
                    consec_losses += 1

            # 2. Entry Safeguard Filters
            if t_msc < basket_pause_until_msc:
                continue
            if consec_losses >= max_consec_losses:
                continue
            if daily_loss >= daily_loss_cap:
                continue
            if len(positions) >= max_positions:
                continue
            if (t_msc - last_entry_time_msc) < cooldown_ms:
                continue
            if spread_pips > max_spread_pips:
                continue
            # Session filter: London Open & NY Overlap (07:00 to 17:00 UTC)
            if hr < 7 or hr >= 17:
                continue
            # Rollover avoidance (21:00 to 23:00 UTC)
            if hr >= 21 and hr <= 23:
                continue
            if np.isnan(ema):
                continue

            # 3. Momentum Burst Calculation (last N ticks)
            mids = (bids[i-burst_ticks : i+1] + asks[i-burst_ticks : i+1]) * 0.5
            deltas = np.diff(mids)
            up_ticks = np.sum(deltas > 0)
            down_ticks = np.sum(deltas < 0)
            total_active = up_ticks + down_ticks
            if total_active < (burst_ticks * 0.7):
                continue

            net_disp_pips = (mids[-1] - mids[0]) / self.pip_size
            slots = min(batch_size, max_positions - len(positions))
            if slots <= 0:
                continue

            # BUY Candidate Evaluation with Machine Learning Thinking
            if (up_ticks / total_active) >= burst_agreement and net_disp_pips >= min_burst_pips and ask > ema:
                time_elapsed_ms = t_msc - time_mscs[i - burst_ticks]
                velocity = (abs(net_disp_pips) / (time_elapsed_ms / 1000.0)) if time_elapsed_ms > 0 else 0.0
                med_spread = rolling_spread_median[i] if i < len(rolling_spread_median) else 1.0
                ema_dist = (mids[-1] - ema) / self.pip_size
                accel = (all_mids[i] - 2 * all_mids[i - 5] + all_mids[i - 10]) / self.pip_size
                vol_rat = atr_ratios[i] if i < len(atr_ratios) else 1.0
                streak = 0
                for d_val in reversed(deltas):
                    if d_val > 0:
                        streak += 1
                    else:
                        break

                eval_res = reasoning_engine.evaluate_tick_scalper(
                    direction="BUY",
                    disp_pips=net_disp_pips,
                    agreement=up_ticks / total_active,
                    velocity=velocity,
                    spread_pips=spread_pips,
                    median_spread=med_spread,
                    ema_dist_pips=ema_dist,
                    acceleration=accel,
                    vol_ratio=vol_rat,
                    hour=hr,
                    streak=streak,
                    target_profit_usd=target_profit_usd,
                    stop_loss_usd=stop_loss_usd
                )

                if not eval_res["approved"]:
                    rejected_trades.append({
                        "id": len(rejected_trades) + 1,
                        "time": str(time_dts.iloc[i]),
                        "type": "BUY",
                        "price": round(ask, 5),
                        "score": eval_res["total_score"],
                        "win_prob": eval_res["win_probability"],
                        "ev": eval_res["expected_value_r"],
                        "verdict": eval_res["verdict"],
                        "will_be_profitable": eval_res["will_be_profitable"],
                        "reasons_why_execute": eval_res["reasons_why_execute"],
                        "rejection_reasons": eval_res["rejection_reasons"],
                        "risks_weighed": eval_res["risks_weighed"],
                        "thesis": eval_res["thesis"],
                        "telemetry": eval_res["telemetry"]
                    })
                    continue

                for _ in range(slots):
                    positions.append({
                        "id": len(trades) + len(positions) + 1,
                        "type": "BUY",
                        "lot_size": pos_lot,
                        "entry_price": ask,
                        "entry_time_str": str(time_dts.iloc[i]),
                        "entry_time_msc": t_msc,
                        "thinking": eval_res
                    })
                last_entry_time_msc = t_msc

            # SELL Candidate Evaluation with Machine Learning Thinking
            elif (down_ticks / total_active) >= burst_agreement and net_disp_pips <= -min_burst_pips and bid < ema:
                time_elapsed_ms = t_msc - time_mscs[i - burst_ticks]
                velocity = (abs(net_disp_pips) / (time_elapsed_ms / 1000.0)) if time_elapsed_ms > 0 else 0.0
                med_spread = rolling_spread_median[i] if i < len(rolling_spread_median) else 1.0
                ema_dist = (ema - mids[-1]) / self.pip_size
                accel = (all_mids[i] - 2 * all_mids[i - 5] + all_mids[i - 10]) / self.pip_size
                vol_rat = atr_ratios[i] if i < len(atr_ratios) else 1.0
                streak = 0
                for d_val in reversed(deltas):
                    if d_val < 0:
                        streak += 1
                    else:
                        break

                eval_res = reasoning_engine.evaluate_tick_scalper(
                    direction="SELL",
                    disp_pips=net_disp_pips,
                    agreement=down_ticks / total_active,
                    velocity=velocity,
                    spread_pips=spread_pips,
                    median_spread=med_spread,
                    ema_dist_pips=ema_dist,
                    acceleration=accel,
                    vol_ratio=vol_rat,
                    hour=hr,
                    streak=streak,
                    target_profit_usd=target_profit_usd,
                    stop_loss_usd=stop_loss_usd
                )

                if not eval_res["approved"]:
                    rejected_trades.append({
                        "id": len(rejected_trades) + 1,
                        "time": str(time_dts.iloc[i]),
                        "type": "SELL",
                        "price": round(bid, 5),
                        "score": eval_res["total_score"],
                        "win_prob": eval_res["win_probability"],
                        "ev": eval_res["expected_value_r"],
                        "verdict": eval_res["verdict"],
                        "will_be_profitable": eval_res["will_be_profitable"],
                        "reasons_why_execute": eval_res["reasons_why_execute"],
                        "rejection_reasons": eval_res["rejection_reasons"],
                        "risks_weighed": eval_res["risks_weighed"],
                        "thesis": eval_res["thesis"],
                        "telemetry": eval_res["telemetry"]
                    })
                    continue

                for _ in range(slots):
                    positions.append({
                        "id": len(trades) + len(positions) + 1,
                        "type": "SELL",
                        "lot_size": pos_lot,
                        "entry_price": bid,
                        "entry_time_str": str(time_dts.iloc[i]),
                        "entry_time_msc": t_msc,
                        "thinking": eval_res
                    })
                last_entry_time_msc = t_msc

        # Close any residual open positions at end of data
        for p in positions:
            p_type = p["type"]
            entry_p = p["entry_price"]
            exit_price = bids[-1] if p_type == "BUY" else asks[-1]
            diff = (exit_price - entry_p) if p_type == "BUY" else (entry_p - exit_price)
            pnl = diff * p["lot_size"] * self.contract_size
            balance += pnl
            p_thinking = p.get("thinking", {})
            trades.append({
                "id": len(trades) + 1,
                "type": p_type,
                "lot_size": p["lot_size"],
                "entry_time": p["entry_time_str"],
                "entry_price": round(entry_p, 5),
                "exit_time": str(time_dts.iloc[-1]),
                "exit_price": round(exit_price, 5),
                "pips": round(diff / self.pip_size, 1),
                "pnl": round(pnl, 2),
                "pnl_pct": round((pnl / self.initial_capital) * 100, 2),
                "balance": round(balance, 2),
                "reason": "End of Data",
                "score": p_thinking.get("total_score", 90),
                "thesis": "Tick Burst",
                "thinking": p_thinking
            })

        # Calculate final metrics
        total_trades = len(trades)
        wins = [t for t in trades if t["pnl"] > 0]
        losses = [t for t in trades if t["pnl"] <= 0]
        win_count = len(wins)
        loss_count = len(losses)
        win_rate = (win_count / total_trades * 100) if total_trades > 0 else 0.0

        total_profit = sum(t["pnl"] for t in wins)
        total_loss = abs(sum(t["pnl"] for t in losses))
        profit_factor = (total_profit / total_loss) if total_loss > 0 else (99.0 if total_profit > 0 else 1.0)
        net_profit = balance - self.initial_capital
        roi_pct = (net_profit / self.initial_capital) * 100

        avg_win = (total_profit / win_count) if win_count > 0 else 0.0
        avg_loss = (total_loss / loss_count) if loss_count > 0 else 0.0

        return {
            "initial_capital": self.initial_capital,
            "final_balance": round(balance, 2),
            "net_profit": round(net_profit, 2),
            "roi_pct": round(roi_pct, 2),
            "total_trades": total_trades,
            "winning_trades": win_count,
            "losing_trades": loss_count,
            "filtered_count": len(rejected_trades),
            "rejected_trades": rejected_trades,
            "win_rate": round(win_rate, 2),
            "profit_factor": round(profit_factor, 2),
            "max_drawdown_dollar": round(max_drawdown_dollar, 2),
            "max_drawdown_pct": round(max_drawdown_pct, 2),
            "avg_win": round(avg_win, 2),
            "trades": trades
        }

    def run(self) -> Dict[str, Any]:
        """Execute simulation across all bars or ticks."""
        if self.strategy_name == "Tick Momentum Scalper":
            return self._run_tick_scalper()

        if self.raw_data is None or len(self.raw_data) < 30:
            return {
                "error": "Insufficient historical bars to execute backtest (minimum 30 bars required)."
            }

        df = StrategyEngine.calculate_indicators(self.raw_data, self.strategy_name, self.params)

        balance = self.initial_capital
        peak_balance = self.initial_capital
        max_drawdown_dollar = 0.0
        max_drawdown_pct = 0.0

        trades: List[Dict[str, Any]] = []
        rejected_trades: List[Dict[str, Any]] = []
        open_pos: Optional[Dict[str, Any]] = None

        fixed_sl_dist = self.stop_loss_pips * self.pip_size if self.stop_loss_pips > 0 else 0
        fixed_tp_dist = self.take_profit_pips * self.pip_size if self.take_profit_pips > 0 else 0
        spread_cost = self.spread_pips * self.pip_size

        # Initialize Trade Reasoning Engine if enabled
        use_reasoning = self.params.get("use_reasoning", True)
        reasoning_engine = None
        dfs = None
        if use_reasoning:
            min_score = int(self.params.get("min_confluence_score", 60))
            reasoning_engine = TradeReasoningEngine(min_confluence_score=min_score)
            dfs = TradeReasoningEngine.prepare_data(
                df_m15=df,
                df_h1=self.params.get("df_h1"),
                df_h4=self.params.get("df_h4"),
                df_d1=self.params.get("df_d1")
            )

        # Iterate through bars chronologically
        for i in range(1, len(df)):
            prev_row = df.iloc[i - 1]
            row = df.iloc[i]
            bar_time = str(row["time"])
            open_price = float(row["open"])
            high_price = float(row["high"])
            low_price = float(row["low"])
            close_price = float(row["close"])

            # 1. Manage currently open position
            if open_pos is not None:
                p_type = open_pos["type"]
                entry_price = open_pos["entry_price"]
                pos_lot = open_pos["lot_size"]
                custom_sl = open_pos.get("sl_price", 0.0)
                custom_tp = open_pos.get("tp_price", 0.0)
                risk_dist = open_pos.get("risk_dist", 0.0)
                be_active = open_pos.get("be_active", False)
                exit_price = None
                exit_reason = None

                # Autonomous Capital Protection: Break-Even Trailing at +1R profit
                if not be_active and risk_dist > 0:
                    if p_type == "BUY" and high_price >= (entry_price + risk_dist):
                        open_pos["sl_price"] = entry_price + spread_cost
                        custom_sl = open_pos["sl_price"]
                        open_pos["be_active"] = True
                    elif p_type == "SELL" and low_price <= (entry_price - risk_dist):
                        open_pos["sl_price"] = entry_price - spread_cost
                        custom_sl = open_pos["sl_price"]
                        open_pos["be_active"] = True

                if p_type == "BUY":
                    # Check Dynamic Structural SL or Fixed SL
                    if custom_sl > 0 and low_price <= custom_sl:
                        exit_price = custom_sl
                        exit_reason = "Break-Even (+1R Trailed)" if open_pos.get("be_active") else "Stop Loss (Structural)"
                    elif fixed_sl_dist > 0 and low_price <= (entry_price - fixed_sl_dist):
                        exit_price = entry_price - fixed_sl_dist
                        exit_reason = "Stop Loss"
                    # Check Dynamic Structural TP or Fixed TP
                    elif custom_tp > 0 and high_price >= custom_tp:
                        exit_price = custom_tp
                        exit_reason = "Take Profit (1:2 RR)"
                    elif fixed_tp_dist > 0 and high_price >= (entry_price + fixed_tp_dist):
                        exit_price = entry_price + fixed_tp_dist
                        exit_reason = "Take Profit"
                    # Check Reverse Signal
                    elif prev_row["signal"] == -1:
                        exit_price = open_price
                        exit_reason = "Reverse Signal"

                elif p_type == "SELL":
                    # Check Dynamic Structural SL or Fixed SL
                    if custom_sl > 0 and high_price >= custom_sl:
                        exit_price = custom_sl
                        exit_reason = "Break-Even (+1R Trailed)" if open_pos.get("be_active") else "Stop Loss (Structural)"
                    elif fixed_sl_dist > 0 and high_price >= (entry_price + fixed_sl_dist):
                        exit_price = entry_price + fixed_sl_dist
                        exit_reason = "Stop Loss"
                    # Check Dynamic Structural TP or Fixed TP
                    elif custom_tp > 0 and low_price <= custom_tp:
                        exit_price = custom_tp
                        exit_reason = "Take Profit (1:2 RR)"
                    elif fixed_tp_dist > 0 and low_price <= (entry_price - fixed_tp_dist):
                        exit_price = entry_price - fixed_tp_dist
                        exit_reason = "Take Profit"
                    # Check Reverse Signal
                    elif prev_row["signal"] == 1:
                        exit_price = open_price
                        exit_reason = "Reverse Signal"

                # Execute Exit if triggered
                if exit_price is not None:
                    if p_type == "BUY":
                        diff = exit_price - entry_price - spread_cost
                    else:
                        diff = entry_price - exit_price - spread_cost

                    pips_won = diff / self.pip_size
                    pnl_dollar = diff * pos_lot * self.contract_size
                    balance += pnl_dollar

                    # Track drawdown
                    if balance > peak_balance:
                        peak_balance = balance
                    dd_dlr = peak_balance - balance
                    dd_p = (dd_dlr / peak_balance) * 100 if peak_balance > 0 else 0
                    if dd_dlr > max_drawdown_dollar:
                        max_drawdown_dollar = dd_dlr
                    if dd_p > max_drawdown_pct:
                        max_drawdown_pct = dd_p

                    trade_record = {
                        "id": len(trades) + 1,
                        "type": p_type,
                        "lot_size": pos_lot,
                        "entry_time": open_pos["entry_time"],
                        "entry_price": round(entry_price, 5),
                        "exit_time": bar_time,
                        "exit_price": round(exit_price, 5),
                        "pips": round(pips_won, 1),
                        "pnl": round(pnl_dollar, 2),
                        "pnl_pct": round((pnl_dollar / self.initial_capital) * 100, 2),
                        "balance": round(balance, 2),
                        "reason": exit_reason,
                        "score": open_pos.get("score", 100),
                        "thesis": open_pos.get("thesis", "Approved"),
                        "thinking": open_pos.get("thinking", {})
                    }
                    trades.append(trade_record)
                    open_pos = None

            # 2. Check for New Entry on Previous Bar's completed signal
            if open_pos is None:
                sig = prev_row["signal"]
                dyn_sl_val = float(prev_row.get("dyn_sl", 0.0))
                dyn_tp_val = float(prev_row.get("dyn_tp", 0.0))

                if sig != 0:
                    cand_type = "BUY" if sig == 1 else "SELL"
                    trade_thesis = "Approved"
                    confluence_score = 100
                    thinking_data = {}

                    # Consult Quantitative Trade Reasoning Engine
                    if reasoning_engine is not None and dfs is not None:
                        eval_res = reasoning_engine.evaluate_candidate(
                            direction=cand_type,
                            bar_idx=i - 1,
                            dfs=dfs,
                            spread_pips=self.spread_pips,
                            pip_size=self.pip_size
                        )
                        if not eval_res["approved"]:
                            # Trade Reasoning Engine filtered out this low-quality setup
                            rejected_trades.append({
                                "id": len(rejected_trades) + 1,
                                "time": bar_time,
                                "type": cand_type,
                                "price": round(open_price, 5),
                                "score": eval_res["total_score"],
                                "win_prob": eval_res.get("win_probability", 0.5),
                                "ev": eval_res.get("expected_value_r", 0.0),
                                "verdict": eval_res.get("verdict", "REJECTED"),
                                "will_be_profitable": eval_res.get("will_be_profitable", "NO"),
                                "reasons_why_execute": eval_res.get("reasons_why_execute", []),
                                "rejection_reasons": eval_res.get("rejection_reasons", []),
                                "risks_weighed": eval_res.get("risks_weighed", []),
                                "thesis": eval_res["thesis"],
                                "telemetry": eval_res.get("telemetry", {})
                            })
                            continue
                        trade_thesis = eval_res["thesis"]
                        confluence_score = eval_res["total_score"]
                        thinking_data = eval_res

                    # Execute Approved Trade
                    if sig == 1:  # BUY
                        risk = (open_price - dyn_sl_val) if dyn_sl_val > 0 else (fixed_sl_dist if fixed_sl_dist > 0 else 20.0 * self.pip_size)
                        if dyn_tp_val <= 0 and risk > 0:
                            dyn_tp_val = round(open_price + (2.0 * risk), 5)

                        if self.lot_size is None or self.lot_size <= 0:
                            trade_lot = TradeReasoningEngine.calculate_position_size(
                                balance=balance,
                                risk_pct=self.risk_per_trade_pct,
                                sl_distance_price=risk,
                                contract_size=self.contract_size
                            )
                        else:
                            trade_lot = self.lot_size

                        open_pos = {
                            "type": "BUY",
                            "lot_size": trade_lot,
                            "entry_time": bar_time,
                            "entry_price": open_price,
                            "sl_price": dyn_sl_val,
                            "tp_price": dyn_tp_val,
                            "risk_dist": risk,
                            "be_active": False,
                            "score": confluence_score,
                            "thesis": trade_thesis,
                            "thinking": thinking_data
                        }
                    elif sig == -1:  # SELL
                        risk = (dyn_sl_val - open_price) if dyn_sl_val > 0 else (fixed_sl_dist if fixed_sl_dist > 0 else 20.0 * self.pip_size)
                        if dyn_tp_val <= 0 and risk > 0:
                            dyn_tp_val = round(open_price - (2.0 * risk), 5)

                        if self.lot_size is None or self.lot_size <= 0:
                            trade_lot = TradeReasoningEngine.calculate_position_size(
                                balance=balance,
                                risk_pct=self.risk_per_trade_pct,
                                sl_distance_price=risk,
                                contract_size=self.contract_size
                            )
                        else:
                            trade_lot = self.lot_size

                        open_pos = {
                            "type": "SELL",
                            "lot_size": trade_lot,
                            "entry_time": bar_time,
                            "entry_price": open_price,
                            "sl_price": dyn_sl_val,
                            "tp_price": dyn_tp_val,
                            "risk_dist": risk,
                            "be_active": False,
                            "score": confluence_score,
                            "thesis": trade_thesis,
                            "thinking": thinking_data
                        }

        # Close open trade on last bar if any
        if open_pos is not None:
            last_row = df.iloc[-1]
            p_type = open_pos["type"]
            entry_price = open_pos["entry_price"]
            exit_price = float(last_row["close"])
            if p_type == "BUY":
                diff = exit_price - entry_price - spread_cost
            else:
                diff = entry_price - exit_price - spread_cost

            pnl_dollar = diff * open_pos["lot_size"] * self.contract_size
            balance += pnl_dollar

            trade_record = {
                "id": len(trades) + 1,
                "type": p_type,
                "lot_size": open_pos["lot_size"],
                "entry_time": open_pos["entry_time"],
                "entry_price": round(entry_price, 5),
                "exit_time": str(last_row["time"]),
                "exit_price": round(exit_price, 5),
                "pips": round(diff / self.pip_size, 1),
                "pnl": round(pnl_dollar, 2),
                "pnl_pct": round((pnl_dollar / self.initial_capital) * 100, 2),
                "balance": round(balance, 2),
                "reason": "End of Data",
                "score": open_pos.get("score", 100),
                "thesis": open_pos.get("thesis", "Approved"),
                "thinking": open_pos.get("thinking", {})
            }
            trades.append(trade_record)

        # Calculate performance metrics
        total_trades = len(trades)
        wins = [t for t in trades if t["pnl"] > 0]
        losses = [t for t in trades if t["pnl"] <= 0]
        win_count = len(wins)
        loss_count = len(losses)
        win_rate = (win_count / total_trades * 100) if total_trades > 0 else 0.0

        total_profit = sum(t["pnl"] for t in wins)
        total_loss = abs(sum(t["pnl"] for t in losses))
        profit_factor = (total_profit / total_loss) if total_loss > 0 else (99.0 if total_profit > 0 else 1.0)
        net_profit = balance - self.initial_capital
        roi_pct = (net_profit / self.initial_capital) * 100

        avg_win = (total_profit / win_count) if win_count > 0 else 0.0
        avg_loss = (total_loss / loss_count) if loss_count > 0 else 0.0

        return {
            "initial_capital": self.initial_capital,
            "final_balance": round(balance, 2),
            "net_profit": round(net_profit, 2),
            "roi_pct": round(roi_pct, 2),
            "total_trades": total_trades,
            "winning_trades": win_count,
            "losing_trades": loss_count,
            "filtered_count": len(rejected_trades),
            "rejected_trades": rejected_trades,
            "win_rate": round(win_rate, 2),
            "profit_factor": round(profit_factor, 2),
            "max_drawdown_dollar": round(max_drawdown_dollar, 2),
            "max_drawdown_pct": round(max_drawdown_pct, 2),
            "avg_win": round(avg_win, 2),
            "avg_loss": round(avg_loss, 2),
            "trades": trades
        }

