"""
Professional Light-Themed Tkinter GUI for MT5 Quantitative Trading Station.
Provides connection management, live account telemetry, and execution logs.
"""

import os
import sys
import time
import threading
from datetime import datetime
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

from config import Config
from core.mt5_connection import MT5Connector
from gui.data_tab import HistoricalDataTab
from gui.backtest_tab import BacktestingTab


# -------------------------------------------------------------
# Color Palette - Professional Institutional Light Theme
# -------------------------------------------------------------
C_BG_APP = "#F3F4F6"         # Cool light gray background
C_CARD_BG = "#FFFFFF"        # Crisp white card surface
C_CARD_BORDER = "#E5E7EB"    # Subtle 1px structural borders
C_CARD_HEADER = "#F9FAFB"    # Muted header background

C_TEXT_MAIN = "#111827"      # High-contrast slate charcoal
C_TEXT_MUTED = "#6B7280"     # Secondary labels and subtitles
C_TEXT_SUBTLE = "#9CA3AF"    # Tertiary information

C_BLUE_PRIMARY = "#2563EB"   # Action blue
C_BLUE_HOVER = "#1D4ED8"
C_BLUE_BG = "#EFF6FF"

C_GREEN_SUCCESS = "#16A34A"  # Success green
C_GREEN_BG = "#DCFCE7"
C_GREEN_BORDER = "#86EFAC"

C_RED_DANGER = "#DC2626"     # Error/danger red
C_RED_BG = "#FEE2E2"
C_RED_BORDER = "#FCA5A5"

C_AMBER_WARN = "#D97706"     # Warning amber
C_AMBER_BG = "#FEF3C7"
C_AMBER_BORDER = "#FDE68A"

FONT_FAMILY = "Segoe UI" if sys.platform == "win32" else "Helvetica"


class MetricCard(tk.Frame):
    """Clean institutional metric display card."""

    def __init__(self, parent, title: str, default_value: str = "--", unit: str = "", **kwargs):
        super().__init__(parent, bg=C_CARD_BG, highlightbackground=C_CARD_BORDER, highlightthickness=1, padx=14, pady=10, **kwargs)
        
        self.lbl_title = tk.Label(
            self,
            text=title.upper(),
            font=(FONT_FAMILY, 8, "bold"),
            fg=C_TEXT_MUTED,
            bg=C_CARD_BG
        )
        self.lbl_title.pack(anchor="w")

        val_frame = tk.Frame(self, bg=C_CARD_BG)
        val_frame.pack(anchor="w", fill="x", pady=(4, 0))

        self.lbl_val = tk.Label(
            val_frame,
            text=default_value,
            font=(FONT_FAMILY, 15, "bold"),
            fg=C_TEXT_MAIN,
            bg=C_CARD_BG
        )
        self.lbl_val.pack(side="left")

        self.lbl_unit = tk.Label(
            val_frame,
            text=f" {unit}",
            font=(FONT_FAMILY, 9),
            fg=C_TEXT_MUTED,
            bg=C_CARD_BG
        )
        if unit:
            self.lbl_unit.pack(side="left", padx=(2, 0), pady=(3, 0))

    def update_value(self, val: str, color: str = C_TEXT_MAIN):
        self.lbl_val.config(text=val, fg=color)

    def update_unit(self, unit: str):
        self.lbl_unit.config(text=f" {unit}")


