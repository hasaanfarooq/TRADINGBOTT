"""
Quantitative Trade Reasoning & Confluence Scoring Engine.
Analyzes past candle anatomy, multi-timeframe trend alignment (D1/H4/H1),
liquidity sweeps (fakeout/rejection traps), and ATR volatility regimes
to determine whether a proposed strategy setup should be executed or rejected.
"""

from typing import Dict, Any, Optional, Tuple
import pandas as pd
import numpy as np


class TradeReasoningEngine:
    """
    Evaluates algorithmic trade candidates using a multi-factor quantitative
    confluence checklist (0 to 100 score). Generates transparent reasoning audit logs.
    """

    def __init__(self, min_confluence_score: int = 70):
        self.min_score = min_confluence_score

    @staticmethod
    def prepare_data(
        df_m15: pd.DataFrame,
        df_h1: Optional[pd.DataFrame] = None,
        df_h4: Optional[pd.DataFrame] = None,
        df_d1: Optional[pd.DataFrame] = None
    ) -> Dict[str, pd.DataFrame]:
        """Precomputes indicators across multiple timeframes for rapid vectorized lookup."""
        result = {}

        # 1. M15: ATR & Volatility
        m15 = df_m15.copy()
        high_low = m15["high"] - m15["low"]
        high_close = (m15["high"] - m15["close"].shift(1)).abs()
        low_close = (m15["low"] - m15["close"].shift(1)).abs()
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        m15["atr14"] = tr.rolling(window=14).mean().bfill()
        m15["atr_ma50"] = m15["atr14"].rolling(window=50).mean().bfill()

        # 2. H1: Trend & Momentum EMA
        if df_h1 is not None and len(df_h1) > 20:
            h1 = df_h1.copy()
            h1["ema20"] = h1["close"].ewm(span=20, adjust=False).mean()
            h1["ema50"] = h1["close"].ewm(span=50, adjust=False).mean()
            h1["h1_bull"] = h1["close"] > h1["ema20"]
            result["h1"] = h1

            # Vectorized backward merge to M15 for instant O(1) bar lookups
            m15 = pd.merge_asof(
                m15.sort_values("time"),
                h1[["time", "h1_bull"]].sort_values("time"),
                on="time",
                direction="backward"
            )
        else:
            result["h1"] = None
            m15["h1_bull"] = None

        # 3. H4: Intermediate Structure & 50 EMA
        if df_h4 is not None and len(df_h4) > 20:
            h4 = df_h4.copy()
            h4["ema50"] = h4["close"].ewm(span=50, adjust=False).mean()
            h4["h4_bull"] = h4["close"] > h4["ema50"]
            result["h4"] = h4

            m15 = pd.merge_asof(
                m15.sort_values("time"),
                h4[["time", "h4_bull"]].sort_values("time"),
                on="time",
                direction="backward"
            )
        else:
            result["h4"] = None
            m15["h4_bull"] = None

        # 4. D1: Macro Institutional Trend
        if df_d1 is not None and len(df_d1) > 10:
            d1 = df_d1.copy()
            d1["ema50"] = d1["close"].ewm(span=50, adjust=False).mean()
            d1["d1_bull"] = d1["close"] > d1["ema50"]
            result["d1"] = d1

            m15 = pd.merge_asof(
                m15.sort_values("time"),
                d1[["time", "d1_bull"]].sort_values("time"),
                on="time",
                direction="backward"
            )
        else:
            result["d1"] = None
            m15["d1_bull"] = None

        result["m15"] = m15
        return result

    def evaluate_candidate(
        self,
        direction: str,
        bar_idx: int,
        dfs: Dict[str, pd.DataFrame],
        spread_pips: float = 1.5,
        pip_size: float = 0.0001
    ) -> Dict[str, Any]:
        """
        Evaluates a proposed trade at bar_idx on M15 across 4 key quantitative pillars:
        1. Multi-Timeframe Trend Alignment (Max 30 pts)
        2. Candle Anatomy & Rejection Price Action (Max 25 pts)
        3. Liquidity Sweep / Fakeout Grab (Max 25 pts)
        4. Volatility & ATR Regime (Max 20 pts)
        """
        m15 = dfs["m15"]
        h1 = dfs.get("h1")
        h4 = dfs.get("h4")
        d1 = dfs.get("d1")

        curr_bar = m15.iloc[bar_idx]
        curr_time = curr_bar["time"]
        c = float(curr_bar["close"])
        o = float(curr_bar["open"])
        h = float(curr_bar["high"])
        l = float(curr_bar["low"])

        reasons = []
        scores = {
            "mtf_trend": 0,
            "candle_anatomy": 0,
            "liquidity_sweep": 0,
            "volatility_regime": 0
        }

        # -------------------------------------------------------------
        # PILLAR 1: Multi-Timeframe Alignment (Max 30 pts)
        # -------------------------------------------------------------
        mtf_pts = 0
        d1_bull = None
        h4_bull = None
        h1_bull = None

        # D1 Institutional Bias (10 pts)
        d1_bull = curr_bar.get("d1_bull")
        if pd.notna(d1_bull):
            if (direction == "BUY" and d1_bull) or (direction == "SELL" and not d1_bull):
                mtf_pts += 10
                reasons.append("[+] D1 Macro Trend Aligned (+10)")
            else:
                reasons.append("[-] Opposing D1 Macro Trend (0)")

        # H4 Intermediate Flow (10 pts)
        h4_bull = curr_bar.get("h4_bull")
        if pd.notna(h4_bull):
            if (direction == "BUY" and h4_bull) or (direction == "SELL" and not h4_bull):
                mtf_pts += 10
                reasons.append("[+] 4H Intermediate Flow Aligned (+10)")
            else:
                reasons.append("[-] Opposing 4H Flow (0)")

        # H1 Immediate Bias (10 pts)
        h1_bull = curr_bar.get("h1_bull")
        if pd.notna(h1_bull):
            if (direction == "BUY" and h1_bull) or (direction == "SELL" and not h1_bull):
                mtf_pts += 10
                reasons.append("[+] 1H Momentum Aligned (+10)")
            else:
                reasons.append("[-] Opposing 1H Momentum (0)")

        # If higher timeframes were not available, grant default baseline
        if d1 is None and h4 is None and h1 is None:
            mtf_pts = 20
            reasons.append("[~] MTF data baseline (+20)")

        scores["mtf_trend"] = min(30, mtf_pts)

        # -------------------------------------------------------------
        # PILLAR 2: Candle Anatomy & Rejection Price Action (Max 25 pts)
        # -------------------------------------------------------------
        anatomy_pts = 0
        total_range = h - l
        if total_range > 0:
            if direction == "BUY":
                lower_wick = min(o, c) - l
                lower_wick_ratio = lower_wick / total_range
                body = c - o

                # Rejection wick check
                if lower_wick_ratio >= 0.35:
                    anatomy_pts += 15
                    reasons.append(f"[+] Strong Bullish Rejection Wick ({lower_wick_ratio*100:.0f}%) (+15)")
                elif lower_wick_ratio >= 0.20:
                    anatomy_pts += 8
                    reasons.append("[+] Moderate Lower Wick (+8)")

                # Bullish body check
                if body > 0:
                    body_ratio = body / total_range
                    if body_ratio >= 0.30:
                        anatomy_pts += 10
                        reasons.append("[+] Solid Bullish Close Displacement (+10)")
                    else:
                        anatomy_pts += 5

            elif direction == "SELL":
                upper_wick = h - max(o, c)
                upper_wick_ratio = upper_wick / total_range
                body = o - c

                if upper_wick_ratio >= 0.35:
                    anatomy_pts += 15
                    reasons.append(f"[+] Strong Bearish Rejection Wick ({upper_wick_ratio*100:.0f}%) (+15)")
                elif upper_wick_ratio >= 0.20:
                    anatomy_pts += 8
                    reasons.append("[+] Moderate Upper Wick (+8)")

                if body > 0:
                    body_ratio = body / total_range
                    if body_ratio >= 0.30:
                        anatomy_pts += 10
                        reasons.append("[+] Solid Bearish Close Displacement (+10)")
                    else:
                        anatomy_pts += 5

        scores["candle_anatomy"] = min(25, anatomy_pts)

        # -------------------------------------------------------------
        # PILLAR 3: Liquidity Sweep / Fakeout Grab (Max 25 pts)
        # -------------------------------------------------------------
        sweep_pts = 0
        # Look back 25 bars on M15 to check if key swing liquidity was grabbed
        start_idx = max(0, bar_idx - 25)
        recent_slice = m15.iloc[start_idx:bar_idx]

        if len(recent_slice) >= 10:
            recent_low = recent_slice["low"].min()
            recent_high = recent_slice["high"].max()

            if direction == "BUY":
                # Did price sweep recent low and close back above?
                if l < recent_low and c > recent_low:
                    sweep_pts += 25
                    reasons.append("[+] Clean Liquidity Sweep (Turtle Soup Low Grabbed & Rejected) (+25)")
                elif abs(l - recent_low) <= (5 * pip_size):
                    sweep_pts += 15
                    reasons.append("[+] Tested Established Support Level (+15)")
                else:
                    sweep_pts += 10
                    reasons.append("[~] Retracement to structural level (+10)")

            elif direction == "SELL":
                # Did price sweep recent high and close back below?
                if h > recent_high and c < recent_high:
                    sweep_pts += 25
                    reasons.append("[+] Clean Liquidity Sweep (Turtle Soup High Grabbed & Rejected) (+25)")
                elif abs(h - recent_high) <= (5 * pip_size):
                    sweep_pts += 15
                    reasons.append("[+] Tested Established Resistance Level (+15)")
                else:
                    sweep_pts += 10
                    reasons.append("[~] Retracement to structural level (+10)")
        else:
            sweep_pts = 10

        scores["liquidity_sweep"] = min(25, sweep_pts)

        # -------------------------------------------------------------
        # PILLAR 4: Volatility & ATR Regime (Max 20 pts)
        # -------------------------------------------------------------
        vol_pts = 0
        atr = float(curr_bar.get("atr14", 0.0))
        atr_avg = float(curr_bar.get("atr_ma50", 0.0))

        if atr > 0:
            # 1. Market not dead / healthy expansion
            if atr >= (0.7 * atr_avg):
                vol_pts += 10
                reasons.append("[+] Healthy ATR Market Volatility (+10)")
            else:
                reasons.append("[-] Low ATR Choppy Regime (0)")

            # 2. Candle range is orderly (not an erratic freak anomaly)
            if total_range >= (0.3 * atr) and total_range <= (2.5 * atr):
                vol_pts += 10
                reasons.append("[+] Orderly Bar Range vs ATR (+10)")
            else:
                vol_pts += 3
        else:
            vol_pts = 15

        scores["volatility_regime"] = min(20, vol_pts)

        # -------------------------------------------------------------
        # TOTAL SCORE & THESIS VERDICT
        # -------------------------------------------------------------
        total_score = sum(scores.values())
        is_approved = total_score >= self.min_score

        verdict_str = f"APPROVED [{total_score}/100]" if is_approved else f"REJECTED [{total_score}/100]"
        thesis = f"{verdict_str} | " + " | ".join(reasons)

        return {
            "approved": is_approved,
            "total_score": total_score,
            "min_score": self.min_score,
            "thesis": thesis,
            "scores": scores
        }

    @staticmethod
    def calculate_position_size(
        balance: float,
        risk_pct: float,
        sl_distance_price: float,
        contract_size: float = 100000.0,
        min_lot: float = 0.01,
        max_lot: float = 20.0
    ) -> float:
        """
        Calculates exact mathematical position sizing so every trade risks
        precisely risk_pct of equity (e.g. 1.0%), regardless of stop loss pip distance.
        """
        if sl_distance_price <= 0 or balance <= 0 or contract_size <= 0:
            return min_lot

        risk_dollars = balance * risk_pct
        calculated_lots = risk_dollars / (sl_distance_price * contract_size)
        clamped_lots = max(min_lot, min(max_lot, round(calculated_lots, 2)))
        return clamped_lots
