"""
Angel One's APIs need a numeric `symboltoken` for every instrument, not just its
trading symbol. This downloads their public instrument master (once, then caches
it locally) and lets you look up tokens by trading symbol + exchange.
"""
import json
import os
import time

import requests

MASTER_URL = "https://margincalculator.angelone.in/OpenAPI_File/files/OpenAPIScripMaster.json"
CACHE_FILE = os.path.join(os.path.dirname(__file__), "instrument_master.json")
CACHE_MAX_AGE_SECONDS = 24 * 3600  # refresh once a day


def _load_master() -> list:
    if os.path.exists(CACHE_FILE) and (time.time() - os.path.getmtime(CACHE_FILE)) < CACHE_MAX_AGE_SECONDS:
        with open(CACHE_FILE) as fh:
            return json.load(fh)
    resp = requests.get(MASTER_URL, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    with open(CACHE_FILE, "w") as fh:
        json.dump(data, fh)
    return data


def find_token(tradingsymbol: str, exchange: str = "NSE") -> str:
    """e.g. find_token('RELIANCE-EQ', 'NSE') -> '2885'"""
    master = _load_master()
    tradingsymbol_upper = tradingsymbol.upper()
    for row in master:
        if row.get("symbol", "").upper() == tradingsymbol_upper and row.get("exch_seg") == exchange:
            return row["token"]
    raise ValueError(f"Could not find symboltoken for {tradingsymbol} on {exchange}. "
                      f"Check the exact trading symbol format (usually SYMBOL-EQ for equities).")
