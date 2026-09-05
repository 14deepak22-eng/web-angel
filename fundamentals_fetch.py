"""
Auto-fills what it can from Yahoo Finance's free data feed (via the `yfinance`
library). This is NOT an official API — it's unofficial and can occasionally
break or return incomplete data, especially for smaller/less-covered stocks.
Treat it as a time-saving starting point, not a source of truth: always
sanity-check against Screener.in before trusting a number, and there are
several fields (ROCE, promoter holding/pledge, true 3-year CAGR, margin
*trend*) it simply cannot provide — those still need manual entry.
"""
import yfinance as yf


def fetch_yahoo_fundamentals(tradingsymbol: str, exchange: str = "NSE") -> dict:
    """
    tradingsymbol: e.g. 'RELIANCE-EQ' (we strip the '-EQ' and add the Yahoo suffix)
    Returns a dict with 'fundamentals' and 'valuation' partials (only the keys
    that were actually available), plus a 'warnings' list explaining any gaps.
    """
    base_symbol = tradingsymbol.replace("-EQ", "").replace("-BE", "")
    yahoo_suffix = ".NS" if exchange.upper() == "NSE" else ".BO"
    yahoo_symbol = f"{base_symbol}{yahoo_suffix}"

    warnings = []
    fundamentals = {}
    valuation = {}

    try:
        info = yf.Ticker(yahoo_symbol).info
    except Exception as e:
        return {"error": f"Could not reach Yahoo Finance for {yahoo_symbol}: {e}"}

    if not info or info.get("regularMarketPrice") is None:
        return {"error": f"No data returned for {yahoo_symbol} — check the trading symbol is correct."}

    def pct(x):
        """Yahoo often returns ratios as decimals (0.15 = 15%) — convert to our whole-number-percent convention."""
        return round(x * 100, 2) if x is not None else None

    # ---- Valuation (generally the most reliable part of this feed) ----
    valuation["cmp"] = info.get("regularMarketPrice") or info.get("currentPrice")
    valuation["pe"] = info.get("trailingPE")
    valuation["fpe"] = info.get("forwardPE")
    valuation["evEbitda"] = info.get("enterpriseToEbitda")
    valuation["pb"] = info.get("priceToBook")
    valuation["divYield"] = pct(info.get("dividendYield"))
    valuation = {k: v for k, v in valuation.items() if v is not None}

    # ---- Fundamentals (patchier — Yahoo's coverage of Indian mid/small caps varies) ----
    if info.get("returnOnEquity") is not None:
        fundamentals["roe"] = pct(info["returnOnEquity"])
    if info.get("profitMargins") is not None:
        fundamentals["netMargin"] = pct(info["profitMargins"])
    if info.get("debtToEquity") is not None:
        # Yahoo reports this as a percentage-like number (e.g. 45.2 meaning 0.45 ratio)
        fundamentals["de"] = round(info["debtToEquity"] / 100, 2)
    if info.get("revenueGrowth") is not None:
        fundamentals["revCagr3"] = pct(info["revenueGrowth"])
        warnings.append("revCagr3 is actually latest YoY revenue growth, not a true 3-year CAGR — Yahoo doesn't provide the latter.")
    if info.get("earningsGrowth") is not None:
        fundamentals["epsCagr3"] = pct(info["earningsGrowth"])
        warnings.append("epsCagr3 is actually latest YoY earnings growth, not a true 3-year CAGR.")

    missing = [f for f in ["roce", "marginChgBps", "promoterHold", "promoterPledge",
                            "revCagr5", "epsCagr5", "qoqRev", "intCov", "currentRatio",
                            "cfo", "pat", "fcf"] if f not in fundamentals]
    if missing:
        warnings.append(f"Not available from Yahoo Finance — still need manual entry from Screener.in: {', '.join(missing)}")
    missing_val = [vf for vf in ["peg", "fcfYield", "sectorPE", "medianPE", "fairValue"] if vf not in valuation]
    if missing_val:
        warnings.append(f"Not available from Yahoo Finance (valuation) — still need manual entry: {', '.join(missing_val)}")

    return {
        "sector": info.get("sector") or info.get("industry"),
        "fundamentals": fundamentals,
        "valuation": valuation,
        "warnings": warnings,
        "sourceSymbol": yahoo_symbol,
    }
