"""
Historical Market Data Downloader Tab.
Fetches real historical OHLCV data directly from MetaTrader 5 for any chosen year or date range.
"""

import sys
import threading
from datetime import datetime, timezone
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import pandas as pd
import MetaTrader5 as mt5

FONT_FAMILY = "Segoe UI" if sys.platform == "win32" else "Helvetica"

TIMEFRAME_MAP = {
    "M1 (1 Minute)": mt5.TIMEFRAME_M1,
    "M5 (5 Minutes)": mt5.TIMEFRAME_M5,
    "M15 (15 Minutes)": mt5.TIMEFRAME_M15,
    "M30 (30 Minutes)": mt5.TIMEFRAME_M30,
    "H1 (1 Hour)": mt5.TIMEFRAME_H1,
    "H4 (4 Hours)": mt5.TIMEFRAME_H4,
    "D1 (Daily)": mt5.TIMEFRAME_D1,
    "W1 (Weekly)": mt5.TIMEFRAME_W1,
}

YEAR_OPTIONS = ["2026", "2025", "2024", "2023", "2022", "2021", "2020", "2019", "2018", "Custom Range"]

PERIOD_OPTIONS = [
    "Last 1 Day",
    "Last 3 Days",
    "Last 1 Week",
    "Last 2 Weeks",
    "Last 1 Month",
    "Last 3 Months",
    "Last 6 Months",
    "Year 2025",
    "Year 2024",
    "Year 2023",
    "Custom Date Range"
]


