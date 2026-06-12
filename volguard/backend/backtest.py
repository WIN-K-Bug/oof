import os
import json
import sqlite3
import pandas as pd
from datetime import datetime, timedelta
from typing import List, Dict, Any
from loguru import logger
from dotenv import load_dotenv

load_dotenv()

DB_PATH = os.getenv("DB_PATH", "backend/db/volguard.db")


class BacktestEngine:
    """Standalone backtesting engine for VolGuard.

    Replays historical NIFTY option tick data from CSV in rolling windows,
    evaluates a reduced 4-gate DCE, simulates signals, and scores outcomes
    (WIN / LOSS / EXPIRED) against future ticks.
    """

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self.results: List[dict] = []
        self.summary: dict = {}

    # ------------------------------------------------------------------
    # Data loading
    # ------------------------------------------------------------------

    def load_historical_ticks(self, csv_path: str) -> pd.DataFrame:
        """Load historical tick CSV. Columns: timestamp, token, symbol,
        ltp, oi, volume, iv, bid, ask. Returns empty DataFrame on error."""
        try:
            df = pd.read_csv(csv_path, dtype={"token": str})
            df["timestamp"] = pd.to_datetime(df["timestamp"])
            df = df.sort_values("timestamp", ascending=True).reset_index(drop=True)
            logger.info(f"[BACKTEST] Loaded {len(df)} historical ticks from {csv_path}")
            return df
        except Exception as e:
            logger.error(f"[BACKTEST] load_historical_ticks failed: {e}")
            return pd.DataFrame()

    # ------------------------------------------------------------------
    # Market state simulation
    # ------------------------------------------------------------------

    def simulate_market_state(self, tick_window: pd.DataFrame) -> dict:
        """Build a mock market state dict mimicking MarketStateManager."""
        # Get latest tick per token
        latest = tick_window.groupby("token").last().reset_index()

        # Calculate spot price (use token 99926000 or 26000 if present, else median LTP)
        spot_tokens = latest[latest["token"].isin(["99926000", "26000"])]
        if not spot_tokens.empty:
            spot_price = float(spot_tokens["ltp"].iloc[-1])
        else:
            spot_price = float(latest["ltp"].median())

        # Calculate running VWAP
        vwap_num = (tick_window["ltp"] * tick_window["volume"]).sum()
        vwap_den = tick_window["volume"].sum()
        vwap = float(vwap_num / vwap_den) if vwap_den > 0 else spot_price

        # Build options states dict (token -> tick data)
        options_states: Dict[str, Any] = {}
        for _, row in latest.iterrows():
            options_states[str(row["token"])] = {
                "ltp": float(row.get("ltp", 0)),
                "oi": int(row.get("oi", 0)),
                "volume": int(row.get("volume", 0)),
                "iv": float(row.get("iv", 0)),
                "bid": float(row.get("bid", 0)),
                "ask": float(row.get("ask", 0)),
                "symbol": str(row.get("symbol", ""))
            }

        return {
            "spot_price": spot_price,
            "vwap": vwap,
            "options_states": options_states,
            "tick_count": len(tick_window),
            "timestamp": tick_window["timestamp"].max().isoformat()
        }

    # ------------------------------------------------------------------
    # Gate evaluation (4 backtestable core gates)
    # ------------------------------------------------------------------

    def evaluate_gates(self, market_state: dict) -> dict:
        """Evaluate the 4 core DCE gates that can be backtested from history."""
        spot = market_state["spot_price"]
        vwap = market_state["vwap"]
        options_states = market_state["options_states"]
        tick_count = market_state["tick_count"]

        # Gate: Spot vs VWAP
        deviation = abs(spot - vwap) / vwap * 100 if vwap > 0 else 999
        gate_vwap = deviation <= 2.0

        # Gate: Momentum direction
        momentum = (spot - vwap) / vwap * 100 if vwap > 0 else 0.0
        gate_momentum = abs(momentum) >= 0.1

        # Gate: Options data available
        live_contracts = sum(1 for s in options_states.values() if s.get("ltp", 0) > 0)
        gate_options = live_contracts >= 10

        # Gate: Volume confirmation
        total_volume = sum(s.get("volume", 0) for s in options_states.values())
        gate_volume = total_volume >= 10000

        # Direction from momentum
        direction = "CE" if momentum > 0 else "PE"

        # Confidence proxy (gates passed / 4 * 100)
        gates_passed = sum([gate_vwap, gate_momentum, gate_options, gate_volume])
        confidence = round(gates_passed / 4 * 100)

        return {
            "gate_vwap": gate_vwap,
            "gate_momentum": gate_momentum,
            "gate_options": gate_options,
            "gate_volume": gate_volume,
            "gates_passed": gates_passed,
            "confidence": confidence,
            "direction": direction,
            "momentum": momentum,
            "spot_price": spot,
            "vwap": vwap,
            "deviation": deviation
        }

    # ------------------------------------------------------------------
    # Signal simulation
    # ------------------------------------------------------------------

    def simulate_signal(self, gate_result: dict, market_state: dict) -> dict:
        """Simulate a signal from gate results. Mirrors generate_signal logic."""
        if gate_result["confidence"] < 75:
            return {"signal": "NO_TRADE", "reason": f"Confidence {gate_result['confidence']}%"}

        spot = gate_result["spot_price"]
        direction = gate_result["direction"]
        atm = round(spot / 50) * 50
        strike = atm + 50 if direction == "CE" else atm - 50

        # Find entry price from options_states
        options = market_state["options_states"]
        best_ltp = 0.0
        best_symbol = ""
        for token, state in options.items():
            sym = state.get("symbol", "")
            if sym.endswith(direction):
                ltp = state.get("ltp", 0.0)
                if ltp > 0 and best_ltp == 0:
                    best_ltp = ltp
                    best_symbol = sym

        if best_ltp <= 0:
            return {"signal": "NO_TRADE", "reason": "No valid LTP found"}

        stop_loss = round(best_ltp * 0.65, 2)
        target = round(best_ltp * 1.65, 2)

        return {
            "signal": f"BUY_{direction}",
            "strike": strike,
            "symbol": best_symbol,
            "entry": best_ltp,
            "stop_loss": stop_loss,
            "target": target,
            "confidence": gate_result["confidence"],
            "direction": direction,
            "timestamp": market_state["timestamp"]
        }

    # ------------------------------------------------------------------
    # Outcome evaluation
    # ------------------------------------------------------------------

    def evaluate_outcome(self, signal: dict, future_ticks: pd.DataFrame) -> str:
        """Determine WIN / LOSS / EXPIRED by replaying ticks after the signal."""
        symbol_ticks = future_ticks[future_ticks["symbol"] == signal.get("symbol", "")]
        if symbol_ticks.empty:
            return "EXPIRED"

        entry = signal["entry"]
        sl = signal["stop_loss"]
        target = signal["target"]

        for _, row in symbol_ticks.iterrows():
            ltp = float(row.get("ltp", 0))
            if ltp >= target:
                return "WIN"
            if ltp <= sl:
                return "LOSS"

        return "EXPIRED"

    # ------------------------------------------------------------------
    # Main runner
    # ------------------------------------------------------------------

    def run(self, csv_path: str, window_minutes: int = 30) -> dict:
        """Replay historical ticks in rolling windows and collect signals."""
        df = self.load_historical_ticks(csv_path)
        if df.empty:
            return {"error": "No data loaded"}

        df["timestamp"] = pd.to_datetime(df["timestamp"])
        start_time = df["timestamp"].min()
        end_time = df["timestamp"].max()
        current_time = start_time + timedelta(minutes=window_minutes)
        last_signal_time = None
        signals_fired = []

        while current_time <= end_time:
            window = df[df["timestamp"] <= current_time]
            market_state = self.simulate_market_state(window)
            gate_result = self.evaluate_gates(market_state)

            # Cooldown: 15 minutes between signals
            cooldown_ok = (
                last_signal_time is None or
                (current_time - last_signal_time).total_seconds() >= 900
            )

            if cooldown_ok:
                signal = self.simulate_signal(gate_result, market_state)
                if signal["signal"] != "NO_TRADE":
                    future = df[df["timestamp"] > current_time]
                    outcome = self.evaluate_outcome(signal, future)
                    signal["outcome"] = outcome
                    signals_fired.append(signal)
                    last_signal_time = current_time
                    logger.info(
                        f"[BACKTEST] {signal['signal']} @ {signal['strike']} "
                        f"entry \u20b9{signal['entry']} \u2192 {outcome}"
                    )

            current_time += timedelta(minutes=5)

        self.results = signals_fired
        return self.calculate_summary()

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------

    def calculate_summary(self) -> dict:
        """Aggregate backtest results into a summary dict."""
        if not self.results:
            return {"total_signals": 0, "message": "No signals fired in backtest period"}

        total = len(self.results)
        wins = sum(1 for r in self.results if r["outcome"] == "WIN")
        losses = sum(1 for r in self.results if r["outcome"] == "LOSS")
        expired = sum(1 for r in self.results if r["outcome"] == "EXPIRED")
        win_rate = round(wins / total * 100, 1) if total > 0 else 0

        ce_signals = sum(1 for r in self.results if "CE" in r["signal"])
        pe_signals = sum(1 for r in self.results if "PE" in r["signal"])

        avg_confidence = round(
            sum(r["confidence"] for r in self.results) / total, 1
        ) if total > 0 else 0

        summary = {
            "total_signals": total,
            "wins": wins,
            "losses": losses,
            "expired": expired,
            "win_rate_pct": win_rate,
            "ce_signals": ce_signals,
            "pe_signals": pe_signals,
            "avg_confidence": avg_confidence,
            "signals": self.results
        }

        logger.info(f"[BACKTEST] \u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550")
        logger.info(f"[BACKTEST] Total signals : {total}")
        logger.info(f"[BACKTEST] Win rate      : {win_rate}%")
        logger.info(f"[BACKTEST] Wins          : {wins}")
        logger.info(f"[BACKTEST] Losses        : {losses}")
        logger.info(f"[BACKTEST] Expired       : {expired}")
        logger.info(f"[BACKTEST] Avg confidence: {avg_confidence}%")
        logger.info(f"[BACKTEST] \u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550")

        self.summary = summary
        return summary

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save_results(self, output_path: str = "backend/db/backtest_results.json") -> None:
        """Save the summary dict as JSON to output_path."""
        try:
            os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
            with open(output_path, "w") as f:
                json.dump(self.summary, f, indent=2, default=str)
            logger.info(f"[BACKTEST] Results saved to {output_path}")
        except Exception as e:
            logger.error(f"[BACKTEST] save_results failed: {e}")


if __name__ == "__main__":
    import sys

    csv_path = sys.argv[1] if len(sys.argv) > 1 else "backend/data/sample_ticks.csv"
    window = int(sys.argv[2]) if len(sys.argv) > 2 else 30

    logger.info(f"[BACKTEST] Starting backtest: {csv_path}, window={window}min")
    engine = BacktestEngine(DB_PATH)
    summary = engine.run(csv_path, window_minutes=window)
    engine.save_results()

    print("\n\u2550\u2550\u2550 BACKTEST SUMMARY \u2550\u2550\u2550")
    for k, v in summary.items():
        if k != "signals":
            print(f"  {k}: {v}")
