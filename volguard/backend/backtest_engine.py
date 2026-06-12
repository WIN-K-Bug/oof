import os
import uuid
import sqlite3
import threading
import pandas as pd
from datetime import datetime, timedelta
from typing import Optional
from loguru import logger
from dotenv import load_dotenv

load_dotenv()

DB_PATH = os.getenv("DB_PATH", "backend/db/volguard.db")
DAILY_LOSS_LIMIT = float(os.getenv("DAILY_LOSS_LIMIT", 5000))
MIN_CONFIDENCE_SCORE = int(os.getenv("MIN_CONFIDENCE_SCORE", 75))
SIGNAL_COOLDOWN_MINUTES = int(os.getenv("SIGNAL_COOLDOWN_MINUTES", 15))
LOT_SIZE = 25

SPOT_TOKENS = ("99926000", "26000")


def init_backtest_db(db_path: str) -> None:
    """Create the backtest_results and backtest_runs tables if missing."""
    try:
        os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS backtest_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                date TEXT NOT NULL,
                time TEXT NOT NULL,
                signal_type TEXT NOT NULL,
                strike REAL NOT NULL,
                symbol TEXT NOT NULL,
                entry_price REAL NOT NULL,
                stop_loss REAL NOT NULL,
                target REAL NOT NULL,
                outcome TEXT NOT NULL,
                pnl REAL NOT NULL,
                confidence INTEGER NOT NULL,
                spot_price REAL NOT NULL,
                vwap REAL NOT NULL,
                momentum REAL NOT NULL
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS backtest_runs (
                run_id TEXT PRIMARY KEY,
                started_at TEXT NOT NULL,
                completed_at TEXT,
                date_from TEXT NOT NULL,
                date_to TEXT NOT NULL,
                total_signals INTEGER DEFAULT 0,
                wins INTEGER DEFAULT 0,
                losses INTEGER DEFAULT 0,
                expired INTEGER DEFAULT 0,
                total_pnl REAL DEFAULT 0.0,
                win_rate REAL DEFAULT 0.0,
                status TEXT DEFAULT 'RUNNING'
            )
            """
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"[BACKTEST] init_backtest_db failed: {e}")


class BacktestEngine:
    """Minute-by-minute DCE replay engine over historical tick/candle data."""

    def __init__(self, db_path: str = DB_PATH) -> None:
        self.db_path = db_path
        self._lock = threading.Lock()
        self.run_id = str(uuid.uuid4())[:8]
        self.is_running = False
        self.progress = 0  # 0 to 100
        self.progress_message = ""
        self.results: list = []
        self.daily_results: dict = {}
        self.summary: dict = {}
        init_backtest_db(db_path)

    # ------------------------------------------------------------------
    # Gate evaluation (simplified 6-gate replica of the live DCE)
    # ------------------------------------------------------------------

    def _evaluate_gates(self, window: pd.DataFrame, spot_price: float) -> dict:
        """Evaluate the 6 replayable gates on all ticks up to this moment."""
        try:
            # VWAP from option ticks only — never spot index ticks
            options_window = window[~window["token"].isin(["99926000", "26000"])]
            vwap_num = (options_window["ltp"] * options_window["volume"]).sum()
            vwap_den = options_window["volume"].sum()
            vwap = float(vwap_num / vwap_den) if vwap_den > 0 else spot_price

            gate_vwap_valid = vwap > 0
            gate_spot_valid = 15000 < spot_price < 35000

            if vwap > 0:
                deviation = abs(spot_price - vwap) / vwap * 100
                gate_deviation = deviation <= 2.0
                momentum = (spot_price - vwap) / vwap * 100
            else:
                gate_deviation = False
                momentum = 0.0

            gate_momentum = abs(momentum) >= 0.1

            options_live = options_window[options_window["ltp"] > 0]
            gate_options = len(options_live) >= 10

            total_volume = options_window["volume"].sum()
            gate_volume = total_volume >= 10000

            gates_passed = sum(
                [
                    gate_vwap_valid,
                    gate_spot_valid,
                    gate_deviation,
                    gate_momentum,
                    gate_options,
                    gate_volume,
                ]
            )
            confidence = round(gates_passed / 6 * 100)
            direction = "CE" if momentum > 0 else "PE"

            return {
                "vwap": vwap,
                "momentum": momentum,
                "spot_price": spot_price,
                "gates_passed": gates_passed,
                "confidence": confidence,
                "direction": direction,
                "gate_vwap_valid": gate_vwap_valid,
                "gate_spot_valid": gate_spot_valid,
                "gate_deviation": gate_deviation,
                "gate_momentum": gate_momentum,
                "gate_options": gate_options,
                "gate_volume": gate_volume,
            }
        except Exception as e:
            logger.error(f"[BACKTEST] _evaluate_gates failed: {e}")
            return {
                "vwap": 0.0,
                "momentum": 0.0,
                "spot_price": 0.0,
                "gates_passed": 0,
                "confidence": 0,
                "direction": "UNKNOWN",
                "gate_vwap_valid": False,
                "gate_spot_valid": False,
                "gate_deviation": False,
                "gate_momentum": False,
                "gate_options": False,
                "gate_volume": False,
            }

    # ------------------------------------------------------------------
    # Strike selection
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_strike(symbol: str, direction: str) -> float:
        """Extract the strike from an option symbol name. Returns 0.0 if unknown."""
        try:
            idx = symbol.rfind(direction)
            if idx < 0:
                return 0.0
            # Strike after the CE/PE marker (e.g. NIFTY10JUN24CE23500)
            trailing = symbol[idx + 2:]
            if trailing.isdigit():
                return float(trailing)
            # Strike before the CE/PE suffix (e.g. NIFTY27JUN2423550CE)
            digits = ""
            for ch in reversed(symbol[:idx]):
                if ch.isdigit():
                    digits = ch + digits
                else:
                    break
            return float(digits) if digits else 0.0
        except Exception:
            return 0.0

    def _select_strike(
        self, window: pd.DataFrame, direction: str, spot_price: float
    ) -> dict:
        """Pick the best ATM+1 OTM strike in the signal direction by highest OI."""
        try:
            atm = round(spot_price / 50) * 50
            target_strike = atm + 50 if direction == "CE" else atm - 50

            opts = window[~window["token"].isin(["99926000", "26000"])]
            if "timestamp" in opts.columns:
                # Use the most recent tick per symbol
                opts = opts.sort_values("timestamp").groupby("symbol").tail(1)

            best_row = None
            best_oi = -1
            for _, row in opts.iterrows():
                symbol = str(row.get("symbol", "") or "")
                if direction not in symbol:
                    continue
                strike_val = self._extract_strike(symbol, direction)
                if strike_val <= 0 or abs(strike_val - target_strike) > 25:
                    continue
                ltp = float(row.get("ltp", 0.0) or 0.0)
                if ltp <= 0:
                    continue
                oi = int(row.get("oi", 0) or 0)
                if oi > best_oi:
                    best_oi = oi
                    best_row = row

            if best_row is None:
                return {}

            entry_price = float(best_row["ltp"])
            return {
                "symbol": best_row["symbol"],
                "token": str(best_row["token"]),
                "entry_price": entry_price,
                "strike": target_strike,
                "stop_loss": round(entry_price * 0.65, 2),
                "target": round(entry_price * 1.65, 2),
            }
        except Exception as e:
            logger.error(f"[BACKTEST] _select_strike failed: {e}")
            return {}

    # ------------------------------------------------------------------
    # Outcome evaluation
    # ------------------------------------------------------------------

    def _evaluate_outcome(
        self, signal: dict, future_window: pd.DataFrame
    ) -> tuple[str, float]:
        """Scan future ticks of the signal symbol for WIN/LOSS/EXPIRED."""
        try:
            future = future_window[future_window["symbol"] == signal["symbol"]]
            if "timestamp" in future.columns:
                future = future.sort_values("timestamp")
            for _, row in future.iterrows():
                ltp = float(row.get("ltp", 0.0) or 0.0)
                if ltp <= 0:
                    continue
                if ltp >= signal["target"]:
                    return (
                        "WIN",
                        round(
                            (signal["target"] - signal["entry_price"]) * LOT_SIZE, 2
                        ),
                    )
                if ltp <= signal["stop_loss"]:
                    return (
                        "LOSS",
                        round(
                            (signal["stop_loss"] - signal["entry_price"]) * LOT_SIZE,
                            2,
                        ),
                    )
            return ("EXPIRED", 0.0)
        except Exception as e:
            logger.error(f"[BACKTEST] _evaluate_outcome failed: {e}")
            return ("EXPIRED", 0.0)

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _save_signal(self, signal_row: dict) -> None:
        """Insert one signal row into backtest_results (thread-safe)."""
        try:
            with self._lock:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT INTO backtest_results (
                        run_id, date, time, signal_type, strike, symbol,
                        entry_price, stop_loss, target, outcome, pnl,
                        confidence, spot_price, vwap, momentum
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        signal_row.get("run_id"),
                        signal_row.get("date"),
                        signal_row.get("time"),
                        signal_row.get("signal_type"),
                        signal_row.get("strike"),
                        signal_row.get("symbol"),
                        signal_row.get("entry_price"),
                        signal_row.get("stop_loss"),
                        signal_row.get("target"),
                        signal_row.get("outcome"),
                        signal_row.get("pnl"),
                        signal_row.get("confidence"),
                        signal_row.get("spot_price"),
                        signal_row.get("vwap"),
                        signal_row.get("momentum"),
                    ),
                )
                conn.commit()
                conn.close()
        except Exception as e:
            logger.error(f"[BACKTEST] _save_signal failed: {e}")

    def _save_run_metadata(self, date_from: str, date_to: str) -> None:
        """Insert the run row with status RUNNING (thread-safe)."""
        try:
            with self._lock:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO backtest_runs
                        (run_id, started_at, date_from, date_to, status)
                    VALUES (?, ?, ?, ?, 'RUNNING')
                    """,
                    (
                        self.run_id,
                        datetime.now().isoformat(),
                        date_from,
                        date_to,
                    ),
                )
                conn.commit()
                conn.close()
        except Exception as e:
            logger.error(f"[BACKTEST] _save_run_metadata failed: {e}")

    def _finalize_run(
        self,
        total: int,
        wins: int,
        losses: int,
        expired: int,
        total_pnl: float,
        win_rate: float,
    ) -> None:
        """Mark the run COMPLETED with final stats (thread-safe)."""
        try:
            with self._lock:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                cursor.execute(
                    """
                    UPDATE backtest_runs
                    SET completed_at = ?, total_signals = ?, wins = ?,
                        losses = ?, expired = ?, total_pnl = ?, win_rate = ?,
                        status = 'COMPLETED'
                    WHERE run_id = ?
                    """,
                    (
                        datetime.now().isoformat(),
                        total,
                        wins,
                        losses,
                        expired,
                        total_pnl,
                        win_rate,
                        self.run_id,
                    ),
                )
                conn.commit()
                conn.close()
        except Exception as e:
            logger.error(f"[BACKTEST] _finalize_run failed: {e}")

    # ------------------------------------------------------------------
    # Replay
    # ------------------------------------------------------------------

    def run_day(self, day_df: pd.DataFrame, date_str: str) -> dict:
        """Replay one full trading day minute by minute."""
        try:
            minutes = sorted(day_df["timestamp"].unique())
            last_signal_time = None
            day_signals: list = []
            day_pnl = 0.0

            for current_minute in minutes:
                current_minute = pd.Timestamp(current_minute)
                window = day_df[day_df["timestamp"] <= current_minute]

                # Spot price: last spot-token tick, fallback to spot_price column
                spot_rows = window[window["token"].isin(["99926000", "26000"])]
                if not spot_rows.empty:
                    spot_price = float(spot_rows["ltp"].iloc[-1])
                elif "spot_price" in window.columns and not window.empty:
                    spot_price = float(window["spot_price"].iloc[-1])
                else:
                    spot_price = 0.0
                if spot_price <= 0:
                    continue

                gates = self._evaluate_gates(window, spot_price)

                # Cooldown
                if (
                    last_signal_time is not None
                    and (current_minute - last_signal_time).total_seconds()
                    < SIGNAL_COOLDOWN_MINUTES * 60
                ):
                    continue

                if gates["confidence"] >= MIN_CONFIDENCE_SCORE:
                    strike_data = self._select_strike(
                        window, gates["direction"], spot_price
                    )
                    if not strike_data:
                        continue
                    future_window = day_df[day_df["timestamp"] > current_minute]
                    outcome, pnl = self._evaluate_outcome(strike_data, future_window)

                    signal_row = {
                        "run_id": self.run_id,
                        "date": date_str,
                        "time": str(current_minute.time()),
                        "signal_type": f"BUY_{gates['direction']}",
                        "strike": strike_data["strike"],
                        "symbol": strike_data["symbol"],
                        "entry_price": strike_data["entry_price"],
                        "stop_loss": strike_data["stop_loss"],
                        "target": strike_data["target"],
                        "outcome": outcome,
                        "pnl": pnl,
                        "confidence": gates["confidence"],
                        "spot_price": gates["spot_price"],
                        "vwap": gates["vwap"],
                        "momentum": gates["momentum"],
                    }
                    day_signals.append(signal_row)
                    self._save_signal(signal_row)
                    last_signal_time = current_minute
                    day_pnl += pnl

            wins = sum(1 for s in day_signals if s["outcome"] == "WIN")
            losses = sum(1 for s in day_signals if s["outcome"] == "LOSS")
            expired = sum(1 for s in day_signals if s["outcome"] == "EXPIRED")

            logger.info(
                f"[BACKTEST] {date_str}: {len(day_signals)} signals | "
                f"P&L: ₹{day_pnl:.2f} | W:{wins} L:{losses} E:{expired}"
            )

            return {
                "date": date_str,
                "signals": day_signals,
                "total_signals": len(day_signals),
                "wins": wins,
                "losses": losses,
                "expired": expired,
                "day_pnl": day_pnl,
                "win_rate": round(wins / len(day_signals) * 100, 1)
                if day_signals
                else 0.0,
            }
        except Exception as e:
            logger.error(f"[BACKTEST] run_day failed for {date_str}: {e}")
            return {
                "date": date_str,
                "signals": [],
                "total_signals": 0,
                "wins": 0,
                "losses": 0,
                "expired": 0,
                "day_pnl": 0.0,
                "win_rate": 0.0,
            }

    def run(self, df: pd.DataFrame) -> dict:
        """Run the backtest across every trading day in the DataFrame."""
        try:
            self.is_running = True
            self.progress = 0

            if df is None or df.empty:
                self.is_running = False
                return {"error": "No data provided for backtest"}

            dates = sorted(df["timestamp"].dt.date.unique())
            logger.info(
                f"[BACKTEST] Starting run {self.run_id} across "
                f"{len(dates)} trading days"
            )
            self._save_run_metadata(str(dates[0]), str(dates[-1]))

            for i, date in enumerate(dates):
                date_str = str(date)
                self.progress = round((i / len(dates)) * 100)
                self.progress_message = f"Replaying {date_str}..."
                day_df = df[df["timestamp"].dt.date == date]
                day_result = self.run_day(day_df, date_str)
                self.daily_results[date_str] = day_result
                self.results.extend(day_result["signals"])

            total = len(self.results)
            wins = sum(1 for r in self.results if r["outcome"] == "WIN")
            losses = sum(1 for r in self.results if r["outcome"] == "LOSS")
            expired = sum(1 for r in self.results if r["outcome"] == "EXPIRED")
            total_pnl = sum(r["pnl"] for r in self.results)
            win_rate = round(wins / total * 100, 1) if total > 0 else 0.0

            self._finalize_run(total, wins, losses, expired, total_pnl, win_rate)

            self.progress = 100
            self.is_running = False
            self.summary = {
                "run_id": self.run_id,
                "date_from": str(dates[0]),
                "date_to": str(dates[-1]),
                "total_signals": total,
                "wins": wins,
                "losses": losses,
                "expired": expired,
                "total_pnl": round(total_pnl, 2),
                "win_rate": win_rate,
                "daily_results": self.daily_results,
            }

            logger.info(f"[BACKTEST] ═══════════════════════════════════")
            logger.info(f"[BACKTEST] Run {self.run_id} COMPLETED")
            logger.info(f"[BACKTEST] Total signals : {total}")
            logger.info(f"[BACKTEST] Win rate      : {win_rate}%")
            logger.info(f"[BACKTEST] Total P&L     : Rs.{total_pnl:.2f}")
            logger.info(f"[BACKTEST] ═══════════════════════════════════")

            return self.summary
        except Exception as e:
            logger.error(f"[BACKTEST] run failed: {e}")
            self.is_running = False
            return {"error": str(e)}

    # ------------------------------------------------------------------
    # Result queries
    # ------------------------------------------------------------------

    def get_results_from_db(self, run_id: str = None) -> list:
        """Fetch backtest result rows, optionally filtered by run_id."""
        try:
            with self._lock:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                if run_id:
                    cursor.execute(
                        "SELECT * FROM backtest_results WHERE run_id = ? "
                        "ORDER BY id DESC LIMIT 500",
                        (run_id,),
                    )
                else:
                    cursor.execute(
                        "SELECT * FROM backtest_results ORDER BY id DESC LIMIT 500"
                    )
                rows = cursor.fetchall()
                columns = [col[0] for col in cursor.description]
                conn.close()
                return [dict(zip(columns, row)) for row in rows]
        except Exception as e:
            logger.error(f"[BACKTEST] get_results_from_db failed: {e}")
            return []

    def get_runs_from_db(self) -> list:
        """Fetch the 20 most recent backtest runs."""
        try:
            with self._lock:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT * FROM backtest_runs ORDER BY started_at DESC LIMIT 20"
                )
                rows = cursor.fetchall()
                columns = [col[0] for col in cursor.description]
                conn.close()
                return [dict(zip(columns, row)) for row in rows]
        except Exception as e:
            logger.error(f"[BACKTEST] get_runs_from_db failed: {e}")
            return []
