"""
Thin wrapper around Angel One's SmartAPI: handles login (TOTP), and fetching
live quotes + historical candles. This talks to Angel One's real servers —
run it on your own machine, not inside a sandboxed environment.
"""
import os
import time
import datetime as dt
from dataclasses import dataclass

import pyotp
from SmartApi import SmartConnect


@dataclass
class AngelSession:
    client: SmartConnect
    feed_token: str
    client_code: str


def login() -> AngelSession:
    """Logs in using credentials from environment variables (see .env.example)."""
    api_key = _require_env("ANGEL_API_KEY")
    client_code = _require_env("ANGEL_CLIENT_CODE")
    mpin = _require_env("ANGEL_MPIN")
    totp_secret = _require_env("ANGEL_TOTP_SECRET")

    client = SmartConnect(api_key)
    totp_code = pyotp.TOTP(totp_secret).now()

    session_data = client.generateSession(client_code, mpin, totp_code)
    if not session_data.get("status", False):
        raise RuntimeError(f"Angel One login failed: {session_data}")

    feed_token = client.getfeedToken()
    return AngelSession(client=client, feed_token=feed_token, client_code=client_code)


def _require_env(name: str) -> str:
    val = os.environ.get(name)
    if not val or "your_" in val:
        raise RuntimeError(
            f"Missing {name}. Copy .env.example to .env and fill in your real Angel One credentials."
        )
    return val


def get_ltp(session: AngelSession, exchange: str, tradingsymbol: str, symboltoken: str) -> dict:
    """Latest traded price + basic quote fields for one instrument."""
    resp = session.client.ltpData(exchange, tradingsymbol, symboltoken)
    if not resp.get("status", False):
        raise RuntimeError(f"ltpData failed for {tradingsymbol}: {resp}")
    return resp["data"]


def get_historical_candles(
    session: AngelSession,
    exchange: str,
    symboltoken: str,
    interval: str = "ONE_DAY",
    lookback_days: int = 400,
) -> list:
    """Daily OHLCV candles for the last `lookback_days` calendar days."""
    to_date = dt.datetime.now()
    from_date = to_date - dt.timedelta(days=lookback_days)
    params = {
        "exchange": exchange,
        "symboltoken": symboltoken,
        "interval": interval,
        "fromdate": from_date.strftime("%Y-%m-%d %H:%M"),
        "todate": to_date.strftime("%Y-%m-%d %H:%M"),
    }
    resp = session.client.getCandleData(params)
    if not resp.get("status", False):
        raise RuntimeError(f"getCandleData failed for token {symboltoken}: {resp}")
    # Each candle: [timestamp, open, high, low, close, volume]
    return resp["data"]


def rate_limited_sleep(seconds: float = 0.35):
    """Angel One rate-limits API calls per second — pause briefly between requests
    when looping over a watchlist so you don't get throttled or blocked."""
    time.sleep(seconds)
