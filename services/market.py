# services/market.py
from __future__ import annotations
from datetime import datetime
import numpy as np
import yfinance as yf
import FinanceDataReader as fdr

from extensions import cache

SYMBOLS = {
    "SPX": {"label": "S&P 500", "symbol": "US500"},
    "NDX": {"label": "NASDAQ 100", "symbol": "NASDAQ100"},
    "DJI": {"label": "Dow Jones", "symbol": "DJI"},
    "RUT": {"label": "Russell 2000", "symbol": "RUT"},
    "VIX": {"label": "VIX", "symbol": "VIX"},
}

def _to_scalar(x):
    try:
        if x is None:
            return None
        if hasattr(x, "iloc"):
            x = x.iloc[0]
        if isinstance(x, (np.ndarray, list)):
            x = x[0]
        return float(x)
    except Exception:
        return None

def _last_close_and_change_pct(symbol: str):
    try:
        df = fdr.DataReader(symbol)
        if df is None or df.empty:
            return None
        close = df["Close"].dropna()
        if len(close) < 2:
            return None
        last = float(close.iloc[-1])
        prev = float(close.iloc[-2])
        change_pct = (last - prev) / prev * 100.0 if prev != 0 else 0.0
        return {"last": last, "change_pct": change_pct}
    except Exception:
        return None

@cache.memoize(timeout=60)  # 1분
def get_indices_snapshot():
    out = {}
    for k, meta in SYMBOLS.items():
        res = _last_close_and_change_pct(meta["symbol"])
        out[k] = {
            "label": meta["label"],
            "symbol": meta["symbol"],
            "ok": res is not None,
            "last": None if res is None else res["last"],
            "change_pct": None if res is None else res["change_pct"],
        }
    return out

@cache.memoize(timeout=60 * 10)  # 10분
def get_nasdaq_panic(window_days: int = 21, drop_pct: float = -3.3, lookback_days: int = 120) -> dict:
    df = yf.download("^IXIC", period=f"{lookback_days}d", interval="1d", progress=False, auto_adjust=False)
    if df is None or df.empty or "Close" not in df:
        return {"ok": False, "error": "no data from yfinance (^IXIC)"}

    close = df["Close"].dropna()
    if len(close) < window_days + 2:
        return {"ok": False, "error": f"not enough data: {len(close)} rows"}

    ret = close.pct_change() * 100.0
    recent = ret.dropna().tail(window_days)
    drops = recent[recent <= drop_pct]
    count = int(drops.shape[0])

    level = "panic" if count >= 4 else ("watch" if count >= 3 else "ok")
    drop_dates = [d.strftime("%Y-%m-%d") for d in drops.index.to_pydatetime()]

    return {
        "ok": True,
        "label": "NASDAQ Panic",
        "symbol": "^IXIC",
        "window_days": window_days,
        "threshold_drop_pct": drop_pct,
        "count": count,
        "level": level,
        "drop_dates": drop_dates,
        "last_date": close.index[-1].to_pydatetime().strftime("%Y-%m-%d"),
        "last_close": _to_scalar(close.tail(1)),
        "last_daily_return_pct": _to_scalar(recent.tail(1)),
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }