# api/finnhub_api.py
import time
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

import pandas as pd
import requests

from config import FINNHUB_API_KEY
from extensions import cache

BASE_URL = "https://finnhub.io/api/v1"

# ✅ 연결 재사용(속도/안정성 ↑)
_SESSION = requests.Session()

def safe_request(path: str, params: Dict[str, Any], timeout: int = 6, retries: int = 2) -> Any:
    """
    - timeout 기본 6초
    - 429 / 5xx는 지수 백오프로 재시도
    """
    url = f"{BASE_URL}{path}"
    last_err: Optional[str] = None

    for attempt in range(retries + 1):
        try:
            res = _SESSION.get(url, params=params, timeout=timeout)

            # rate limit / 서버오류 재시도
            if res.status_code in (429, 500, 502, 503, 504):
                wait = min(1.0 * (2 ** attempt), 4.0)
                last_err = f"HTTP {res.status_code}"
                time.sleep(wait)
                continue

            res.raise_for_status()
            return res.json()
        except Exception as e:
            last_err = str(e)
            wait = min(0.7 * (2 ** attempt), 3.0)
            time.sleep(wait)

    return {
        "error": "request failed",
        "path": path,
        "reason": last_err,
    }

# ---- 캐시 TTL 가이드 ----
# quote: 20~30초 / profile: 6시간 / metrics: 2~5분 / target: 10~30분 / etf holdings: 6시간 / news: 10분

@cache.memoize(timeout=30)
def get_quote_raw(ticker: str):
    return safe_request("/quote", {"symbol": ticker, "token": FINNHUB_API_KEY})

@cache.memoize(timeout=60 * 60 * 6)
def get_profile_raw(ticker: str):
    return safe_request("/stock/profile2", {"symbol": ticker, "token": FINNHUB_API_KEY})

@cache.memoize(timeout=60 * 3)
def get_metrics_raw(ticker: str):
    return safe_request("/stock/metric", {"symbol": ticker, "metric": "all", "token": FINNHUB_API_KEY})

@cache.memoize(timeout=60 * 15)
def get_price_target_raw(ticker: str):
    return safe_request("/stock/price-target", {"symbol": ticker, "token": FINNHUB_API_KEY})

@cache.memoize(timeout=60 * 10)
def get_company_news_raw(ticker: str, from_date: str, to_date: str):
    return safe_request("/company-news", {"symbol": ticker, "from": from_date, "to": to_date, "token": FINNHUB_API_KEY})

@cache.memoize(timeout=60 * 60 * 6)
def get_etf_holdings_raw(ticker: str):
    return safe_request("/etf/holdings", {"symbol": ticker, "token": FINNHUB_API_KEY})

def get_company_news_auto(ticker: str, days: int = 7):
    to_date = datetime.today().date()
    from_date = to_date - timedelta(days=days)
    return get_company_news_raw(ticker, from_date.isoformat(), to_date.isoformat())

# (선택) 캔들/지표는 계산 비용도 있으니 캐시 걸어두면 좋음
@cache.memoize(timeout=60 * 10)
def get_candle_data(ticker: str, days: int = 90):
    now = int(time.time())
    past = now - 60 * 60 * 24 * days
    res = safe_request("/stock/candle", {
        "symbol": ticker,
        "resolution": "D",
        "from": past,
        "to": now,
        "token": FINNHUB_API_KEY
    })
    if res.get("s") != "ok":
        return None

    df = pd.DataFrame({"timestamp": res["t"], "close": res["c"]})
    df["date"] = pd.to_datetime(df["timestamp"], unit="s")
    df = df[df["date"].dt.dayofweek < 5]
    return df

def calculate_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["MA5"] = df["close"].rolling(window=5).mean()
    df["MA20"] = df["close"].rolling(window=20).mean()
    delta = df["close"].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(window=14).mean()
    avg_loss = loss.rolling(window=14).mean()
    rs = avg_gain / avg_loss
    df["RSI"] = 100 - (100 / (1 + rs))
    df.dropna(inplace=True)
    return df