class MT5TradingStationGUI:
    """Main Application GUI."""

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("MT5 Algorithmic Trading Station")
        self.root.geometry("1200x820")
        self.root.minsize(1020, 680)
        self.root.configure(bg=C_BG_APP)

        # Connection manager
        self.connector = MT5Connector()
        self.is_connecting = False
        self.poll_running = False

        # Build UI layout
        self._setup_styles()
        self._create_header()
        self._create_main_content()
        self._create_status_bar()

        # Load default credentials
        self._load_config_fields()

        # Initial log entry
        self.log_message("Station initialized. Ready for MT5 terminal connection.", "INFO")

        # Handle window close cleanly
        self.root.protocol("WM_DELETE_WINDOW", self._on_closing)

    def _setup_styles(self):
        style = ttk.Style(self.root)
        style.theme_use("clam")

        style.configure(
            "TEntry",
            fieldbackground="#FFFFFF",
            foreground=C_TEXT_MAIN,
            bordercolor=C_CARD_BORDER,
            lightcolor=C_CARD_BORDER,
            darkcolor=C_CARD_BORDER,
            padding=6,
            font=(FONT_FAMILY, 9)
        )

        style.configure(
            "TCombobox",
            fieldbackground="#FFFFFF",
            background="#FFFFFF",
            foreground=C_TEXT_MAIN,
            bordercolor=C_CARD_BORDER,
            padding=5,
            font=(FONT_FAMILY, 9)
        )

        style.configure(
            "TNotebook",
            background=C_BG_APP,
            borderwidth=0
        )
        style.configure(
            "TNotebook.Tab",
            background="#E5E7EB",
            foreground="#4B5563",
            padding=[16, 8],
            font=(FONT_FAMILY, 9, "bold")
        )
        style.map(
            "TNotebook.Tab",
            background=[("selected", "#FFFFFF")],
            foreground=[("selected", C_BLUE_PRIMARY)]
        )

    def _create_header(self):
        """Top bar displaying title, connection status badge, latency, and system time."""
        header = tk.Frame(self.root, bg=C_CARD_BG, highlightbackground=C_CARD_BORDER, highlightthickness=1, height=64)
        header.pack(fill="x", side="top", padx=16, pady=(16, 8))
        header.pack_propagate(False)

        # Left: App Brand & Subtitle
        left_box = tk.Frame(header, bg=C_CARD_BG)
        left_box.pack(side="left", fill="y", padx=16)

        title_lbl = tk.Label(
            left_box,
            text="MT5 ALGO TRADING WORKSTATION",
            font=(FONT_FAMILY, 13, "bold"),
            fg=C_TEXT_MAIN,
            bg=C_CARD_BG
        )
        title_lbl.pack(anchor="w", pady=(8, 0))

        subtitle_lbl = tk.Label(
            left_box,
            text="Core Quantitative Terminal Connector & Telemetry",
            font=(FONT_FAMILY, 8),
            fg=C_TEXT_MUTED,
            bg=C_CARD_BG
        )
        subtitle_lbl.pack(anchor="w")

        # Right: Status Badges
        right_box = tk.Frame(header, bg=C_CARD_BG)
        right_box.pack(side="right", fill="y", padx=16)

        # Latency badge
        self.lbl_ping = tk.Label(
            right_box,
            text="⏱ -- ms",
            font=(FONT_FAMILY, 9, "bold"),
            fg=C_TEXT_MUTED,
            bg=C_BG_APP,
            padx=10,
            pady=4,
            relief="solid",
            bd=1
        )
        self.lbl_ping.config(highlightbackground=C_CARD_BORDER, highlightthickness=1)
        self.lbl_ping.pack(side="left", padx=8, pady=16)

        # Connection status pill
        self.status_badge = tk.Label(
            right_box,
            text="● DISCONNECTED",
            font=(FONT_FAMILY, 9, "bold"),
            fg=C_RED_DANGER,
            bg=C_RED_BG,
            padx=14,
            pady=5,
            relief="solid",
            bd=1
        )
        self.status_badge.config(highlightbackground=C_RED_BORDER, highlightthickness=1)
        self.status_badge.pack(side="left", pady=16)

    def _create_main_content(self):
        """Create tabbed interface: 1) Terminal & Telemetry, 2) Data Fetcher, 3) Backtester."""
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True, padx=16, pady=4)

        # Tab 1: Live Terminal & Telemetry
        self.tab_live = tk.Frame(self.notebook, bg=C_BG_APP)
        self.notebook.add(self.tab_live, text="  📊 Live Terminal & Telemetry  ")

        # Tab 2: Real Historical Data Fetcher
        self.tab_data = HistoricalDataTab(self.notebook, self.connector, self.log_message, self)
        self.notebook.add(self.tab_data, text="  📥 Historical Data Fetcher  ")

        # Tab 3: Quantitative Backtester
        self.tab_backtest = BacktestingTab(self.notebook, self.connector, self.log_message, self)
        self.notebook.add(self.tab_backtest, text="  🧪 Quantitative Backtester  ")

        # Split Live Tab into Left (Config/Controls) and Right (Metrics & Logs)
        left_col = tk.Frame(self.tab_live, bg=C_BG_APP, width=380)
        left_col.pack(side="left", fill="y", padx=(0, 8), pady=8)
        left_col.pack_propagate(False)

        right_col = tk.Frame(self.tab_live, bg=C_BG_APP)
        right_col.pack(side="right", fill="both", expand=True, padx=(8, 0), pady=8)

        self._build_connection_card(left_col)
        self._build_account_metrics_card(right_col)
        self._build_logs_card(right_col)

    def _build_connection_card(self, parent):
        """Configuration panel for Login, Password, Server, Path and Buttons."""
        card = tk.Frame(parent, bg=C_CARD_BG, highlightbackground=C_CARD_BORDER, highlightthickness=1)
        card.pack(fill="both", expand=True)

        # Card Title Header
        ch = tk.Frame(card, bg=C_CARD_HEADER, padx=16, pady=10, highlightbackground=C_CARD_BORDER, highlightthickness=1)
        ch.pack(fill="x")
        tk.Label(ch, text="CONNECTION & AUTHENTICATION", font=(FONT_FAMILY, 9, "bold"), fg=C_TEXT_MAIN, bg=C_CARD_HEADER).pack(side="left")

        body = tk.Frame(card, bg=C_CARD_BG, padx=18, pady=14)
        body.pack(fill="both", expand=True)

        # Account / Login Field
        tk.Label(body, text="MT5 Account / Login ID", font=(FONT_FAMILY, 9, "bold"), fg=C_TEXT_MAIN, bg=C_CARD_BG).pack(anchor="w", pady=(2, 4))
        self.entry_login = ttk.Entry(body, font=(FONT_FAMILY, 9))
        self.entry_login.pack(fill="x", pady=(0, 10))

        # Password Field + Show Toggle
        tk.Label(body, text="Account Password", font=(FONT_FAMILY, 9, "bold"), fg=C_TEXT_MAIN, bg=C_CARD_BG).pack(anchor="w", pady=(2, 4))
        pwd_box = tk.Frame(body, bg=C_CARD_BG)
        pwd_box.pack(fill="x", pady=(0, 10))
        
        self.entry_pwd = ttk.Entry(pwd_box, show="•", font=(FONT_FAMILY, 9))
        self.entry_pwd.pack(side="left", fill="x", expand=True)
        
        self.pwd_visible = False
        self.btn_toggle_pwd = tk.Button(
            pwd_box,
            text="👁",
            font=(FONT_FAMILY, 8),
            bg=C_BG_APP,
            fg=C_TEXT_MUTED,
            relief="solid",
            bd=1,
            cursor="hand2",
            command=self._toggle_password
        )
        self.btn_toggle_pwd.pack(side="right", padx=(4, 0))

        # Server Field
        tk.Label(body, text="Broker Server", font=(FONT_FAMILY, 9, "bold"), fg=C_TEXT_MAIN, bg=C_CARD_BG).pack(anchor="w", pady=(2, 4))
        self.combo_server = ttk.Combobox(body, values=["MetaQuotes-Demo", "ICMarketsSC-Demo", "Exness-Real", "FTMO-Server"], font=(FONT_FAMILY, 9))
        self.combo_server.pack(fill="x", pady=(0, 10))

        # Terminal Path Field
        tk.Label(body, text="Terminal Path (Optional)", font=(FONT_FAMILY, 9, "bold"), fg=C_TEXT_MAIN, bg=C_CARD_BG).pack(anchor="w", pady=(2, 4))
        path_box = tk.Frame(body, bg=C_CARD_BG)
        path_box.pack(fill="x", pady=(0, 10))

        self.entry_path = ttk.Entry(path_box, font=(FONT_FAMILY, 8))
        self.entry_path.pack(side="left", fill="x", expand=True)

        btn_browse = tk.Button(
            path_box,
            text="Browse...",
            font=(FONT_FAMILY, 8),
            bg=C_BG_APP,
            fg=C_TEXT_MAIN,
            relief="solid",
            bd=1,
            cursor="hand2",
            command=self._browse_path
        )
        btn_browse.pack(side="right", padx=(4, 0))

        # Save to .env checkbox
        self.var_save_env = tk.BooleanVar(value=True)
        chk_env = tk.Checkbutton(
            body,
            text="Save credentials securely to local .env",
            variable=self.var_save_env,
            font=(FONT_FAMILY, 8),
            fg=C_TEXT_MUTED,
            bg=C_CARD_BG,
            activebackground=C_CARD_BG,
            selectcolor=C_CARD_BG
        )
        chk_env.pack(anchor="w", pady=(4, 16))

        # Primary Action Buttons
        self.btn_connect = tk.Button(
            body,
            text="CONNECT TO MT5",
            font=(FONT_FAMILY, 10, "bold"),
            bg=C_BLUE_PRIMARY,
            fg="#FFFFFF",
            activebackground=C_BLUE_HOVER,
            activeforeground="#FFFFFF",
            relief="flat",
            bd=0,
            cursor="hand2",
            pady=10,
            command=self._on_click_connect
        )
        self.btn_connect.pack(fill="x", pady=(0, 8))

        self.btn_disconnect = tk.Button(
            body,
            text="DISCONNECT",
            font=(FONT_FAMILY, 9, "bold"),
            bg=C_BG_APP,
            fg=C_RED_DANGER,
            activebackground=C_RED_BG,
            activeforeground=C_RED_DANGER,
            relief="solid",
            bd=1,
            cursor="hand2",
            pady=8,
            state="disabled",
            command=self._on_click_disconnect
        )
        self.btn_disconnect.pack(fill="x", pady=(0, 8))

        # Secondary Utility Buttons
        util_box = tk.Frame(body, bg=C_CARD_BG)
        util_box.pack(fill="x", pady=(4, 0))

        self.btn_test = tk.Button(
            util_box,
            text="Ping / Verify",
            font=(FONT_FAMILY, 8),
            bg=C_BG_APP,
            fg=C_TEXT_MAIN,
            relief="solid",
            bd=1,
            cursor="hand2",
            command=self._on_test_connection
        )
        self.btn_test.pack(side="left", fill="x", expand=True, padx=(0, 4))

        btn_save = tk.Button(
            util_box,
            text="Save to .env",
            font=(FONT_FAMILY, 8),
            bg=C_BG_APP,
            fg=C_TEXT_MAIN,
            relief="solid",
            bd=1,
            cursor="hand2",
            command=self._save_credentials_manual
        )
        btn_save.pack(side="right", fill="x", expand=True, padx=(4, 0))

    def _build_account_metrics_card(self, parent):
        """Top-right area: Live MT5 account cards (Balance, Equity, Margin, Free Margin, Profit, Trader Info)."""
        card = tk.Frame(parent, bg=C_CARD_BG, highlightbackground=C_CARD_BORDER, highlightthickness=1)
        card.pack(fill="x", pady=(0, 10))

        # Header with Account Name and Mode
        ch = tk.Frame(card, bg=C_CARD_HEADER, padx=16, pady=10, highlightbackground=C_CARD_BORDER, highlightthickness=1)
        ch.pack(fill="x")

        tk.Label(ch, text="LIVE ACCOUNT TELEMETRY", font=(FONT_FAMILY, 9, "bold"), fg=C_TEXT_MAIN, bg=C_CARD_HEADER).pack(side="left")

        self.lbl_acc_badge = tk.Label(
            ch,
            text="STANDBY",
            font=(FONT_FAMILY, 8, "bold"),
            fg=C_TEXT_MUTED,
            bg=C_BG_APP,
            padx=8,
            pady=2,
            relief="solid",
            bd=1
        )
        self.lbl_acc_badge.pack(side="right")

        self.lbl_acc_details = tk.Label(
            ch,
            text="Account: -- | Server: --",
            font=(FONT_FAMILY, 8),
            fg=C_TEXT_MUTED,
            bg=C_CARD_HEADER
        )
        self.lbl_acc_details.pack(side="right", padx=12)

        # Metrics Grid (2 rows x 3 columns)
        grid_frame = tk.Frame(card, bg=C_CARD_BG, padx=12, pady=12)
        grid_frame.pack(fill="x")

        # Configure 3 equal columns
        for c in range(3):
            grid_frame.columnconfigure(c, weight=1, uniform="metric_cols")

        # Row 1
        self.card_balance = MetricCard(grid_frame, "Balance", "$0.00", "USD")
        self.card_balance.grid(row=0, column=0, padx=6, pady=6, sticky="nsew")

        self.card_equity = MetricCard(grid_frame, "Equity", "$0.00", "USD")
        self.card_equity.grid(row=0, column=1, padx=6, pady=6, sticky="nsew")

        self.card_profit = MetricCard(grid_frame, "Floating P&L", "$0.00", "USD")
        self.card_profit.grid(row=0, column=2, padx=6, pady=6, sticky="nsew")

        # Row 2
        self.card_freemargin = MetricCard(grid_frame, "Free Margin", "$0.00", "USD")
        self.card_freemargin.grid(row=1, column=0, padx=6, pady=6, sticky="nsew")

        self.card_margin_lvl = MetricCard(grid_frame, "Margin Level", "0.00%", "")
        self.card_margin_lvl.grid(row=1, column=1, padx=6, pady=6, sticky="nsew")

        self.card_leverage = MetricCard(grid_frame, "Leverage / EA", "1:100", "EA: OK")
        self.card_leverage.grid(row=1, column=2, padx=6, pady=6, sticky="nsew")

    def _build_logs_card(self, parent):
        """Bottom-right area: Clean log terminal."""
        card = tk.Frame(parent, bg=C_CARD_BG, highlightbackground=C_CARD_BORDER, highlightthickness=1)
        card.pack(fill="both", expand=True)

        # Header
        ch = tk.Frame(card, bg=C_CARD_HEADER, padx=16, pady=8, highlightbackground=C_CARD_BORDER, highlightthickness=1)
        ch.pack(fill="x")

        tk.Label(ch, text="SYSTEM & AUDIT LOGS", font=(FONT_FAMILY, 9, "bold"), fg=C_TEXT_MAIN, bg=C_CARD_HEADER).pack(side="left")

        # Log action buttons
        btn_clear = tk.Button(
            ch,
            text="Clear",
            font=(FONT_FAMILY, 8),
            bg=C_BG_APP,
            fg=C_TEXT_MUTED,
            relief="solid",
            bd=1,
            cursor="hand2",
            command=self._clear_logs
        )
        btn_clear.pack(side="right", padx=(4, 0))

        btn_copy = tk.Button(
            ch,
            text="Copy All",
            font=(FONT_FAMILY, 8),
            bg=C_BG_APP,
            fg=C_TEXT_MUTED,
            relief="solid",
            bd=1,
            cursor="hand2",
            command=self._copy_logs
        )
        btn_copy.pack(side="right")

        # Log Text Box
        body = tk.Frame(card, bg=C_CARD_BG, padx=10, pady=10)
        body.pack(fill="both", expand=True)

        scroll = tk.Scrollbar(body)
        scroll.pack(side="right", fill="y")

        self.txt_log = tk.Text(
            body,
            bg="#FAFAFA",
            fg=C_TEXT_MAIN,
            font=("Consolas" if sys.platform == "win32" else "Courier", 9),
            relief="flat",
            bd=1,
            highlightbackground=C_CARD_BORDER,
            highlightthickness=1,
            yscrollcommand=scroll.set,
            padx=10,
            pady=8
        )
        self.txt_log.pack(side="left", fill="both", expand=True)
        scroll.config(command=self.txt_log.yview)

        # Configure Log Tag Styles
        self.txt_log.tag_config("TIME", foreground=C_TEXT_SUBTLE)
        self.txt_log.tag_config("INFO", foreground=C_BLUE_PRIMARY)
        self.txt_log.tag_config("SUCCESS", foreground=C_GREEN_SUCCESS, font=("Consolas", 9, "bold"))
        self.txt_log.tag_config("ERROR", foreground=C_RED_DANGER, font=("Consolas", 9, "bold"))
        self.txt_log.tag_config("WARNING", foreground=C_AMBER_WARN, font=("Consolas", 9, "bold"))

    def _create_status_bar(self):
        """Bottom-most footer bar."""
        footer = tk.Frame(self.root, bg=C_CARD_BG, highlightbackground=C_CARD_BORDER, highlightthickness=1, height=28)
        footer.pack(fill="x", side="bottom")

        self.lbl_terminal_info = tk.Label(
            footer,
            text="MetaTrader 5: Disconnected",
            font=(FONT_FAMILY, 8),
            fg=C_TEXT_MUTED,
            bg=C_CARD_BG
        )
        self.lbl_terminal_info.pack(side="left", padx=16)

        self.lbl_clock = tk.Label(
            footer,
            text="",
            font=(FONT_FAMILY, 8),
            fg=C_TEXT_MUTED,
            bg=C_CARD_BG
        )
        self.lbl_clock.pack(side="right", padx=16)
        self._update_clock()

    def _update_clock(self):
        now_str = datetime.now().strftime("%Y-%m-%d  %H:%M:%S")
        self.lbl_clock.config(text=f"Local: {now_str}")
        self.root.after(1000, self._update_clock)

    # -------------------------------------------------------------
    # Logic & Event Handlers
    # -------------------------------------------------------------
    def _load_config_fields(self):
        """Preload credentials from .env or config defaults."""
        login = Config.get_mt5_login()
        if login > 0:
            self.entry_login.insert(0, str(login))

        pwd = Config.get_mt5_password()
        if pwd:
            self.entry_pwd.insert(0, pwd)

        server = Config.get_mt5_server()
        if server:
            self.combo_server.set(server)
        else:
            self.combo_server.set("MetaQuotes-Demo")

        path = Config.get_mt5_path()
        if path:
            self.entry_path.insert(0, path)

    def _toggle_password(self):
        if self.pwd_visible:
            self.entry_pwd.config(show="•")
            self.btn_toggle_pwd.config(text="👁")
            self.pwd_visible = False
        else:
            self.entry_pwd.config(show="")
            self.btn_toggle_pwd.config(text="🔒")
            self.pwd_visible = True

    def _browse_path(self):
        path = filedialog.askopenfilename(
            title="Locate MetaTrader 5 Terminal executable",
            filetypes=[("Executable Files", "*.exe"), ("All Files", "*.*")]
        )
        if path:
            self.entry_path.delete(0, tk.END)
            self.entry_path.insert(0, path)

    def log_message(self, message: str, level: str = "INFO"):
        """Append formatted timestamped message to the log box."""
        now = datetime.now().strftime("%H:%M:%S")
        self.txt_log.insert(tk.END, f"[{now}] ", "TIME")
        self.txt_log.insert(tk.END, f"[{level:<7}] ", level)
        self.txt_log.insert(tk.END, f"{message}\n")
        self.txt_log.see(tk.END)

    def _clear_logs(self):
        self.txt_log.delete("1.0", tk.END)

    def _copy_logs(self):
        content = self.txt_log.get("1.0", tk.END)
        self.root.clipboard_clear()
        self.root.clipboard_append(content)
        messagebox.showinfo("Copied", "Logs copied to clipboard.")

    def _save_credentials_manual(self):
        try:
            login = int(self.entry_login.get().strip() or "0")
        except ValueError:
            messagebox.showerror("Error", "Login ID must be a valid number.")
            return

        pwd = self.entry_pwd.get().strip()
        server = self.combo_server.get().strip()
        path = self.entry_path.get().strip()

        ok = Config.save_credentials(login, pwd, server, path)
        if ok:
            self.log_message("Credentials successfully saved to .env", "SUCCESS")
            messagebox.showinfo("Saved", "Configuration saved to .env file.")
        else:
            self.log_message("Failed to write to .env", "ERROR")
            messagebox.showerror("Error", "Could not write to .env file.")

    def _set_connecting_state(self, is_connecting: bool):
        self.is_connecting = is_connecting
        if is_connecting:
            self.btn_connect.config(text="CONNECTING...", state="disabled", bg=C_AMBER_WARN)
            self.status_badge.config(
                text="● CONNECTING...",
                fg=C_AMBER_WARN,
                bg=C_AMBER_BG,
                highlightbackground=C_AMBER_BORDER
            )
        else:
            self.btn_connect.config(text="CONNECT TO MT5", state="normal", bg=C_BLUE_PRIMARY)

    def _on_click_connect(self):
        if self.is_connecting:
            return

        # Validate inputs
        login_raw = self.entry_login.get().strip()
        if not login_raw.isdigit():
            messagebox.showwarning("Invalid Input", "Please enter a valid numeric Account / Login ID.")
            return

        login = int(login_raw)
        pwd = self.entry_pwd.get().strip()
        server = self.combo_server.get().strip()
        path = self.entry_path.get().strip()

        if not pwd:
            messagebox.showwarning("Invalid Input", "Please enter your MT5 account password.")
            return

        if not server:
            messagebox.showwarning("Invalid Input", "Please specify the broker server.")
            return

        # Optionally persist
        if self.var_save_env.get():
            Config.save_credentials(login, pwd, server, path)

        self._set_connecting_state(True)
        self.log_message(f"Initiating connection to {server} (Login: {login})...", "INFO")

        # Run connection on background thread to prevent GUI freezing
        threading.Thread(
            target=self._threaded_connect,
            args=(login, pwd, server, path),
            daemon=True
        ).start()

    def _threaded_connect(self, login: int, pwd: str, server: str, path: str):
        success, message = self.connector.connect(login, pwd, server, path)
        # Dispatch back to GUI thread
        self.root.after(0, self._handle_connect_result, success, message)

    def _handle_connect_result(self, success: bool, message: str):
        self._set_connecting_state(False)
        if success:
            self.status_badge.config(
                text="● CONNECTED",
                fg=C_GREEN_SUCCESS,
                bg=C_GREEN_BG,
                highlightbackground=C_GREEN_BORDER
            )
            self.btn_connect.config(state="disabled")
            self.btn_disconnect.config(state="normal")
            self.log_message(message, "SUCCESS")

            # Update terminal and account information
            self._refresh_account_metrics()
            self._start_telemetry_polling()

            # Update available symbols in Data and Backtest tabs
            try:
                symbols = self.connector.get_available_symbols()
                if symbols:
                    self.tab_data.combo_symbol.config(values=symbols)
                    self.tab_backtest.combo_symbol.config(values=symbols)
            except Exception:
                pass
        else:
            self.status_badge.config(
                text="● DISCONNECTED",
                fg=C_RED_DANGER,
                bg=C_RED_BG,
                highlightbackground=C_RED_BORDER
            )
            self.btn_connect.config(state="normal")
            self.btn_disconnect.config(state="disabled")
            self.log_message(message, "ERROR")
            messagebox.showerror("Connection Failed", message)

    def _on_click_disconnect(self):
        self.poll_running = False
        self.log_message("Disconnecting from MetaTrader 5...", "INFO")
        threading.Thread(target=self._threaded_disconnect, daemon=True).start()

    def _threaded_disconnect(self):
        success, message = self.connector.disconnect()
        self.root.after(0, self._handle_disconnect_result, success, message)

    def _handle_disconnect_result(self, success: bool, message: str):
        self.status_badge.config(
            text="● DISCONNECTED",
            fg=C_RED_DANGER,
            bg=C_RED_BG,
            highlightbackground=C_RED_BORDER
        )
        self.btn_connect.config(state="normal")
        self.btn_disconnect.config(state="disabled")
        self.lbl_ping.config(text="⏱ -- ms")
        self.lbl_terminal_info.config(text="MetaTrader 5: Disconnected")
        self.lbl_acc_badge.config(text="STANDBY", bg=C_BG_APP, fg=C_TEXT_MUTED)
        self.lbl_acc_details.config(text="Account: -- | Server: --")

        # Reset metric cards
        self.card_balance.update_value("$0.00")
        self.card_equity.update_value("$0.00")
        self.card_profit.update_value("$0.00", C_TEXT_MAIN)
        self.card_freemargin.update_value("$0.00")
        self.card_margin_lvl.update_value("0.00%")
        self.card_leverage.update_value("--")
        self.card_leverage.update_unit("EA: --")

        self.log_message(message, "INFO")

    def _on_test_connection(self):
        if not self.connector.is_connected:
            self.log_message("Test ping: Not connected to any terminal.", "WARNING")
            messagebox.showinfo("Status", "Terminal is currently disconnected.")
            return

        alive = self.connector.test_connection_state()
        if alive:
            term = self.connector.get_terminal_data()
            ping = term.get("ping_ms", 0.0) if term else 0.0
            self.lbl_ping.config(text=f"⏱ {ping:.1f} ms")
            self.log_message(f"Ping OK. Terminal response time: {ping:.1f} ms", "SUCCESS")
        else:
            self.log_message("Terminal connection lost or not responding.", "ERROR")
            self._handle_disconnect_result(True, "Lost terminal connection.")

    def _refresh_account_metrics(self):
        """Fetch latest account data and update UI cards."""
        data = self.connector.get_account_data()
        term = self.connector.get_terminal_data()

        if not data:
            return

        currency = data.get("currency", "USD")
        balance = data.get("balance", 0.0)
        equity = data.get("equity", 0.0)
        profit = data.get("profit", 0.0)
        freemargin = data.get("margin_free", 0.0)
        margin_lvl = data.get("margin_level", "0.00%")
        leverage = data.get("leverage", "1:100")
        ea_allowed = data.get("trade_expert", False)

        # Update metric cards
        self.card_balance.update_value(f"${balance:,.2f}")
        self.card_balance.update_unit(currency)

        self.card_equity.update_value(f"${equity:,.2f}")
        self.card_equity.update_unit(currency)

        # Profit colored green if positive, red if negative
        profit_color = C_GREEN_SUCCESS if profit >= 0 else C_RED_DANGER
        self.card_profit.update_value(f"{'+' if profit > 0 else ''}${profit:,.2f}", profit_color)
        self.card_profit.update_unit(currency)

        self.card_freemargin.update_value(f"${freemargin:,.2f}")
        self.card_freemargin.update_unit(currency)

        self.card_margin_lvl.update_value(margin_lvl)

        ea_status = "EA: ALLOWED" if ea_allowed else "EA: DISABLED"
        self.card_leverage.update_value(leverage)
        self.card_leverage.update_unit(ea_status)

        # Update header badge
        trade_mode = data.get("trade_mode", "Demo")
        self.lbl_acc_badge.config(
            text=f"{trade_mode.upper()} ACCOUNT",
            bg=C_GREEN_BG if trade_mode == "Real" else C_BLUE_BG,
            fg=C_GREEN_SUCCESS if trade_mode == "Real" else C_BLUE_PRIMARY
        )
        self.lbl_acc_details.config(
            text=f"Trader: {data.get('name', 'N/A')}  |  Server: {data.get('server', 'N/A')}"
        )

        # Update footer and ping
        if term:
            ping = term.get("ping_ms", 0.0)
            self.lbl_ping.config(text=f"⏱ {ping:.1f} ms")
            self.lbl_terminal_info.config(
                text=f"MT5: Build {term.get('build', 'N/A')} ({term.get('name', 'Terminal')}) | Broker: {data.get('company', 'MetaQuotes')}"
            )

    def _start_telemetry_polling(self):
        """Periodically poll account metrics in background without blocking UI."""
        self.poll_running = True
        self._schedule_poll_tick()

    def _schedule_poll_tick(self):
        if not self.poll_running or not self.connector.is_connected:
            return

        self._refresh_account_metrics()
        # Schedule next poll in 2500ms
        self.root.after(2500, self._schedule_poll_tick)

    def _on_closing(self):
        """Ensure clean shutdown when closing the application."""
        self.poll_running = False
        if self.connector.is_connected:
            self.connector.disconnect()
        self.root.destroy()
