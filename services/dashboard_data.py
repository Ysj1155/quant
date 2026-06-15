from __future__ import annotations

from typing import Dict, List

import pandas as pd

from data.csv_manager import PORTFOLIO_FILE
from services.analysis_utils import currency_label, is_cash_type, load_account_values


def load_current_portfolio_rows(include_cash: bool = False) -> List[Dict]:
    if not PORTFOLIO_FILE.exists():
        return []

    df = pd.read_csv(PORTFOLIO_FILE, encoding="utf-8-sig")
    rows: List[Dict] = []
    for row in df.to_dict("records"):
        ticker = str(row.get("ticker") or "").strip()
        asset_type = str(row.get("type") or "").strip()
        if not include_cash and (is_cash_type(asset_type) or not ticker):
            continue

        rows.append({
            "account_number": str(row.get("account_number") or "").strip(),
            "type": asset_type,
            "ticker": ticker or asset_type,
            "currency": currency_label(row.get("currency")),
            "quantity": float(row.get("quantity") or 0),
            "purchase_amount": float(row.get("purchase_amount") or 0),
            "evaluation_amount": float(row.get("evaluation_amount") or 0),
            "profit_loss": float(row.get("profit_loss") or 0),
            "profit_rate": float(row.get("profit_rate") or 0),
            "evaluation_ratio": float(row.get("evaluation_ratio") or 0),
        })
    return rows


def _exposure_label(row: Dict, mode: str) -> str:
    asset_type = str(row.get("type") or "").strip()
    ticker = str(row.get("ticker") or "").strip()
    currency = currency_label(row.get("currency"))

    if mode == "holding":
        return asset_type if is_cash_type(asset_type) else (ticker or asset_type or "Unknown")
    if mode == "currency":
        return currency or "Unknown"
    return asset_type or "Unknown"


def build_portfolio_exposure(mode: str = "asset_type") -> Dict:
    mode = mode if mode in {"asset_type", "holding", "currency"} else "asset_type"
    rows = load_current_portfolio_rows(include_cash=True)
    bucket: Dict[str, Dict] = {}

    for row in rows:
        amount = float(row.get("evaluation_amount") or 0.0)
        if amount <= 0:
            continue

        label = _exposure_label(row, mode)
        item = bucket.setdefault(label, {
            "label": label,
            "total_value": 0.0,
            "profit_loss": 0.0,
            "items": [],
        })
        item["total_value"] += amount
        item["profit_loss"] += float(row.get("profit_loss") or 0.0)
        item["items"].append({
            "ticker": row.get("ticker") or label,
            "type": row.get("type") or "",
            "currency": row.get("currency") or "",
            "evaluation_amount": amount,
            "profit_loss": float(row.get("profit_loss") or 0.0),
        })

    total = sum(item["total_value"] for item in bucket.values())
    exposures = []
    for item in bucket.values():
        weight = (item["total_value"] / total * 100.0) if total else 0.0
        exposures.append({
            **item,
            "weight_pct": weight,
            "item_count": len(item["items"]),
        })

    exposures.sort(key=lambda item: item["total_value"], reverse=True)
    return {
        "ok": True,
        "mode": mode,
        "total_value": total,
        "exposures": exposures,
    }


def load_account_value_rows() -> pd.DataFrame:
    return load_account_values()
