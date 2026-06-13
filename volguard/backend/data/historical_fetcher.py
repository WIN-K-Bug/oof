import os
import io
import csv
import requests
import pandas as pd
from datetime import datetime, timedelta
from typing import Optional
from loguru import logger
from dotenv import load_dotenv

load_dotenv()

ANGEL_API_KEY = os.getenv("ANGEL_API_KEY", "")


class HistoricalFetcher:
    """Fetches historical NIFTY option data from Angel One API or a CSV upload."""

    def __init__(self, auth_token: str = "") -> None:
        self.auth_token = auth_token
        self.base_url = "https://apiconnect.angelbroking.com"
        self.headers = {
            "Authorization": f"Bearer {auth_token}",
            "Content-Type": "application/json",
            "X-ApiKey": ANGEL_API_KEY,
            "X-ClientLocalIP": "127.0.0.1",
            "X-ClientPublicIP": "127.0.0.1",
            "X-MACAddress": "00:00:00:00:00:00",
            "X-PrivateKey": ANGEL_API_KEY,
        }

    def get_last_n_trading_days(self, n: int = 5) -> list:
        """Last n weekdays as 'YYYY-MM-DD' strings, ascending (oldest first)."""
        try:
            days: list = []
            current = datetime.now().date() - timedelta(days=1)
            while len(days) < n:
                if current.weekday() < 5:  # Monday=0 .. Friday=4
                    days.append(current.strftime("%Y-%m-%d"))
                current -= timedelta(days=1)
            return list(reversed(days))
        except Exception as e:
            logger.error(f"[FETCHER] get_last_n_trading_days failed: {e}")
            return []

    def fetch_candle_data(
        self,
        token: str,
        from_date: str,
        to_date: str,
        interval: str = "ONE_MINUTE",
        exchange: str = "NFO",
    ) -> pd.DataFrame:
        """Fetch historical OHLC candles from Angel One for one token."""
        try:
            url = (
                f"{self.base_url}/rest/secure/angelbroking/historical/v1/getCandleData"
            )
            body = {
                "exchange": exchange,
                "symboltoken": token,
                "interval": interval,
                "fromdate": f"{from_date} 09:15",
                "todate": f"{to_date} 15:30",
            }
            response = requests.post(url, json=body, headers=self.headers, timeout=30)
            if response.status_code != 200:
                logger.error(
                    f"[FETCHER] fetch_candle_data HTTP {response.status_code} "
                    f"for token {token}"
                )
                return pd.DataFrame()
            data = response.json()
            candles = data.get("data") or []
            if not candles:
                return pd.DataFrame()
            df = pd.DataFrame(
                candles,
                columns=["timestamp", "open", "high", "low", "close", "volume"],
            )
            df["token"] = str(token)
            df["timestamp"] = pd.to_datetime(df["timestamp"])
            return df
        except Exception as e:
            logger.error(f"[FETCHER] fetch_candle_data failed for token {token}: {e}")
            return pd.DataFrame()

    def fetch_week_data(self, instrument_mapper, days: int = 5) -> pd.DataFrame:
        """Fetch minute candles for all NIFTY options (max 200 tokens) + spot."""
        try:
            days_list = self.get_last_n_trading_days(days)
            if not days_list:
                logger.error("[FETCHER] No trading days could be resolved.")
                return pd.DataFrame()
            from_date = days_list[0]
            to_date = days_list[-1]

            tokens = instrument_mapper.get_all_tokens()[:200]  # avoid rate limits
            frames: list = []
            for token in tokens:
                df = self.fetch_candle_data(token, from_date, to_date)
                if not df.empty:
                    frames.append(df)

            # Special case: spot index fetched from NSE exchange
            spot_df = self.fetch_candle_data(
                "99926000", from_date, to_date, exchange="NSE"
            )
            if not spot_df.empty:
                frames.append(spot_df)

            if not frames:
                logger.error("[FETCHER] No candle data fetched from Angel One.")
                return pd.DataFrame()

            combined = pd.concat(frames, ignore_index=True)
            combined["symbol"] = combined["token"].map(
                lambda t: instrument_mapper.get_symbol(t)
                or ("NIFTY" if t == "99926000" else "")
            )
            # Backtest engine consumes 'ltp' — use candle close as LTP proxy
            combined["ltp"] = combined["close"].astype(float)
            combined["volume"] = combined["volume"].fillna(0).astype(int)
            combined = combined.sort_values("timestamp").reset_index(drop=True)

            # Fill spot_price with the closest spot tick by timestamp
            spot_rows = (
                combined[combined["token"] == "99926000"][["timestamp", "ltp"]]
                .rename(columns={"ltp": "spot_price"})
                .sort_values("timestamp")
            )
            if not spot_rows.empty:
                combined = pd.merge_asof(
                    combined.sort_values("timestamp"),
                    spot_rows,
                    on="timestamp",
                    direction="nearest",
                )
            else:
                combined["spot_price"] = 0.0

            logger.info(
                f"[FETCHER] Fetched {len(combined)} rows across {days} trading days"
            )
            return combined
        except Exception as e:
            logger.error(f"[FETCHER] fetch_week_data failed: {e}")
            return pd.DataFrame()

    def load_from_csv(self, csv_content: str) -> pd.DataFrame:
        """Parse an uploaded CSV string into a backtest-ready DataFrame.

        Expected columns:
        date, time, token, symbol, ltp, oi, volume, iv, bid, ask, spot_price
        """
        try:
            df = pd.read_csv(io.StringIO(csv_content))
            # Cast to str first: pandas may parse date/time columns as
            # non-string dtypes, which breaks string concatenation.
            df["timestamp"] = pd.to_datetime(
                df["date"].astype(str) + " " + df["time"].astype(str)
            )
            for col in ("ltp", "iv", "bid", "ask", "spot_price"):
                if col in df.columns:
                    df[col] = df[col].astype(float)
            for col in ("oi", "volume"):
                if col in df.columns:
                    df[col] = df[col].astype(int)
            df["token"] = df["token"].astype(str)
            df = df.sort_values("timestamp").reset_index(drop=True)
            df = df[df["ltp"] > 0].reset_index(drop=True)
            logger.info(f"[FETCHER] Loaded {len(df)} rows from CSV upload")
            return df
        except Exception as e:
            logger.error(f"[FETCHER] load_from_csv failed: {e}")
            return pd.DataFrame()

    def validate_dataframe(self, df: pd.DataFrame) -> tuple[bool, str]:
        """Check the DataFrame is valid for backtesting."""
        try:
            if df is None or df.empty:
                return (False, "No data loaded")
            required = ["timestamp", "token", "symbol", "ltp", "volume", "spot_price"]
            missing = [c for c in required if c not in df.columns]
            if missing:
                return (False, f"Missing columns: {missing}")
            if len(df) < 10:
                return (False, "Too few rows — need at least 10")
            unique_days = df["timestamp"].dt.date.nunique()
            if unique_days < 1:
                return (False, "Need at least 1 full trading day")
            return (
                True,
                f"Valid: {len(df)} rows across {unique_days} trading days",
            )
        except Exception as e:
            return (False, str(e))
