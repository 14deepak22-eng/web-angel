"""
Tiny SQLite persistence layer. One row per stock (manual + fetched data as
JSON blobs), one row for global config. Good enough for a personal dashboard
tracking a few dozen stocks — swap for Postgres later if you outgrow it.
"""
import json
import os
import sqlite3
import threading

DB_PATH = os.environ.get("DB_PATH", os.path.join(os.path.dirname(__file__), "..", "screener.db"))
_lock = threading.Lock()

DEFAULT_CONFIG = {
    "invWeights": {"quality": 25, "growth": 20, "valuation": 20, "balanceSheet": 15, "cashFlow": 10, "catalyst": 5, "momentum": 5},
    "tradeWeights": {"momentum": 25, "relStrength": 20, "techSetup": 20, "volume": 15, "catalyst": 10, "volRisk": 10},
    "nifty12m": 14.5, "niftyCmp": 24800, "nifty50dma": 24300, "nifty200dma": 23600, "vix": 13.2,
    "capital": 1000000, "riskPct": 1,
}

DEFAULT_STOCK_JSON_FIELDS = {
    "fundamentals": {"roce": 0, "roe": 0, "ebitdaMargin": 0, "marginChgBps": 0, "netMargin": 0,
                      "revCagr3": 0, "revCagr5": 0, "epsCagr3": 0, "epsCagr5": 0, "qoqRev": 0,
                      "de": 0, "intCov": 0, "currentRatio": 0, "cfo": 0, "pat": 1, "fcf": 0,
                      "promoterHold": 0, "promoterPledge": 0},
    "valuation": {"cmp": 0, "pe": None, "fpe": None, "evEbitda": None, "pb": None, "peg": None,
                  "fcfYield": None, "divYield": None, "sectorPE": None, "medianPE": None, "fairValue": None},
    "technicals": {"cmp": 0, "dma20": 0, "dma50": 0, "dma100": 0, "dma200": 0, "rsi": 50, "macd": 0,
                   "adx": 0, "atr": 0, "vol": 0, "avgVol": 0, "high52": 0, "breakout": False,
                   "ret1m": 0, "ret3m": 0, "ret6m": 0, "ret12m": 0},
    "risk": {"beta": 1, "histVol": 0, "dd1y": 0, "dd3y": 0, "currDD": 0, "advt": 0},
    "catalysts": [],
    "hypothesis": {"thesis": "", "horizon": "Long Term", "bullProb": "", "bullRet": "", "baseProb": "",
                    "baseRet": "", "bearProb": "", "bearRet": "", "invalidation": "", "reviewDate": "", "status": "Under Review"},
    "flags": {"debtRising": False, "acctIrreg": False, "majorDilution": False, "insiderSelling": False,
              "relatedParty": False, "govConcern": False},
}


