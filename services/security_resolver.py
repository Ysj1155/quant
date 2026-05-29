from __future__ import annotations

import re
from typing import Dict, List

import pandas as pd

from data.csv_manager import DATA_DIR, read_csv_smart
from services.analysis_utils import currency_label, latest_investment_positions
from services.kr_security_master import find_kr_security_candidates

SECURITY_MAP_FILE = DATA_DIR / "security_map.csv"

SECURITY_MAP_COLUMNS = [
    "source_name",
    "asset_type",
    "currency",
    "market",
    "symbol",
    "asset_class",
    "price_source",
    "status",
    "note",
]

STATUS_LABELS = {
    "confirmed": "검산 가능",
    "auto": "자동 추정",
    "review": "확인 필요",
    "unresolved": "매칭 불가",
    "excluded": "별도 자산",
}

TICKER_RE = re.compile(r"^[A-Z][A-Z0-9.\-]{0,11}$")


def _clean(value: object) -> str:
    return str(value or "").strip()


def _key(name: object, asset_type: object, currency: object) -> tuple[str, str, str]:
    return (
        _clean(name).casefold(),
        _clean(asset_type).casefold(),
        currency_label(currency).casefold(),
    )


def _empty_map() -> pd.DataFrame:
    return pd.DataFrame(columns=SECURITY_MAP_COLUMNS)


def load_security_map() -> pd.DataFrame:
    if not SECURITY_MAP_FILE.exists():
        return _empty_map()

    df = read_csv_smart(SECURITY_MAP_FILE)
    if df.empty:
        return _empty_map()

    out = df.copy()
    for column in SECURITY_MAP_COLUMNS:
        if column not in out.columns:
            out[column] = ""
        out[column] = out[column].fillna("").astype(str).str.strip()
    return out[SECURITY_MAP_COLUMNS]


def _mapped_by_key() -> Dict[tuple[str, str, str], Dict]:
    mapped: Dict[tuple[str, str, str], Dict] = {}
    for row in load_security_map().to_dict("records"):
        mapped[_key(row["source_name"], row["asset_type"], row["currency"])] = row
    return mapped


def _is_us_position(name: str, asset_type: str, currency: str) -> bool:
    return currency_label(currency) == "USD" or "외화" in asset_type or asset_type.lower() in ("us", "foreign")


def _is_kr_stock(asset_type: str, currency: str) -> bool:
    return currency_label(currency) == "KRW" and "주식" in asset_type and "외화" not in asset_type


def _is_commodity(asset_type: str, name: str) -> bool:
    return "금" in asset_type or "금 현물" in name


def _from_map(position: Dict, mapped: Dict) -> Dict:
    status = mapped.get("status") or "review"
    return {
        **position,
        "market": mapped.get("market", ""),
        "symbol": mapped.get("symbol", ""),
        "asset_class": mapped.get("asset_class", ""),
        "price_source": mapped.get("price_source", ""),
        "status": status,
        "status_label": STATUS_LABELS.get(status, status),
        "source": "security_map",
        "note": mapped.get("note", ""),
    }


