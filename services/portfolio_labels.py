from __future__ import annotations

from typing import Dict

import pandas as pd

from data.csv_manager import DATA_DIR, read_csv_smart
from services.analysis_utils import currency_label, is_cash_type

PORTFOLIO_LABEL_FILE = DATA_DIR / "portfolio_labels.csv"

PORTFOLIO_LABEL_COLUMNS = [
    "source_name",
    "asset_type",
    "currency",
    "portfolio_sector",
    "portfolio_role",
    "risk_bucket",
    "tags",
    "note",
]

DEFAULT_LABEL = {
    "portfolio_sector": "미분류",
    "portfolio_role": "관찰 필요",
    "risk_bucket": "미분류",
    "tags": "",
    "note": "portfolio_labels.csv에 수동 분류를 추가하면 더 정확하게 묶입니다.",
    "label_source": "fallback",
}

CASH_LABEL = {
    "portfolio_sector": "현금",
    "portfolio_role": "대기 자금",
    "risk_bucket": "낮음",
    "tags": "현금",
    "note": "현금성 자산입니다.",
    "label_source": "rule",
}


def _clean(value: object) -> str:
    return str(value or "").strip()


def _key(name: object, asset_type: object, currency: object) -> tuple[str, str, str]:
    return (
        _clean(name).casefold(),
        _clean(asset_type).casefold(),
        currency_label(currency).casefold(),
    )


def _empty_labels() -> pd.DataFrame:
    return pd.DataFrame(columns=PORTFOLIO_LABEL_COLUMNS)


def load_portfolio_labels() -> pd.DataFrame:
    if not PORTFOLIO_LABEL_FILE.exists():
        return _empty_labels()

    df = read_csv_smart(PORTFOLIO_LABEL_FILE)
    if df.empty:
        return _empty_labels()

    out = df.copy()
    for column in PORTFOLIO_LABEL_COLUMNS:
        if column not in out.columns:
            out[column] = ""
        out[column] = out[column].fillna("").astype(str).str.strip()
    out["currency"] = out["currency"].apply(currency_label)
    return out[PORTFOLIO_LABEL_COLUMNS]


def mapped_portfolio_labels() -> Dict[tuple[str, str, str], Dict]:
    mapped: Dict[tuple[str, str, str], Dict] = {}
    for row in load_portfolio_labels().to_dict("records"):
        mapped[_key(row["source_name"], row["asset_type"], row["currency"])] = row
    return mapped


def classify_position(name: object, asset_type: object, currency: object, mapped: Dict[tuple[str, str, str], Dict] | None = None) -> Dict:
    clean_asset_type = _clean(asset_type)
    if is_cash_type(clean_asset_type):
        return CASH_LABEL.copy()

    label_map = mapped if mapped is not None else mapped_portfolio_labels()
    row = label_map.get(_key(name, asset_type, currency))
    if row:
        return {
            "portfolio_sector": row.get("portfolio_sector") or DEFAULT_LABEL["portfolio_sector"],
            "portfolio_role": row.get("portfolio_role") or DEFAULT_LABEL["portfolio_role"],
            "risk_bucket": row.get("risk_bucket") or DEFAULT_LABEL["risk_bucket"],
            "tags": row.get("tags") or "",
            "note": row.get("note") or "",
            "label_source": "portfolio_labels",
        }

    return DEFAULT_LABEL.copy()
