"""
The bridge between Angel One and the database: logs in, pulls prices/history
for every stock in the DB, computes technicals/risk, and writes them back.
Called by the scheduler automatically, and by the "Refresh Now" API route on demand.
"""
import datetime as dt
import logging
import os
import threading

import angel_client
import instruments
import technicals
import db

logger = logging.getLogger("refresh_service")

NIFTY_EXCHANGE = os.environ.get("NIFTY_EXCHANGE", "NSE")
NIFTY_SYMBOLTOKEN = os.environ.get("NIFTY_SYMBOLTOKEN", "99926000")

_refresh_lock = threading.Lock()
_last_error = None
_last_run_at = None


def get_status() -> dict:
    return {"lastRunAt": _last_run_at, "lastError": _last_error}


def refresh_all() -> dict:
    """Logs in once, refreshes every stock in the DB, updates config.nifty12m.
    Safe to call concurrently — only one refresh runs at a time."""
    global _last_error, _last_run_at
    if not _refresh_lock.acquire(blocking=False):
        return {"skipped": True, "reason": "A refresh is already in progress"}

    updated, failed = [], []
    try:
        session = angel_client.login()
        nifty_candles = angel_client.get_historical_candles(session, NIFTY_EXCHANGE, NIFTY_SYMBOLTOKEN, lookback_days=800)
        nifty_close = technicals.candles_to_df(nifty_candles)["close"]
        nifty_12m = technicals.pct_return(nifty_close, 252)

        cfg = db.get_config()
        cfg["nifty12m"] = nifty_12m if nifty_12m == nifty_12m else cfg.get("nifty12m", 14.5)  # skip NaN
        db.save_config(cfg)
        angel_client.rate_limited_sleep()

        for stock in db.list_stocks():
            ticker = stock["ticker"]
            try:
                symboltoken = stock.get("symboltoken") or instruments.find_token(
                    stock["tradingsymbol"], stock["exchange"])
                candles = angel_client.get_historical_candles(session, stock["exchange"], symboltoken, lookback_days=800)
                tr = technicals.compute_technicals_and_risk(candles, nifty_candles)
                now = dt.datetime.now(dt.timezone.utc).isoformat()
                db.update_stock_market_data(
                    ticker, tr["technicals"], tr["risk"], tr["technicals"]["cmp"], symboltoken, now
                )
                updated.append(ticker)
            except Exception as e:
                logger.exception("Failed refreshing %s", ticker)
                failed.append({"ticker": ticker, "error": str(e)})
            angel_client.rate_limited_sleep()

        _last_error = None
    except Exception as e:
        logger.exception("Refresh failed")
        _last_error = str(e)
    finally:
        _last_run_at = dt.datetime.now(dt.timezone.utc).isoformat()
        _refresh_lock.release()

    return {"updated": updated, "failed": failed, "error": _last_error, "at": _last_run_at}


def refresh_one(ticker: str) -> dict:
    """Refreshes a single stock — used right after adding a new one to the watchlist."""
    stock = db.get_stock(ticker)
    if not stock:
        return {"error": f"{ticker} not found"}
    try:
        session = angel_client.login()
        symboltoken = stock.get("symboltoken") or instruments.find_token(stock["tradingsymbol"], stock["exchange"])
        candles = angel_client.get_historical_candles(session, stock["exchange"], symboltoken, lookback_days=800)
        nifty_candles = angel_client.get_historical_candles(session, NIFTY_EXCHANGE, NIFTY_SYMBOLTOKEN, lookback_days=800)
        tr = technicals.compute_technicals_and_risk(candles, nifty_candles)
        now = dt.datetime.now(dt.timezone.utc).isoformat()
        db.update_stock_market_data(ticker, tr["technicals"], tr["risk"], tr["technicals"]["cmp"], symboltoken, now)
        return {"ok": True, "ticker": ticker}
    except Exception as e:
        logger.exception("Failed refreshing %s", ticker)
        return {"error": str(e)}


_fund_refresh_lock = threading.Lock()
_last_fund_error = None
_last_fund_run_at = None


def get_fundamentals_status() -> dict:
    return {"lastRunAt": _last_fund_run_at, "lastError": _last_fund_error}


def refresh_fundamentals_all() -> dict:
    """
    Automated counterpart to the manual "Auto-fetch fundamentals" button —
    runs Yahoo Finance fundamentals fetch for every stock in the DB, on a
    schedule, so the ranked list fills in over time without needing anyone
    to click a per-stock button. Fundamentals change slowly (quarterly at
    most), so this runs far less often than the price refresh — no need to
    hit Yahoo every 30 minutes for numbers that update every few months.
    """
    global _last_fund_error, _last_fund_run_at
    import fundamentals_fetch
    import time

    if not _fund_refresh_lock.acquire(blocking=False):
        return {"skipped": True, "reason": "A fundamentals refresh is already in progress"}

    updated, failed = [], []
    try:
        for stock in db.list_stocks():
            ticker = stock["ticker"]
            try:
                result = fundamentals_fetch.fetch_yahoo_fundamentals(stock["tradingsymbol"], stock["exchange"])
                if result.get("error"):
                    failed.append({"ticker": ticker, "error": result["error"]})
                else:
                    db.upsert_stock_manual(
                        ticker,
                        sector=result.get("sector") if not stock.get("sector") else None,
                        fundamentals=result.get("fundamentals") or None,
                        valuation=result.get("valuation") or None,
                    )
                    updated.append(ticker)
            except Exception as e:
                logger.exception("Failed fetching fundamentals for %s", ticker)
                failed.append({"ticker": ticker, "error": str(e)})
            time.sleep(2)  # be gentle with Yahoo's free, unofficial feed between requests
        _last_fund_error = None
    except Exception as e:
        logger.exception("Fundamentals refresh failed")
        _last_fund_error = str(e)
    finally:
        _last_fund_run_at = dt.datetime.now(dt.timezone.utc).isoformat()
        _fund_refresh_lock.release()

    return {"updated": updated, "failed": failed, "error": _last_fund_error, "at": _last_fund_run_at}
