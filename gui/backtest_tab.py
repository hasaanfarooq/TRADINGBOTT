"""
Quantitative Backtesting View.
Executes rule-based algorithmic strategies on real MT5 historical data.
"""

import sys
import threading
from datetime import datetime, timezone
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import pandas as pd
import MetaTrader5 as mt5

from core.backtester import Backtester
from gui.data_tab import TIMEFRAME_MAP, YEAR_OPTIONS

FONT_FAMILY = "Segoe UI" if sys.platform == "win32" else "Helvetica"


class BacktestingTab(tk.Frame):
    """View for configuring, executing, and analyzing algorithmic backtests on real MT5 data."""

    def __init__(self, parent, connector, log_callback, app_ref, **kwargs):
        super().__init__(parent, bg="#F3F4F6", **kwargs)
        self.connector = connector
        self.log_callback = log_callback
        self.app_ref = app_ref
        self.is_running = False
        self.last_results = None

        self._build_ui()

    def _build_ui(self):
        container = tk.Frame(self, bg="#F3F4F6")
        container.pack(fill="both", expand=True, padx=16, pady=16)

        # Left Column: Configuration & Parameters (width ~380px)
        left_col = tk.Frame(container, bg="#F3F4F6", width=380)
        left_col.pack(side="left", fill="y", padx=(0, 10))
        left_col.pack_propagate(False)

        # Right Column: Performance Scorecard and Trade Ledger
        right_col = tk.Frame(container, bg="#F3F4F6")
        right_col.pack(side="right", fill="both", expand=True)

        self._build_config_panel(left_col)
        self._build_results_panel(right_col)

    def _build_config_panel(self, parent):
        card = tk.Frame(parent, bg="#FFFFFF", highlightbackground="#E5E7EB", highlightthickness=1)
        card.pack(fill="both", expand=True)

        # Card Header
        ch = tk.Frame(card, bg="#F9FAFB", padx=16, pady=10, highlightbackground="#E5E7EB", highlightthickness=1)
        ch.pack(fill="x")
        tk.Label(ch, text="BACKTEST SETUP & PARAMETERS", font=(FONT_FAMILY, 9, "bold"), fg="#111827", bg="#F9FAFB").pack(side="left")

        # Scrollable or compact body
        body = tk.Frame(card, bg="#FFFFFF", padx=16, pady=12)
        body.pack(fill="both", expand=True)

        # Market Data Source
        tk.Label(body, text="MARKET SPECIFICATIONS", font=(FONT_FAMILY, 8, "bold"), fg="#2563EB", bg="#FFFFFF").pack(anchor="w", pady=(0, 4))
        
        row1 = tk.Frame(body, bg="#FFFFFF")
        row1.pack(fill="x", pady=(0, 8))

        f_sym = tk.Frame(row1, bg="#FFFFFF")
        f_sym.pack(side="left", fill="x", expand=True, padx=(0, 6))
        tk.Label(f_sym, text="Symbol", font=(FONT_FAMILY, 8), fg="#6B7280", bg="#FFFFFF").pack(anchor="w")
        self.combo_symbol = ttk.Combobox(f_sym, values=["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "USDCHF", "XAUUSD", "BTCUSD"], font=(FONT_FAMILY, 9))
        self.combo_symbol.set("EURUSD")
        self.combo_symbol.pack(fill="x", pady=(2, 0))

        f_tf = tk.Frame(row1, bg="#FFFFFF")
        f_tf.pack(side="right", fill="x", expand=True, padx=(6, 0))
        tk.Label(f_tf, text="Timeframe", font=(FONT_FAMILY, 8), fg="#6B7280", bg="#FFFFFF").pack(anchor="w")
        self.combo_tf = ttk.Combobox(f_tf, values=list(TIMEFRAME_MAP.keys()), font=(FONT_FAMILY, 9), state="readonly")
        self.combo_tf.set("H1 (1 Hour)")
        self.combo_tf.pack(fill="x", pady=(2, 0))

        # Target Year
        tk.Label(body, text="Historical Period (Real Year)", font=(FONT_FAMILY, 8), fg="#6B7280", bg="#FFFFFF").pack(anchor="w")
        self.combo_year = ttk.Combobox(body, values=YEAR_OPTIONS, font=(FONT_FAMILY, 9), state="readonly")
        self.combo_year.set("2024")
        self.combo_year.pack(fill="x", pady=(2, 12))

        # Strategy Selection
        tk.Label(body, text="ALGORITHMIC STRATEGY (RULE-BASED)", font=(FONT_FAMILY, 8, "bold"), fg="#2563EB", bg="#FFFFFF").pack(anchor="w", pady=(0, 4))
        self.combo_strategy = ttk.Combobox(
            body,
            values=[
                "EMA Crossover",
                "RSI Mean Reversion",
                "MACD Momentum",
                "Bollinger Breakout"
            ],
            font=(FONT_FAMILY, 9),
            state="readonly"
        )
        self.combo_strategy.set("EMA Crossover")
        self.combo_strategy.bind("<<ComboboxSelected>>", self._on_strategy_change)
        self.combo_strategy.pack(fill="x", pady=(2, 10))

        # Dynamic Strategy Params Frame
        self.f_strat_params = tk.Frame(body, bg="#F9FAFB", highlightbackground="#E5E7EB", highlightthickness=1, padx=10, pady=8)
        self.f_strat_params.pack(fill="x", pady=(0, 12))
        self._render_strategy_params("EMA Crossover")

        # Capital & Risk Controls
        tk.Label(body, text="CAPITAL & EXECUTION CONTROLS", font=(FONT_FAMILY, 8, "bold"), fg="#2563EB", bg="#FFFFFF").pack(anchor="w", pady=(0, 4))

        row_cap = tk.Frame(body, bg="#FFFFFF")
        row_cap.pack(fill="x", pady=(0, 6))

        f_cap = tk.Frame(row_cap, bg="#FFFFFF")
        f_cap.pack(side="left", fill="x", expand=True, padx=(0, 6))
        tk.Label(f_cap, text="Initial Capital ($)", font=(FONT_FAMILY, 8), fg="#6B7280", bg="#FFFFFF").pack(anchor="w")
        self.entry_capital = ttk.Entry(f_cap, font=(FONT_FAMILY, 9))
        self.entry_capital.insert(0, "10000")
        self.entry_capital.pack(fill="x", pady=(2, 0))

        f_lot = tk.Frame(row_cap, bg="#FFFFFF")
        f_lot.pack(side="right", fill="x", expand=True, padx=(6, 0))
        tk.Label(f_lot, text="Trade Lot Size", font=(FONT_FAMILY, 8), fg="#6B7280", bg="#FFFFFF").pack(anchor="w")
        self.entry_lot = ttk.Entry(f_lot, font=(FONT_FAMILY, 9))
        self.entry_lot.insert(0, "0.1")
        self.entry_lot.pack(fill="x", pady=(2, 0))

        row_sltp = tk.Frame(body, bg="#FFFFFF")
        row_sltp.pack(fill="x", pady=(0, 6))

        f_sl = tk.Frame(row_sltp, bg="#FFFFFF")
        f_sl.pack(side="left", fill="x", expand=True, padx=(0, 6))
        tk.Label(f_sl, text="Stop Loss (Pips)", font=(FONT_FAMILY, 8), fg="#6B7280", bg="#FFFFFF").pack(anchor="w")
        self.entry_sl = ttk.Entry(f_sl, font=(FONT_FAMILY, 9))
        self.entry_sl.insert(0, "30")
        self.entry_sl.pack(fill="x", pady=(2, 0))

        f_tp = tk.Frame(row_sltp, bg="#FFFFFF")
        f_tp.pack(side="right", fill="x", expand=True, padx=(6, 0))
        tk.Label(f_tp, text="Take Profit (Pips)", font=(FONT_FAMILY, 8), fg="#6B7280", bg="#FFFFFF").pack(anchor="w")
        self.entry_tp = ttk.Entry(f_tp, font=(FONT_FAMILY, 9))
        self.entry_tp.insert(0, "60")
        self.entry_tp.pack(fill="x", pady=(2, 0))

        # Spread
        row_spd = tk.Frame(body, bg="#FFFFFF")
        row_spd.pack(fill="x", pady=(0, 14))
        tk.Label(row_spd, text="Broker Spread (Pips)", font=(FONT_FAMILY, 8), fg="#6B7280", bg="#FFFFFF").pack(side="left")
        self.entry_spread = ttk.Entry(row_spd, width=8, font=(FONT_FAMILY, 9))
        self.entry_spread.insert(0, "1.5")
        self.entry_spread.pack(side="right")

        # Action Buttons
        self.btn_run = tk.Button(
            body,
            text="RUN QUANTITATIVE BACKTEST",
            font=(FONT_FAMILY, 10, "bold"),
            bg="#2563EB",
            fg="#FFFFFF",
            activebackground="#1D4ED8",
            activeforeground="#FFFFFF",
            relief="flat",
            bd=0,
            cursor="hand2",
            pady=10,
            command=self._on_click_run
        )
        self.btn_run.pack(fill="x", pady=(4, 6))

        self.btn_export = tk.Button(
            body,
            text="Export Trade Ledger (CSV)",
            font=(FONT_FAMILY, 8),
            bg="#F3F4F6",
            fg="#111827",
            activebackground="#E5E7EB",
            relief="solid",
            bd=1,
            cursor="hand2",
            pady=6,
            state="disabled",
            command=self._on_click_export
        )
        self.btn_export.pack(fill="x")

    def _on_strategy_change(self, event=None):
        self._render_strategy_params(self.combo_strategy.get())

    def _render_strategy_params(self, strategy: str):
        for child in self.f_strat_params.winfo_children():
            child.destroy()

        if strategy == "EMA Crossover":
            row = tk.Frame(self.f_strat_params, bg="#F9FAFB")
            row.pack(fill="x")
            
            f1 = tk.Frame(row, bg="#F9FAFB")
            f1.pack(side="left", fill="x", expand=True, padx=(0, 4))
            tk.Label(f1, text="Fast EMA Period", font=(FONT_FAMILY, 8), fg="#4B5563", bg="#F9FAFB").pack(anchor="w")
            self.param_fast_ema = ttk.Entry(f1, font=(FONT_FAMILY, 8))
            self.param_fast_ema.insert(0, "9")
            self.param_fast_ema.pack(fill="x")

            f2 = tk.Frame(row, bg="#F9FAFB")
            f2.pack(side="right", fill="x", expand=True, padx=(4, 0))
            tk.Label(f2, text="Slow EMA Period", font=(FONT_FAMILY, 8), fg="#4B5563", bg="#F9FAFB").pack(anchor="w")
            self.param_slow_ema = ttk.Entry(f2, font=(FONT_FAMILY, 8))
            self.param_slow_ema.insert(0, "21")
            self.param_slow_ema.pack(fill="x")

        elif strategy == "RSI Mean Reversion":
            row1 = tk.Frame(self.f_strat_params, bg="#F9FAFB")
            row1.pack(fill="x", pady=(0, 4))
            tk.Label(row1, text="RSI Period", font=(FONT_FAMILY, 8), fg="#4B5563", bg="#F9FAFB").pack(side="left")
            self.param_rsi_period = ttk.Entry(row1, width=8, font=(FONT_FAMILY, 8))
            self.param_rsi_period.insert(0, "14")
            self.param_rsi_period.pack(side="right")

            row2 = tk.Frame(self.f_strat_params, bg="#F9FAFB")
            row2.pack(fill="x")
            f1 = tk.Frame(row2, bg="#F9FAFB")
            f1.pack(side="left", fill="x", expand=True, padx=(0, 4))
            tk.Label(f1, text="Oversold Level", font=(FONT_FAMILY, 8), fg="#4B5563", bg="#F9FAFB").pack(anchor="w")
            self.param_rsi_os = ttk.Entry(f1, font=(FONT_FAMILY, 8))
            self.param_rsi_os.insert(0, "30")
            self.param_rsi_os.pack(fill="x")

            f2 = tk.Frame(row2, bg="#F9FAFB")
            f2.pack(side="right", fill="x", expand=True, padx=(4, 0))
            tk.Label(f2, text="Overbought Level", font=(FONT_FAMILY, 8), fg="#4B5563", bg="#F9FAFB").pack(anchor="w")
            self.param_rsi_ob = ttk.Entry(f2, font=(FONT_FAMILY, 8))
            self.param_rsi_ob.insert(0, "70")
            self.param_rsi_ob.pack(fill="x")

        elif strategy == "MACD Momentum":
            row = tk.Frame(self.f_strat_params, bg="#F9FAFB")
            row.pack(fill="x")
            
            f1 = tk.Frame(row, bg="#F9FAFB")
            f1.pack(side="left", fill="x", expand=True, padx=(0, 2))
            tk.Label(f1, text="Fast (12)", font=(FONT_FAMILY, 8), fg="#4B5563", bg="#F9FAFB").pack(anchor="w")
            self.param_macd_fast = ttk.Entry(f1, font=(FONT_FAMILY, 8))
            self.param_macd_fast.insert(0, "12")
            self.param_macd_fast.pack(fill="x")

            f2 = tk.Frame(row, bg="#F9FAFB")
            f2.pack(side="left", fill="x", expand=True, padx=2)
            tk.Label(f2, text="Slow (26)", font=(FONT_FAMILY, 8), fg="#4B5563", bg="#F9FAFB").pack(anchor="w")
            self.param_macd_slow = ttk.Entry(f2, font=(FONT_FAMILY, 8))
            self.param_macd_slow.insert(0, "26")
            self.param_macd_slow.pack(fill="x")

            f3 = tk.Frame(row, bg="#F9FAFB")
            f3.pack(side="right", fill="x", expand=True, padx=(2, 0))
            tk.Label(f3, text="Signal (9)", font=(FONT_FAMILY, 8), fg="#4B5563", bg="#F9FAFB").pack(anchor="w")
            self.param_macd_signal = ttk.Entry(f3, font=(FONT_FAMILY, 8))
            self.param_macd_signal.insert(0, "9")
            self.param_macd_signal.pack(fill="x")

        elif strategy == "Bollinger Breakout":
            row = tk.Frame(self.f_strat_params, bg="#F9FAFB")
            row.pack(fill="x")
            
            f1 = tk.Frame(row, bg="#F9FAFB")
            f1.pack(side="left", fill="x", expand=True, padx=(0, 4))
            tk.Label(f1, text="Period (20)", font=(FONT_FAMILY, 8), fg="#4B5563", bg="#F9FAFB").pack(anchor="w")
            self.param_bb_period = ttk.Entry(f1, font=(FONT_FAMILY, 8))
            self.param_bb_period.insert(0, "20")
            self.param_bb_period.pack(fill="x")

            f2 = tk.Frame(row, bg="#F9FAFB")
            f2.pack(side="right", fill="x", expand=True, padx=(4, 0))
            tk.Label(f2, text="Std Dev (2.0)", font=(FONT_FAMILY, 8), fg="#4B5563", bg="#F9FAFB").pack(anchor="w")
            self.param_bb_std = ttk.Entry(f2, font=(FONT_FAMILY, 8))
            self.param_bb_std.insert(0, "2.0")
            self.param_bb_std.pack(fill="x")

    def _build_results_panel(self, parent):
        # 1. Performance Telemetry Cards Grid (2 rows x 3 columns)
        sc_card = tk.Frame(parent, bg="#FFFFFF", highlightbackground="#E5E7EB", highlightthickness=1)
        sc_card.pack(fill="x", pady=(0, 10))

        ch = tk.Frame(sc_card, bg="#F9FAFB", padx=16, pady=8, highlightbackground="#E5E7EB", highlightthickness=1)
        ch.pack(fill="x")
        tk.Label(ch, text="QUANTITATIVE PERFORMANCE SCORECARD", font=(FONT_FAMILY, 9, "bold"), fg="#111827", bg="#F9FAFB").pack(side="left")

        grid = tk.Frame(sc_card, bg="#FFFFFF", padx=10, pady=10)
        grid.pack(fill="x")

        for c in range(3):
            grid.columnconfigure(c, weight=1, uniform="bt_cols")

        self.card_net_profit = self._create_result_box(grid, 0, 0, "NET PROFIT", "$0.00", "(0.00%)")
        self.card_win_rate = self._create_result_box(grid, 0, 1, "WIN RATE", "0.0%", "0 / 0 Trades")
        self.card_profit_factor = self._create_result_box(grid, 0, 2, "PROFIT FACTOR", "0.00", "Gross Win / Loss")

        self.card_drawdown = self._create_result_box(grid, 1, 0, "MAX DRAWDOWN", "$0.00", "(0.00%)")
        self.card_trades_count = self._create_result_box(grid, 1, 1, "TOTAL TRADES", "0", "0 Wins  |  0 Losses")
        self.card_avg_win_loss = self._create_result_box(grid, 1, 2, "AVG WIN / LOSS", "$0.00 / $0.00", "Expectancy: $0.00")

        # 2. Detailed Trade Execution Ledger Table
        tbl_card = tk.Frame(parent, bg="#FFFFFF", highlightbackground="#E5E7EB", highlightthickness=1)
        tbl_card.pack(fill="both", expand=True)

        tbl_hdr = tk.Frame(tbl_card, bg="#F9FAFB", padx=14, pady=8, highlightbackground="#E5E7EB", highlightthickness=1)
        tbl_hdr.pack(fill="x")
        tk.Label(tbl_hdr, text="TRADE EXECUTION LEDGER", font=(FONT_FAMILY, 9, "bold"), fg="#111827", bg="#F9FAFB").pack(side="left")
        self.lbl_trade_count = tk.Label(tbl_hdr, text="0 Trades Recorded", font=(FONT_FAMILY, 8), fg="#6B7280", bg="#F9FAFB")
        self.lbl_trade_count.pack(side="right")

        tbl_body = tk.Frame(tbl_card, bg="#FFFFFF", padx=8, pady=8)
        tbl_body.pack(fill="both", expand=True)

        cols = ("id", "type", "entry_time", "entry_price", "exit_time", "exit_price", "pips", "pnl", "reason")
        self.tree = ttk.Treeview(tbl_body, columns=cols, show="headings", height=12)

        self.tree.heading("id", text="#")
        self.tree.heading("type", text="Type")
        self.tree.heading("entry_time", text="Entry Time")
        self.tree.heading("entry_price", text="Entry Price")
        self.tree.heading("exit_time", text="Exit Time")
        self.tree.heading("exit_price", text="Exit Price")
        self.tree.heading("pips", text="Pips")
        self.tree.heading("pnl", text="Net P&L ($)")
        self.tree.heading("reason", text="Exit Reason")

        self.tree.column("id", width=40, anchor="center")
        self.tree.column("type", width=70, anchor="center")
        self.tree.column("entry_time", width=140, anchor="center")
        self.tree.column("entry_price", width=90, anchor="e")
        self.tree.column("exit_time", width=140, anchor="center")
        self.tree.column("exit_price", width=90, anchor="e")
        self.tree.column("pips", width=70, anchor="e")
        self.tree.column("pnl", width=90, anchor="e")
        self.tree.column("reason", width=110, anchor="w")

        scroll_y = ttk.Scrollbar(tbl_body, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll_y.set)

        self.tree.pack(side="left", fill="both", expand=True)
        scroll_y.pack(side="right", fill="y")

        # Color tags
        self.tree.tag_configure("WIN", foreground="#16A34A")
        self.tree.tag_configure("LOSS", foreground="#DC2626")

    def _create_result_box(self, parent, row, col, title, initial_val, sub_val):
        box = tk.Frame(parent, bg="#FFFFFF", highlightbackground="#E5E7EB", highlightthickness=1, padx=12, pady=8)
        box.grid(row=row, column=col, padx=4, pady=4, sticky="nsew")

        tk.Label(box, text=title, font=(FONT_FAMILY, 7, "bold"), fg="#6B7280", bg="#FFFFFF").pack(anchor="w")
        val_lbl = tk.Label(box, text=initial_val, font=(FONT_FAMILY, 12, "bold"), fg="#111827", bg="#FFFFFF")
        val_lbl.pack(anchor="w", pady=(2, 0))
        sub_lbl = tk.Label(box, text=sub_val, font=(FONT_FAMILY, 8), fg="#9CA3AF", bg="#FFFFFF")
        sub_lbl.pack(anchor="w")

        return {"main": val_lbl, "sub": sub_lbl}

    def _on_click_run(self):
        if self.is_running:
            return

        symbol = self.combo_symbol.get().strip().upper()
        tf_name = self.combo_tf.get()
        tf = TIMEFRAME_MAP.get(tf_name, mt5.TIMEFRAME_H1)
        year_sel = self.combo_year.get()

        try:
            year_int = int(year_sel) if year_sel != "Custom Range" else 2024
        except ValueError:
            year_int = 2024

        d_from = datetime(year_int, 1, 1, tzinfo=timezone.utc)
        d_to = datetime(year_int, 12, 31, 23, 59, 59, tzinfo=timezone.utc)

        # Risk parameters
        try:
            initial_capital = float(self.entry_capital.get())
            lot_size = float(self.entry_lot.get())
            sl_pips = float(self.entry_sl.get())
            tp_pips = float(self.entry_tp.get())
            spread_pips = float(self.entry_spread.get())
        except ValueError:
            messagebox.showerror("Invalid Input", "Please enter valid numeric values for capital, lot, SL, TP, and spread.")
            return

        strategy_name = self.combo_strategy.get()
        params = {}

        if strategy_name == "EMA Crossover":
            params["fast_ema"] = self.param_fast_ema.get()
            params["slow_ema"] = self.param_slow_ema.get()
        elif strategy_name == "RSI Mean Reversion":
            params["rsi_period"] = self.param_rsi_period.get()
            params["rsi_oversold"] = self.param_rsi_os.get()
            params["rsi_overbought"] = self.param_rsi_ob.get()
        elif strategy_name == "MACD Momentum":
            params["macd_fast"] = self.param_macd_fast.get()
            params["macd_slow"] = self.param_macd_slow.get()
            params["macd_signal"] = self.param_macd_signal.get()
        elif strategy_name == "Bollinger Breakout":
            params["bb_period"] = self.param_bb_period.get()
            params["bb_std"] = self.param_bb_std.get()

        self.is_running = True
        self.btn_run.config(text="SIMULATING REAL DATA...", state="disabled", bg="#D97706")
        self.log_callback(f"Starting Quantitative Backtest: {strategy_name} on {symbol} (Year: {year_sel}, TF: {tf_name})...", "INFO")

        threading.Thread(
            target=self._threaded_backtest,
            args=(symbol, tf, d_from, d_to, strategy_name, params, initial_capital, lot_size, sl_pips, tp_pips, spread_pips),
            daemon=True
        ).start()

    def _threaded_backtest(self, symbol, tf, d_from, d_to, strategy_name, params, capital, lot, sl, tp, spread):
        # 1. Fetch real historical data from MT5
        df, msg = self.connector.fetch_historical_data(symbol, tf, d_from, d_to)
        if df is None or len(df) == 0:
            self.after(0, self._handle_backtest_error, f"Failed to fetch historical data: {msg}")
            return

        # 2. Get symbol specifications (point, pip size, contract size)
        s_info = self.connector.get_symbol_info(symbol)

        # 3. Execute backtesting simulation
        bt = Backtester(
            data=df,
            strategy_name=strategy_name,
            params=params,
            initial_capital=capital,
            lot_size=lot,
            stop_loss_pips=sl,
            take_profit_pips=tp,
            spread_pips=spread,
            pip_size=s_info["pip_size"],
            contract_size=s_info["contract_size"]
        )
        results = bt.run()
        self.after(0, self._handle_backtest_success, results, symbol, strategy_name, len(df))

    def _handle_backtest_error(self, err_msg: str):
        self.is_running = False
        self.btn_run.config(text="RUN QUANTITATIVE BACKTEST", state="normal", bg="#2563EB")
        self.log_callback(err_msg, "ERROR")
        messagebox.showerror("Backtest Error", err_msg)

    def _handle_backtest_success(self, results: dict, symbol: str, strategy: str, total_bars: int):
        self.is_running = False
        self.btn_run.config(text="RUN QUANTITATIVE BACKTEST", state="normal", bg="#2563EB")

        if "error" in results:
            self.log_callback(results["error"], "ERROR")
            messagebox.showwarning("Backtest Notice", results["error"])
            return

        self.last_results = results
        self.btn_export.config(state="normal")

        # Extract metrics
        net_profit = results["net_profit"]
        roi_pct = results["roi_pct"]
        win_rate = results["win_rate"]
        profit_factor = results["profit_factor"]
        dd_dollar = results["max_drawdown_dollar"]
        dd_pct = results["max_drawdown_pct"]
        total_trades = results["total_trades"]
        wins = results["winning_trades"]
        losses = results["losing_trades"]
        avg_win = results["avg_win"]
        avg_loss = results["avg_loss"]

        # Update metric cards
        profit_color = "#16A34A" if net_profit >= 0 else "#DC2626"
        self.card_net_profit["main"].config(text=f"{'+' if net_profit > 0 else ''}${net_profit:,.2f}", fg=profit_color)
        self.card_net_profit["sub"].config(text=f"ROI: {'+' if roi_pct > 0 else ''}{roi_pct:.2f}%", fg=profit_color)

        self.card_win_rate["main"].config(text=f"{win_rate:.1f}%")
        self.card_win_rate["sub"].config(text=f"{wins} Wins / {total_trades} Trades")

        self.card_profit_factor["main"].config(text=f"{profit_factor:.2f}")
        self.card_profit_factor["sub"].config(text=f"Expectancy: ${(net_profit / total_trades if total_trades > 0 else 0):.2f}")

        self.card_drawdown["main"].config(text=f"${dd_dollar:,.2f}", fg="#DC2626")
        self.card_drawdown["sub"].config(text=f"-{dd_pct:.2f}% Max Peak")

        self.card_trades_count["main"].config(text=f"{total_trades:,}")
        self.card_trades_count["sub"].config(text=f"{wins} Won  |  {losses} Lost")

        self.card_avg_win_loss["main"].config(text=f"${avg_win:,.2f} / ${avg_loss:,.2f}")
        rr = (avg_win / avg_loss) if avg_loss > 0 else 0
        self.card_avg_win_loss["sub"].config(text=f"R:R Achieved: {rr:.2f}:1")

        # Populate Trade Ledger
        for row in self.tree.get_children():
            self.tree.delete(row)

        trades = results["trades"]
        for t in trades:
            tag = "WIN" if t["pnl"] > 0 else "LOSS"
            self.tree.insert(
                "",
                "end",
                values=(
                    t["id"],
                    t["type"],
                    t["entry_time"],
                    f"{t['entry_price']:.5f}",
                    t["exit_time"],
                    f"{t['exit_price']:.5f}",
                    f"{t['pips']:.1f}",
                    f"{'+' if t['pnl'] > 0 else ''}${t['pnl']:.2f}",
                    t["reason"]
                ),
                tags=(tag,)
            )

        self.lbl_trade_count.config(text=f"{len(trades)} Trades on {total_bars:,} Real MT5 Bars")
        self.log_callback(
            f"Backtest Finished: {strategy} | Net PnL: ${net_profit:,.2f} ({roi_pct:+.2f}%) | Win Rate: {win_rate:.1f}% | Trades: {total_trades}",
            "SUCCESS" if net_profit >= 0 else "WARNING"
        )

    def _on_click_export(self):
        if not self.last_results or not self.last_results.get("trades"):
            return

        df_trades = pd.DataFrame(self.last_results["trades"])
        symbol = self.combo_symbol.get()
        year = self.combo_year.get()
        strat = self.combo_strategy.get().replace(" ", "_")
        default_name = f"Backtest_{symbol}_{year}_{strat}_trades.csv"

        filepath = filedialog.asksaveasfilename(
            defaultextension=".csv",
            initialfile=default_name,
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")]
        )
        if filepath:
            df_trades.to_csv(filepath, index=False)
            self.log_callback(f"Backtest trade ledger exported to: {filepath}", "SUCCESS")
            messagebox.showinfo("Export Successful", f"Saved {len(df_trades):,} trades to:\n{filepath}")
