"""
Quantitative Backtesting Engine.
Executes rule-based algorithmic strategies on real historical OHLCV data.
Calculates risk metrics, trade execution reports, and performance analytics.
"""

from typing import Dict, Any, List, Optional
import pandas as pd
import numpy as np


class StrategyEngine:
    """Calculates technical indicators and generates trade signals without AI."""

    @staticmethod
    def calculate_indicators(df: pd.DataFrame, strategy: str, params: Dict[str, Any]) -> pd.DataFrame:
        df = df.copy()

        if strategy == "EMA Crossover":
            fast_p = int(params.get("fast_ema", 9))
            slow_p = int(params.get("slow_ema", 21))
            df["fast_ema"] = df["close"].ewm(span=fast_p, adjust=False).mean()
            df["slow_ema"] = df["close"].ewm(span=slow_p, adjust=False).mean()

            # Signal: 1 for BUY, -1 for SELL, 0 for HOLD
            df["signal"] = 0
            # Crossover logic
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

            df["signal"] = 0
            # Buy when RSI crosses above oversold level from below
            buy_cond = (df["rsi"] > oversold) & (df["rsi"].shift(1) <= oversold)
            # Sell when RSI crosses below overbought level from above
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

            df["signal"] = 0
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

            df["signal"] = 0
            buy_cond = (df["close"] > df["bb_upper"]) & (df["close"].shift(1) <= df["bb_upper"].shift(1))
            sell_cond = (df["close"] < df["bb_lower"]) & (df["close"].shift(1) >= df["bb_lower"].shift(1))
            df.loc[buy_cond, "signal"] = 1
            df.loc[sell_cond, "signal"] = -1

        else:
            df["signal"] = 0

        return df


class Backtester:
    """Simulates trade execution with realistic spread, slippage, SL/TP."""

    def __init__(
        self,
        data: pd.DataFrame,
        strategy_name: str,
        params: Dict[str, Any],
        initial_capital: float = 10000.0,
        lot_size: float = 0.1,
        stop_loss_pips: float = 0.0,
        take_profit_pips: float = 0.0,
        spread_pips: float = 1.5,
        pip_size: float = 0.0001,
        contract_size: float = 100000.0
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
        open_pos: Optional[Dict[str, Any]] = None

        sl_dist = self.stop_loss_pips * self.pip_size if self.stop_loss_pips > 0 else 0
        tp_dist = self.take_profit_pips * self.pip_size if self.take_profit_pips > 0 else 0
        spread_cost = self.spread_pips * self.pip_size

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
                exit_price = None
                exit_reason = None

                if p_type == "BUY":
                    # Check Stop Loss
                    if sl_dist > 0 and low_price <= (entry_price - sl_dist):
                        exit_price = entry_price - sl_dist
                        exit_reason = "Stop Loss"
                    # Check Take Profit
                    elif tp_dist > 0 and high_price >= (entry_price + tp_dist):
                        exit_price = entry_price + tp_dist
                        exit_reason = "Take Profit"
                    # Check Reverse Signal
                    elif prev_row["signal"] == -1:
                        exit_price = open_price
                        exit_reason = "Reverse Signal"

                elif p_type == "SELL":
                    # Check Stop Loss
                    if sl_dist > 0 and high_price >= (entry_price + sl_dist):
                        exit_price = entry_price + sl_dist
                        exit_reason = "Stop Loss"
                    # Check Take Profit
                    elif tp_dist > 0 and low_price <= (entry_price - tp_dist):
                        exit_price = entry_price - tp_dist
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
                        "reason": exit_reason
                    }
                    trades.append(trade_record)
                    open_pos = None

            # 2. Check for New Entry on Previous Bar's completed signal
            if open_pos is None:
                sig = prev_row["signal"]
                if sig == 1:  # BUY
                    open_pos = {
                        "type": "BUY",
                        "lot_size": self.lot_size,
                        "entry_time": bar_time,
                        "entry_price": open_price
                    }
                elif sig == -1:  # SELL
                    open_pos = {
                        "type": "SELL",
                        "lot_size": self.lot_size,
                        "entry_time": bar_time,
                        "entry_price": open_price
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
                "reason": "End of Data"
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
            "win_rate": round(win_rate, 2),
            "profit_factor": round(profit_factor, 2),
            "max_drawdown_dollar": round(max_drawdown_dollar, 2),
            "max_drawdown_pct": round(max_drawdown_pct, 2),
            "avg_win": round(avg_win, 2),
            "avg_loss": round(avg_loss, 2),
            "trades": trades
        }
