import os
import sqlite3
import threading
import time
import math
from datetime import datetime, date, timedelta
from typing import Optional, Dict, Any
from loguru import logger
from dotenv import load_dotenv
import pyotp
from SmartApi import SmartConnect
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from data.instrument_mapper import InstrumentMapper
from data.websocket_handler import WebSocketHandler

load_dotenv()

ANGEL_API_KEY = os.getenv("ANGEL_API_KEY", "")
ANGEL_CLIENT_ID = os.getenv("ANGEL_CLIENT_ID", "")
ANGEL_PASSWORD = os.getenv("ANGEL_PASSWORD", "")
ANGEL_TOTP_SECRET = os.getenv("ANGEL_TOTP_SECRET", "")
FASTAPI_PORT = int(os.getenv("FASTAPI_PORT", 8000))
DB_PATH = os.getenv("DB_PATH", "backend/db/volguard.db")
DAILY_LOSS_LIMIT = float(os.getenv("DAILY_LOSS_LIMIT", 5000))
SIGNAL_COOLDOWN_MINUTES = int(os.getenv("SIGNAL_COOLDOWN_MINUTES", 15))
MIN_CONFIDENCE_SCORE = int(os.getenv("MIN_CONFIDENCE_SCORE", 75))


# ---------------------------------------------------------------------------
# Section 2: Angel One Authentication
# ---------------------------------------------------------------------------

def authenticate_angel_one() -> dict:
    """Authenticate with Angel One SmartAPI using TOTP. Returns {} on failure."""
    try:
        totp = pyotp.TOTP(ANGEL_TOTP_SECRET).now()
        obj = SmartConnect(api_key=ANGEL_API_KEY)
        data = obj.generateSession(ANGEL_CLIENT_ID, ANGEL_PASSWORD, totp)
        auth_token = data["data"]["jwtToken"]
        feed_token = obj.getfeedToken()
        refresh_token = data["data"]["refreshToken"]
        logger.info(
            f"[AUTH] Angel One authenticated successfully. Client: {ANGEL_CLIENT_ID}"
        )
        return {
            "auth_token": auth_token,
            "feed_token": feed_token,
            "refresh_token": refresh_token,
        }
    except Exception as e:
        logger.error(f"[AUTH] Angel One authentication failed: {e}")
        return {}


# ---------------------------------------------------------------------------
# Section 3: SQLite Signal Logger
# ---------------------------------------------------------------------------

class SignalLogger:
    """Thread-safe SQLite logger for signals and daily P&L."""

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self._lock = threading.Lock()
        self._init_db()

    def _init_db(self) -> None:
        try:
            with self._lock:
                os.makedirs(os.path.dirname(self.db_path) or ".", exist_ok=True)
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS signals (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp TEXT NOT NULL,
                        signal_type TEXT NOT NULL,
                        strike_price REAL NOT NULL,
                        symbol TEXT NOT NULL,
                        spot_price REAL NOT NULL,
                        confidence_score INTEGER NOT NULL,
                        gates_passed INTEGER NOT NULL,
                        entry_price REAL NOT NULL,
                        stop_loss REAL NOT NULL,
                        target REAL NOT NULL,
                        expiry TEXT NOT NULL,
                        vwap REAL,
                        gss REAL,
                        vanna REAL,
                        iv_skew REAL,
                        iv_rank REAL,
                        outcome TEXT DEFAULT 'PENDING'
                    )
                    """
                )
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS daily_pnl (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        date TEXT NOT NULL,
                        realized_pnl REAL DEFAULT 0.0,
                        signal_count INTEGER DEFAULT 0
                    )
                    """
                )
                conn.commit()
                conn.close()
        except Exception as e:
            logger.error(f"[DB] _init_db failed: {e}")

    def log_signal(self, signal: dict) -> None:
        try:
            with self._lock:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT INTO signals (
                        timestamp, signal_type, strike_price, symbol, spot_price,
                        confidence_score, gates_passed, entry_price, stop_loss,
                        target, expiry, vwap, gss, vanna, iv_skew, iv_rank
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        signal.get("timestamp"),
                        signal.get("signal_type"),
                        signal.get("strike_price"),
                        signal.get("symbol"),
                        signal.get("spot_price"),
                        signal.get("confidence_score"),
                        signal.get("gates_passed"),
                        signal.get("entry_price"),
                        signal.get("stop_loss"),
                        signal.get("target"),
                        signal.get("expiry"),
                        signal.get("vwap"),
                        signal.get("gss"),
                        signal.get("vanna"),
                        signal.get("iv_skew"),
                        signal.get("iv_rank"),
                    ),
                )
                conn.commit()
                conn.close()
            logger.info(
                f"[DB] Signal logged: {signal.get('signal_type')} "
                f"@ {signal.get('strike_price')}"
            )
        except Exception as e:
            logger.error(f"[DB] log_signal failed: {e}")

    def get_today_pnl(self) -> float:
        try:
            with self._lock:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                today = date.today().strftime("%Y-%m-%d")
                cursor.execute(
                    "SELECT realized_pnl FROM daily_pnl WHERE date = ?", (today,)
                )
                row = cursor.fetchone()
                conn.close()
                return float(row[0]) if row else 0.0
        except Exception as e:
            logger.error(f"[DB] get_today_pnl failed: {e}")
            return 0.0

    def get_recent_signals(self, limit: int = 20) -> list:
        try:
            with self._lock:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT * FROM signals ORDER BY id DESC LIMIT ?", (limit,)
                )
                rows = cursor.fetchall()
                columns = [col[0] for col in cursor.description]
                conn.close()
                return [dict(zip(columns, row)) for row in rows]
        except Exception as e:
            logger.error(f"[DB] get_recent_signals failed: {e}")
            return []

    def update_signal_outcome(self, signal_id: int, outcome: str) -> None:
        try:
            with self._lock:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE signals SET outcome = ? WHERE id = ?",
                    (outcome, signal_id),
                )
                conn.commit()
                conn.close()
        except Exception as e:
            logger.error(f"[DB] update_signal_outcome failed: {e}")


