from __future__ import annotations

from typing import Dict, List

import pandas as pd

from extensions import cache
from services.analysis_utils import (
    latest_investment_positions,
    load_account_values,
    mask_account,
    safe_pct,
)


def _position_payload(row: pd.Series, total_eval: float, total_abs_pnl: float) -> Dict:
    pnl = float(row.get("profit_loss", 0.0) or 0.0)
    eval_amount = float(row.get("evaluation_amount", 0.0) or 0.0)
    return {
        "name": str(row.get("ticker", "")).strip(),
        "account_label": mask_account(str(row.get("account_number", ""))),
        "asset_type": str(row.get("type", "")).strip(),
        "currency": str(row.get("currency", "")).strip(),
        "quantity": float(row.get("quantity", 0.0) or 0.0),
        "purchase_amount": float(row.get("purchase_amount", 0.0) or 0.0),
        "evaluation_amount": eval_amount,
        "profit_loss": pnl,
        "profit_rate": float(row.get("profit_rate", 0.0) or 0.0),
        "value_weight_pct": safe_pct(eval_amount, total_eval),
        "pnl_contribution_pct": safe_pct(abs(pnl), total_abs_pnl),
    }


def _build_contributors(positions: pd.DataFrame, total_eval: float) -> Dict:
    if positions.empty:
        return {"top_gainers": [], "top_losers": [], "all": []}

    total_abs_pnl = float(positions["profit_loss"].abs().sum())
    rows = [
        _position_payload(row, total_eval=total_eval, total_abs_pnl=total_abs_pnl)
        for _, row in positions.iterrows()
    ]
    gainers = [row for row in rows if row["profit_loss"] > 0]
    losers = [row for row in rows if row["profit_loss"] < 0]

    return {
        "top_gainers": sorted(gainers, key=lambda row: row["profit_loss"], reverse=True)[:5],
        "top_losers": sorted(losers, key=lambda row: row["profit_loss"])[:5],
        "all": sorted(rows, key=lambda row: abs(row["profit_loss"]), reverse=True),
    }


def _build_asset_type_summary(positions: pd.DataFrame, total_eval: float) -> List[Dict]:
    if positions.empty:
        return []

    grouped = (
        positions.groupby("type", dropna=False)
        .agg({
            "ticker": "count",
            "purchase_amount": "sum",
            "evaluation_amount": "sum",
            "profit_loss": "sum",
        })
        .reset_index()
        .rename(columns={"ticker": "count", "type": "asset_type"})
    )
    grouped["profit_rate"] = grouped.apply(
        lambda row: safe_pct(float(row["profit_loss"]), float(row["purchase_amount"])),
        axis=1,
    )
    grouped["weight_pct"] = grouped["evaluation_amount"].apply(lambda value: safe_pct(float(value), total_eval))

    rows = []
    for row in grouped.sort_values("evaluation_amount", ascending=False).to_dict("records"):
        rows.append({
            "asset_type": str(row.get("asset_type", "")).strip(),
            "count": int(row.get("count", 0) or 0),
            "purchase_amount": float(row.get("purchase_amount", 0.0) or 0.0),
            "evaluation_amount": float(row.get("evaluation_amount", 0.0) or 0.0),
            "profit_loss": float(row.get("profit_loss", 0.0) or 0.0),
            "profit_rate": float(row.get("profit_rate", 0.0) or 0.0),
            "weight_pct": float(row.get("weight_pct", 0.0) or 0.0),
        })
    return rows


def _build_monthly_changes(account_values: pd.DataFrame, limit: int = 12) -> List[Dict]:
    if account_values.empty:
        return []

    df = account_values.copy()
    df["month"] = df["date"].dt.to_period("M").astype(str)
    monthly = df.groupby("month", as_index=False).tail(1).copy()
    monthly["change"] = monthly["total_value"].diff()
    monthly["change_pct"] = monthly["total_value"].pct_change() * 100.0

    rows = []
    for row in monthly.tail(limit).to_dict("records"):
        rows.append({
            "month": row["month"],
            "total_value": float(row["total_value"]),
            "change": None if pd.isna(row["change"]) else float(row["change"]),
            "change_pct": None if pd.isna(row["change_pct"]) else float(row["change_pct"]),
        })
    return rows


def _build_daily_moves(account_values: pd.DataFrame, limit: int = 5) -> Dict:
    if account_values.empty:
        return {"best_days": [], "worst_days": []}

    df = account_values.copy()
    df["change"] = df["total_value"].diff()
    df["change_pct"] = df["total_value"].pct_change() * 100.0
    df = df.dropna(subset=["change", "change_pct"])

    def serialize(rows: pd.DataFrame) -> List[Dict]:
        return [
            {
                "date": row["date"].strftime("%Y-%m-%d"),
                "total_value": float(row["total_value"]),
                "change": float(row["change"]),
                "change_pct": float(row["change_pct"]),
            }
            for _, row in rows.iterrows()
        ]

    return {
        "best_days": serialize(df.sort_values("change", ascending=False).head(limit)),
        "worst_days": serialize(df.sort_values("change", ascending=True).head(limit)),
    }


@cache.memoize(timeout=60)
def build_performance_summary() -> Dict:
    latest_date, positions = latest_investment_positions()
    account_values = load_account_values()

    if positions.empty:
        return {"ok": False, "error": "no latest positions found"}

    latest_total_value = None
    if not account_values.empty:
        latest_total_value = float(account_values["total_value"].iloc[-1])

    invested_eval = float(positions["evaluation_amount"].sum())
    total_eval = latest_total_value if latest_total_value is not None else invested_eval
    purchase_amount = float(positions["purchase_amount"].sum())
    profit_loss = float(positions["profit_loss"].sum())

    largest_position = positions.sort_values("evaluation_amount", ascending=False).head(1)
    top_position = None
    if not largest_position.empty:
        row = largest_position.iloc[0]
        top_position = {
            "name": str(row.get("ticker", "")).strip(),
            "asset_type": str(row.get("type", "")).strip(),
            "evaluation_amount": float(row.get("evaluation_amount", 0.0) or 0.0),
            "weight_pct": safe_pct(float(row.get("evaluation_amount", 0.0) or 0.0), total_eval),
        }

    return {
        "ok": True,
        "asof_date": latest_date,
        "summary": {
            "latest_total_value": latest_total_value,
            "invested_evaluation_amount": invested_eval,
            "purchase_amount": purchase_amount,
            "profit_loss": profit_loss,
            "profit_rate": safe_pct(profit_loss, purchase_amount),
            "position_count": int(len(positions)),
            "top_position": top_position,
        },
        "contributors": _build_contributors(positions, total_eval=total_eval),
        "asset_type_summary": _build_asset_type_summary(positions, total_eval=total_eval),
        "monthly_changes": _build_monthly_changes(account_values),
        "daily_moves": _build_daily_moves(account_values),
    }
