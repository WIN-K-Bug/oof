import os
import json
import asyncio
import threading
import time
from datetime import datetime
from typing import Callable, Optional
from loguru import logger
from dotenv import load_dotenv
from SmartApi.smartWebSocketV2 import SmartWebSocketV2

load_dotenv()


class WebSocketHandler:
    """Live data ingestion spine: Angel One SmartAPI WebSocket V2 client.

    Receives real-time ticks, normalizes them through a field fallback
    chain, and pushes them to the shared memory buffer via callback.
    """

    def __init__(
        self,
        auth_token: str,
        api_key: str,
        client_code: str,
        feed_token: str,
        on_tick_callback: Callable,
    ) -> None:
        self.auth_token = auth_token
        self.api_key = api_key
        self.client_code = client_code
        self.feed_token = feed_token
        self.on_tick_callback = on_tick_callback
        self.sws = None
        self.is_connected = False
        self.is_running = False
        self._tick_count = 0
        self._last_tick_time: Optional[float] = None
        self._reconnect_delay = 1
        self._subscribed_tokens: list = []
        self._reconnecting = False

    def build_token_list(self, token_map: dict) -> list:
        """Build the Angel One subscription payload: NSE spot + all NFO tokens."""
        try:
            nfo_tokens = list(token_map.keys())
            return [
                {"exchangeType": 1, "tokens": ["99926000", "26000"]},
                {"exchangeType": 2, "tokens": nfo_tokens},
            ]
        except Exception as e:
            logger.error(f"[WS] build_token_list failed: {e}")
            return []

    def parse_tick(self, tick: dict) -> dict:
        """Normalize a raw broker tick via the field fallback chain."""
        if not isinstance(tick, dict):
            return {}
        try:
            token = (
                tick.get("token")
                or tick.get("symbolToken")
                or tick.get("instrumentToken")
                or tick.get("tk")
                or "0"
            )

            # Angel One sends LTP * 100
            ltp = float(
                tick.get("last_traded_price")
                or tick.get("ltp")
                or tick.get("last_price")
                or tick.get("lastTradedPrice")
                or tick.get("lp")
                or 0.0
            ) / 100

            oi = int(
                tick.get("open_interest")
                or tick.get("oi")
                or tick.get("openInterest")
                or 0
            )

            volume = int(
                tick.get("volume_trade_for_the_day")
                or tick.get("volume")
                or tick.get("vol")
                or 0
            )

            bid = float(
                tick.get("best_5_buy_data", [{}])[0].get("price", 0)
                if tick.get("best_5_buy_data")
                else 0
            ) / 100
            ask = float(
                tick.get("best_5_sell_data", [{}])[0].get("price", 0)
                if tick.get("best_5_sell_data")
                else 0
            ) / 100

            iv = float(
                tick.get("implied_volatility")
                or tick.get("iv")
                or 0.0
            )

            return {
                "token": token,
                "ltp": ltp,
                "oi": oi,
                "volume": volume,
                "bid": bid,
                "ask": ask,
                "iv": iv,
                "timestamp": datetime.now().isoformat(),
            }
        except Exception as e:
            logger.error(f"[WS] parse_tick failed: {e}")
            return {}

    def on_data(self, wsapp, message) -> None:
        """Raw callback fired by SmartWebSocketV2 on every tick."""
        try:
            if isinstance(message, (bytes, bytearray)):
                try:
                    message = message.decode("utf-8")
                except Exception:
                    pass

            if isinstance(message, str):
                try:
                    tick_raw = json.loads(message)
                except Exception:
                    tick_raw = message
            else:
                tick_raw = message

            parsed_tick = self.parse_tick(tick_raw)
            if not parsed_tick:
                return

            self._tick_count += 1
            self._last_tick_time = time.time()
            self.on_tick_callback(parsed_tick)

            if self._tick_count % 500 == 0:
                logger.info(
                    f"[WS] Tick #{self._tick_count} received. "
                    f"Token: {parsed_tick['token']} LTP: {parsed_tick['ltp']}"
                )
        except Exception as e:
            logger.error(f"[WS] on_data failed: {e}")

    def on_open(self, wsapp) -> None:
        try:
            self.is_connected = True
            self._reconnect_delay = 1
            logger.info("[WS] WebSocket connection opened successfully.")
            if self._subscribed_tokens:
                self.subscribe(self._subscribed_tokens)
        except Exception as e:
            logger.error(f"[WS] on_open failed: {e}")

    def on_error(self, wsapp, error) -> None:
        self.is_connected = False
        logger.error(f"[WS] WebSocket error: {error}")

    def on_close(self, wsapp) -> None:
        self.is_connected = False
        logger.warning("[WS] WebSocket connection closed.")

    def subscribe(self, token_list: list) -> None:
        """Subscribe in SNAP_QUOTE mode (full market depth + greeks)."""
        try:
            self._subscribed_tokens = token_list
            if self.sws is None or not self.is_connected:
                logger.warning(
                    "[WS] Cannot subscribe: WebSocket not connected. "
                    "Tokens stored for resubscription on connect."
                )
                return
            self.sws.subscribe(
                correlation_id="volguard_v1", mode=3, token_list=token_list
            )
            logger.info(
                f"[WS] Subscribed to "
                f"{sum(len(t.get('tokens', [])) for t in token_list)} instruments."
            )
        except Exception as e:
            logger.error(f"[WS] subscribe failed: {e}")

    def connect(self, token_list: list) -> None:
        """Open the WebSocket connection and wire up callbacks."""
        self._subscribed_tokens = token_list
        self.is_running = True

        self.sws = SmartWebSocketV2(
            auth_token=self.auth_token,
            api_key=self.api_key,
            client_code=self.client_code,
            feed_token=self.feed_token,
        )

        self.sws.on_open = self.on_open
        self.sws.on_data = self.on_data
        self.sws.on_error = self.on_error
        self.sws.on_close = self.on_close

        try:
            self.sws.connect()
        except (ConnectionResetError, ConnectionError, OSError, TimeoutError) as e:
            logger.error(f"[WS] connect failed: {e}")
            if not self._reconnecting:
                self._handle_reconnect()
            else:
                raise
        except Exception as e:
            logger.error(f"[WS] connect failed: {e}")
            if not self._reconnecting:
                self._handle_reconnect()
            else:
                raise

    def _handle_reconnect(self) -> None:
        """Exponential backoff reconnect loop. Runs in a thread (blocking sleep)."""
        self.is_connected = False
        self._reconnecting = True
        try:
            while self.is_running:
                logger.warning(f"[WS] Reconnecting in {self._reconnect_delay}s...")
                time.sleep(self._reconnect_delay)
                self._reconnect_delay = min(self._reconnect_delay * 2, 15)
                try:
                    self.connect(self._subscribed_tokens)
                    break
                except Exception as e:
                    logger.error(f"[WS] Reconnect attempt failed: {e}")
                    continue
        finally:
            self._reconnecting = False

    def disconnect(self) -> None:
        """Stop the handler and close the connection cleanly."""
        self.is_running = False
        self.is_connected = False
        if self.sws is not None:
            try:
                self.sws.close_connection()
            except Exception as e:
                logger.error(f"[WS] disconnect failed: {e}")
        logger.info("[WS] WebSocket disconnected cleanly.")

    def get_health(self) -> dict:
        """Live health metrics for the tick health monitor."""
        return {
            "is_connected": self.is_connected,
            "is_running": self.is_running,
            "tick_count": self._tick_count,
            "last_tick_time": self._last_tick_time,
            "seconds_since_last_tick": (
                round(time.time() - self._last_tick_time, 1)
                if self._last_tick_time
                else None
            ),
            "reconnect_delay": self._reconnect_delay,
        }