# ---------------------------------------------------------------------------
# Section 4: MarketStateManager
# ---------------------------------------------------------------------------

class MarketStateManager:
    """Thread-safe central memory buffer for live market state."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._state: Dict[str, Any] = {}
        self._spot_price: float = 0.0
        self._vwap: float = 0.0
        self._vwap_sum: float = 0.0
        self._vwap_volume: float = 0.0
        self._tick_count: int = 0
        self._last_tick_time: Optional[float] = None
        self._volguard_blocked: bool = False
        self._daily_loss_limit_hit: bool = False
        self._last_signal_time: Optional[float] = None
        self._signal_logger: Optional[SignalLogger] = None
        self._instrument_mapper: Optional[InstrumentMapper] = None

    def attach_logger(self, logger: SignalLogger) -> None:
        self._signal_logger = logger

    def attach_mapper(self, mapper: InstrumentMapper) -> None:
        self._instrument_mapper = mapper

    def on_tick(self, tick: dict) -> None:
        """Callback passed to WebSocketHandler. Updates state, spot, and VWAP."""
        with self._lock:
            token = tick.get("token", "")
            if token in ("99926000", "26000"):
                self._spot_price = tick.get("ltp", self._spot_price)
            self._state[token] = tick

            ltp = tick.get("ltp", 0.0)
            vol = tick.get("volume", 0)
            if ltp > 0 and vol > 0:
                self._vwap_sum += ltp * vol
                self._vwap_volume += vol
                self._vwap = self._vwap_sum / self._vwap_volume

            self._tick_count += 1
            self._last_tick_time = time.time()

    def get_state(self, token: str) -> dict:
        with self._lock:
            return self._state.get(token, {})

    def get_all_states(self) -> dict:
        with self._lock:
            return dict(self._state)

    def get_spot_price(self) -> float:
        with self._lock:
            return self._spot_price

    def get_vwap(self) -> float:
        with self._lock:
            return self._vwap

    def is_market_hours(self) -> bool:
        """True if current IST time is 09:20-15:00 on a weekday."""
        ist_now = datetime.utcnow() + timedelta(hours=5, minutes=30)
        if ist_now.weekday() >= 5:  # Saturday=5, Sunday=6
            return False
        market_open = ist_now.replace(hour=9, minute=20, second=0, microsecond=0)
        market_close = ist_now.replace(hour=15, minute=0, second=0, microsecond=0)
        return market_open <= ist_now <= market_close

    def is_tick_healthy(self) -> bool:
        if self._last_tick_time is None:
            return False
        if self.is_market_hours() and (time.time() - self._last_tick_time) > 10:
            return False
        return True

    def check_cooldown(self) -> bool:
        """True if the signal cooldown window has cleared."""
        if self._last_signal_time is None:
            return True
        if time.time() - self._last_signal_time >= SIGNAL_COOLDOWN_MINUTES * 60:
            return True
        return False

    def set_last_signal_time(self) -> None:
        self._last_signal_time = time.time()


# ---------------------------------------------------------------------------
# Section 4B: Analytics calculators (IV Rank, GSS, Vanna, IV Skew)
# ---------------------------------------------------------------------------

def calculate_iv_rank(current_iv: float, iv_history: list) -> float:
    """IV Rank: position of current IV within its historical range (0-100)."""
    try:
        if not iv_history or len(iv_history) < 2:
            return 50.0
        iv_min = min(iv_history)
        iv_max = max(iv_history)
        if iv_max == iv_min:
            return 50.0
        iv_rank = (current_iv - iv_min) / (iv_max - iv_min) * 100
        return round(iv_rank, 2)
    except Exception as e:
        logger.error(f"[CALC] calculate_iv_rank failed: {e}")
        return 50.0


def calculate_gss(options_states: dict, spot_price: float, strike_map: dict) -> float:
    """Gamma Squeeze Score: OI concentration within 13 strikes around ATM."""
    try:
        atm = round(spot_price / 50) * 50
        atm_range = range(int(atm - 300), int(atm + 350), 50)  # 13 strikes around ATM
        total_oi = 0
        atm_oi = 0
        for token, state in options_states.items():
            oi = int(state.get("oi", 0))
            ltp = float(state.get("ltp", 0.0))
            if oi <= 0 or ltp <= 0:
                continue
            total_oi += oi
            strike = strike_map.get(token, 0.0)
            if strike in atm_range:
                atm_oi += oi
        if total_oi == 0:
            return 0.0
        return round(atm_oi / total_oi, 4)
    except Exception as e:
        logger.error(f"[CALC] calculate_gss failed: {e}")
        return 0.0


def calculate_vanna(options_states: dict, spot_price: float) -> float:
    """Vanna proxy: OI-weighted IV sensitivity across all live contracts."""
    try:
        vanna_sum = 0.0
        for token, state in options_states.items():
            ltp = float(state.get("ltp", 0.0))
            oi = int(state.get("oi", 0))
            iv = float(state.get("iv", 0.0))
            bid = float(state.get("bid", 0.0))
            ask = float(state.get("ask", 0.0))
            if ltp <= 0 or oi <= 0:
                continue
            spread = ask - bid
            if spread <= 0:
                continue
            # Proxy: OI-weighted IV sensitivity
            vanna_contribution = (oi * iv * ltp) / (spread + 0.01)
            vanna_sum += vanna_contribution
        return round(vanna_sum / 1000, 2)  # Scale down for readability
    except Exception as e:
        logger.error(f"[CALC] calculate_vanna failed: {e}")
        return 0.0


def calculate_iv_skew(
    options_states: dict, spot_price: float, strike_map: dict
) -> float:
    """IV Skew: average OTM Put IV minus average OTM Call IV."""
    try:
        atm = round(spot_price / 50) * 50
        put_ivs = []
        call_ivs = []
        for token, state in options_states.items():
            iv = float(state.get("iv", 0.0))
            ltp = float(state.get("ltp", 0.0))
            if iv <= 0 or ltp <= 0:
                continue
            strike = strike_map.get(token, 0.0)
            if strike <= 0:
                continue
            symbol = state.get("symbol", "") or ""
            if symbol.endswith("PE") and strike < atm:  # OTM Put
                put_ivs.append(iv)
            elif symbol.endswith("CE") and strike > atm:  # OTM Call
                call_ivs.append(iv)
        if not put_ivs or not call_ivs:
            return 0.0
        avg_put_iv = sum(put_ivs) / len(put_ivs)
        avg_call_iv = sum(call_ivs) / len(call_ivs)
        return round(avg_put_iv - avg_call_iv, 4)
    except Exception as e:
        logger.error(f"[CALC] calculate_iv_skew failed: {e}")
        return 0.0


# ---------------------------------------------------------------------------
# Section 5: DCE Gates 0-10
# ---------------------------------------------------------------------------

class DirectionalConvictionEngine:
    """Runs the Directional Conviction Engine gate checks (gates 0-10)."""

    def __init__(self, state_manager: MarketStateManager) -> None:
        self.state_manager = state_manager
        self.gates_passed = 0
        self.gate_results: Dict[str, bool] = {}
        self.gate_details: Dict[str, str] = {}
        self._momentum: float = 0.0
        self._gss: float = 0.0
        self._vanna: float = 0.0
        self._iv_skew: float = 0.0
        self._iv_rank: float = 50.0
        self._direction: str = "UNKNOWN"
        self._spread_quality: float = 0.0
        self._total_volume: int = 0
        self._oi_concentration: float = 0.0
        self._bullish_signals: int = 0
        self._bearish_signals: int = 0

    def _record(self, gate_key: str, result: bool, detail: str) -> bool:
        self.gate_results[gate_key] = result
        self.gate_details[gate_key] = detail
        return result

    def gate_0(self) -> bool:
        """Daily Loss Limit."""
        try:
            if self.state_manager._signal_logger is None:
                return self._record(
                    "gate_0", True, "No signal logger attached — loss check skipped."
                )
            pnl = self.state_manager._signal_logger.get_today_pnl()
            if pnl <= -DAILY_LOSS_LIMIT:
                self.state_manager._daily_loss_limit_hit = True
                return self._record(
                    "gate_0",
                    False,
                    f"Daily loss limit hit: ₹{pnl:.0f}. System locked for today.",
                )
            return self._record(
                "gate_0",
                True,
                f"Daily P&L: ₹{pnl:.0f} — within limit of ₹{DAILY_LOSS_LIMIT:.0f}",
            )
        except Exception as e:
            logger.error(f"[DCE] gate_0 failed: {e}")
            return self._record("gate_0", False, f"Gate error: {e}")

    def gate_1(self) -> bool:
        """Market Hours."""
        try:
            if self.state_manager.is_market_hours():
                return self._record("gate_1", True, "Market is open (09:20–15:00 IST)")
            return self._record("gate_1", False, "Outside market hours")
        except Exception as e:
            logger.error(f"[DCE] gate_1 failed: {e}")
            return self._record("gate_1", False, f"Gate error: {e}")

    def gate_2(self) -> bool:
        """Tick Health."""
        try:
            if self.state_manager.is_tick_healthy():
                return self._record(
                    "gate_2",
                    True,
                    f"Data feed healthy. "
                    f"{self.state_manager._tick_count} ticks received.",
                )
            return self._record(
                "gate_2", False, "Stale data feed — no tick in last 10 seconds."
            )
        except Exception as e:
            logger.error(f"[DCE] gate_2 failed: {e}")
            return self._record("gate_2", False, f"Gate error: {e}")

    def gate_3(self) -> bool:
        """Spot Price Valid."""
        try:
            spot = float(self.state_manager.get_spot_price() or 0.0)
            if 15000.0 < spot < 35000.0:
                return self._record("gate_3", True, f"Spot price valid: ₹{spot:.2f}")
            return self._record(
                "gate_3", False, f"Spot price out of valid range: ₹{spot:.2f}"
            )
        except Exception as e:
            logger.error(f"[DCE] gate_3 failed: {e}")
            return self._record("gate_3", False, f"Gate error: {e}")

    def gate_4(self) -> bool:
        """VWAP Calculated."""
        try:
            vwap = float(self.state_manager.get_vwap() or 0.0)
            if vwap > 0.0:
                return self._record("gate_4", True, f"VWAP active: ₹{vwap:.2f}")
            return self._record(
                "gate_4",
                False,
                "VWAP not yet calculated — insufficient volume data.",
            )
        except Exception as e:
            logger.error(f"[DCE] gate_4 failed: {e}")
            return self._record("gate_4", False, f"Gate error: {e}")

    def gate_5(self) -> bool:
        """Spot vs VWAP."""
        try:
            spot = float(self.state_manager.get_spot_price() or 0.0)
            vwap = float(self.state_manager.get_vwap() or 0.0)
            if vwap == 0.0:
                return self._record(
                    "gate_5", False, "VWAP unavailable — cannot compare spot to VWAP."
                )
            deviation = abs(spot - vwap) / vwap * 100
            if deviation <= 2.0:
                return self._record(
                    "gate_5",
                    True,
                    f"Spot ₹{spot:.2f} within 2% of VWAP ₹{vwap:.2f} "
                    f"(dev: {deviation:.2f}%)",
                )
            return self._record(
                "gate_5",
                False,
                f"Spot ₹{spot:.2f} too far from VWAP ₹{vwap:.2f} "
                f"(dev: {deviation:.2f}%) — no clear trend",
            )
        except Exception as e:
            logger.error(f"[DCE] gate_5 failed: {e}")
            return self._record("gate_5", False, f"Gate error: {e}")

    def gate_6(self) -> bool:
        """Signal Cooldown."""
        try:
            if self.state_manager.check_cooldown():
                return self._record(
                    "gate_6", True, "Cooldown cleared. Next signal allowed."
                )
            return self._record(
                "gate_6",
                False,
                f"Signal cooldown active — "
                f"{SIGNAL_COOLDOWN_MINUTES} min between signals.",
            )
        except Exception as e:
            logger.error(f"[DCE] gate_6 failed: {e}")
            return self._record("gate_6", False, f"Gate error: {e}")

    def gate_7(self) -> bool:
        """VolGuard Status."""
        try:
            if not self.state_manager._volguard_blocked:
                return self._record(
                    "gate_7", True, "VolGuard is active and unblocked."
                )
            return self._record(
                "gate_7", False, "VolGuard is blocked — unusual volatility detected."
            )
        except Exception as e:
            logger.error(f"[DCE] gate_7 failed: {e}")
            return self._record("gate_7", False, f"Gate error: {e}")

    def gate_8(self) -> bool:
        """Minimum Tick Count."""
        try:
            tick_count = self.state_manager._tick_count
            if tick_count >= 100:
                return self._record("gate_8", True, f"Sufficient ticks: {tick_count}")
            return self._record(
                "gate_8",
                False,
                f"Warming up — only {tick_count} ticks so far. Need 100.",
            )
        except Exception as e:
            logger.error(f"[DCE] gate_8 failed: {e}")
            return self._record("gate_8", False, f"Gate error: {e}")

    def gate_9(self) -> bool:
        """Options Data Available."""
        try:
            states = self.state_manager.get_all_states()
            options_count = sum(1 for t in states.values() if t.get("ltp", 0) > 0)
            if options_count >= 10:
                return self._record(
                    "gate_9",
                    True,
                    f"{options_count} live option contracts with valid LTP.",
                )
            return self._record(
                "gate_9",
                False,
                f"Insufficient live option data: only {options_count} contracts.",
            )
        except Exception as e:
            logger.error(f"[DCE] gate_9 failed: {e}")
            return self._record("gate_9", False, f"Gate error: {e}")

    def gate_10(self) -> bool:
        """Price Momentum."""
        try:
            spot = float(self.state_manager.get_spot_price() or 0.0)
            vwap = float(self.state_manager.get_vwap() or 0.0)
            if vwap == 0.0:
                return self._record(
                    "gate_10", False, "VWAP unavailable — cannot compute momentum."
                )
            momentum = (spot - vwap) / vwap * 100
            self._momentum = momentum
            if abs(momentum) >= 0.1:
                return self._record(
                    "gate_10", True, f"Momentum: {momentum:+.3f}% from VWAP"
                )
            return self._record(
                "gate_10",
                False,
                f"No directional momentum detected ({momentum:+.3f}%)",
            )
        except Exception as e:
            logger.error(f"[DCE] gate_10 failed: {e}")
            return self._record("gate_10", False, f"Gate error: {e}")

    def run_gates_0_to_10(self) -> dict:
        """Run all gates in order and return aggregated results."""
        self.gates_passed = 0
        self.gate_results = {}
        self.gate_details = {}

        gates = [
            self.gate_0,
            self.gate_1,
            self.gate_2,
            self.gate_3,
            self.gate_4,
            self.gate_5,
            self.gate_6,
            self.gate_7,
            self.gate_8,
            self.gate_9,
            self.gate_10,
        ]
        for gate in gates:
            if gate():
                self.gates_passed += 1

        return {
            "gates_passed": self.gates_passed,
            "gate_results": self.gate_results,
            "gate_details": self.gate_details,
        }

    def gate_11(self) -> bool:
        """Gamma Squeeze Score."""
        try:
            states = self.state_manager.get_all_states()
            spot = float(self.state_manager.get_spot_price() or 0.0)
            strike_map = {}
            if self.state_manager._instrument_mapper:
                for token in states:
                    sd = self.state_manager._instrument_mapper.get_strike_data(token)
                    if sd:
                        strike_map[token] = sd.get("strike", 0.0)
            gss = calculate_gss(states, spot, strike_map)
            self._gss = gss
            if gss >= 0.60:
                return self._record(
                    "gate_11",
                    True,
                    f"GSS: {gss:.4f} — institutional gamma concentration confirmed.",
                )
            return self._record(
                "gate_11",
                False,
                f"GSS: {gss:.4f} — below 0.60 threshold. Weak gamma concentration.",
            )
        except Exception as e:
            logger.error(f"[DCE] gate_11 failed: {e}")
            return self._record("gate_11", False, f"Gate error: {e}")

    def gate_12(self) -> bool:
        """Vanna Trigger."""
        try:
            states = self.state_manager.get_all_states()
            spot = float(self.state_manager.get_spot_price() or 0.0)
            vanna = calculate_vanna(states, spot)
            self._vanna = vanna
            if abs(vanna) >= 5000:
                return self._record(
                    "gate_12",
                    True,
                    f"Vanna: {vanna:.2f} — institutional momentum confirmed.",
                )
            return self._record(
                "gate_12", False, f"Vanna: {vanna:.2f} — below |5000| threshold."
            )
        except Exception as e:
            logger.error(f"[DCE] gate_12 failed: {e}")
            return self._record("gate_12", False, f"Gate error: {e}")

    def gate_13(self) -> bool:
        """IV Rank Skew."""
        try:
            states = self.state_manager.get_all_states()
            spot = float(self.state_manager.get_spot_price() or 0.0)
            strike_map = {}
            if self.state_manager._instrument_mapper:
                for token in states:
                    sd = self.state_manager._instrument_mapper.get_strike_data(token)
                    if sd:
                        strike_map[token] = sd.get("strike", 0.0)
            iv_skew = calculate_iv_skew(states, spot, strike_map)
            self._iv_skew = iv_skew
            all_ivs = [
                float(s.get("iv", 0.0))
                for s in states.values()
                if float(s.get("iv", 0.0)) > 0
            ]
            current_iv = sum(all_ivs) / len(all_ivs) if all_ivs else 0.0
            iv_rank = calculate_iv_rank(current_iv, all_ivs)
            self._iv_rank = iv_rank
            if abs(iv_skew) > 3.0:
                return self._record(
                    "gate_13",
                    True,
                    f"IV Skew: {iv_skew:.4f} — directional asymmetry confirmed. "
                    f"IV Rank: {iv_rank:.1f}",
                )
            return self._record(
                "gate_13",
                False,
                f"IV Skew: {iv_skew:.4f} — below |3.0| threshold. "
                f"IV Rank: {iv_rank:.1f}",
            )
        except Exception as e:
            logger.error(f"[DCE] gate_13 failed: {e}")
            return self._record("gate_13", False, f"Gate error: {e}")

    def gate_14(self) -> bool:
        """Bid-Ask Spread Quality."""
        try:
            states = self.state_manager.get_all_states()
            tight_spreads = 0
            total_checked = 0
            for state in states.values():
                bid = float(state.get("bid", 0.0))
                ask = float(state.get("ask", 0.0))
                ltp = float(state.get("ltp", 0.0))
                if ltp <= 0 or bid <= 0 or ask <= 0:
                    continue
                total_checked += 1
                spread_pct = (ask - bid) / ltp * 100
                if spread_pct <= 5.0:  # spread within 5% of LTP = liquid
                    tight_spreads += 1
            if total_checked == 0:
                return self._record(
                    "gate_14",
                    False,
                    "No contracts with valid bid/ask quotes to assess liquidity.",
                )
            ratio = tight_spreads / total_checked
            self._spread_quality = ratio
            if ratio >= 0.60:
                return self._record(
                    "gate_14", True, f"Spread quality: {ratio:.1%} contracts liquid."
                )
            return self._record(
                "gate_14",
                False,
                f"Poor liquidity: only {ratio:.1%} contracts have tight spreads.",
            )
        except Exception as e:
            logger.error(f"[DCE] gate_14 failed: {e}")
            return self._record("gate_14", False, f"Gate error: {e}")

    def gate_15(self) -> bool:
        """Volume Confirmation."""
        try:
            states = self.state_manager.get_all_states()
            total_volume = sum(int(s.get("volume", 0)) for s in states.values())
            self._total_volume = total_volume
            if total_volume >= 10000:
                return self._record(
                    "gate_15",
                    True,
                    f"Total options volume: {total_volume:,} — confirmed.",
                )
            return self._record(
                "gate_15",
                False,
                f"Low volume: {total_volume:,} — below 10,000 threshold.",
            )
        except Exception as e:
            logger.error(f"[DCE] gate_15 failed: {e}")
            return self._record("gate_15", False, f"Gate error: {e}")

    def gate_16(self) -> bool:
        """OI Concentration."""
        try:
            states = self.state_manager.get_all_states()
            spot = float(self.state_manager.get_spot_price() or 0.0)
            atm = round(spot / 50) * 50
            total_oi = sum(int(s.get("oi", 0)) for s in states.values())
            if total_oi == 0:
                return self._record(
                    "gate_16", False, "No open interest data available."
                )
            atm_oi = 0
            for token, state in states.items():
                oi = int(state.get("oi", 0))
                if self.state_manager._instrument_mapper:
                    sd = self.state_manager._instrument_mapper.get_strike_data(token)
                    if sd:
                        strike = sd.get("strike", 0.0)
                        if abs(strike - atm) <= 200:
                            atm_oi += oi
            concentration = atm_oi / total_oi if total_oi > 0 else 0.0
            self._oi_concentration = concentration
            if concentration >= 0.30:
                return self._record(
                    "gate_16",
                    True,
                    f"OI concentration near ATM: {concentration:.1%}",
                )
            return self._record(
                "gate_16",
                False,
                f"Weak OI concentration near ATM: {concentration:.1%} — below 30%",
            )
        except Exception as e:
            logger.error(f"[DCE] gate_16 failed: {e}")
            return self._record("gate_16", False, f"Gate error: {e}")

    def gate_17(self) -> bool:
        """Directional Alignment."""
        try:
            momentum = getattr(self, "_momentum", 0.0)
            iv_skew = getattr(self, "_iv_skew", 0.0)
            vanna = getattr(self, "_vanna", 0.0)

            bullish_signals = 0
            bearish_signals = 0

            if momentum > 0:
                bullish_signals += 1
            else:
                bearish_signals += 1

            if iv_skew < 0:  # negative skew = calls expensive = bullish
                bullish_signals += 1
            else:
                bearish_signals += 1

            if vanna > 0:
                bullish_signals += 1
            else:
                bearish_signals += 1

            self._direction = "CE" if bullish_signals >= 2 else "PE"
            self._bullish_signals = bullish_signals
            self._bearish_signals = bearish_signals

            if bullish_signals >= 2 or bearish_signals >= 2:
                return self._record(
                    "gate_17",
                    True,
                    f"Direction: "
                    f"{'BULLISH' if self._direction == 'CE' else 'BEARISH'} "
                    f"({bullish_signals} bull / {bearish_signals} bear "
                    f"signals aligned)",
                )
            return self._record(
                "gate_17", False, "Mixed signals — no directional consensus."
            )
        except Exception as e:
            logger.error(f"[DCE] gate_17 failed: {e}")
            return self._record("gate_17", False, f"Gate error: {e}")

    def run_gates_11_to_17(self) -> dict:
        """Run gates 11-17, accumulating into the existing gates_passed counter."""
        gates = [
            self.gate_11,
            self.gate_12,
            self.gate_13,
            self.gate_14,
            self.gate_15,
            self.gate_16,
            self.gate_17,
        ]
        for gate in gates:
            if gate():
                self.gates_passed += 1

        return {
            "gates_passed": self.gates_passed,
            "gate_results": self.gate_results,
            "gate_details": self.gate_details,
        }

    def run_all_gates(self) -> dict:
        """Run all 18 gates (0-17) and compute the confidence score."""
        self.run_gates_0_to_10()
        self.run_gates_11_to_17()

        total_gates = 18  # gates 0-17
        confidence = round((self.gates_passed / total_gates) * 100)

        return {
            "gates_passed": self.gates_passed,
            "total_gates": total_gates,
            "confidence_score": confidence,
            "gate_results": self.gate_results,
            "gate_details": self.gate_details,
            "direction": getattr(self, "_direction", "UNKNOWN"),
            "momentum": getattr(self, "_momentum", 0.0),
            "gss": getattr(self, "_gss", 0.0),
            "vanna": getattr(self, "_vanna", 0.0),
            "iv_skew": getattr(self, "_iv_skew", 0.0),
            "iv_rank": getattr(self, "_iv_rank", 50.0),
        }


# ---------------------------------------------------------------------------
# Section 5B: Signal Output Engine
# ---------------------------------------------------------------------------

def generate_signal(
    dce_result: dict,
    state_manager: "MarketStateManager",
    instrument_mapper: InstrumentMapper,
) -> dict:
    """Produce a trade signal from the full DCE result. Always returns a dict."""
    try:
        # Step 1 — Confidence gate
        confidence = dce_result.get("confidence_score", 0)
        if confidence < MIN_CONFIDENCE_SCORE:
            return {
                "signal": "NO_TRADE",
                "reason": f"Confidence {confidence}% below minimum "
                f"{MIN_CONFIDENCE_SCORE}%",
            }

        # Step 2 — Direction
        direction = dce_result.get("direction", "UNKNOWN")
        if direction == "UNKNOWN":
            return {
                "signal": "NO_TRADE",
                "reason": "No directional consensus from DCE",
            }

        # Step 3 — Strike selection
        spot = float(state_manager.get_spot_price() or 0.0)
        expiry = instrument_mapper.get_nearest_expiry()
        atm = round(spot / 50) * 50

        # Select strike: ATM + 1 step OTM in signal direction
        if direction == "CE":
            target_strike = atm + 50  # slightly OTM call
        else:
            target_strike = atm - 50  # slightly OTM put

        # Find the token for this strike + direction
        atm_strikes = instrument_mapper.get_atm_strikes(spot, expiry, num_strikes=3)
        selected_token = None
        selected_symbol = None
        best_oi = 0

        for token, data in atm_strikes.items():
            if data.get("option_type") != direction:
                continue
            if abs(data.get("strike", 0) - target_strike) > 25:
                continue
            # Pick by highest OI — institutional preference
            state = state_manager.get_state(token)
            oi = int(state.get("oi", 0))
            if oi > best_oi:
                best_oi = oi
                selected_token = token
                selected_symbol = data.get("symbol", "")

        # Step 4 — Entry price and risk levels
        if not selected_token:
            return {
                "signal": "NO_TRADE",
                "reason": "No valid strike found for signal direction",
            }

        state = state_manager.get_state(selected_token)
        entry_price = float(state.get("ltp", 0.0))

        if entry_price <= 0:
            return {
                "signal": "NO_TRADE",
                "reason": "Invalid entry price (LTP is 0)",
            }

        # Risk management
        stop_loss = round(entry_price * 0.65, 2)  # 35% stop loss
        target = round(entry_price * 1.65, 2)  # 65% target
        risk_reward = round((target - entry_price) / (entry_price - stop_loss), 2)

        # Step 5 — Build and return signal dict
        signal = {
            "signal": f"BUY_{direction}",
            "symbol": selected_symbol,
            "strike_price": target_strike,
            "expiry": expiry,
            "entry_price": entry_price,
            "stop_loss": stop_loss,
            "target": target,
            "risk_reward": risk_reward,
            "spot_price": spot,
            "confidence_score": confidence,
            "gates_passed": dce_result.get("gates_passed", 0),
            "direction": direction,
            "vwap": float(state_manager.get_vwap() or 0.0),
            "gss": dce_result.get("gss", 0.0),
            "vanna": dce_result.get("vanna", 0.0),
            "iv_skew": dce_result.get("iv_skew", 0.0),
            "iv_rank": dce_result.get("iv_rank", 50.0),
            "timestamp": datetime.now().isoformat(),
            "cooldown_active": not state_manager.check_cooldown(),
        }

        # Log to SQLite
        if state_manager._signal_logger:
            state_manager._signal_logger.log_signal(signal)
            state_manager.set_last_signal_time()

        return signal
    except Exception as e:
        logger.error(f"[SIGNAL] generate_signal failed: {e}")
        return {"signal": "NO_TRADE", "reason": f"Signal generation error: {e}"}


# ---------------------------------------------------------------------------
# Section 6: FastAPI app initialization (routes added in later prompts)
# ---------------------------------------------------------------------------

app = FastAPI(title="VolGuard API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

state_manager = MarketStateManager()
signal_logger = SignalLogger(DB_PATH)
instrument_mapper = InstrumentMapper()
dce = DirectionalConvictionEngine(state_manager)

state_manager.attach_logger(signal_logger)
state_manager.attach_mapper(instrument_mapper)

# Module-level runtime state (must be initialized before the routes)
latest_dce_result: dict = {}
latest_signal: dict = {}
ws_handler: Optional[WebSocketHandler] = None


# ---------------------------------------------------------------------------
# Section 7: Background DCE Evaluation Loop
# ---------------------------------------------------------------------------

def run_dce_loop(state_mgr: MarketStateManager, mapper: InstrumentMapper) -> None:
    """Background thread: evaluate all DCE gates every 1 second."""
    global latest_dce_result, latest_signal
    logger.info("[DCE] Background evaluation loop started.")
    while True:
        try:
            time.sleep(1)
            dce = DirectionalConvictionEngine(state_mgr)
            result = dce.run_all_gates()
            latest_dce_result = result

            # Tick health monitor — warn if stale during market hours
            if state_mgr.is_market_hours() and not state_mgr.is_tick_healthy():
                logger.warning(
                    "[HEALTH] ⚠️ Stale data feed detected — no tick in last "
                    "10 seconds. Signals suppressed until feed recovers."
                )
                latest_signal = {"signal": "NO_TRADE", "reason": "Stale data feed"}
                continue  # Skip signal generation this cycle

            # Only attempt signal generation if confidence >= threshold
            confidence = result.get("confidence_score", 0)
            if confidence >= MIN_CONFIDENCE_SCORE:
                signal = generate_signal(result, state_mgr, mapper)
                if signal.get("signal") != "NO_TRADE":
                    latest_signal = signal
                    logger.info(
                        f"[SIGNAL] {signal['signal']} | "
                        f"Strike: {signal['strike_price']} | "
                        f"Entry: ₹{signal['entry_price']} | "
                        f"SL: ₹{signal['stop_loss']} | "
                        f"Target: ₹{signal['target']} | "
                        f"Confidence: {confidence}%"
                    )
        except Exception as e:
            logger.error(f"[DCE] Loop error: {e}")
            time.sleep(1)


# ---------------------------------------------------------------------------
# Section 8: Application Startup
# ---------------------------------------------------------------------------

def startup() -> None:
    """One-time startup: authenticate, launch WebSocket and DCE threads."""
    global ws_handler

    logger.info("[VOLGUARD] ═══════════════════════════════════")
    logger.info("[VOLGUARD] VolGuard Signal System Starting...")
    logger.info("[VOLGUARD] ═══════════════════════════════════")

    # Step 1: Authenticate with Angel One
    auth = authenticate_angel_one()
    if not auth:
        logger.error(
            "[VOLGUARD] Authentication failed. Running in offline/demo mode."
        )
        auth = {"auth_token": "demo", "feed_token": "demo", "refresh_token": "demo"}

    # Step 2: InstrumentMapper is already loaded (singleton at module level)
    logger.info(
        f"[VOLGUARD] Instrument mapper ready: "
        f"{len(instrument_mapper.token_map)} tokens"
    )

    # Step 3: Launch WebSocket handler in background thread
    def launch_websocket():
        global ws_handler
        try:
            token_list = instrument_mapper.build_token_list(
                instrument_mapper.token_map
            ) if hasattr(instrument_mapper, "build_token_list") else None
            ws_handler = WebSocketHandler(
                auth_token=auth["auth_token"],
                api_key=ANGEL_API_KEY,
                client_code=ANGEL_CLIENT_ID,
                feed_token=auth["feed_token"],
                on_tick_callback=state_manager.on_tick,
            )
            if token_list is None:
                token_list = ws_handler.build_token_list(
                    instrument_mapper.token_map
                )
            ws_handler.connect(token_list)
        except Exception as e:
            logger.error(f"[VOLGUARD] WebSocket launch failed: {e}")

    ws_thread = threading.Thread(
        target=launch_websocket, daemon=True, name="WebSocketThread"
    )
    ws_thread.start()
    logger.info("[VOLGUARD] WebSocket thread launched.")

    # Step 4: Launch DCE evaluation loop in background thread
    dce_thread = threading.Thread(
        target=run_dce_loop,
        args=(state_manager, instrument_mapper),
        daemon=True,
        name="DCELoopThread",
    )
    dce_thread.start()
    logger.info("[VOLGUARD] DCE evaluation loop launched.")
    logger.info("[VOLGUARD] System ready. Listening for market data...")


# ---------------------------------------------------------------------------
# Section 9: FastAPI Routes
# ---------------------------------------------------------------------------

@app.get("/health")
def health_check():
    try:
        return {
            "status": "ok",
            "timestamp": datetime.now().isoformat(),
            "version": "1.0.0",
        }
    except Exception as e:
        logger.error(f"[API] /health failed: {e}")
        return {"status": "error", "error": str(e)}


@app.get("/api/dashboard")
def get_dashboard():
    try:
        spot = float(state_manager.get_spot_price() or 0.0)
        vwap = float(state_manager.get_vwap() or 0.0)
        tick_count = state_manager._tick_count
        ws_connected = ws_handler.is_connected if ws_handler else False
        tick_healthy = state_manager.is_tick_healthy()
        market_hours = state_manager.is_market_hours()
        volguard_blocked = state_manager._volguard_blocked
        daily_loss_hit = state_manager._daily_loss_limit_hit
        confidence = latest_dce_result.get("confidence_score", 0)
        gates_passed = latest_dce_result.get("gates_passed", 0)

        return {
            # Top-level flat keys (for simple UI access)
            "tick_count": tick_count,
            "volguard_blocked": volguard_blocked,
            "market_hours_active": market_hours,
            "websocket_connected": ws_connected,
            "tick_healthy": tick_healthy,
            "daily_loss_limit_hit": daily_loss_hit,
            "spot_price": spot,
            "vwap": vwap,
            "confidence_score": confidence,
            "gates_passed": gates_passed,
            # Nested system_status block
            "system_status": {
                "volguard_blocked": volguard_blocked,
                "market_hours_active": market_hours,
                "websocket_connected": ws_connected,
                "tick_healthy": tick_healthy,
                "daily_loss_limit_hit": daily_loss_hit,
                "uptime_ticks": tick_count,
            },
            # Nested market_state block
            "market_state": {
                "spot_price": spot,
                "vwap": vwap,
                "volguard_blocked": volguard_blocked,
                "market_hours_active": market_hours,
                "websocket_connected": ws_connected,
                "tick_count": tick_count,
                "tick_healthy": tick_healthy,
            },
            # DCE result block
            "dce": latest_dce_result,
            # Latest signal block
            "signal": latest_signal,
        }
    except Exception as e:
        logger.error(f"[API] /api/dashboard failed: {e}")
        return {"error": str(e), "timestamp": datetime.now().isoformat()}


@app.get("/api/gates")
def get_gates():
    try:
        return {
            "gates_passed": latest_dce_result.get("gates_passed", 0),
            "total_gates": latest_dce_result.get("total_gates", 18),
            "confidence_score": latest_dce_result.get("confidence_score", 0),
            "gate_results": latest_dce_result.get("gate_results", {}),
            "gate_details": latest_dce_result.get("gate_details", {}),
            "direction": latest_dce_result.get("direction", "UNKNOWN"),
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        logger.error(f"[API] /api/gates failed: {e}")
        return {"error": str(e), "timestamp": datetime.now().isoformat()}


@app.get("/api/signal")
def get_signal():
    try:
        if not latest_signal:
            return {
                "signal": "NO_TRADE",
                "reason": "No signal generated yet",
                "timestamp": datetime.now().isoformat(),
            }
        return latest_signal
    except Exception as e:
        logger.error(f"[API] /api/signal failed: {e}")
        return {"error": str(e), "timestamp": datetime.now().isoformat()}


@app.get("/api/signals/history")
def get_signal_history(limit: int = 20):
    try:
        signals = signal_logger.get_recent_signals(limit=limit)
        return {
            "signals": signals,
            "count": len(signals),
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        logger.error(f"[API] /api/signals/history failed: {e}")
        return {"error": str(e), "timestamp": datetime.now().isoformat()}


@app.get("/api/status")
def get_status():
    try:
        ws_health = ws_handler.get_health() if ws_handler else {}
        return {
            "system": "VolGuard v1.0",
            "websocket": ws_health,
            "tick_count": state_manager._tick_count,
            "spot_price": state_manager.get_spot_price(),
            "vwap": state_manager.get_vwap(),
            "market_hours": state_manager.is_market_hours(),
            "tick_healthy": state_manager.is_tick_healthy(),
            "volguard_blocked": state_manager._volguard_blocked,
            "daily_loss_hit": state_manager._daily_loss_limit_hit,
            "confidence_score": latest_dce_result.get("confidence_score", 0),
            "cooldown_active": not state_manager.check_cooldown(),
            "today_pnl": signal_logger.get_today_pnl(),
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        logger.error(f"[API] /api/status failed: {e}")
        return {"error": str(e), "timestamp": datetime.now().isoformat()}


@app.post("/api/volguard/toggle")
def toggle_volguard():
    try:
        state_manager._volguard_blocked = not state_manager._volguard_blocked
        status = "BLOCKED" if state_manager._volguard_blocked else "ACTIVE"
        logger.info(f"[VOLGUARD] VolGuard manually toggled: {status}")
        return {
            "volguard_blocked": state_manager._volguard_blocked,
            "status": status,
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        logger.error(f"[API] /api/volguard/toggle failed: {e}")
        return {"error": str(e), "timestamp": datetime.now().isoformat()}


@app.post("/api/signals/{signal_id}/outcome")
def update_outcome(signal_id: int, outcome: str):
    from fastapi import HTTPException
    try:
        valid_outcomes = ["WIN", "LOSS", "PENDING", "EXPIRED"]
        if outcome not in valid_outcomes:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid outcome. Must be one of: {valid_outcomes}",
            )
        signal_logger.update_signal_outcome(signal_id, outcome)
        return {
            "signal_id": signal_id,
            "outcome": outcome,
            "timestamp": datetime.now().isoformat(),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[API] /api/signals/outcome failed: {e}")
        return {"error": str(e), "timestamp": datetime.now().isoformat()}


# ---------------------------------------------------------------------------
# Section 10: FastAPI Startup Event
# ---------------------------------------------------------------------------

@app.on_event("startup")
async def on_startup():
    thread = threading.Thread(target=startup, daemon=True, name="StartupThread")
    thread.start()


if __name__ == "__main__":
    logger.info("[VOLGUARD] Launching VolGuard...")
    uvicorn.run("main:app", host="0.0.0.0", port=FASTAPI_PORT, reload=False)
