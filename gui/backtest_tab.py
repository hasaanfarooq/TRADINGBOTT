"""
Quantitative Backtesting View.
Executes rule-based algorithmic strategies on real MT5 historical data.
"""

import sys
import threading
from datetime import datetime, timezone, timedelta
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from typing import List, Dict, Any, Optional
import pandas as pd
import MetaTrader5 as mt5

from core.backtester import Backtester
from gui.data_tab import TIMEFRAME_MAP, YEAR_OPTIONS, PERIOD_OPTIONS

TF_MINUTES = {
    mt5.TIMEFRAME_M1: 1,
    mt5.TIMEFRAME_M5: 5,
    mt5.TIMEFRAME_M15: 15,
    mt5.TIMEFRAME_M30: 30,
    mt5.TIMEFRAME_H1: 60,
    mt5.TIMEFRAME_H4: 240,
    mt5.TIMEFRAME_D1: 1440,
    mt5.TIMEFRAME_W1: 10080
}

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
        self.current_trades: List[Dict[str, Any]] = []
        self.current_rejected: List[Dict[str, Any]] = []
        self.current_view_mode = "EXECUTED"

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

        # 1. Card Header (Pinned to Top)
        ch = tk.Frame(card, bg="#F9FAFB", padx=16, pady=10, highlightbackground="#E5E7EB", highlightthickness=1)
        ch.pack(side="top", fill="x")
        tk.Label(ch, text="BACKTEST SETUP & PARAMETERS", font=(FONT_FAMILY, 9, "bold"), fg="#111827", bg="#F9FAFB").pack(side="left")

        # 2. Pinned Action Buttons Footer (ALWAYS 100% VISIBLE AT BOTTOM)
        f_actions = tk.Frame(card, bg="#FFFFFF", padx=14, pady=10, highlightbackground="#E5E7EB", highlightthickness=1)
        f_actions.pack(side="bottom", fill="x")

        self.btn_run = tk.Button(
            f_actions,
            text="RUN QUANTITATIVE BACKTEST",
            font=(FONT_FAMILY, 10, "bold"),
            bg="#2563EB",
            fg="#FFFFFF",
            activebackground="#1D4ED8",
            activeforeground="#FFFFFF",
            relief="flat",
            bd=0,
            cursor="hand2",
            pady=9,
            command=self._on_click_run
        )
        self.btn_run.pack(fill="x", pady=(0, 4))

        self.btn_export = tk.Button(
            f_actions,
            text="Export Trade Ledger (CSV)",
            font=(FONT_FAMILY, 8),
            bg="#F3F4F6",
            fg="#111827",
            activebackground="#E5E7EB",
            relief="solid",
            bd=1,
            cursor="hand2",
            pady=5,
            state="disabled",
            command=self._on_click_export
        )
        self.btn_export.pack(fill="x")

        # 3. Middle Scrollable Parameters Body
        canvas_frame = tk.Frame(card, bg="#FFFFFF")
        canvas_frame.pack(side="top", fill="both", expand=True)

        canvas = tk.Canvas(canvas_frame, bg="#FFFFFF", highlightthickness=0)
        scrollbar = ttk.Scrollbar(canvas_frame, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)

        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        body = tk.Frame(canvas, bg="#FFFFFF", padx=14, pady=8)
        body_id = canvas.create_window((0, 0), window=body, anchor="nw")

        def _on_body_configure(event):
            canvas.configure(scrollregion=canvas.bbox("all"))

        def _on_canvas_configure(event):
            canvas.itemconfig(body_id, width=event.width)

        body.bind("<Configure>", _on_body_configure)
        canvas.bind("<Configure>", _on_canvas_configure)

        def _on_mousewheel(event):
            if canvas.winfo_exists() and canvas.winfo_ismapped():
                canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        canvas.bind("<Enter>", lambda e: canvas.bind_all("<MouseWheel>", _on_mousewheel))
        canvas.bind("<Leave>", lambda e: canvas.unbind_all("<MouseWheel>"))

        # Market Data Source
        tk.Label(body, text="MARKET SPECIFICATIONS", font=(FONT_FAMILY, 8, "bold"), fg="#2563EB", bg="#FFFFFF").pack(anchor="w", pady=(0, 4))
        
        row1 = tk.Frame(body, bg="#FFFFFF")
        row1.pack(fill="x", pady=(0, 6))

        f_sym = tk.Frame(row1, bg="#FFFFFF")
        f_sym.pack(side="left", fill="x", expand=True, padx=(0, 4))
        tk.Label(f_sym, text="Symbol", font=(FONT_FAMILY, 8), fg="#6B7280", bg="#FFFFFF").pack(anchor="w")
        self.combo_symbol = ttk.Combobox(f_sym, values=["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "USDCHF", "XAUUSD", "BTCUSD"], font=(FONT_FAMILY, 9))
        self.combo_symbol.set("EURUSD")
        self.combo_symbol.pack(fill="x", pady=(2, 0))

        f_tf = tk.Frame(row1, bg="#FFFFFF")
        f_tf.pack(side="right", fill="x", expand=True, padx=(4, 0))
        tk.Label(f_tf, text="Timeframe", font=(FONT_FAMILY, 8), fg="#6B7280", bg="#FFFFFF").pack(anchor="w")
        self.combo_tf = ttk.Combobox(f_tf, values=list(TIMEFRAME_MAP.keys()), font=(FONT_FAMILY, 9), state="readonly")
        self.combo_tf.set("M15 (15 Minutes)")
        self.combo_tf.bind("<<ComboboxSelected>>", self._on_timeframe_change)
        self.combo_tf.pack(fill="x", pady=(2, 0))

        # Historical Period Selection (Days, Weeks, Months, Years)
        tk.Label(body, text="HISTORICAL PERIOD (DAYS / WEEKS / MONTHS)", font=(FONT_FAMILY, 8, "bold"), fg="#2563EB", bg="#FFFFFF").pack(anchor="w", pady=(0, 4))
        self.combo_period = ttk.Combobox(body, values=PERIOD_OPTIONS, font=(FONT_FAMILY, 9), state="readonly")
        self.combo_period.set("Last 1 Week")
        self.combo_period.bind("<<ComboboxSelected>>", self._on_period_change)
        self.combo_period.pack(fill="x", pady=(0, 4))

        # Start and End Date Inputs (Auto-filled by period or editable for custom range)
        row_dates = tk.Frame(body, bg="#FFFFFF")
        row_dates.pack(fill="x", pady=(0, 8))

        f_dfrom = tk.Frame(row_dates, bg="#FFFFFF")
        f_dfrom.pack(side="left", fill="x", expand=True, padx=(0, 3))
        tk.Label(f_dfrom, text="Start Date", font=(FONT_FAMILY, 7), fg="#6B7280", bg="#FFFFFF").pack(anchor="w")
        self.entry_date_from = ttk.Entry(f_dfrom, font=(FONT_FAMILY, 8))
        self.entry_date_from.pack(fill="x", pady=(1, 0))

        f_dto = tk.Frame(row_dates, bg="#FFFFFF")
        f_dto.pack(side="right", fill="x", expand=True, padx=(3, 0))
        tk.Label(f_dto, text="End Date", font=(FONT_FAMILY, 7), fg="#6B7280", bg="#FFFFFF").pack(anchor="w")
        self.entry_date_to = ttk.Entry(f_dto, font=(FONT_FAMILY, 8))
        self.entry_date_to.pack(fill="x", pady=(1, 0))

        self._update_period_dates("Last 1 Week")

        # Strategy Selection
        tk.Label(body, text="ALGORITHMIC STRATEGY (RULE-BASED)", font=(FONT_FAMILY, 8, "bold"), fg="#2563EB", bg="#FFFFFF").pack(anchor="w", pady=(0, 4))
        self.combo_strategy = ttk.Combobox(
            body,
            values=[
                "Apex Institutional Matrix Elite (Adaptive Slope & Target)",
                "Apex Institutional Matrix (XAUUSD / EURUSD)",
                "Tick Momentum Scalper",
                "CRT Range + CISD/FVG (A++ Institutional)",
                "HTF Bias + Fib 0.77-0.78 OTE",
                "EMA Crossover",
                "RSI Mean Reversion",
                "MACD Momentum",
                "Bollinger Breakout"
            ],
            font=(FONT_FAMILY, 9),
            state="readonly"
        )
        self.combo_strategy.set("Apex Institutional Matrix Elite (Adaptive Slope & Target)")
        self.combo_strategy.bind("<<ComboboxSelected>>", self._on_strategy_change)
        self.combo_strategy.pack(fill="x", pady=(2, 8))

        # Dynamic Strategy Params Frame
        self.f_strat_params = tk.Frame(body, bg="#F9FAFB", highlightbackground="#E5E7EB", highlightthickness=1, padx=8, pady=6)
        self.f_strat_params.pack(fill="x", pady=(0, 8))
        self._render_strategy_params("Apex Institutional Matrix Elite (Adaptive Slope & Target)")

        # Capital Specification (The ONLY user-controlled parameter)
        tk.Label(body, text="CAPITAL ALLOCATION (USER INPUT)", font=(FONT_FAMILY, 8, "bold"), fg="#2563EB", bg="#FFFFFF").pack(anchor="w", pady=(0, 4))

        f_cap = tk.Frame(body, bg="#FFFFFF")
        f_cap.pack(fill="x", pady=(0, 3))
        tk.Label(f_cap, text="Initial Trading Capital ($)", font=(FONT_FAMILY, 8), fg="#6B7280", bg="#FFFFFF").pack(anchor="w")
        self.entry_capital = ttk.Entry(f_cap, font=(FONT_FAMILY, 10, "bold"))
        self.entry_capital.insert(0, "10000")
        self.entry_capital.pack(fill="x", pady=(2, 3))

        # Quick Capital Preset Buttons ($1k, $5k, $10k, $25k, $50k)
        f_pills = tk.Frame(body, bg="#FFFFFF")
        f_pills.pack(fill="x", pady=(0, 8))
        presets = ["1,000", "5,000", "10,000", "25,000", "50,000"]
        for p in presets:
            btn_p = tk.Button(
                f_pills,
                text=f"${p}",
                font=(FONT_FAMILY, 7, "bold"),
                bg="#F3F4F6",
                fg="#374151",
                activebackground="#E5E7EB",
                relief="flat",
                bd=0,
                padx=2,
                pady=2,
                cursor="hand2",
                command=lambda val=p.replace(",", ""): self._set_capital_preset(val)
            )
            btn_p.pack(side="left", expand=True, fill="x", padx=1)

        # Autonomous Reasoning Model Specifications Card
        f_ai_specs = tk.Frame(body, bg="#F8FAFC", highlightbackground="#E2E8F0", highlightthickness=1, padx=8, pady=6)
        f_ai_specs.pack(fill="x", pady=(0, 4))

        h_ai = tk.Frame(f_ai_specs, bg="#F8FAFC")
        h_ai.pack(fill="x", pady=(0, 3))
        tk.Label(h_ai, text="[ REASONING MODEL AUTONOMOUS SETUP ]", font=(FONT_FAMILY, 7, "bold"), fg="#059669", bg="#F8FAFC").pack(side="left")

        specs = [
            ("Risk Sizing:", "1.0% Equity Risk (Auto Lot Sizing)"),
            ("Stop Loss:", "Dynamic Structural Swing + ATR Cushion"),
            ("Take Profit:", "Strict 1:2 R:R Ratio Target (+2.0% Gain)"),
            ("Protection:", "Auto Break-Even Trailing at +1R Profit"),
            ("Broker Spread:", "Live Broker Auto-Detection (MT5 Specs)")
        ]
        for label, val in specs:
            row_s = tk.Frame(f_ai_specs, bg="#F8FAFC")
            row_s.pack(fill="x", pady=1)
            tk.Label(row_s, text=label, font=(FONT_FAMILY, 7, "bold"), fg="#475569", bg="#F8FAFC", width=12, anchor="w").pack(side="left")
            tk.Label(row_s, text=val, font=(FONT_FAMILY, 7), fg="#0F172A", bg="#F8FAFC", anchor="w").pack(side="left", fill="x", expand=True)

    def _get_valid_htf_options(self) -> List[str]:
        """Returns timeframes strictly higher than the currently selected execution timeframe."""
        exec_name = self.combo_tf.get() if hasattr(self, "combo_tf") else "M15 (15 Minutes)"
        exec_tf = TIMEFRAME_MAP.get(exec_name, mt5.TIMEFRAME_M15)
        exec_mins = TF_MINUTES.get(exec_tf, 15)
        options = [
            name for name, tf_val in TIMEFRAME_MAP.items()
            if TF_MINUTES.get(tf_val, 0) > exec_mins and TF_MINUTES.get(tf_val, 0) <= 1440
        ]
        if not options:
            options = ["D1 (Daily)"]
        return options

    def _on_timeframe_change(self, event=None):
        """Called when user changes execution timeframe in combo_tf."""
        exec_name = self.combo_tf.get()
        if hasattr(self, "lbl_exec_tf") and self.lbl_exec_tf.winfo_exists():
            self.lbl_exec_tf.config(text=f"Execution TF: {exec_name.split()[0]}")

        valid_options = self._get_valid_htf_options()

        for widget_name in ("param_apex_elite_htf", "param_apex_htf", "param_crt_htf", "param_fib_htf"):
            if hasattr(self, widget_name):
                w = getattr(self, widget_name)
                if w.winfo_exists():
                    curr = w.get()
                    w["values"] = valid_options
                    if curr not in valid_options:
                        if "H1 (1 Hour)" in valid_options:
                            w.set("H1 (1 Hour)")
                        elif "H4 (4 Hours)" in valid_options:
                            w.set("H4 (4 Hours)")
                        else:
                            w.set(valid_options[0])

    def _update_period_dates(self, period_sel: str):
        """Calculates and populates the start and end date entry fields based on chosen period."""
        now = datetime.now(timezone.utc)
        if period_sel == "Last 1 Day":
            d_from = now - timedelta(days=1)
            d_to = now
        elif period_sel == "Last 3 Days":
            d_from = now - timedelta(days=3)
            d_to = now
        elif period_sel == "Last 1 Week":
            d_from = now - timedelta(days=7)
            d_to = now
        elif period_sel == "Last 2 Weeks":
            d_from = now - timedelta(days=14)
            d_to = now
        elif period_sel == "Last 1 Month":
            d_from = now - timedelta(days=30)
            d_to = now
        elif period_sel == "Last 3 Months":
            d_from = now - timedelta(days=90)
            d_to = now
        elif period_sel == "Last 6 Months":
            d_from = now - timedelta(days=180)
            d_to = now
        elif period_sel.startswith("Year ") or (period_sel.isdigit() and len(period_sel) == 4):
            y_str = period_sel.replace("Year ", "").strip()
            y_int = int(y_str) if y_str.isdigit() else 2024
            d_from = datetime(y_int, 1, 1, tzinfo=timezone.utc)
            d_to = datetime(y_int, 12, 31, 23, 59, 59, tzinfo=timezone.utc)
        elif period_sel == "Custom Date Range":
            return
        else:
            d_from = now - timedelta(days=7)
            d_to = now

        if hasattr(self, "entry_date_from"):
            self.entry_date_from.delete(0, tk.END)
            self.entry_date_from.insert(0, d_from.strftime("%Y-%m-%d"))
        if hasattr(self, "entry_date_to"):
            self.entry_date_to.delete(0, tk.END)
            self.entry_date_to.insert(0, d_to.strftime("%Y-%m-%d"))

    def _on_period_change(self, event=None):
        period_sel = self.combo_period.get()
        self._update_period_dates(period_sel)

    def _on_strategy_change(self, event=None):
        self._render_strategy_params(self.combo_strategy.get())

    def _render_strategy_params(self, strategy: str):
        for child in self.f_strat_params.winfo_children():
            child.destroy()

        if strategy == "Apex Institutional Matrix Elite (Adaptive Slope & Target)":
            row_badge = tk.Frame(self.f_strat_params, bg="#F9FAFB")
            row_badge.pack(fill="x", pady=(0, 4))
            tk.Label(row_badge, text="Apex Matrix Elite (Evolved)", font=(FONT_FAMILY, 8, "bold"), fg="#16A34A", bg="#F9FAFB").pack(side="left")
            tk.Label(row_badge, text="Slope & Adaptive Target", font=(FONT_FAMILY, 8, "bold"), fg="#7C3AED", bg="#F9FAFB").pack(side="right")

            f_spec = tk.Frame(self.f_strat_params, bg="#F0FDF4", highlightbackground="#BBF7D0", highlightthickness=1, padx=6, pady=4)
            f_spec.pack(fill="x", pady=(0, 4))
            tk.Label(f_spec, text="• XAUUSD: D1 50 EMA Slope Velocity Filter (MaxDD 4.6%) | 1:2.2 RR Target", font=(FONT_FAMILY, 7, "bold"), fg="#15803D", bg="#F0FDF4", anchor="w").pack(fill="x")
            tk.Label(f_spec, text="• EURUSD: CRT Swing Liquidity Sweep + CISD + FVG | 1:2.0 RR Target", font=(FONT_FAMILY, 7, "bold"), fg="#047857", bg="#F0FDF4", anchor="w").pack(fill="x")

            valid_htf = self._get_valid_htf_options()
            default_htf = "H1 (1 Hour)" if "H1 (1 Hour)" in valid_htf else ("H4 (4 Hours)" if "H4 (4 Hours)" in valid_htf else valid_htf[0])

            row1 = tk.Frame(self.f_strat_params, bg="#F9FAFB")
            row1.pack(fill="x", pady=(0, 3))
            tk.Label(row1, text="Anchor Timeframe", font=(FONT_FAMILY, 8, "bold"), fg="#111827", bg="#F9FAFB").pack(side="left")
            self.param_apex_elite_htf = ttk.Combobox(row1, values=valid_htf, width=13, font=(FONT_FAMILY, 8), state="readonly")
            self.param_apex_elite_htf.set(default_htf)
            self.param_apex_elite_htf.pack(side="right")

            row2 = tk.Frame(self.f_strat_params, bg="#F9FAFB")
            row2.pack(fill="x", pady=(0, 2))
            exec_name = self.combo_tf.get().split()[0] if hasattr(self, "combo_tf") else "M15"
            self.lbl_exec_tf = tk.Label(row2, text=f"Execution: {exec_name}", font=(FONT_FAMILY, 8), fg="#4B5563", bg="#F9FAFB")
            self.lbl_exec_tf.pack(side="left")
            tk.Label(row2, text="Confluence: D1 + H4 + H1 + Slope", font=(FONT_FAMILY, 8, "bold"), fg="#059669", bg="#F9FAFB").pack(side="right")

            sep = tk.Frame(self.f_strat_params, bg="#E5E7EB", height=1)
            sep.pack(fill="x", pady=4)

            self.var_use_reasoning = tk.BooleanVar(value=True)
            chk_reasoning = tk.Checkbutton(
                self.f_strat_params,
                text="Enable A++ Reasoning Engine (Thinking Filter)",
                variable=self.var_use_reasoning,
                font=(FONT_FAMILY, 8, "bold"),
                fg="#1E40AF",
                bg="#F9FAFB",
                activebackground="#F9FAFB"
            )
            chk_reasoning.pack(anchor="w")

            row_score = tk.Frame(self.f_strat_params, bg="#F9FAFB")
            row_score.pack(fill="x", pady=(2, 0))
            tk.Label(row_score, text="Min Confluence Score:", font=(FONT_FAMILY, 8), fg="#4B5563", bg="#F9FAFB").pack(side="left")
            self.combo_min_score = ttk.Combobox(row_score, values=["50", "55", "60", "65", "70", "75"], width=6, font=(FONT_FAMILY, 8), state="readonly")
            self.combo_min_score.set("60")
            self.combo_min_score.pack(side="left", padx=(6, 0))
            tk.Label(row_score, text="/ 100 pts", font=(FONT_FAMILY, 8), fg="#6B7280", bg="#F9FAFB").pack(side="left")

        elif strategy == "Apex Institutional Matrix (XAUUSD / EURUSD)":
            row_badge = tk.Frame(self.f_strat_params, bg="#F9FAFB")
            row_badge.pack(fill="x", pady=(0, 4))
            tk.Label(row_badge, text="Apex Institutional Matrix", font=(FONT_FAMILY, 8, "bold"), fg="#2563EB", bg="#F9FAFB").pack(side="left")
            tk.Label(row_badge, text="Gold & Forex Microstructure", font=(FONT_FAMILY, 8, "bold"), fg="#7C3AED", bg="#F9FAFB").pack(side="right")

            f_spec = tk.Frame(self.f_strat_params, bg="#EEF2FF", highlightbackground="#C7D2FE", highlightthickness=1, padx=6, pady=4)
            f_spec.pack(fill="x", pady=(0, 4))
            tk.Label(f_spec, text="• XAUUSD: Asian Breakout & Retest Expansion | 1:2.0 RR Target", font=(FONT_FAMILY, 7, "bold"), fg="#1E40AF", bg="#EEF2FF", anchor="w").pack(fill="x")
            tk.Label(f_spec, text="• EURUSD: Anchor CRT Sweep + CISD + FVG | 1:1.4+ RR Target", font=(FONT_FAMILY, 7, "bold"), fg="#4338CA", bg="#EEF2FF", anchor="w").pack(fill="x")

            valid_htf = self._get_valid_htf_options()
            default_htf = "H1 (1 Hour)" if "H1 (1 Hour)" in valid_htf else ("H4 (4 Hours)" if "H4 (4 Hours)" in valid_htf else valid_htf[0])

            row1 = tk.Frame(self.f_strat_params, bg="#F9FAFB")
            row1.pack(fill="x", pady=(0, 3))
            tk.Label(row1, text="Anchor Timeframe", font=(FONT_FAMILY, 8, "bold"), fg="#111827", bg="#F9FAFB").pack(side="left")
            self.param_apex_htf = ttk.Combobox(row1, values=valid_htf, width=13, font=(FONT_FAMILY, 8), state="readonly")
            self.param_apex_htf.set(default_htf)
            self.param_apex_htf.pack(side="right")

            row2 = tk.Frame(self.f_strat_params, bg="#F9FAFB")
            row2.pack(fill="x", pady=(0, 2))
            exec_name = self.combo_tf.get().split()[0] if hasattr(self, "combo_tf") else "M15"
            self.lbl_exec_tf = tk.Label(row2, text=f"Execution: {exec_name}", font=(FONT_FAMILY, 8), fg="#4B5563", bg="#F9FAFB")
            self.lbl_exec_tf.pack(side="left")
            tk.Label(row2, text="Confluence: D1 + H4 + H1 (>2 TFs)", font=(FONT_FAMILY, 8, "bold"), fg="#059669", bg="#F9FAFB").pack(side="right")

            sep = tk.Frame(self.f_strat_params, bg="#E5E7EB", height=1)
            sep.pack(fill="x", pady=4)

            self.var_use_reasoning = tk.BooleanVar(value=True)
            chk_reasoning = tk.Checkbutton(
                self.f_strat_params,
                text="Enable A++ Reasoning Engine (Thinking Filter)",
                variable=self.var_use_reasoning,
                font=(FONT_FAMILY, 8, "bold"),
                fg="#1E40AF",
                bg="#F9FAFB",
                activebackground="#F9FAFB"
            )
            chk_reasoning.pack(anchor="w")

            row_score = tk.Frame(self.f_strat_params, bg="#F9FAFB")
            row_score.pack(fill="x", pady=(2, 0))
            tk.Label(row_score, text="Min Confluence Score:", font=(FONT_FAMILY, 8), fg="#4B5563", bg="#F9FAFB").pack(side="left")
            self.combo_min_score = ttk.Combobox(row_score, values=["50", "55", "60", "65", "70", "75"], width=6, font=(FONT_FAMILY, 8), state="readonly")
            self.combo_min_score.set("60")
            self.combo_min_score.pack(side="left", padx=(6, 0))
            tk.Label(row_score, text="/ 100 pts", font=(FONT_FAMILY, 8), fg="#6B7280", bg="#F9FAFB").pack(side="left")

        elif strategy == "Tick Momentum Scalper":
            row_badge = tk.Frame(self.f_strat_params, bg="#F9FAFB")
            row_badge.pack(fill="x", pady=(0, 4))
            tk.Label(row_badge, text="High-Frequency Tick Scalper", font=(FONT_FAMILY, 8, "bold"), fg="#2563EB", bg="#F9FAFB").pack(side="left")
            tk.Label(row_badge, text="Instant Green Scalp", font=(FONT_FAMILY, 8, "bold"), fg="#059669", bg="#F9FAFB").pack(side="right")

            row1 = tk.Frame(self.f_strat_params, bg="#F9FAFB")
            row1.pack(fill="x", pady=(0, 3))

            f_tp = tk.Frame(row1, bg="#F9FAFB")
            f_tp.pack(side="left", fill="x", expand=True, padx=(0, 2))
            tk.Label(f_tp, text="Profit Target", font=(FONT_FAMILY, 7, "bold"), fg="#16A34A", bg="#F9FAFB").pack(anchor="w")
            self.param_tms_tp = ttk.Combobox(f_tp, values=["Instant Green (>$0.00)", "$0.10", "$0.20", "$0.50", "$1.00", "$1.50"], font=(FONT_FAMILY, 8), state="readonly")
            self.param_tms_tp.set("Instant Green (>$0.00)")
            self.param_tms_tp.pack(fill="x", pady=(1, 0))

            f_sl = tk.Frame(row1, bg="#F9FAFB")
            f_sl.pack(side="right", fill="x", expand=True, padx=(2, 0))
            tk.Label(f_sl, text="Hard Stop Loss ($)", font=(FONT_FAMILY, 7, "bold"), fg="#DC2626", bg="#F9FAFB").pack(anchor="w")
            self.param_tms_sl = ttk.Combobox(f_sl, values=["$1.50", "$2.00", "$2.50", "$3.00", "$4.00"], font=(FONT_FAMILY, 8), state="readonly")
            self.param_tms_sl.set("$2.50")
            self.param_tms_sl.pack(fill="x", pady=(1, 0))

            row2 = tk.Frame(self.f_strat_params, bg="#F9FAFB")
            row2.pack(fill="x", pady=(3, 3))

            f_pos = tk.Frame(row2, bg="#F9FAFB")
            f_pos.pack(side="left", fill="x", expand=True, padx=(0, 2))
            tk.Label(f_pos, text="Max Trades (Positions)", font=(FONT_FAMILY, 7, "bold"), fg="#374151", bg="#F9FAFB").pack(anchor="w")
            self.param_tms_max_pos = ttk.Combobox(f_pos, values=["10", "20", "30", "40", "50"], font=(FONT_FAMILY, 8), state="readonly")
            self.param_tms_max_pos.set("30")
            self.param_tms_max_pos.pack(fill="x", pady=(1, 0))

            f_batch = tk.Frame(row2, bg="#F9FAFB")
            f_batch.pack(side="right", fill="x", expand=True, padx=(2, 0))
            tk.Label(f_batch, text="Burst Entry Batch", font=(FONT_FAMILY, 7, "bold"), fg="#2563EB", bg="#F9FAFB").pack(anchor="w")
            self.param_tms_batch = ttk.Combobox(f_batch, values=["1", "2", "3", "5"], font=(FONT_FAMILY, 8), state="readonly")
            self.param_tms_batch.set("3")
            self.param_tms_batch.pack(fill="x", pady=(1, 0))

            row3 = tk.Frame(self.f_strat_params, bg="#F9FAFB")
            row3.pack(fill="x", pady=(3, 2))
            tk.Label(row3, text="Stall Decay: 45s max hold", font=(FONT_FAMILY, 7, "bold"), fg="#D97706", bg="#F9FAFB").pack(side="left")
            tk.Label(row3, text="Basket Stop: -$25.00 limit", font=(FONT_FAMILY, 7, "bold"), fg="#991B1B", bg="#F9FAFB").pack(side="right")

            row4 = tk.Frame(self.f_strat_params, bg="#F9FAFB")
            row4.pack(fill="x", pady=(2, 0))
            tk.Label(row4, text="Filter: London/NY 07-17 UTC | 1M 50 EMA", font=(FONT_FAMILY, 7), fg="#4B5563", bg="#F9FAFB").pack(anchor="w")
            tk.Label(row4, text="Symbols: Liquid only (EURUSD, XAUUSD, US30, NAS100)", font=(FONT_FAMILY, 7), fg="#6B7280", bg="#F9FAFB").pack(anchor="w")

        if strategy == "CRT Range + CISD/FVG (A++ Institutional)":
            valid_htf = self._get_valid_htf_options()
            default_htf = "H1 (1 Hour)" if "H1 (1 Hour)" in valid_htf else ("H4 (4 Hours)" if "H4 (4 Hours)" in valid_htf else valid_htf[0])

            row1 = tk.Frame(self.f_strat_params, bg="#F9FAFB")
            row1.pack(fill="x", pady=(0, 4))
            tk.Label(row1, text="CRT Anchor Timeframe", font=(FONT_FAMILY, 8, "bold"), fg="#111827", bg="#F9FAFB").pack(side="left")
            self.param_crt_htf = ttk.Combobox(row1, values=valid_htf, width=13, font=(FONT_FAMILY, 8), state="readonly")
            self.param_crt_htf.set(default_htf)
            self.param_crt_htf.pack(side="right")

            row2 = tk.Frame(self.f_strat_params, bg="#F9FAFB")
            row2.pack(fill="x", pady=(0, 2))
            exec_name = self.combo_tf.get().split()[0] if hasattr(self, "combo_tf") else "M15"
            self.lbl_exec_tf = tk.Label(row2, text=f"Execution TF: {exec_name}", font=(FONT_FAMILY, 8), fg="#4B5563", bg="#F9FAFB")
            self.lbl_exec_tf.pack(side="left")
            tk.Label(row2, text="Model: CISD + FVG/IFVG", font=(FONT_FAMILY, 8, "bold"), fg="#2563EB", bg="#F9FAFB").pack(side="right")

            row3 = tk.Frame(self.f_strat_params, bg="#F9FAFB")
            row3.pack(fill="x", pady=(0, 2))
            tk.Label(row3, text="SL: Top/Bottom of CISD", font=(FONT_FAMILY, 8), fg="#DC2626", bg="#F9FAFB").pack(side="left")
            tk.Label(row3, text="TP: Target Other CRT Side", font=(FONT_FAMILY, 8, "bold"), fg="#16A34A", bg="#F9FAFB").pack(side="right")

            row4 = tk.Frame(self.f_strat_params, bg="#F9FAFB")
            row4.pack(fill="x", pady=(0, 4))
            tk.Label(row4, text="Narrative: Multi-TF (>2 TFs)", font=(FONT_FAMILY, 8, "bold"), fg="#059669", bg="#F9FAFB").pack(side="left")
            tk.Label(row4, text="Grade: A++ Setup Only", font=(FONT_FAMILY, 8, "bold"), fg="#7C3AED", bg="#F9FAFB").pack(side="right")

            sep = tk.Frame(self.f_strat_params, bg="#E5E7EB", height=1)
            sep.pack(fill="x", pady=4)

            self.var_use_reasoning = tk.BooleanVar(value=True)
            chk_reasoning = tk.Checkbutton(
                self.f_strat_params,
                text="Enable A++ Reasoning Engine (Thinking Filter)",
                variable=self.var_use_reasoning,
                font=(FONT_FAMILY, 8, "bold"),
                fg="#1E40AF",
                bg="#F9FAFB",
                activebackground="#F9FAFB"
            )
            chk_reasoning.pack(anchor="w")

            row_score = tk.Frame(self.f_strat_params, bg="#F9FAFB")
            row_score.pack(fill="x", pady=(2, 0))
            tk.Label(row_score, text="Min Confluence Score:", font=(FONT_FAMILY, 8), fg="#4B5563", bg="#F9FAFB").pack(side="left")
            self.combo_min_score = ttk.Combobox(row_score, values=["50", "55", "60", "65", "70", "75"], width=6, font=(FONT_FAMILY, 8), state="readonly")
            self.combo_min_score.set("65")
            self.combo_min_score.pack(side="left", padx=(6, 0))
            tk.Label(row_score, text="/ 100 pts", font=(FONT_FAMILY, 8), fg="#6B7280", bg="#F9FAFB").pack(side="left")

        elif strategy == "HTF Bias + Fib 0.77-0.78 OTE":
            valid_htf = self._get_valid_htf_options()
            default_htf = "H1 (1 Hour)" if "H1 (1 Hour)" in valid_htf else ("H4 (4 Hours)" if "H4 (4 Hours)" in valid_htf else valid_htf[0])

            row1 = tk.Frame(self.f_strat_params, bg="#F9FAFB")
            row1.pack(fill="x", pady=(0, 4))

            tk.Label(row1, text="Higher Timeframe Bias", font=(FONT_FAMILY, 8, "bold"), fg="#111827", bg="#F9FAFB").pack(side="left")
            self.param_fib_htf = ttk.Combobox(row1, values=valid_htf, width=13, font=(FONT_FAMILY, 8), state="readonly")
            self.param_fib_htf.set(default_htf)
            self.param_fib_htf.pack(side="right")

            row2 = tk.Frame(self.f_strat_params, bg="#F9FAFB")
            row2.pack(fill="x", pady=(0, 2))
            exec_name = self.combo_tf.get().split()[0] if hasattr(self, "combo_tf") else "M15"
            self.lbl_exec_tf = tk.Label(row2, text=f"Execution TF: {exec_name}", font=(FONT_FAMILY, 8), fg="#4B5563", bg="#F9FAFB")
            self.lbl_exec_tf.pack(side="left")
            tk.Label(row2, text="Zone: 0.77-0.78 Fib", font=(FONT_FAMILY, 8, "bold"), fg="#2563EB", bg="#F9FAFB").pack(side="right")

            row3 = tk.Frame(self.f_strat_params, bg="#F9FAFB")
            row3.pack(fill="x", pady=(0, 4))
            tk.Label(row3, text="SL: Structural Swing", font=(FONT_FAMILY, 8), fg="#DC2626", bg="#F9FAFB").pack(side="left")
            tk.Label(row3, text="TP: Goal 1:2 Risk/Reward", font=(FONT_FAMILY, 8, "bold"), fg="#16A34A", bg="#F9FAFB").pack(side="right")

            # Quantitative Reasoning & Thinking Controls
            sep = tk.Frame(self.f_strat_params, bg="#E5E7EB", height=1)
            sep.pack(fill="x", pady=4)

            self.var_use_reasoning = tk.BooleanVar(value=True)
            chk_reasoning = tk.Checkbutton(
                self.f_strat_params,
                text="Enable Quantitative Reasoning (Thinking Filter)",
                variable=self.var_use_reasoning,
                font=(FONT_FAMILY, 8, "bold"),
                fg="#1E40AF",
                bg="#F9FAFB",
                activebackground="#F9FAFB"
            )
            chk_reasoning.pack(anchor="w")

            row_score = tk.Frame(self.f_strat_params, bg="#F9FAFB")
            row_score.pack(fill="x", pady=(2, 0))
            tk.Label(row_score, text="Min Confluence Score:", font=(FONT_FAMILY, 8), fg="#4B5563", bg="#F9FAFB").pack(side="left")
            self.combo_min_score = ttk.Combobox(row_score, values=["50", "55", "60", "65", "70", "75"], width=6, font=(FONT_FAMILY, 8), state="readonly")
            self.combo_min_score.set("65")
            self.combo_min_score.pack(side="left", padx=(6, 0))
            tk.Label(row_score, text="/ 100 pts", font=(FONT_FAMILY, 8), fg="#6B7280", bg="#F9FAFB").pack(side="left")

        elif strategy == "EMA Crossover":
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

        # 2. Detailed Trade Execution Ledger Table Card
        tbl_card = tk.Frame(parent, bg="#FFFFFF", highlightbackground="#E5E7EB", highlightthickness=1)
        tbl_card.pack(fill="both", expand=True)

        tbl_hdr = tk.Frame(tbl_card, bg="#F9FAFB", padx=10, pady=6, highlightbackground="#E5E7EB", highlightthickness=1)
        tbl_hdr.pack(fill="x")

        f_hdr_left = tk.Frame(tbl_hdr, bg="#F9FAFB")
        f_hdr_left.pack(side="left")

        tk.Label(f_hdr_left, text="TRADE EXECUTION LEDGER", font=(FONT_FAMILY, 9, "bold"), fg="#111827", bg="#F9FAFB").pack(side="left", padx=(0, 10))

        self.btn_view_executed = tk.Button(
            f_hdr_left,
            text="✅ Executed Trades (0)",
            font=(FONT_FAMILY, 8, "bold"),
            bg="#2563EB",
            fg="#FFFFFF",
            relief="flat",
            padx=8,
            pady=2,
            cursor="hand2",
            command=lambda: self._switch_trade_view("EXECUTED")
        )
        self.btn_view_executed.pack(side="left", padx=2)

        self.btn_view_rejected = tk.Button(
            f_hdr_left,
            text="🧠 Filtered Setups (0)",
            font=(FONT_FAMILY, 8),
            bg="#F3F4F6",
            fg="#4B5563",
            relief="flat",
            padx=8,
            pady=2,
            cursor="hand2",
            command=lambda: self._switch_trade_view("REJECTED")
        )
        self.btn_view_rejected.pack(side="left", padx=2)

        self.lbl_trade_count = tk.Label(tbl_hdr, text="0 Trades Recorded", font=(FONT_FAMILY, 8), fg="#6B7280", bg="#F9FAFB")
        self.lbl_trade_count.pack(side="right")

        tbl_body = tk.Frame(tbl_card, bg="#FFFFFF", padx=6, pady=4)
        tbl_body.pack(fill="both", expand=True)

        cols = ("id", "type", "entry_time", "entry_price", "exit_time", "exit_price", "pips", "pnl", "score", "reason")
        self.tree = ttk.Treeview(tbl_body, columns=cols, show="headings", height=7)

        self.tree.heading("id", text="#")
        self.tree.heading("type", text="Type")
        self.tree.heading("entry_time", text="Entry / Time")
        self.tree.heading("entry_price", text="Price")
        self.tree.heading("exit_time", text="Exit / Status")
        self.tree.heading("exit_price", text="Exit Price")
        self.tree.heading("pips", text="Pips")
        self.tree.heading("pnl", text="Net P&L / EV")
        self.tree.heading("score", text="Score")
        self.tree.heading("reason", text="Thesis / Reason")

        self.tree.column("id", width=35, anchor="center")
        self.tree.column("type", width=60, anchor="center")
        self.tree.column("entry_time", width=130, anchor="center")
        self.tree.column("entry_price", width=80, anchor="e")
        self.tree.column("exit_time", width=120, anchor="center")
        self.tree.column("exit_price", width=80, anchor="e")
        self.tree.column("pips", width=60, anchor="e")
        self.tree.column("pnl", width=85, anchor="e")
        self.tree.column("score", width=55, anchor="center")
        self.tree.column("reason", width=150, anchor="w")

        scroll_y = ttk.Scrollbar(tbl_body, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll_y.set)

        self.tree.pack(side="left", fill="both", expand=True)
        scroll_y.pack(side="right", fill="y")

        # Color tags
        self.tree.tag_configure("WIN", foreground="#16A34A")
        self.tree.tag_configure("LOSS", foreground="#DC2626")
        self.tree.tag_configure("REJECTED", foreground="#D97706")
        self.tree.bind("<<TreeviewSelect>>", self._on_tree_select)

        # 3. Trade Thinking Process & Profitability Rationale Inspector
        self._build_thinking_inspector(tbl_card)

    def _create_result_box(self, parent, row, col, title, initial_val, sub_val):
        box = tk.Frame(parent, bg="#FFFFFF", highlightbackground="#E5E7EB", highlightthickness=1, padx=12, pady=8)
        box.grid(row=row, column=col, padx=4, pady=4, sticky="nsew")

        tk.Label(box, text=title, font=(FONT_FAMILY, 7, "bold"), fg="#6B7280", bg="#FFFFFF").pack(anchor="w")
        val_lbl = tk.Label(box, text=initial_val, font=(FONT_FAMILY, 12, "bold"), fg="#111827", bg="#FFFFFF")
        val_lbl.pack(anchor="w", pady=(2, 0))
        sub_lbl = tk.Label(box, text=sub_val, font=(FONT_FAMILY, 8), fg="#9CA3AF", bg="#FFFFFF")
        sub_lbl.pack(anchor="w")

        return {"main": val_lbl, "sub": sub_lbl}

    def _build_thinking_inspector(self, parent):
        self.f_inspector_card = tk.Frame(parent, bg="#F8FAFC", highlightbackground="#E2E8F0", highlightthickness=1, padx=10, pady=8)
        self.f_inspector_card.pack(fill="x", padx=6, pady=(0, 6))

        # 1. Header & Dynamic Badges
        hdr_row = tk.Frame(self.f_inspector_card, bg="#F8FAFC")
        hdr_row.pack(fill="x", pady=(0, 4))

        tk.Label(
            hdr_row,
            text="🧠 QUANTITATIVE REASONING & PROFITABILITY INSPECTOR",
            font=(FONT_FAMILY, 8, "bold"),
            fg="#1E293B",
            bg="#F8FAFC"
        ).pack(side="left")

        self.f_insp_badges = tk.Frame(hdr_row, bg="#F8FAFC")
        self.f_insp_badges.pack(side="right")

        self.lbl_insp_verdict = tk.Label(self.f_insp_badges, text="READY FOR AUDIT", font=(FONT_FAMILY, 7, "bold"), bg="#E2E8F0", fg="#475569", padx=6, pady=1)
        self.lbl_insp_verdict.pack(side="left", padx=2)

        self.lbl_insp_score = tk.Label(self.f_insp_badges, text="Score: -", font=(FONT_FAMILY, 7, "bold"), bg="#E2E8F0", fg="#475569", padx=6, pady=1)
        self.lbl_insp_score.pack(side="left", padx=2)

        self.lbl_insp_prob = tk.Label(self.f_insp_badges, text="Win Prob: -", font=(FONT_FAMILY, 7, "bold"), bg="#DBEAFE", fg="#1D4ED8", padx=6, pady=1)
        self.lbl_insp_prob.pack(side="left", padx=2)

        self.lbl_insp_ev = tk.Label(self.f_insp_badges, text="EV: -", font=(FONT_FAMILY, 7, "bold"), bg="#EDE9FE", fg="#6D28D9", padx=6, pady=1)
        self.lbl_insp_ev.pack(side="left", padx=2)

        # 2. Profitability Answer Banner
        self.f_profit_banner = tk.Frame(self.f_inspector_card, bg="#FFFFFF", highlightbackground="#CBD5E1", highlightthickness=1, padx=8, pady=4)
        self.f_profit_banner.pack(fill="x", pady=(0, 6))

        tk.Label(
            self.f_profit_banner,
            text="WILL THIS TRADE BE PROFITABLE?",
            font=(FONT_FAMILY, 7, "bold"),
            fg="#2563EB",
            bg="#FFFFFF"
        ).pack(side="left", padx=(0, 6))

        self.lbl_profit_answer = tk.Label(
            self.f_profit_banner,
            text="Select any executed trade or filtered setup above to view full quantitative reasoning.",
            font=(FONT_FAMILY, 8),
            fg="#334155",
            bg="#FFFFFF",
            anchor="w"
        )
        self.lbl_profit_answer.pack(side="left", fill="x", expand=True)

        # 3. Three-Column Detailed Audit Deck
        deck = tk.Frame(self.f_inspector_card, bg="#F8FAFC")
        deck.pack(fill="x")

        # Column 1: Why Execute?
        col1 = tk.Frame(deck, bg="#FFFFFF", highlightbackground="#CBD5E1", highlightthickness=1, padx=6, pady=4)
        col1.pack(side="left", fill="both", expand=True, padx=(0, 3))
        tk.Label(col1, text="💡 WHY EXECUTE? (CONFLUENCES & THESIS)", font=(FONT_FAMILY, 7, "bold"), fg="#16A34A", bg="#FFFFFF").pack(anchor="w")
        self.txt_why_execute = tk.Label(
            col1,
            text="• Multi-timeframe trend alignment\n• Liquidity sweep and rejection\n• Orderflow burst velocity",
            font=(FONT_FAMILY, 7),
            fg="#374151",
            bg="#FFFFFF",
            justify="left",
            anchor="nw"
        )
        self.txt_why_execute.pack(anchor="w", fill="both", expand=True, pady=(2, 0))

        # Column 2: Rejection / Risks Weighed
        col2 = tk.Frame(deck, bg="#FFFFFF", highlightbackground="#CBD5E1", highlightthickness=1, padx=6, pady=4)
        col2.pack(side="left", fill="both", expand=True, padx=3)
        self.lbl_col2_title = tk.Label(col2, text="⚠️ RISKS WEIGHED / REJECTION DIAGNOSIS", font=(FONT_FAMILY, 7, "bold"), fg="#DC2626", bg="#FFFFFF")
        self.lbl_col2_title.pack(anchor="w")
        self.txt_rejection = tk.Label(
            col2,
            text="• Spread-to-profit compression evaluated\n• 1M 50 EMA mean reversion buffer verified\n• Low volatility chop avoidance filter",
            font=(FONT_FAMILY, 7),
            fg="#374151",
            bg="#FFFFFF",
            justify="left",
            anchor="nw"
        )
        self.txt_rejection.pack(anchor="w", fill="both", expand=True, pady=(2, 0))

        # Column 3: Market Telemetry
        col3 = tk.Frame(deck, bg="#FFFFFF", highlightbackground="#CBD5E1", highlightthickness=1, padx=6, pady=4, width=190)
        col3.pack(side="right", fill="y", padx=(3, 0))
        tk.Label(col3, text="📊 MARKET TELEMETRY", font=(FONT_FAMILY, 7, "bold"), fg="#2563EB", bg="#FFFFFF").pack(anchor="w")
        self.txt_telemetry = tk.Label(
            col3,
            text="Velocity: - pips/s\nEMA Dist: - pips\nATR Vol: - x\nBroker Spread: - pips\nSession: -",
            font=(FONT_FAMILY, 7),
            fg="#475569",
            bg="#FFFFFF",
            justify="left",
            anchor="nw"
        )
        self.txt_telemetry.pack(anchor="w", fill="both", expand=True, pady=(2, 0))

    def _render_thinking_inspector(self, record: Dict[str, Any], is_rejected: bool = False):
        if not record:
            return

        thinking = record.get("thinking", {})
        score = thinking.get("total_score", record.get("score", 100))
        win_prob = thinking.get("win_probability", record.get("win_prob", 0.5))
        ev = thinking.get("expected_value_r", record.get("ev", 0.0))
        will_profit = thinking.get("will_be_profitable", record.get("will_be_profitable", "Evaluated by Reasoning Model"))
        why_exec = thinking.get("reasons_why_execute", record.get("reasons_why_execute", []))
        rejections = thinking.get("rejection_reasons", record.get("rejection_reasons", []))
        risks = thinking.get("risks_weighed", record.get("risks_weighed", []))
        telemetry = thinking.get("telemetry", record.get("telemetry", {}))
        verdict = thinking.get("verdict", "REJECTED" if is_rejected else "APPROVED")

        # Update Verdict Badge
        if verdict == "APPROVED" and not is_rejected:
            self.lbl_insp_verdict.config(text="[ APPROVED: A++ SETUP ]", bg="#DCFCE7", fg="#15803D")
            self.f_profit_banner.config(highlightbackground="#86EFAC")
        else:
            self.lbl_insp_verdict.config(text="[ REJECTED: DISQUALIFIED ]", bg="#FEE2E2", fg="#B91C1C")
            self.f_profit_banner.config(highlightbackground="#FCA5A5")

        self.lbl_insp_score.config(text=f"Score: {score}/100")
        prob_pct = (win_prob * 100) if win_prob <= 1.0 else win_prob
        self.lbl_insp_prob.config(text=f"ML Win Prob: {prob_pct:.1f}%")
        self.lbl_insp_ev.config(text=f"EV: {'+' if ev >= 0 else ''}{ev:.2f}")

        # Update Profitability Answer Banner
        self.lbl_profit_answer.config(text=will_profit)

        # Update Why Execute Column
        if why_exec:
            why_text = "\n".join([f"✓ {item}" for item in why_exec[:4]])
        else:
            thesis = record.get("thesis", "Approved Institutional Setup")
            why_text = f"✓ {thesis}"
        self.txt_why_execute.config(text=why_text)

        # Update Rejection / Risks Column
        if is_rejected or verdict == "REJECTED":
            self.lbl_col2_title.config(text="❌ WHY REJECTED? (DISQUALIFYING REASONS)", fg="#DC2626")
            if rejections:
                rej_text = "\n".join([f"✗ {item}" for item in rejections[:4]])
            else:
                rej_text = f"✗ Score {score}/100 below required confluence threshold."
            self.txt_rejection.config(text=rej_text)
        else:
            self.lbl_col2_title.config(text="⚠️ RISKS WEIGHED & MITIGATED", fg="#D97706")
            if risks:
                risk_text = "\n".join([f"• {item}" for item in risks[:4]])
            else:
                risk_text = "• Spread drag within tolerance\n• 50 EMA mean-reversion risk acceptable\n• Protected by structural invalidation level"
            self.txt_rejection.config(text=risk_text)

        # Update Telemetry Column
        vel = telemetry.get("velocity", "-")
        ema_d = telemetry.get("ema_dist_pips", "-")
        atr_r = telemetry.get("vol_ratio", telemetry.get("atr_pips", "-"))
        sprd = telemetry.get("spread_pips", "-")
        hr = telemetry.get("hour_utc", "-")
        self.txt_telemetry.config(
            text=f"Velocity: {vel} p/s\nEMA Dist: {ema_d} pips\nATR Vol: {atr_r}\nSpread: {sprd} pips\nSession: {hr}:00 UTC"
        )

    def _switch_trade_view(self, mode: str):
        self.current_view_mode = mode
        for row in self.tree.get_children():
            self.tree.delete(row)

        if mode == "EXECUTED":
            self.btn_view_executed.config(bg="#2563EB", fg="#FFFFFF")
            self.btn_view_rejected.config(bg="#F3F4F6", fg="#4B5563")

            for t in self.current_trades:
                tag = "WIN" if t["pnl"] > 0 else "LOSS"
                score_display = f"{t.get('score', 100)} pts"
                self.tree.insert(
                    "",
                    "end",
                    iid=f"trade_{t['id']}",
                    values=(
                        t["id"],
                        t["type"],
                        t["entry_time"],
                        f"{t['entry_price']:.5f}",
                        t["exit_time"],
                        f"{t['exit_price']:.5f}",
                        f"{t['pips']:.1f}",
                        f"{'+' if t['pnl'] > 0 else ''}${t['pnl']:.2f}",
                        score_display,
                        t["reason"]
                    ),
                    tags=(tag,)
                )
            if self.current_trades:
                first_iid = f"trade_{self.current_trades[0]['id']}"
                self.tree.selection_set(first_iid)
                self._render_thinking_inspector(self.current_trades[0], is_rejected=False)

        elif mode == "REJECTED":
            self.btn_view_executed.config(bg="#F3F4F6", fg="#4B5563")
            self.btn_view_rejected.config(bg="#DC2626", fg="#FFFFFF")

            for r in self.current_rejected:
                score_display = f"{r.get('score', 0)} pts"
                rejs = r.get("rejection_reasons", [r.get("thesis", "Disqualified")])
                reason_summary = rejs[0] if rejs else "Low Confluence Score"
                ev_val = r.get("ev", 0.0)
                prob_val = r.get("win_prob", 0.5) * 100
                self.tree.insert(
                    "",
                    "end",
                    iid=f"rej_{r['id']}",
                    values=(
                        r["id"],
                        r["type"],
                        r["time"],
                        f"{r['price']:.5f}",
                        "FILTERED",
                        "-",
                        "-",
                        f"{ev_val:+.2f} EV ({prob_val:.0f}%)",
                        score_display,
                        reason_summary[:40]
                    ),
                    tags=("REJECTED",)
                )
            if self.current_rejected:
                first_iid = f"rej_{self.current_rejected[0]['id']}"
                self.tree.selection_set(first_iid)
                self._render_thinking_inspector(self.current_rejected[0], is_rejected=True)

    def _on_tree_select(self, event=None):
        selected = self.tree.selection()
        if not selected:
            return
        item_id = selected[0]

        if item_id.startswith("trade_"):
            try:
                t_id = int(item_id.replace("trade_", ""))
                match = next((t for t in self.current_trades if t["id"] == t_id), None)
                if match:
                    self._render_thinking_inspector(match, is_rejected=False)
            except Exception:
                pass
        elif item_id.startswith("rej_"):
            try:
                r_id = int(item_id.replace("rej_", ""))
                match = next((r for r in self.current_rejected if r["id"] == r_id), None)
                if match:
                    self._render_thinking_inspector(match, is_rejected=True)
            except Exception:
                pass

    def _set_capital_preset(self, val: str):
        """Quick preset capital button handler."""
        self.entry_capital.delete(0, tk.END)
        self.entry_capital.insert(0, val)

    def _on_click_run(self):
        if self.is_running:
            return

        symbol = self.combo_symbol.get().strip().upper()
        tf_name = self.combo_tf.get()
        tf = TIMEFRAME_MAP.get(tf_name, mt5.TIMEFRAME_M15)
        period_name = self.combo_period.get() if hasattr(self, "combo_period") else "Last 1 Week"

        # Determine d_from and d_to
        try:
            d_from_str = self.entry_date_from.get().strip()
            d_to_str = self.entry_date_to.get().strip()
            d_from = datetime.strptime(d_from_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            d_to = datetime.strptime(d_to_str, "%Y-%m-%d").replace(hour=23, minute=59, second=59, tzinfo=timezone.utc)
            if d_from >= d_to:
                raise ValueError("Start date must be earlier than End date.")
        except Exception:
            now = datetime.now(timezone.utc)
            if period_name == "Last 1 Day":
                d_from = now - timedelta(days=1)
            elif period_name == "Last 3 Days":
                d_from = now - timedelta(days=3)
            elif period_name == "Last 1 Week":
                d_from = now - timedelta(days=7)
            elif period_name == "Last 2 Weeks":
                d_from = now - timedelta(days=14)
            elif period_name == "Last 1 Month":
                d_from = now - timedelta(days=30)
            elif period_name == "Last 3 Months":
                d_from = now - timedelta(days=90)
            elif period_name == "Last 6 Months":
                d_from = now - timedelta(days=180)
            else:
                d_from = datetime(2024, 1, 1, tzinfo=timezone.utc)
            d_to = now

        # Capital parameter (User specifies ONLY capital)
        try:
            cap_str = self.entry_capital.get().replace(",", "").replace("$", "").strip()
            initial_capital = float(cap_str)
            if initial_capital <= 0:
                raise ValueError
        except ValueError:
            messagebox.showerror("Invalid Capital", "Please enter a valid positive trading capital amount (e.g. 10000).")
            return

        # Execution parameters are set up autonomously by the Quantitative Reasoning Model
        lot_size = 0.0   # 0.0 triggers dynamic institutional risk sizing (1.0% equity risk per trade)
        sl_pips = 0.0    # 0.0 triggers dynamic structural swing SL + ATR shield
        tp_pips = 0.0    # 0.0 triggers strict 1:2 Risk/Reward target (+2.0% profit)

        # Auto-detect broker spread directly from MT5 terminal
        s_info = self.connector.get_symbol_info(symbol)
        spread_pips = float(s_info.get("spread_pips", 1.2)) if s_info and s_info.get("spread_pips", 0) > 0 else 1.2

        strategy_name = self.combo_strategy.get()
        params = {}

        htf_tf = None
        if strategy_name == "Apex Institutional Matrix Elite (Adaptive Slope & Target)":
            htf_choice = getattr(self, "param_apex_elite_htf", ttk.Combobox()).get() or "H1 (1 Hour)"
            htf_tf = TIMEFRAME_MAP.get(htf_choice, mt5.TIMEFRAME_H1)

            exec_mins = TF_MINUTES.get(tf, 15)
            anchor_mins = TF_MINUTES.get(htf_tf, 60)
            if anchor_mins <= exec_mins:
                valid_options = self._get_valid_htf_options()
                htf_choice = valid_options[0]
                htf_tf = TIMEFRAME_MAP.get(htf_choice, mt5.TIMEFRAME_H4)
                if hasattr(self, "param_apex_elite_htf"):
                    self.param_apex_elite_htf.set(htf_choice)
                self.log_callback(f"[Apex Elite] Anchor TF must be higher than Execution ({tf_name}). Auto-promoted Anchor to {htf_choice}.", "WARNING")

            params["symbol"] = symbol
            params["htf_name"] = htf_choice
            params["use_reasoning"] = getattr(self, "var_use_reasoning", tk.BooleanVar(value=True)).get()
            params["min_confluence_score"] = int(getattr(self, "combo_min_score", ttk.Combobox()).get() or "60")

        elif strategy_name == "Apex Institutional Matrix (XAUUSD / EURUSD)":
            htf_choice = getattr(self, "param_apex_htf", ttk.Combobox()).get() or "H1 (1 Hour)"
            htf_tf = TIMEFRAME_MAP.get(htf_choice, mt5.TIMEFRAME_H1)

            exec_mins = TF_MINUTES.get(tf, 15)
            anchor_mins = TF_MINUTES.get(htf_tf, 60)
            if anchor_mins <= exec_mins:
                valid_options = self._get_valid_htf_options()
                htf_choice = valid_options[0]
                htf_tf = TIMEFRAME_MAP.get(htf_choice, mt5.TIMEFRAME_H4)
                if hasattr(self, "param_apex_htf"):
                    self.param_apex_htf.set(htf_choice)
                self.log_callback(f"[Apex Matrix] Anchor TF must be higher than Execution ({tf_name}). Auto-promoted Anchor to {htf_choice}.", "WARNING")

            params["symbol"] = symbol
            params["htf_name"] = htf_choice
            params["use_reasoning"] = getattr(self, "var_use_reasoning", tk.BooleanVar(value=True)).get()
            params["min_confluence_score"] = int(getattr(self, "combo_min_score", ttk.Combobox()).get() or "60")

        elif strategy_name == "CRT Range + CISD/FVG (A++ Institutional)":
            htf_choice = getattr(self, "param_crt_htf", ttk.Combobox()).get() or "H1 (1 Hour)"
            htf_tf = TIMEFRAME_MAP.get(htf_choice, mt5.TIMEFRAME_H1)

            # Ensure Anchor Timeframe is strictly higher than Execution Timeframe
            exec_mins = TF_MINUTES.get(tf, 15)
            anchor_mins = TF_MINUTES.get(htf_tf, 60)
            if anchor_mins <= exec_mins:
                valid_options = self._get_valid_htf_options()
                htf_choice = valid_options[0]
                htf_tf = TIMEFRAME_MAP.get(htf_choice, mt5.TIMEFRAME_H4)
                if hasattr(self, "param_crt_htf"):
                    self.param_crt_htf.set(htf_choice)
                self.log_callback(f"[CRT Setup] Anchor TF must be higher than Execution ({tf_name}). Auto-promoted Anchor to {htf_choice}.", "WARNING")

            params["htf_name"] = htf_choice
            params["buffer_pips"] = 2.0
            params["use_reasoning"] = getattr(self, "var_use_reasoning", tk.BooleanVar(value=True)).get()
            params["min_confluence_score"] = int(getattr(self, "combo_min_score", ttk.Combobox()).get() or "65")

        elif strategy_name == "HTF Bias + Fib 0.77-0.78 OTE":
            htf_choice = self.param_fib_htf.get()
            htf_tf = TIMEFRAME_MAP.get(htf_choice, mt5.TIMEFRAME_H1)

            exec_mins = TF_MINUTES.get(tf, 15)
            anchor_mins = TF_MINUTES.get(htf_tf, 60)
            if anchor_mins <= exec_mins:
                valid_options = self._get_valid_htf_options()
                htf_choice = valid_options[0]
                htf_tf = TIMEFRAME_MAP.get(htf_choice, mt5.TIMEFRAME_H4)
                if hasattr(self, "param_fib_htf"):
                    self.param_fib_htf.set(htf_choice)
                self.log_callback(f"[Fib Setup] HTF Bias must be higher than Execution ({tf_name}). Auto-promoted HTF to {htf_choice}.", "WARNING")

            params["htf_name"] = htf_choice
            params["swing_len_htf"] = 3
            params["swing_len_m15"] = 3
            params["buffer_pips"] = 2.0
            params["use_reasoning"] = getattr(self, "var_use_reasoning", tk.BooleanVar(value=True)).get()
            params["min_confluence_score"] = int(getattr(self, "combo_min_score", ttk.Combobox()).get() or "65")
        elif strategy_name == "EMA Crossover":
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
        elif strategy_name == "Tick Momentum Scalper":
            tp_text = self.param_tms_tp.get() if hasattr(self, "param_tms_tp") else "Instant Green"
            if "Instant" in tp_text or "<=" in tp_text:
                params["target_profit_usd"] = 0.01
            else:
                try:
                    params["target_profit_usd"] = float(tp_text.replace("$", ""))
                except Exception:
                    params["target_profit_usd"] = 0.01

            try:
                params["stop_loss_usd"] = float(self.param_tms_sl.get().replace("$", ""))
            except Exception:
                params["stop_loss_usd"] = 2.50

            try:
                params["max_positions"] = int(self.param_tms_max_pos.get())
            except Exception:
                params["max_positions"] = 30

            try:
                params["batch_size"] = int(self.param_tms_batch.get())
            except Exception:
                params["batch_size"] = 3

            params["max_hold_seconds"] = 45.0
            params["cooldown_ms"] = 100
            params["burst_ticks"] = 10
            params["burst_agreement"] = 0.70
            params["min_burst_pips"] = 0.6
            params["max_spread_pips"] = 1.5
            params["basket_stop_usd"] = 25.0
            params["basket_pause_sec"] = 300
            params["max_consec_losses"] = 5
            params["daily_loss_cap"] = 100.0

        self.is_running = True
        self.btn_run.config(text="SIMULATING REAL DATA...", state="disabled", bg="#D97706")
        self.log_callback(f"Starting Quantitative Backtest: {strategy_name} on {symbol} ({period_name}: {d_from.strftime('%Y-%m-%d')} to {d_to.strftime('%Y-%m-%d')})...", "INFO")

        threading.Thread(
            target=self._threaded_backtest,
            args=(symbol, tf, d_from, d_to, strategy_name, params, initial_capital, lot_size, sl_pips, tp_pips, spread_pips, htf_tf),
            daemon=True
        ).start()

    def _threaded_backtest(self, symbol, tf, d_from, d_to, strategy_name, params, capital, lot, sl, tp, spread, htf_tf=None):
        # 1. Fetch real historical data from MT5
        if strategy_name == "Tick Momentum Scalper":
            self.log_callback(f"Tick Scalper: Fetching real millisecond broker ticks for {symbol}...", "INFO")
            df_ticks, tick_msg = self.connector.fetch_ticks_range(symbol, d_from, d_to)
            df_m1, _ = self.connector.fetch_historical_data(symbol, mt5.TIMEFRAME_M1, d_from, d_to)
            params["df_m1"] = df_m1

            if df_ticks is not None and len(df_ticks) > 50:
                self.log_callback(f"Ingested {len(df_ticks):,} real broker ticks.", "SUCCESS")
                params["df_ticks"] = df_ticks
                df = df_ticks
            elif df_m1 is not None and len(df_m1) > 0:
                self.log_callback("Broker tick stream limited; utilizing 1M micro-tick emulation.", "WARNING")
                df = df_m1
            else:
                self.after(0, self._handle_backtest_error, f"Failed to fetch tick or 1M data for {symbol}: {tick_msg}")
                return
        else:
            df, msg = self.connector.fetch_historical_data(symbol, tf, d_from, d_to)
            if df is None or len(df) == 0:
                self.after(0, self._handle_backtest_error, f"Failed to fetch historical data: {msg}")
                return

        # If multi-timeframe strategy or reasoning engine enabled, fetch HTF data
        if htf_tf is not None:
            df_htf, _ = self.connector.fetch_historical_data(symbol, htf_tf, d_from, d_to)
            if df_htf is not None and len(df_htf) > 0:
                params["df_htf"] = df_htf

        # Pre-fetch H1, H4, and D1 for Quantitative Reasoning Engine and Multi-Timeframe Narrative
        if params.get("use_reasoning", False) or "Apex" in strategy_name or strategy_name.startswith("CRT"):
            self.log_callback("Multi-Timeframe Narrative: Ingesting D1, 4H, and 1H market structure...", "INFO")
            df_h1, _ = self.connector.fetch_historical_data(symbol, mt5.TIMEFRAME_H1, d_from, d_to)
            df_h4, _ = self.connector.fetch_historical_data(symbol, mt5.TIMEFRAME_H4, d_from, d_to)
            df_d1, _ = self.connector.fetch_historical_data(symbol, mt5.TIMEFRAME_D1, d_from, d_to)
            params["df_h1"] = df_h1
            params["df_h4"] = df_h4
            params["df_d1"] = df_d1

        # 2. Get symbol specifications (point, pip size, contract size)
        s_info = self.connector.get_symbol_info(symbol)
        params["pip_size"] = s_info["pip_size"]
        params["symbol"] = symbol

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
        filtered_count = results.get("filtered_count", 0)
        self.card_trades_count["sub"].config(text=f"{wins} Won | {losses} Lost | {filtered_count} Filtered")

        self.card_avg_win_loss["main"].config(text=f"${avg_win:,.2f} / ${avg_loss:,.2f}")
        rr = (avg_win / avg_loss) if avg_loss > 0 else 0
        self.card_avg_win_loss["sub"].config(text=f"R:R Achieved: {rr:.2f}:1")

        # Store results and populate view switcher
        self.current_trades = results.get("trades", [])
        self.current_rejected = results.get("rejected_trades", [])

        # Update button counts
        self.btn_view_executed.config(text=f"✅ Executed Trades ({len(self.current_trades)})")
        self.btn_view_rejected.config(text=f"🧠 Filtered Setups ({len(self.current_rejected)})")

        # Render Executed Trades by default
        self._switch_trade_view("EXECUTED")

        unit_name = "Ticks" if strategy == "Tick Momentum Scalper" else "Bars"
        self.lbl_trade_count.config(text=f"{len(self.current_trades)} Trades ({filtered_count} Filtered) on {total_bars:,} {unit_name}")
        self.log_callback(
            f"Backtest Finished: {strategy} | Net PnL: ${net_profit:,.2f} ({roi_pct:+.2f}%) | Win Rate: {win_rate:.1f}% | Approved: {total_trades} | Filtered Out: {filtered_count}",
            "SUCCESS" if net_profit >= 0 else "WARNING"
        )

    def _on_click_export(self):
        if not self.last_results or not self.last_results.get("trades"):
            return

        df_trades = pd.DataFrame(self.last_results["trades"])
        symbol = self.combo_symbol.get()
        period_str = self.combo_period.get().replace(" ", "_") if hasattr(self, "combo_period") else "backtest"
        strat = self.combo_strategy.get().replace(" ", "_")
        default_name = f"Backtest_{symbol}_{period_str}_{strat}_trades.csv"

        filepath = filedialog.asksaveasfilename(
            defaultextension=".csv",
            initialfile=default_name,
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")]
        )
        if filepath:
            df_trades.to_csv(filepath, index=False)
            self.log_callback(f"Backtest trade ledger exported to: {filepath}", "SUCCESS")
            messagebox.showinfo("Export Successful", f"Saved {len(df_trades):,} trades to:\n{filepath}")