def _conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with _lock, _conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS stocks (
                ticker TEXT PRIMARY KEY,
                sector TEXT DEFAULT '',
                tradingsymbol TEXT,
                exchange TEXT DEFAULT 'NSE',
                symboltoken TEXT,
                fundamentals TEXT, valuation TEXT, technicals TEXT, risk TEXT,
                catalysts TEXT, hypothesis TEXT, flags TEXT,
                updated_at TEXT
            )
        """)
        conn.execute("CREATE TABLE IF NOT EXISTS config (id INTEGER PRIMARY KEY CHECK (id = 1), data TEXT)")
        row = conn.execute("SELECT 1 FROM config WHERE id = 1").fetchone()
        if not row:
            conn.execute("INSERT INTO config (id, data) VALUES (1, ?)", (json.dumps(DEFAULT_CONFIG),))
        conn.commit()


def get_config() -> dict:
    with _conn() as conn:
        row = conn.execute("SELECT data FROM config WHERE id = 1").fetchone()
        return json.loads(row["data"]) if row else dict(DEFAULT_CONFIG)


def save_config(config: dict):
    with _lock, _conn() as conn:
        conn.execute("UPDATE config SET data = ? WHERE id = 1", (json.dumps(config),))
        conn.commit()


def list_stocks() -> list:
    with _conn() as conn:
        rows = conn.execute("SELECT * FROM stocks ORDER BY ticker").fetchall()
        return [_row_to_stock(r) for r in rows]


def get_stock(ticker: str):
    with _conn() as conn:
        row = conn.execute("SELECT * FROM stocks WHERE ticker = ?", (ticker,)).fetchone()
        return _row_to_stock(row) if row else None


def _row_to_stock(row) -> dict:
    return {
        "ticker": row["ticker"], "sector": row["sector"],
        "tradingsymbol": row["tradingsymbol"], "exchange": row["exchange"], "symboltoken": row["symboltoken"],
        "fundamentals": json.loads(row["fundamentals"]), "valuation": json.loads(row["valuation"]),
        "technicals": json.loads(row["technicals"]), "risk": json.loads(row["risk"]),
        "catalysts": json.loads(row["catalysts"]), "hypothesis": json.loads(row["hypothesis"]),
        "flags": json.loads(row["flags"]), "updatedAt": row["updated_at"],
    }


def upsert_stock_manual(ticker: str, sector: str = None, tradingsymbol: str = None, exchange: str = None,
                         fundamentals: dict = None, valuation: dict = None, catalysts: list = None,
                         hypothesis: dict = None, flags: dict = None):
    """Adds a stock if new, or updates the hand-entered fields on an existing one.
    Fetched fields (technicals/risk) are left untouched here — refresh_service.py owns those."""
    existing = get_stock(ticker)
    d = existing or {
        "sector": "", "tradingsymbol": tradingsymbol or "", "exchange": exchange or "NSE", "symboltoken": None,
        "fundamentals": dict(DEFAULT_STOCK_JSON_FIELDS["fundamentals"]),
        "valuation": dict(DEFAULT_STOCK_JSON_FIELDS["valuation"]),
        "technicals": dict(DEFAULT_STOCK_JSON_FIELDS["technicals"]),
        "risk": dict(DEFAULT_STOCK_JSON_FIELDS["risk"]),
        "catalysts": list(DEFAULT_STOCK_JSON_FIELDS["catalysts"]),
        "hypothesis": dict(DEFAULT_STOCK_JSON_FIELDS["hypothesis"]),
        "flags": dict(DEFAULT_STOCK_JSON_FIELDS["flags"]),
        "updatedAt": None,
    }
    if sector is not None: d["sector"] = sector
    if tradingsymbol is not None: d["tradingsymbol"] = tradingsymbol
    if exchange is not None: d["exchange"] = exchange
    if fundamentals is not None: d["fundamentals"] = {**d["fundamentals"], **fundamentals}
    if valuation is not None: d["valuation"] = {**d["valuation"], **valuation}
    if catalysts is not None: d["catalysts"] = catalysts
    if hypothesis is not None: d["hypothesis"] = {**d["hypothesis"], **hypothesis}
    if flags is not None: d["flags"] = {**d["flags"], **flags}

    with _lock, _conn() as conn:
        conn.execute("""
            INSERT INTO stocks (ticker, sector, tradingsymbol, exchange, symboltoken,
                fundamentals, valuation, technicals, risk, catalysts, hypothesis, flags, updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(ticker) DO UPDATE SET
                sector=excluded.sector, tradingsymbol=excluded.tradingsymbol, exchange=excluded.exchange,
                fundamentals=excluded.fundamentals, valuation=excluded.valuation,
                catalysts=excluded.catalysts, hypothesis=excluded.hypothesis, flags=excluded.flags
        """, (ticker, d["sector"], d["tradingsymbol"], d["exchange"], d.get("symboltoken"),
              json.dumps(d["fundamentals"]), json.dumps(d["valuation"]), json.dumps(d["technicals"]),
              json.dumps(d["risk"]), json.dumps(d["catalysts"]), json.dumps(d["hypothesis"]),
              json.dumps(d["flags"]), d.get("updatedAt")))
        conn.commit()


def update_stock_market_data(ticker: str, technicals: dict, risk: dict, cmp_: float, symboltoken: str, updated_at: str):
    with _lock, _conn() as conn:
        row = conn.execute("SELECT valuation FROM stocks WHERE ticker = ?", (ticker,)).fetchone()
        if not row:
            return
        valuation = json.loads(row["valuation"])
        valuation["cmp"] = cmp_
        conn.execute("""
            UPDATE stocks SET technicals=?, risk=?, valuation=?, symboltoken=?, updated_at=? WHERE ticker=?
        """, (json.dumps(technicals), json.dumps(risk), json.dumps(valuation), symboltoken, updated_at, ticker))
        conn.commit()


def delete_stock(ticker: str):
    with _lock, _conn() as conn:
        conn.execute("DELETE FROM stocks WHERE ticker = ?", (ticker,))
        conn.commit()
