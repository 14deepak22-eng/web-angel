"""
Turns raw daily OHLCV candles (as returned by Angel One's getCandleData) into the
same technical & risk fields the screener's scoring engine expects. Standard,
widely-used formulas — treat these as solid defaults, not the only valid way
to compute them.
"""
import pandas as pd
import numpy as np


def candles_to_df(candles: list) -> pd.DataFrame:
    df = pd.DataFrame(candles, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.sort_values("timestamp").reset_index(drop=True)
    for c in ["open", "high", "low", "close", "volume"]:
        df[c] = df[c].astype(float)
    return df


def sma(series: pd.Series, window: int) -> float:
    if len(series) < window:
        return float("nan")
    return float(series.tail(window).mean())


def rsi(close: pd.Series, period: int = 14) -> float:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi_val = 100 - (100 / (1 + rs))
    return float(rsi_val.iloc[-1]) if not rsi_val.empty else float("nan")


def true_range(df: pd.DataFrame) -> pd.Series:
    prev_close = df["close"].shift(1)
    tr = pd.concat([
        df["high"] - df["low"],
        (df["high"] - prev_close).abs(),
        (df["low"] - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr


def atr(df: pd.DataFrame, period: int = 14) -> float:
    tr = true_range(df)
    atr_series = tr.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    return float(atr_series.iloc[-1]) if not atr_series.empty else float("nan")


def adx(df: pd.DataFrame, period: int = 14) -> float:
    up_move = df["high"].diff()
    down_move = -df["low"].diff()
    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)
    tr = true_range(df)
    atr_s = tr.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    plus_di = 100 * pd.Series(plus_dm, index=df.index).ewm(alpha=1 / period, min_periods=period, adjust=False).mean() / atr_s
    minus_di = 100 * pd.Series(minus_dm, index=df.index).ewm(alpha=1 / period, min_periods=period, adjust=False).mean() / atr_s
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    adx_series = dx.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    return float(adx_series.iloc[-1]) if not adx_series.empty else float("nan")


def macd_hist(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> float:
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    return float((macd_line - signal_line).iloc[-1])


def pct_return(close: pd.Series, trading_days_back: int) -> float:
    if len(close) <= trading_days_back:
        return float("nan")
    old = close.iloc[-trading_days_back - 1]
    new = close.iloc[-1]
    if old == 0:
        return float("nan")
    return float((new / old - 1) * 100)


def max_drawdown(close: pd.Series, trading_days: int) -> float:
    window = close.tail(trading_days) if len(close) >= trading_days else close
    running_max = window.cummax()
    drawdown = (window - running_max) / running_max * 100
    return float(drawdown.min())


def current_drawdown_from_ath(close: pd.Series) -> float:
    ath = close.max()
    if ath == 0:
        return float("nan")
    return float((close.iloc[-1] - ath) / ath * 100)


def beta(stock_close: pd.Series, index_close: pd.Series, trading_days: int = 750) -> float:
    s = stock_close.pct_change().tail(trading_days).dropna()
    i = index_close.pct_change().tail(trading_days).dropna()
    n = min(len(s), len(i))
    if n < 30:
        return float("nan")
    s, i = s.tail(n).values, i.tail(n).values
    cov = np.cov(s, i)[0][1]
    var = np.var(i)
    return float(cov / var) if var else float("nan")


def annualized_volatility(close: pd.Series, trading_days: int = 252) -> float:
    rets = close.pct_change().tail(trading_days).dropna()
    if len(rets) < 20:
        return float("nan")
    return float(rets.std() * (252 ** 0.5) * 100)


def compute_technicals_and_risk(candles: list, nifty_candles: list = None) -> dict:
    """Returns a dict matching the `technicals` and `risk` objects the scoring
    engine (score_engine.py / the web dashboard) expects."""
    df = candles_to_df(candles)
    close = df["close"]

    out = {
        "technicals": {
            "cmp": float(close.iloc[-1]),
            "dma20": sma(close, 20),
            "dma50": sma(close, 50),
            "dma100": sma(close, 100),
            "dma200": sma(close, 200),
            "rsi": rsi(close, 14),
            "macd": macd_hist(close),
            "adx": adx(df, 14),
            "atr": atr(df, 14),
            "vol": float(df["volume"].iloc[-1]) / 1000,       # in '000 to match the dashboard's units
            "avgVol": float(df["volume"].tail(20).mean()) / 1000,
            "high52": float(df["close"].tail(252).max()) if len(df) >= 1 else float("nan"),
            "breakout": bool(close.iloc[-1] >= df["high"].tail(20).iloc[:-1].max()) if len(df) > 20 else False,
            "ret1m": pct_return(close, 21),
            "ret3m": pct_return(close, 63),
            "ret6m": pct_return(close, 126),
            "ret12m": pct_return(close, 252),
        },
        "risk": {
            "beta": None,
            "histVol": annualized_volatility(close),
            "dd1y": max_drawdown(close, 252),
            "dd3y": max_drawdown(close, 750),
            "currDD": current_drawdown_from_ath(close),
            "advt": float((df["close"] * df["volume"]).tail(20).mean()) / 1e7,  # ₹ Crore
        },
    }

    if nifty_candles:
        nifty_df = candles_to_df(nifty_candles)
        out["risk"]["beta"] = beta(close, nifty_df["close"])

    return out
