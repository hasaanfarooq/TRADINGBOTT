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

    def run(self) -> Dict[str, Any]:
        """Execute simulation across all bars."""
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
                        "thesis": open_pos.get("thesis", "Approved")
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
                                "time": bar_time,
                                "type": cand_type,
                                "score": eval_res["total_score"],
                                "thesis": eval_res["thesis"]
                            })
                            continue
                        trade_thesis = eval_res["thesis"]
                        confluence_score = eval_res["total_score"]

                    # Execute Approved Trade
                    if sig == 1:  # BUY
                        risk = (open_price - dyn_sl_val) if dyn_sl_val > 0 else (fixed_sl_dist if fixed_sl_dist > 0 else 20.0 * self.pip_size)
                        if risk > 0 and dyn_sl_val > 0:
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
                            "thesis": trade_thesis
                        }
                    elif sig == -1:  # SELL
                        risk = (dyn_sl_val - open_price) if dyn_sl_val > 0 else (fixed_sl_dist if fixed_sl_dist > 0 else 20.0 * self.pip_size)
                        if risk > 0 and dyn_sl_val > 0:
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
                            "thesis": trade_thesis
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
                "thesis": open_pos.get("thesis", "Approved")
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