def resolve_security(position: Dict, mapped: Dict[tuple[str, str, str], Dict]) -> Dict:
    name = _clean(position.get("name"))
    asset_type = _clean(position.get("asset_type"))
    currency = currency_label(position.get("currency"))
    map_row = mapped.get(_key(name, asset_type, currency))
    if map_row and (map_row.get("symbol") or map_row.get("status") in ("confirmed", "excluded")):
        return _from_map(position, map_row)

    if _is_commodity(asset_type, name):
        return {
            **position,
            "market": "KR",
            "symbol": "",
            "asset_class": "commodity",
            "price_source": "manual",
            "status": "excluded",
            "status_label": STATUS_LABELS["excluded"],
            "source": "rule",
            "note": "금현물은 주식 가격 API 검산 대상에서 분리합니다.",
        }

    upper_name = name.upper()
    if _is_us_position(name, asset_type, currency) and TICKER_RE.fullmatch(upper_name):
        return {
            **position,
            "market": "US",
            "symbol": upper_name,
            "asset_class": "stock_or_etf",
            "price_source": "finnhub",
            "status": "auto",
            "status_label": STATUS_LABELS["auto"],
            "source": "ticker_like_name",
            "note": "종목명이 미국 티커 형식이라 자동 추정했습니다.",
        }

    if _is_us_position(name, asset_type, currency):
        return {
            **position,
            "market": "US",
            "symbol": "",
            "asset_class": "stock_or_etf",
            "price_source": "finnhub",
            "status": "review",
            "status_label": STATUS_LABELS["review"],
            "source": "rule",
            "note": "미국 종목 후보 검색 또는 사용자 확인이 필요합니다.",
        }

    if _is_kr_stock(asset_type, currency):
        candidates = find_kr_security_candidates(name, limit=5)
        if len(candidates) == 1 and candidates[0].get("name") == name:
            candidate = candidates[0]
            return {
                **position,
                "market": candidate.get("market", "KR"),
                "symbol": candidate.get("code", ""),
                "asset_class": "stock",
                "price_source": "kis_master",
                "status": "auto",
                "status_label": STATUS_LABELS["auto"],
                "source": "kr_security_master",
                "note": f"KIS 국내 종목 사전에서 {candidate.get('name')}({candidate.get('code')})로 자동 매칭했습니다.",
            }

        if candidates:
            candidate_text = ", ".join(
                f"{item.get('name')}({item.get('code')}, {item.get('market')})"
                for item in candidates[:3]
            )
            return {
                **position,
                "market": "KR",
                "symbol": "",
                "asset_class": "stock",
                "price_source": "kis_master",
                "status": "review",
                "status_label": STATUS_LABELS["review"],
                "source": "kr_security_master",
                "note": f"국내 종목 사전 후보 확인 필요: {candidate_text}",
            }

        return {
            **position,
            "market": "KR",
            "symbol": "",
            "asset_class": "stock",
            "price_source": "krx",
            "status": "review",
            "status_label": STATUS_LABELS["review"],
            "source": "rule",
            "note": "국내 종목 사전 캐시가 없거나 일치 후보를 찾지 못했습니다.",
        }

    return {
        **position,
        "market": "",
        "symbol": "",
        "asset_class": "",
        "price_source": "",
        "status": "unresolved",
        "status_label": STATUS_LABELS["unresolved"],
        "source": "rule",
        "note": "가격 검산 대상인지 판단할 정보가 부족합니다.",
    }


def _positions_from_latest_snapshot() -> tuple[str, List[Dict]]:
    latest_date, df = latest_investment_positions()
    if df.empty:
        return latest_date, []

    grouped = (
        df.groupby(["ticker", "type", "currency"], dropna=False)
        .agg({
            "quantity": "sum",
            "evaluation_amount": "sum",
        })
        .reset_index()
        .sort_values("evaluation_amount", ascending=False)
    )

    rows: List[Dict] = []
    for _, row in grouped.iterrows():
        rows.append({
            "name": _clean(row["ticker"]),
            "asset_type": _clean(row["type"]),
            "currency": currency_label(row["currency"]),
            "quantity": float(row["quantity"]),
            "evaluation_amount": float(row["evaluation_amount"]),
        })
    return latest_date, rows


def build_security_resolution_summary() -> Dict:
    latest_date, positions = _positions_from_latest_snapshot()
    mapped = _mapped_by_key()
    rows = [resolve_security(position, mapped) for position in positions]

    confirmed_statuses = {"confirmed", "auto"}
    confirmed = sum(1 for row in rows if row["status"] in confirmed_statuses)
    review = sum(1 for row in rows if row["status"] == "review")
    unresolved = sum(1 for row in rows if row["status"] == "unresolved")
    excluded = sum(1 for row in rows if row["status"] == "excluded")
    priceable = max(0, len(rows) - excluded)
    coverage_pct = (confirmed / priceable * 100.0) if priceable else 0.0

    return {
        "latest_date": latest_date,
        "map_file": str(SECURITY_MAP_FILE),
        "total_count": len(rows),
        "priceable_count": priceable,
        "confirmed_count": confirmed,
        "review_count": review,
        "unresolved_count": unresolved,
        "excluded_count": excluded,
        "coverage_pct": coverage_pct,
        "rows": rows,
    }
