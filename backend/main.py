import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

# Load .env from the project root (one level up from this backend/ folder)
load_dotenv(Path(__file__).parent.parent / ".env")

from fastapi import FastAPI, Request, Depends, HTTPException, Response, Form, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
from pydantic import BaseModel

import db
import auth
import scheduler
import refresh_service
import score_engine
import fundamentals_fetch
import screener_csv_import
import screener_excel_import

STATIC_DIR = Path(__file__).parent.parent / "static"

app = FastAPI(title="NSE Stock Screener")


@app.on_event("startup")
def on_startup():
    db.init_db()
    if os.environ.get("ENABLE_SCHEDULER", "true").lower() == "true":
        scheduler.start()


@app.on_event("shutdown")
def on_shutdown():
    scheduler.stop()


# ---------------------------------------------------------------- auth pages
LOGIN_PAGE = """
<!DOCTYPE html><html><head><title>Sign in</title>
<style>
  body{background:#0D1117;color:#E6EDF3;font-family:-apple-system,sans-serif;
       display:flex;align-items:center;justify-content:center;height:100vh;margin:0;}
  form{background:#151B23;border:1px solid #2A323C;border-radius:8px;padding:28px;width:280px;}
  h1{font-size:16px;margin:0 0 16px;}
  input{width:100%;padding:9px 10px;margin-bottom:12px;background:#1B2330;border:1px solid #2A323C;
        border-radius:5px;color:#E6EDF3;box-sizing:border-box;}
  button{width:100%;padding:9px;background:#D4A72C;color:#241B03;border:none;border-radius:5px;
         font-weight:600;cursor:pointer;}
  .err{color:#F85149;font-size:12.5px;margin-bottom:10px;}
</style></head><body>
<form method="post" action="/login">
  <h1>NSE Stock Screener</h1>
  {error_html}
  <input type="password" name="password" placeholder="Password" autofocus>
  <button type="submit">Sign in</button>
</form>
</body></html>
"""


@app.get("/login", response_class=HTMLResponse)
def login_page(error: Optional[str] = None):
    error_html = '<div class="err">Wrong password — try again.</div>' if error else ""
    return LOGIN_PAGE.replace("{error_html}", error_html)


@app.post("/login")
def do_login(password: str = Form(...)):
    if not auth.check_password(password):
        return RedirectResponse(url="/login?error=1", status_code=303)
    resp = RedirectResponse(url="/", status_code=303)
    resp.set_cookie(auth.COOKIE_NAME, auth.make_session_cookie(), max_age=auth.MAX_AGE_SECONDS,
                     httponly=True, samesite="lax")
    return resp


@app.get("/logout")
def logout():
    resp = RedirectResponse(url="/login", status_code=303)
    resp.delete_cookie(auth.COOKIE_NAME)
    return resp


# ---------------------------------------------------------------- dashboard
@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    token = request.cookies.get(auth.COOKIE_NAME)
    if not auth.is_valid_session(token):
        return RedirectResponse(url="/login")
    return FileResponse(STATIC_DIR / "dashboard.html")


# ---------------------------------------------------------------- API models
class ConfigUpdate(BaseModel):
    invWeights: Optional[dict] = None
    tradeWeights: Optional[dict] = None
    nifty12m: Optional[float] = None
    niftyCmp: Optional[float] = None
    nifty50dma: Optional[float] = None
    nifty200dma: Optional[float] = None
    vix: Optional[float] = None
    capital: Optional[float] = None
    riskPct: Optional[float] = None


class StockUpsert(BaseModel):
    sector: Optional[str] = None
    tradingsymbol: Optional[str] = None
    exchange: Optional[str] = None
    fundamentals: Optional[dict] = None
    valuation: Optional[dict] = None
    catalysts: Optional[list] = None
    hypothesis: Optional[dict] = None
    flags: Optional[dict] = None


# ---------------------------------------------------------------- API routes
@app.get("/api/state")
def api_state(_: None = Depends(auth.require_login)):
    cfg = db.get_config()
    stocks = db.list_stocks()
    out = []
    for s in stocks:
        scores = score_engine.compute_all(
            s, cfg.get("nifty12m", 14.5), cfg.get("capital", 1000000), cfg.get("riskPct", 1),
            cfg.get("invWeights"), cfg.get("tradeWeights"),
        )
        out.append({"stock": s, "scores": scores})
    return {"config": cfg, "stocks": out, "refreshStatus": refresh_service.get_status()}


@app.post("/api/config")
def api_update_config(update: ConfigUpdate, _: None = Depends(auth.require_login)):
    cfg = db.get_config()
    for k, v in update.dict(exclude_unset=True).items():
        cfg[k] = v
    db.save_config(cfg)
    return {"ok": True, "config": cfg}


@app.post("/api/stock/{ticker}")
def api_upsert_stock(ticker: str, body: StockUpsert, _: None = Depends(auth.require_login)):
    db.upsert_stock_manual(ticker, **body.dict(exclude_unset=True))
    return {"ok": True, "stock": db.get_stock(ticker)}


@app.delete("/api/stock/{ticker}")
def api_delete_stock(ticker: str, _: None = Depends(auth.require_login)):
    db.delete_stock(ticker)
    return {"ok": True}


@app.post("/api/refresh")
def api_refresh_all(_: None = Depends(auth.require_login)):
    return refresh_service.refresh_all()


@app.post("/api/refresh/{ticker}")
def api_refresh_one(ticker: str, _: None = Depends(auth.require_login)):
    return refresh_service.refresh_one(ticker)


@app.post("/api/fetch-fundamentals/{ticker}")
def api_fetch_fundamentals(ticker: str, _: None = Depends(auth.require_login)):
    stock = db.get_stock(ticker)
    if not stock:
        return {"error": f"{ticker} not found"}
    result = fundamentals_fetch.fetch_yahoo_fundamentals(stock["tradingsymbol"], stock["exchange"])
    if "error" in result:
        return result
    db.upsert_stock_manual(
        ticker,
        sector=result.get("sector") if not stock.get("sector") else None,
        fundamentals=result.get("fundamentals") or None,
        valuation=result.get("valuation") or None,
    )
    return {"ok": True, "warnings": result.get("warnings", []), "stock": db.get_stock(ticker)}


@app.post("/api/import-screener-csv")
async def api_import_screener_csv(file: UploadFile = File(...), _: None = Depends(auth.require_login)):
    """
    Bulk-imports fundamentals/valuation from a Screener.in CSV export.
    Matches rows to stocks you've already added by trading symbol — it never
    creates new stocks, only fills in data for ones you've added.
    """
    contents = await file.read()
    result = screener_csv_import.import_csv(contents)
    return result


@app.post("/api/import-screener-excel/{ticker}")
async def api_import_screener_excel(ticker: str, file: UploadFile = File(...), _: None = Depends(auth.require_login)):
    """
    Imports fundamentals from Screener.in's per-company Excel export
    ("Export to Excel" on a company's screener.in page) for one specific
    stock you've already added.
    """
    stock = db.get_stock(ticker)
    if not stock:
        return {"error": f"{ticker} not found"}
    contents = await file.read()
    result = screener_excel_import.parse_screener_excel(contents)
    if result.get("error"):
        return result
    db.upsert_stock_manual(
        ticker,
        fundamentals=result.get("fundamentals") or None,
        valuation=result.get("valuation") or None,
    )
    return {"ok": True, "company_name": result.get("company_name"),
            "warnings": result.get("warnings", []), "stock": db.get_stock(ticker)}


@app.get("/api/health")
def health():
    return {"ok": True}
