from __future__ import annotations

import FinanceDataReader as fdr

from extensions import cache

SYMBOLS = {
    "SPX": {"label": "S&P 500", "symbol": "US500"},
    "NDX": {"label": "NASDAQ 100", "symbol": "NASDAQ100"},
    "DJI": {"label": "Dow Jones", "symbol": "DJI"},
    "RUT": {"label": "Russell 2000", "symbol": "RUT"},
    "VIX": {"label": "VIX", "symbol": "VIX"},
}


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

        return {
            "last": last,
            "change_pct": change_pct,
        }
    except Exception:
        return None


@cache.memoize(timeout=60)
def get_indices_snapshot():
    out = {}
    for key, meta in SYMBOLS.items():
        res = _last_close_and_change_pct(meta["symbol"])
        out[key] = {
            "label": meta["label"],
            "symbol": meta["symbol"],
            "ok": res is not None,
            "last": None if res is None else res["last"],
            "change_pct": None if res is None else res["change_pct"],
        }
    return out
