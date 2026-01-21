#domain/sector.py
from functools import lru_cache
from yahooquery import Ticker
from api.finnhub_api import get_profile_raw

# 한글/표기 혼용 티커 보정 (필요 시 확장)
TICKER_MAP = {
    "애플": "AAPL", "엔비디아": "NVDA", "테슬라": "TSLA",
    "알파벳 A": "GOOGL", "아마존닷컴": "AMZN",
    "TSMC(ADR)": "TSM", "카디널 헬스": "CAH",
    "PROSHARES QQQ 3X": "TQQQ", "INVESCO QQQ TRUST UNIT SER 1": "QQQ"
}

def normalize_symbol(raw: str):
    if not raw:
        return None
    raw = str(raw).strip()
    if raw in TICKER_MAP:
        return TICKER_MAP[raw]
    t = raw.upper()
    if all(ch.isalnum() or ch in (".", "-") for ch in t):
        return t
    return None


SECTOR_NORMALIZE = {
    "basic materials": "Materials",
    "communication services": "Communication Services",
    "consumer cyclical": "Consumer Discretionary",
    "consumer defensive": "Consumer Staples",
    "consumer staples": "Consumer Staples",
    "energy": "Energy",
    "financial services": "Financials",
    "financial": "Financials",
    "healthcare": "Healthcare",
    "industrials": "Industrials",
    "real estate": "Real Estate",
    "technology": "Information Technology",
    "information technology": "Information Technology",
    "utilities": "Utilities",
}

def norm_sector_name(s: str) -> str:
    key = (s or "").strip().lower()
    return SECTOR_NORMALIZE.get(key, s or "Unknown")


@lru_cache(maxsize=1024)
def is_etf(symbol: str) -> bool:
    try:
        qt = Ticker(symbol).quote_type
        if isinstance(qt, dict) and symbol in qt:
            return (qt[symbol].get("quoteType") == "ETF")
    except Exception:
        pass
    return False


@lru_cache(maxsize=256)
def get_etf_sector_weights(symbol: str):
    """
    ETF 섹터 비중값을 {섹터명: 가중치(0~1)}로 반환.
    yahooquery.fund_sector_weightings는 [{"technology": 45.67, ...}] 형태.
    """
    try:
        data = Ticker(symbol).fund_sector_weightings

        if isinstance(data, dict) and "sectorWeightings" in data:
            rows = data["sectorWeightings"]
        else:
            rows = data

        if not rows:
            return None

        if isinstance(rows, list):
            row = rows[0] if rows else {}
        elif isinstance(rows, dict):
            row = rows
        else:
            return None

        weights = {}
        for k, v in row.items():
            try:
                w = float(v)
            except Exception:
                continue
            if w <= 0:
                continue
            weights[norm_sector_name(k)] = w / 100.0

        s = sum(weights.values()) or 1.0
        return {k: w / s for k, w in weights.items()} if weights else None
    except Exception:
        return None


@lru_cache(maxsize=2048)
def get_sector_for_symbol(symbol: str) -> str:
    """개별 종목 섹터 (ETF 아님). Yahoo 우선, 실패 시 Finnhub 보조."""
    try:
        prof = Ticker(symbol).asset_profile
        if isinstance(prof, dict) and symbol in prof:
            sec = prof[symbol].get("sector")
            if sec:
                return norm_sector_name(sec)
    except Exception:
        pass

    try:
        prof2 = get_profile_raw(symbol)
        if isinstance(prof2, dict):
            sec = prof2.get("finnhubIndustry")
            if sec:
                return norm_sector_name(sec)
    except Exception:
        pass

    return "Unknown"


def add_to_bucket(bucket: dict, sector: str, sym: str, value: float):
    if sector not in bucket:
        bucket[sector] = {"total_value": 0, "stocks": []}
    bucket[sector]["total_value"] += int(value)
    bucket[sector]["stocks"].append({"ticker": sym, "price": int(value)})