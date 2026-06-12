import os
import requests
from datetime import datetime
from loguru import logger
from dotenv import load_dotenv

load_dotenv()

MASTER_CONTRACT_URL = (
    "https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json"
)


class InstrumentMapper:
    """Downloads the Angel One master contract and maps NIFTY options tokens."""

    def __init__(self) -> None:
        self.token_map: dict = {}
        self.symbol_map: dict = {}
        self.strike_data: dict = {}
        self.api_key: str = os.getenv("ANGEL_API_KEY", "")
        self.load()

    def download_master_contract(self) -> list:
        """Download the Angel One master contract JSON. Returns [] on failure."""
        try:
            response = requests.get(MASTER_CONTRACT_URL, timeout=30)
            if response.status_code != 200:
                logger.error(
                    f"[TOKEN MAPPER] download_master_contract failed: "
                    f"HTTP {response.status_code}"
                )
                return []
            return response.json()
        except Exception as e:
            logger.error(f"[TOKEN MAPPER] download_master_contract failed: {e}")
            return []

    def load(self) -> None:
        """Filter the master contract to NIFTY options and build lookup maps."""
        try:
            entries = self.download_master_contract()
            for entry in entries:
                symbol = entry.get("symbol", "")
                if entry.get("exch_seg") != "NFO":
                    continue
                if not symbol.startswith("NIFTY"):
                    continue
                if not symbol.endswith(("CE", "PE")):
                    continue

                token = entry.get("token", "")
                # Angel One stores strikes multiplied by 100
                strike = float(entry.get("strike", 0)) / 100
                expiry = entry.get("expiry", "")
                option_type = "CE" if symbol.endswith("CE") else "PE"
                lot_size = int(entry.get("lotsize", 25))

                self.token_map[token] = symbol
                self.symbol_map[symbol] = token
                self.strike_data[token] = {
                    "strike": strike,
                    "option_type": option_type,
                    "expiry": expiry,
                    "symbol": symbol,
                    "lot_size": lot_size,
                }

            logger.info(
                f"[TOKEN MAPPER] Successfully loaded {len(self.token_map)} "
                f"NIFTY option chain instruments into memory."
            )
            if len(self.token_map) == 0:
                logger.warning(
                    "[TOKEN MAPPER] No instruments loaded. "
                    "Check network or Angel One API availability."
                )
        except Exception as e:
            logger.error(f"[TOKEN MAPPER] load failed: {e}")

    def get_token(self, symbol: str) -> str:
        try:
            return self.symbol_map.get(symbol, "")
        except Exception as e:
            logger.error(f"[TOKEN MAPPER] get_token failed: {e}")
            return ""

    def get_symbol(self, token: str) -> str:
        try:
            return self.token_map.get(token, "")
        except Exception as e:
            logger.error(f"[TOKEN MAPPER] get_symbol failed: {e}")
            return ""

    def get_strike_data(self, token: str) -> dict:
        try:
            return self.strike_data.get(token, {})
        except Exception as e:
            logger.error(f"[TOKEN MAPPER] get_strike_data failed: {e}")
            return {}

    def get_all_tokens(self) -> list:
        try:
            return list(self.token_map.keys())
        except Exception as e:
            logger.error(f"[TOKEN MAPPER] get_all_tokens failed: {e}")
            return []

    def get_options_chain(self, expiry: str) -> dict:
        """Return {token: strike_data} for all instruments matching the expiry."""
        try:
            if not expiry:
                return {}
            return {
                token: data
                for token, data in self.strike_data.items()
                if data["expiry"] == expiry
            }
        except Exception as e:
            logger.error(f"[TOKEN MAPPER] get_options_chain failed: {e}")
            return {}

    def get_nearest_expiry(self) -> str:
        """Return the earliest expiry that is today or later, in DDMMMYYYY format."""
        try:
            today = datetime.now().date()
            valid: list = []
            for expiry in {data["expiry"] for data in self.strike_data.values()}:
                if not expiry:
                    continue
                try:
                    parsed = datetime.strptime(expiry, "%d%b%Y").date()
                except ValueError as e:
                    logger.error(
                        f"[TOKEN MAPPER] get_nearest_expiry failed: "
                        f"could not parse expiry '{expiry}': {e}"
                    )
                    continue
                if parsed >= today:
                    valid.append((parsed, expiry))
            if not valid:
                return ""
            return min(valid, key=lambda item: item[0])[1]
        except Exception as e:
            logger.error(f"[TOKEN MAPPER] get_nearest_expiry failed: {e}")
            return ""

    def get_atm_strikes(
        self, spot_price: float, expiry: str, num_strikes: int = 10
    ) -> dict:
        """Return {token: strike_data} for strikes within ATM +/- num_strikes steps of 50."""
        try:
            if not expiry:
                return {}
            atm = round(spot_price / 50) * 50
            strike_list = [
                float(atm + step * 50)
                for step in range(-num_strikes, num_strikes + 1)
            ]
            return {
                token: data
                for token, data in self.strike_data.items()
                if data["expiry"] == expiry and data["strike"] in strike_list
            }
        except Exception as e:
            logger.error(f"[TOKEN MAPPER] get_atm_strikes failed: {e}")
            return {}
