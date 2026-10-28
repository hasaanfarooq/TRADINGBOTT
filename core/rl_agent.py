"""
Reinforcement Learning & Experience Replay Trade Agent.
Learns online from winning and losing trades, maintains an episodic memory of market states,
and checks memory before executing new setups to veto recurring failure patterns.
"""

import os
import json
import math
from typing import Dict, List, Any, Optional, Tuple
import numpy as np


class RLTradeAgent:
    """
    Reinforcement Learning Trade Agent with Experience Replay & Failure Memory.
    Features:
    1. Online Temporal-Difference Q-Learning.
    2. Episodic Failure Cluster Recognition (Vetoes trades matching past loss signatures).
    3. Dynamic Heat Governor (Tightens risk and admission hurdles after loss streaks).
    4. State-Action value tracking across volatility, session, and trend regimes.
    5. Persistent memory serialization.
    """

    def __init__(
        self,
        learning_rate: float = 0.15,
        discount_factor: float = 0.90,
        similarity_threshold: float = 0.92,
        memory_file: Optional[str] = None
    ):
        self.alpha = learning_rate
        self.gamma = discount_factor
        self.similarity_threshold = similarity_threshold
        self.memory_file = memory_file or os.path.join(os.path.dirname(__file__), "rl_memory.json")

        # Q-Table: State Hash -> [Q(SKIP), Q(EXECUTE)]
        self.q_table: Dict[str, List[float]] = {}

        # Episodic Experience Buffer: List of past trade experiences
        self.experience_memory: List[Dict[str, Any]] = []

        # Failure Memory: High-priority buffer of stopped-out trades
        self.failure_signatures: List[Dict[str, Any]] = []

        # Dynamic State Tracking
        self.consecutive_losses = 0
        self.total_learned_trades = 0
        self.total_vetoed_trades = 0

        # Feature normalization scales
        self.feature_scales = {
            "hour": 24.0,
            "vol_ratio": 2.5,
            "spread_pips": 5.0,
            "ema_dist_pips": 50.0,
            "d1_slope": 0.5,
            "score": 100.0
        }

        self.load_memory()

    def extract_state_vector(
        self,
        hour: int,
        vol_ratio: float,
        spread_pips: float,
        ema_dist_pips: float,
        d1_slope: float,
        confluence_score: float,
        consec_losses: int
    ) -> List[float]:
        """Encodes market environment into a normalized continuous state vector."""
        h_norm = (hour % 24) / 24.0
        v_norm = min(3.0, max(0.1, float(vol_ratio))) / 2.5
        s_norm = min(10.0, max(0.1, float(spread_pips))) / 5.0
        e_norm = min(100.0, max(-100.0, float(ema_dist_pips))) / 50.0
        d_norm = min(1.0, max(-1.0, float(d1_slope)))
        sc_norm = min(100.0, max(0.0, float(confluence_score))) / 100.0
        cl_norm = min(5, max(0, int(consec_losses))) / 5.0

        return [
            round(h_norm, 3),
            round(v_norm, 3),
            round(s_norm, 3),
            round(e_norm, 3),
            round(d_norm, 3),
            round(sc_norm, 3),
            round(cl_norm, 3)
        ]

    def get_state_key(self, direction: str, state_vec: List[float]) -> str:
        """Discretizes continuous state vector into a categorical Q-table bin."""
        # Bucketing: Hour bucket (Asian, London, NY), Vol bucket (Low, Normal, High), Slope (Bull, Bear, Flat)
        h_val = state_vec[0] * 24.0
        session_bin = "ASIA" if h_val < 7 else ("LDN" if h_val < 13 else ("NY" if h_val < 18 else "OFF"))

        v_val = state_vec[1] * 2.5
        vol_bin = "VOL_LO" if v_val < 0.8 else ("VOL_HI" if v_val > 1.4 else "VOL_NORM")

        d_val = state_vec[4]
        slope_bin = "SLOPE_UP" if d_val > 0.05 else ("SLOPE_DN" if d_val < -0.05 else "SLOPE_FLAT")

        streak_bin = f"STREAK_{int(state_vec[6] * 5)}"

        return f"{direction}_{session_bin}_{vol_bin}_{slope_bin}_{streak_bin}"

    def calculate_similarity(self, vec_a: List[float], vec_b: List[float]) -> float:
        """Calculates normalized distance similarity between two market states."""
        # Focus on the 6 market regime features (hour, vol, spread, ema, slope, score)
        a = np.array(vec_a[:6], dtype=float)
        b = np.array(vec_b[:6], dtype=float)
        dist = np.linalg.norm(a - b)
        return float(1.0 / (1.0 + dist))

    def evaluate_trade(
        self,
        direction: str,
        hour: int,
        vol_ratio: float,
        spread_pips: float,
        ema_dist_pips: float,
        d1_slope: float,
        confluence_score: float
    ) -> Dict[str, Any]:
        """
        Consults RL Memory BEFORE taking trade.
        Returns:
            approved: bool
            veto_reason: Optional[str]
            q_value: float
            failure_similarity: float
            memory_learnings: List[str]
        """
        state_vec = self.extract_state_vector(
            hour=hour,
            vol_ratio=vol_ratio,
            spread_pips=spread_pips,
            ema_dist_pips=ema_dist_pips,
            d1_slope=d1_slope,
            confluence_score=confluence_score,
            consec_losses=self.consecutive_losses
        )
        state_key = self.get_state_key(direction, state_vec)

        # Initialize Q-values if unseen state: [Q(SKIP), Q(EXECUTE)]
        if state_key not in self.q_table:
            self.q_table[state_key] = [0.0, 0.5]  # optimistic prior for exploration

        q_skip, q_exec = self.q_table[state_key]

        memory_learnings: List[str] = []
        is_vetoed = False
        veto_reasons: List[str] = []
        max_failure_sim = 0.0
        matching_failure = None
        matching_failures = []

        # -------------------------------------------------------------
        # 1. Check Failure Memory Buffer (Recurring Loss Signatures)
        # -------------------------------------------------------------
        for f_sig in reversed(self.failure_signatures[-100:]):
            if f_sig["direction"] == direction:
                sim = self.calculate_similarity(state_vec, f_sig["state_vector"])
                if sim >= self.similarity_threshold:
                    matching_failures.append((sim, f_sig))
                if sim > max_failure_sim:
                    max_failure_sim = sim
                    matching_failure = f_sig

        # VETO only if there is a recurring cluster of at least 2 matching failures
        if len(matching_failures) >= 2 and matching_failure is not None:
            f_reason = matching_failure.get("exit_reason", "Stop Loss")
            total_penalty = sum(m[1].get("loss_amount", 0.0) for m in matching_failures)
            is_vetoed = True
            msg = (
                f"RL Memory Veto ({max_failure_sim*100:.1f}% match to recurring failure cluster): "
                f"State matches {len(matching_failures)} prior {f_reason}s (Total Lost: -${total_penalty:.2f})."
            )
            veto_reasons.append(msg)
            memory_learnings.append(msg)

        # -------------------------------------------------------------
        # 2. Check RL Q-Value (Expected Policy Value)
        # -------------------------------------------------------------
        if q_exec < -0.30:
            is_vetoed = True
            msg = f"RL Negative Q-Value ({q_exec:+.2f}R): Persistent negative expectation in this market regime."
            veto_reasons.append(msg)
            memory_learnings.append(msg)
        else:
            memory_learnings.append(f"RL Q-Value Favorable ({q_exec:+.2f}R): Positive statistical expectation.")

        # -------------------------------------------------------------
        # 3. Dynamic Heat Governor (After Consecutive Losses)
        # -------------------------------------------------------------
        if self.consecutive_losses >= 2:
            required_score = 65
            if confluence_score < required_score:
                is_vetoed = True
                msg = (
                    f"RL Heat Governor Veto: Drawdown defense active ({self.consecutive_losses} consecutive losses). "
                    f"Requires minimum {required_score} confluence score (got {confluence_score:.0f})."
                )
                veto_reasons.append(msg)
                memory_learnings.append(msg)
                # Decay governor after vetoing so the agent resumes exploration
                self.consecutive_losses = max(0, self.consecutive_losses - 1)
            else:
                memory_learnings.append(f"Drawdown Defense Pass: Confluence {confluence_score:.0f} cleared elevated {required_score} hurdle.")

        if is_vetoed:
            self.total_vetoed_trades += 1

        return {
            "approved": not is_vetoed,
            "state_vector": state_vec,
            "state_key": state_key,
            "q_value": round(q_exec, 3),
            "q_skip": round(q_skip, 3),
            "failure_similarity": round(max_failure_sim, 3),
            "veto_reasons": veto_reasons,
            "memory_learnings": memory_learnings,
            "consec_losses": self.consecutive_losses
        }

    def record_trade_outcome(
        self,
        trade_id: int,
        direction: str,
        state_vec: List[float],
        state_key: str,
        pnl: float,
        risk_dollar: float,
        exit_reason: str
    ):
        """
        Online Learning Update.
        Called immediately when a trade closes to update Q-values and Failure Memory.
        """
        risk_dollar = max(1.0, float(risk_dollar))
        r_multiple = pnl / risk_dollar

        # Reward formulation with penalty for loss streaks and high drawdown
        if pnl > 0:
            reward = min(3.0, r_multiple)
            self.consecutive_losses = 0
        else:
            reward = max(-2.5, r_multiple)
            self.consecutive_losses += 1

            # Store in failure memory signature buffer
            self.failure_signatures.append({
                "trade_id": trade_id,
                "direction": direction,
                "state_vector": state_vec,
                "loss_amount": abs(pnl),
                "r_multiple": r_multiple,
                "exit_reason": exit_reason
            })
            # Keep failure signatures bounded to last 200
            if len(self.failure_signatures) > 200:
                self.failure_signatures.pop(0)

        # Online Q-learning Temporal Difference update:
        # Q(s, a) = Q(s, a) + alpha * [Reward - Q(s, a)]
        if state_key not in self.q_table:
            self.q_table[state_key] = [0.0, 0.5]

        old_q = self.q_table[state_key][1]
        new_q = old_q + self.alpha * (reward - old_q)
        self.q_table[state_key][1] = round(new_q, 4)

        # Store in episodic memory
        self.experience_memory.append({
            "id": trade_id,
            "direction": direction,
            "state_key": state_key,
            "pnl": round(pnl, 2),
            "r_multiple": round(r_multiple, 2),
            "reward": round(reward, 3),
            "new_q": round(new_q, 3),
            "exit_reason": exit_reason
        })
        if len(self.experience_memory) > 500:
            self.experience_memory.pop(0)

        self.total_learned_trades += 1

    def save_memory(self):
        """Persists Q-table and Failure Signatures to disk."""
        try:
            payload = {
                "total_learned": self.total_learned_trades,
                "total_vetoed": self.total_vetoed_trades,
                "q_table": self.q_table,
                "failure_signatures": self.failure_signatures[-150:]
            }
            with open(self.memory_file, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2)
        except Exception as e:
            pass

    def load_memory(self):
        """Loads persistent Q-table and Failure Signatures from disk if available."""
        if os.path.exists(self.memory_file):
            try:
                with open(self.memory_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.q_table = data.get("q_table", {})
                    self.failure_signatures = data.get("failure_signatures", [])
                    self.total_learned_trades = data.get("total_learned", 0)
                    self.total_vetoed_trades = data.get("total_vetoed", 0)
            except Exception:
                self.q_table = {}
                self.failure_signatures = []

    def reset_episode(self):
        """Resets dynamic intra-run variables while preserving long-term learned Q-values."""
        self.consecutive_losses = 0
        self.experience_memory.clear()
