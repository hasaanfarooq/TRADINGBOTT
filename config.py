"""
Configuration manager for MT5 Trading Bot.
Handles loading and updating environment variables and app settings.
"""

import os
from pathlib import Path
from dotenv import load_dotenv, set_key

BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / ".env"

# Ensure .env is loaded
if ENV_PATH.exists():
    load_dotenv(dotenv_path=ENV_PATH)
else:
    load_dotenv()


class Config:
    """Application and MT5 connection configurations."""

    @classmethod
    def get_mt5_login(cls) -> int:
        val = os.getenv("MT5_LOGIN", os.getenv("MT5_ACCOUNT", "0"))
        try:
            return int(val)
        except (ValueError, TypeError):
            return 0

    @classmethod
    def get_mt5_password(cls) -> str:
        return os.getenv("MT5_PASSWORD", "")

    @classmethod
    def get_mt5_server(cls) -> str:
        return os.getenv("MT5_SERVER", "MetaQuotes-Demo")

    @classmethod
    def get_mt5_path(cls) -> str:
        default_path = r"C:\Program Files\MetaTrader 5\terminal64.exe"
        return os.getenv("MT5_PATH", default_path)

    @classmethod
    def save_credentials(cls, login: int, password: str, server: str, path: str = "") -> bool:
        """Persist updated credentials to .env file."""
        try:
            if not ENV_PATH.exists():
                ENV_PATH.touch()

            set_key(str(ENV_PATH), "MT5_ACCOUNT", str(login))
            set_key(str(ENV_PATH), "MT5_LOGIN", str(login))
            set_key(str(ENV_PATH), "MT5_PASSWORD", password)
            set_key(str(ENV_PATH), "MT5_SERVER", server)
            if path:
                set_key(str(ENV_PATH), "MT5_PATH", path)
            return True
        except Exception as e:
            print(f"Error saving to .env: {e}")
            return False
