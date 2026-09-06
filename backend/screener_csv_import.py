"""
Imports fundamentals from a Screener.in CSV export — the sanctioned way to
get bulk data out of Screener.in (they don't offer a public API, and their
Terms of Service don't permit scraping their pages directly).

How to get the CSV:
  1. On screener.in, build or open a screen containing the columns you want
     (ROCE, Debt to equity, Sales growth 3Years %, Promoter holding, Promoter
     pledge %, etc. — whatever you've added to your screen's columns).
  2. Click "Export to Excel" / "Download" on the results table.
  3. Upload that file here.

Column names in Screener's export can vary depending on what you added to
your screen. COLUMN_MAP below covers the common ones — if your export uses
different header text, add a line here mapping it to the right field name.
"""

import pandas as pd
import io

import db

# Screener.in export column name -> our db.py field name.
# Left side must match your CSV's actual header text exactly.
FUNDAMENTALS_COLUMN_MAP = {
    "ROCE %": "roce",
    "ROE %": "roe",
    "Debt to equity": "de",
    "Sales growth 3Years %": "revCagr3",
    "Sales growth 5Years %": "revCagr5",
    "Profit growth 3Years %": "epsCagr3",
    "Profit growth 5Years %": "epsCagr5",
    "OPM %": "ebitdaMargin",
    "NPM last year %": "netMargin",
    "Promoter holding %": "promoterHold",
    "Pledged percentage": "promoterPledge",
    "Interest Coverage Ratio": "intCov",
    "Current ratio": "currentRatio",
}

VALUATION_COLUMN_MAP = {
    "Price to Earning": "pe",
    "Price to book value": "pb",
    "EV/EBITDA": "evEbitda",
    "Dividend yield %": "divYield",
}

SYMBOL_COLUMNS_TRIED = ["NSE Code", "BSE Code", "Symbol", "Name"]


def _find_symbol_column(df: pd.DataFrame) -> str | None:
    for col in SYMBOL_COLUMNS_TRIED:
        if col in df.columns:
            return col
    return None


def _match_ticker_by_symbol(csv_symbol: str, stocks: list) -> str | None:
    """
    Screener's CSV symbol (e.g. 'RELIANCE') needs matching against our stored
    tradingsymbol (e.g. 'RELIANCE-EQ'). Strips the -EQ/-BE suffix and compares
    case-insensitively.
    """
    csv_symbol_clean = csv_symbol.strip().upper()
    for s in stocks:
        stored = (s.get("tradingsymbol") or "").replace("-EQ", "").replace("-BE", "").strip().upper()
        if stored == csv_symbol_clean:
            return s["ticker"]
    return None


def import_csv(file_bytes: bytes) -> dict:
    """
    Returns {"matched": [...], "unmatched": [...], "error": str|None}
    matched = list of {"ticker": ..., "fields_updated": [...]}
    unmatched = list of CSV symbols that didn't match any stock you've added
    """
    try:
        df = pd.read_csv(io.BytesIO(file_bytes))
    except Exception as e:
        return {"error": f"Could not read this as a CSV file: {e}", "matched": [], "unmatched": []}

    symbol_col = _find_symbol_column(df)
    if not symbol_col:
        return {
            "error": f"Couldn't find a symbol column in this CSV. Expected one of: "
                     f"{', '.join(SYMBOL_COLUMNS_TRIED)}. Found columns: {', '.join(df.columns)}",
            "matched": [], "unmatched": [],
        }

    present_fund_cols = {c: f for c, f in FUNDAMENTALS_COLUMN_MAP.items() if c in df.columns}
    present_val_cols = {c: f for c, f in VALUATION_COLUMN_MAP.items() if c in df.columns}

    if not present_fund_cols and not present_val_cols:
        return {
            "error": "None of the expected fundamentals/valuation columns were found in this CSV. "
                     "Check that your Screener.in screen includes the columns you want to import "
                     "(see this module's docstring for the exact names expected).",
            "matched": [], "unmatched": [],
        }

    stocks = db.list_stocks()
    matched = []
    unmatched = []

    for _, row in df.iterrows():
        csv_symbol = str(row[symbol_col])
        ticker = _match_ticker_by_symbol(csv_symbol, stocks)
        if not ticker:
            unmatched.append(csv_symbol)
            continue

        fundamentals_update = {}
        for csv_col, field in present_fund_cols.items():
            val = row.get(csv_col)
            if pd.notna(val):
                fundamentals_update[field] = float(val)

        valuation_update = {}
        for csv_col, field in present_val_cols.items():
            val = row.get(csv_col)
            if pd.notna(val):
                valuation_update[field] = float(val)

        if fundamentals_update or valuation_update:
            db.upsert_stock_manual(
                ticker,
                fundamentals=fundamentals_update or None,
                valuation=valuation_update or None,
            )
            matched.append({
                "ticker": ticker,
                "fields_updated": list(fundamentals_update.keys()) + list(valuation_update.keys()),
            })

    return {"error": None, "matched": matched, "unmatched": unmatched}
