from __future__ import annotations

from typing import Dict, List

import pandas as pd

from data.csv_manager import PORTFOLIO_FILE
from services.analysis_utils import is_cash_type, load_account_values


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
            "ticker": ticker or asset_type,
            "quantity": float(row.get("quantity") or 0),
            "purchase_amount": float(row.get("purchase_amount") or 0),
            "evaluation_amount": float(row.get("evaluation_amount") or 0),
            "profit_loss": float(row.get("profit_loss") or 0),
            "profit_rate": float(row.get("profit_rate") or 0),
            "evaluation_ratio": float(row.get("evaluation_ratio") or 0),
        })
    return rows


def load_account_value_rows() -> pd.DataFrame:
    return load_account_values()