class HistoricalDataTab(tk.Frame):
    """View for querying, displaying, and exporting real MT5 historical data."""

    def __init__(self, parent, connector, log_callback, app_ref, **kwargs):
        super().__init__(parent, bg="#F3F4F6", **kwargs)
        self.connector = connector
        self.log_callback = log_callback
        self.app_ref = app_ref
        self.current_data: pd.DataFrame = None
        self.is_fetching = False

        self._build_ui()

    def _build_ui(self):
        # Top Configuration Bar Card
        config_card = tk.Frame(self, bg="#FFFFFF", highlightbackground="#E5E7EB", highlightthickness=1, padx=16, pady=14)
        config_card.pack(fill="x", padx=16, pady=(16, 10))

        # Title
        tk.Label(
            config_card,
            text="REAL HISTORICAL DATA QUERY ENGINE",
            font=(FONT_FAMILY, 9, "bold"),
            fg="#111827",
            bg="#FFFFFF"
        ).pack(anchor="w", pady=(0, 10))

        controls_row = tk.Frame(config_card, bg="#FFFFFF")
        controls_row.pack(fill="x")

        # Symbol
        f_sym = tk.Frame(controls_row, bg="#FFFFFF")
        f_sym.pack(side="left", padx=(0, 12))
        tk.Label(f_sym, text="Symbol", font=(FONT_FAMILY, 8, "bold"), fg="#6B7280", bg="#FFFFFF").pack(anchor="w")
        self.combo_symbol = ttk.Combobox(f_sym, values=["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "USDCHF", "XAUUSD", "BTCUSD"], width=12, font=(FONT_FAMILY, 9))
        self.combo_symbol.set("EURUSD")
        self.combo_symbol.pack(pady=(2, 0))

        # Timeframe
        f_tf = tk.Frame(controls_row, bg="#FFFFFF")
        f_tf.pack(side="left", padx=(0, 12))
        tk.Label(f_tf, text="Timeframe", font=(FONT_FAMILY, 8, "bold"), fg="#6B7280", bg="#FFFFFF").pack(anchor="w")
        self.combo_tf = ttk.Combobox(f_tf, values=list(TIMEFRAME_MAP.keys()), width=16, font=(FONT_FAMILY, 9), state="readonly")
        self.combo_tf.set("H1 (1 Hour)")
        self.combo_tf.pack(pady=(2, 0))

        # Year Period
        f_yr = tk.Frame(controls_row, bg="#FFFFFF")
        f_yr.pack(side="left", padx=(0, 12))
        tk.Label(f_yr, text="Target Year", font=(FONT_FAMILY, 8, "bold"), fg="#6B7280", bg="#FFFFFF").pack(anchor="w")
        self.combo_year = ttk.Combobox(f_yr, values=YEAR_OPTIONS, width=14, font=(FONT_FAMILY, 9), state="readonly")
        self.combo_year.set("2024")
        self.combo_year.bind("<<ComboboxSelected>>", self._on_year_selected)
        self.combo_year.pack(pady=(2, 0))

        # Date Range inputs (for custom range)
        self.f_custom_date = tk.Frame(controls_row, bg="#FFFFFF")
        self.f_custom_date.pack(side="left", padx=(0, 12))
        
        tk.Label(self.f_custom_date, text="From (YYYY-MM-DD)", font=(FONT_FAMILY, 8, "bold"), fg="#6B7280", bg="#FFFFFF").pack(anchor="w")
        self.entry_date_from = ttk.Entry(self.f_custom_date, width=12, font=(FONT_FAMILY, 9))
        self.entry_date_from.insert(0, "2024-01-01")
        self.entry_date_from.pack(pady=(2, 0))

        self.f_custom_date_to = tk.Frame(controls_row, bg="#FFFFFF")
        self.f_custom_date_to.pack(side="left", padx=(0, 12))
        tk.Label(self.f_custom_date_to, text="To (YYYY-MM-DD)", font=(FONT_FAMILY, 8, "bold"), fg="#6B7280", bg="#FFFFFF").pack(anchor="w")
        self.entry_date_to = ttk.Entry(self.f_custom_date_to, width=12, font=(FONT_FAMILY, 9))
        self.entry_date_to.insert(0, "2024-12-31")
        self.entry_date_to.pack(pady=(2, 0))

        # Action Buttons
        f_btns = tk.Frame(controls_row, bg="#FFFFFF")
        f_btns.pack(side="right", pady=(14, 0))

        self.btn_fetch = tk.Button(
            f_btns,
            text="FETCH DATA",
            font=(FONT_FAMILY, 9, "bold"),
            bg="#2563EB",
            fg="#FFFFFF",
            activebackground="#1D4ED8",
            activeforeground="#FFFFFF",
            relief="flat",
            bd=0,
            cursor="hand2",
            padx=14,
            pady=6,
            command=self._on_click_fetch
        )
        self.btn_fetch.pack(side="left", padx=(0, 6))

        self.btn_export = tk.Button(
            f_btns,
            text="Export CSV",
            font=(FONT_FAMILY, 9),
            bg="#F3F4F6",
            fg="#111827",
            activebackground="#E5E7EB",
            relief="solid",
            bd=1,
            cursor="hand2",
            padx=10,
            pady=5,
            state="disabled",
            command=self._on_click_export
        )
        self.btn_export.pack(side="left")

        # Telemetry Summary Cards
        self._build_summary_cards()

        # Data Preview Table
        self._build_table_view()

    def _build_summary_cards(self):
        sc_frame = tk.Frame(self, bg="#F3F4F6")
        sc_frame.pack(fill="x", padx=16, pady=(0, 10))

        for c in range(5):
            sc_frame.columnconfigure(c, weight=1, uniform="sc_cols")

        self.card_bars = self._create_mini_card(sc_frame, 0, "TOTAL BARS", "0")
        self.card_range = self._create_mini_card(sc_frame, 1, "DATE RANGE", "--")
        self.card_high = self._create_mini_card(sc_frame, 2, "PERIOD HIGH", "0.00000")
        self.card_low = self._create_mini_card(sc_frame, 3, "PERIOD LOW", "0.00000")
        self.card_spread = self._create_mini_card(sc_frame, 4, "AVG SPREAD", "0.0 pts")

    def _create_mini_card(self, parent, col, title, initial_val):
        card = tk.Frame(parent, bg="#FFFFFF", highlightbackground="#E5E7EB", highlightthickness=1, padx=12, pady=8)
        card.grid(row=0, column=col, padx=4, sticky="nsew")

        tk.Label(card, text=title, font=(FONT_FAMILY, 7, "bold"), fg="#6B7280", bg="#FFFFFF").pack(anchor="w")
        val_lbl = tk.Label(card, text=initial_val, font=(FONT_FAMILY, 11, "bold"), fg="#111827", bg="#FFFFFF")
        val_lbl.pack(anchor="w", pady=(2, 0))
        return val_lbl

    def _build_table_view(self):
        container = tk.Frame(self, bg="#FFFFFF", highlightbackground="#E5E7EB", highlightthickness=1)
        container.pack(fill="both", expand=True, padx=16, pady=(0, 16))

        # Header
        ch = tk.Frame(container, bg="#F9FAFB", padx=14, pady=8, highlightbackground="#E5E7EB", highlightthickness=1)
        ch.pack(fill="x")

        tk.Label(ch, text="REAL MARKET RATES PREVIEW", font=(FONT_FAMILY, 9, "bold"), fg="#111827", bg="#F9FAFB").pack(side="left")
        self.lbl_table_count = tk.Label(ch, text="Showing 0 bars", font=(FONT_FAMILY, 8), fg="#6B7280", bg="#F9FAFB")
        self.lbl_table_count.pack(side="right")

        # Treeview
        tbl_frame = tk.Frame(container, bg="#FFFFFF")
        tbl_frame.pack(fill="both", expand=True, padx=8, pady=8)

        columns = ("time", "open", "high", "low", "close", "volume", "spread")
        self.tree = ttk.Treeview(tbl_frame, columns=columns, show="headings", height=15)

        self.tree.heading("time", text="Date & Time (UTC)")
        self.tree.heading("open", text="Open")
        self.tree.heading("high", text="High")
        self.tree.heading("low", text="Low")
        self.tree.heading("close", text="Close")
        self.tree.heading("volume", text="Tick Volume")
        self.tree.heading("spread", text="Spread (pts)")

        self.tree.column("time", width=160, anchor="center")
        self.tree.column("open", width=100, anchor="e")
        self.tree.column("high", width=100, anchor="e")
        self.tree.column("low", width=100, anchor="e")
        self.tree.column("close", width=100, anchor="e")
        self.tree.column("volume", width=110, anchor="e")
        self.tree.column("spread", width=90, anchor="center")

        scroll_y = ttk.Scrollbar(tbl_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll_y.set)

        self.tree.pack(side="left", fill="both", expand=True)
        scroll_y.pack(side="right", fill="y")

    def _on_year_selected(self, event=None):
        sel = self.combo_year.get()
        if sel != "Custom Range":
            year_int = int(sel)
            self.entry_date_from.delete(0, tk.END)
            self.entry_date_from.insert(0, f"{year_int}-01-01")
            self.entry_date_to.delete(0, tk.END)
            self.entry_date_to.insert(0, f"{year_int}-12-31")

    def _on_click_fetch(self):
        if self.is_fetching:
            return

        symbol = self.combo_symbol.get().strip().upper()
        tf_name = self.combo_tf.get()
        tf = TIMEFRAME_MAP.get(tf_name, mt5.TIMEFRAME_H1)

        date_from_str = self.entry_date_from.get().strip()
        date_to_str = self.entry_date_to.get().strip()

        try:
            d_from = datetime.strptime(date_from_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            d_to = datetime.strptime(date_to_str + " 23:59:59", "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        except ValueError:
            messagebox.showerror("Invalid Date", "Dates must be in YYYY-MM-DD format.")
            return

        if d_from >= d_to:
            messagebox.showerror("Invalid Range", "Start date must precede End date.")
            return

        self.is_fetching = True
        self.btn_fetch.config(text="FETCHING...", state="disabled", bg="#D97706")
        self.log_callback(f"Querying MT5 historical bars: {symbol} [{tf_name}] from {date_from_str} to {date_to_str}...", "INFO")

        threading.Thread(
            target=self._threaded_fetch,
            args=(symbol, tf, d_from, d_to),
            daemon=True
        ).start()

    def _threaded_fetch(self, symbol, tf, d_from, d_to):
        df, msg = self.connector.fetch_historical_data(symbol, tf, d_from, d_to)
        self.after(0, self._handle_fetch_result, df, msg)

    def _handle_fetch_result(self, df: pd.DataFrame, msg: str):
        self.is_fetching = False
        self.btn_fetch.config(text="FETCH DATA", state="normal", bg="#2563EB")

        if df is None or len(df) == 0:
            self.log_callback(msg, "ERROR")
            messagebox.showwarning("No Data", msg)
            return

        self.current_data = df
        self.btn_export.config(state="normal")
        self.log_callback(msg, "SUCCESS")

        # Update metrics
        total = len(df)
        high_val = df["high"].max()
        low_val = df["low"].min()
        avg_spread = df["spread"].mean()
        t_start = str(df["time"].iloc[0])[:10]
        t_end = str(df["time"].iloc[-1])[:10]

        self.card_bars.config(text=f"{total:,}")
        self.card_range.config(text=f"{t_start} → {t_end}")
        self.card_high.config(text=f"{high_val:.5f}")
        self.card_low.config(text=f"{low_val:.5f}")
        self.card_spread.config(text=f"{avg_spread:.1f} pts")

        # Populate treeview
        for row in self.tree.get_children():
            self.tree.delete(row)

        # Show preview rows (first 300 to ensure instantaneous UI response)
        preview_limit = min(300, total)
        for i in range(preview_limit):
            r = df.iloc[i]
            self.tree.insert(
                "",
                "end",
                values=(
                    str(r["time"]),
                    f"{r['open']:.5f}",
                    f"{r['high']:.5f}",
                    f"{r['low']:.5f}",
                    f"{r['close']:.5f}",
                    f"{int(r['tick_volume']):,}",
                    f"{int(r['spread'])}"
                )
            )

        self.lbl_table_count.config(text=f"Displaying first {preview_limit:,} of {total:,} bars")

    def _on_click_export(self):
        if self.current_data is None:
            return

        symbol = self.combo_symbol.get()
        year = self.combo_year.get()
        default_name = f"{symbol}_{year}_historical_data.csv"

        filepath = filedialog.asksaveasfilename(
            defaultextension=".csv",
            initialfile=default_name,
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")]
        )
        if filepath:
            self.current_data.to_csv(filepath, index=False)
            self.log_callback(f"Historical data exported successfully to: {filepath}", "SUCCESS")
            messagebox.showinfo("Export Successful", f"Saved {len(self.current_data):,} rows to:\n{filepath}")
