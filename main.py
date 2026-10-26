"""
Main entry point for MT5 Algorithmic Trading Station.
"""

import sys
import tkinter as tk
from gui import MT5TradingStationGUI


def set_dpi_awareness():
    """Enable high-DPI scaling on Windows for crisp typography."""
    if sys.platform == "win32":
        try:
            from ctypes import windll
            # Per-monitor DPI aware
            windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            try:
                windll.user32.SetProcessDPIAware()
            except Exception:
                pass


def main():
    set_dpi_awareness()
    root = tk.Tk()
    app = MT5TradingStationGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
