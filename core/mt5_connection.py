"""
MT5 Connection Manager.
Handles thread-safe initialization, authentication, status querying,
and account metrics for MetaTrader 5.
"""

import time
import os
import threading
from typing import Optional, Dict, Any, Tuple
import MetaTrader5 as mt5


class MT5Connector:
    """Manages the lifecycle and state of a MetaTrader 5 terminal connection."""

    def __init__(self):
        self._lock = threading.Lock()
        self.is_connected = False
        self.last_login: Optional[int] = None
        self.last_server: Optional[str] = None
        self.last_error_message: str = ""
        self.terminal_build: str = "N/A"
        self.ping_ms: float = 0.0

    def connect(
        self,
        login: int,
        password: str,
        server: str,
        path: Optional[str] = None,
        timeout: int = 60000
    ) -> Tuple[bool, str]:
        """
        Connect and authenticate with the MetaTrader 5 terminal.
        Returns: (success: bool, status_message: str)
        """
        with self._lock:
            # Check if custom path is provided and valid
            init_params = {"timeout": timeout}
            if path and os.path.isfile(path):
                init_params["path"] = path

            # First initialize the terminal
            t0 = time.perf_counter()
            initialized = mt5.initialize(**init_params)
            
            if not initialized:
                err_code, err_desc = mt5.last_error()
                self.is_connected = False
                self.last_error_message = f"Terminal init failed: [{err_code}] {err_desc}"
                return False, self.last_error_message

            # Log in to the trade account
            authorized = mt5.login(login=login, password=password, server=server)
            latency = (time.perf_counter() - t0) * 1000.0
            self.ping_ms = round(latency, 1)

            if not authorized:
                err_code, err_desc = mt5.last_error()
                self.is_connected = False
                self.last_error_message = f"Login failed: [{err_code}] {err_desc}"
                mt5.shutdown()
                return False, self.last_error_message

            # Verify account info is accessible
            acc_info = mt5.account_info()
            if acc_info is None:
                err_code, err_desc = mt5.last_error()
                self.is_connected = False
                self.last_error_message = f"Connected but failed to fetch account: [{err_code}] {err_desc}"
                mt5.shutdown()
                return False, self.last_error_message

            # Terminal details
            term_info = mt5.terminal_info()
            if term_info:
                self.terminal_build = f"Build {term_info.build} ({term_info.name})"
                if term_info.ping_last > 0:
                    self.ping_ms = term_info.ping_last / 1000.0  # microseconds to ms

            self.is_connected = True
            self.last_login = login
            self.last_server = server
            self.last_error_message = ""
            return True, f"Successfully connected to {server} (Account #{login})"

    def disconnect(self) -> Tuple[bool, str]:
        """Safely shut down the MT5 terminal connection."""
        with self._lock:
            try:
                mt5.shutdown()
                self.is_connected = False
                self.last_error_message = ""
                return True, "Disconnected from MetaTrader 5"
            except Exception as e:
                self.is_connected = False
                return False, f"Error during disconnect: {str(e)}"

    def get_account_data(self) -> Optional[Dict[str, Any]]:
        """Retrieve latest account snapshot."""
        with self._lock:
            if not self.is_connected:
                return None
            
            acc = mt5.account_info()
            if acc is None:
                self.is_connected = False
                return None

            trade_mode_map = {
                0: "Demo",
                1: "Contest",
                2: "Real"
            }

            return {
                "login": acc.login,
                "name": acc.name,
                "server": acc.server,
                "company": acc.company,
                "currency": acc.currency,
                "leverage": f"1:{acc.leverage}",
                "balance": acc.balance,
                "equity": acc.equity,
                "profit": acc.profit,
                "margin": acc.margin,
                "margin_free": acc.margin_free,
                "margin_level": f"{acc.margin_level:.2f}%" if acc.margin_level > 0 else "0.00%",
                "trade_mode": trade_mode_map.get(acc.trade_mode, "Unknown"),
                "trade_allowed": acc.trade_allowed,
                "trade_expert": acc.trade_expert,  # EA / Algo trading allowed
                "limit_orders": acc.limit_orders,
            }

    def get_terminal_data(self) -> Optional[Dict[str, Any]]:
        """Retrieve terminal operational metrics."""
        with self._lock:
            if not self.is_connected:
                return None
            
            term = mt5.terminal_info()
            if term is None:
                return None

            return {
                "connected": term.connected,
                "build": term.build,
                "name": term.name,
                "trade_allowed": term.trade_allowed,
                "ping_ms": round(term.ping_last / 1000.0, 1) if term.ping_last > 0 else self.ping_ms,
                "path": term.path,
                "data_path": term.data_path,
            }

    def test_connection_state(self) -> bool:
        """Lightweight check if MT5 connection is currently active."""
        with self._lock:
            if not self.is_connected:
                return False
            term = mt5.terminal_info()
            if term and term.connected:
                return True
            self.is_connected = False
            return False

    def get_available_symbols(self) -> list:
        """Fetch all available trading symbols from MT5."""
        with self._lock:
            try:
                symbols = mt5.symbols_get()
                if symbols:
                    return sorted([s.name for s in symbols])
            except Exception:
                pass
            return ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "USDCHF", "NZDUSD", "XAUUSD", "BTCUSD"]

    def get_symbol_info(self, symbol: str) -> Dict[str, Any]:
        """Fetch pip/point/contract specifications for a symbol."""
        with self._lock:
            s_info = mt5.symbol_info(symbol)
            if s_info:
                # Standard forex pip is 0.0001 (or 0.01 for JPY/gold)
                pip_size = 0.01 if s_info.digits in (2, 3) else 0.0001
                return {
                    "symbol": s_info.name,
                    "digits": s_info.digits,
                    "point": s_info.point,
                    "pip_size": pip_size,
                    "contract_size": s_info.trade_contract_size if s_info.trade_contract_size > 0 else 100000.0,
                    "spread": s_info.spread
                }
            return {
                "symbol": symbol,
                "digits": 5,
                "point": 0.00001,
                "pip_size": 0.0001,
                "contract_size": 100000.0,
                "spread": 15
            }

    def fetch_historical_data(
        self,
        symbol: str,
        timeframe: int,
        date_from: Any,
        date_to: Any
    ) -> Tuple[Optional[Any], str]:
        """
        Fetch real historical rates directly from MT5 broker terminal for the given period.
        Returns: (pandas.DataFrame or None, status_message: str)
        """
        import pandas as pd

        with self._lock:
            if not self.is_connected:
                # If not connected, attempt quick local terminal check
                if not mt5.terminal_info():
                    return None, "Error: MT5 terminal is not connected. Connect first."

            # Ensure symbol is selected in Market Watch
            selected = mt5.symbol_select(symbol, True)
            if not selected:
                # Try fetching anyway, as some brokers don't require select
                pass

            t0 = time.perf_counter()
            rates = mt5.copy_rates_range(symbol, timeframe, date_from, date_to)
            elapsed = round((time.perf_counter() - t0) * 1000, 1)

            if rates is None or len(rates) == 0:
                err_code, err_desc = mt5.last_error()
                return None, f"No data returned for {symbol}. MT5 Error: [{err_code}] {err_desc}"

            df = pd.DataFrame(rates)
            # Format readable timestamp
            df["time_raw"] = df["time"]
            df["time"] = pd.to_datetime(df["time"], unit="s")
            
            total_bars = len(df)
            msg = f"Fetched {total_bars:,} real bars for {symbol} ({elapsed} ms)"
            return df, msg

    def fetch_ticks_range(
        self,
        symbol: str,
        date_from: Any,
        date_to: Any
    ) -> Tuple[Optional[Any], str]:
        """
        Fetch real historical millisecond ticks directly from MT5 broker terminal for the given period.
        Automatically chunks requests into 1-day windows to reliably bypass MT5 single-call buffer limits.
        Returns: (pandas.DataFrame or None, status_message: str)
        """
        import pandas as pd
        from datetime import timedelta

        with self._lock:
            if not self.is_connected and not mt5.terminal_info():
                return None, "Error: MT5 terminal is not connected."

            mt5.symbol_select(symbol, True)
            t0 = time.perf_counter()

            total_duration = date_to - date_from
            if total_duration <= timedelta(days=1):
                ticks = mt5.copy_ticks_range(symbol, date_from, date_to, mt5.COPY_TICKS_ALL)
                if ticks is not None and len(ticks) > 0:
                    df = pd.DataFrame(ticks)
                    df["time_dt"] = pd.to_datetime(df["time_msc"], unit="ms")
                    elapsed = round((time.perf_counter() - t0) * 1000, 1)
                    return df, f"Fetched {len(df):,} real ticks for {symbol} ({elapsed} ms)"

            # Multi-day chunking
            curr_start = date_from
            step = timedelta(days=1)
            chunk_frames = []

            while curr_start < date_to:
                curr_end = min(curr_start + step, date_to)
                ticks = mt5.copy_ticks_range(symbol, curr_start, curr_end, mt5.COPY_TICKS_ALL)
                if ticks is not None and len(ticks) > 0:
                    chunk_frames.append(pd.DataFrame(ticks))
                curr_start = curr_end

            elapsed = round((time.perf_counter() - t0) * 1000, 1)

            if not chunk_frames:
                err_code, err_desc = mt5.last_error()
                return None, f"No tick data returned for {symbol}. MT5 Error: [{err_code}] {err_desc}"

            df = pd.concat(chunk_frames, ignore_index=True)
            df = df.drop_duplicates(subset=["time_msc"])
            df["time_dt"] = pd.to_datetime(df["time_msc"], unit="ms")
            total_ticks = len(df)
            msg = f"Fetched {total_ticks:,} real ticks for {symbol} ({elapsed} ms)"
            return df, msg


