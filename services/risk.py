from __future__ import annotations

from typing import Dict, List

import pandas as pd

from extensions import cache
from services.analysis_utils import currency_label, investment_positions, latest_snapshot, load_account_values, safe_pct
from services.periods import filter_by_period
from services.portfolio_labels import classify_position, mapped_portfolio_labels


def _exposure_by(df: pd.DataFrame, column: str, total_value: float, label_name: str) -> List[Dict]:
    if df.empty:
        return []

    grouped = (
        df.groupby(column, dropna=False)
        .agg({"evaluation_amount": "sum", "ticker": "count"})
        .reset_index()
        .rename(columns={column: label_name, "ticker": "count"})
    )

    rows = []
    for row in grouped.sort_values("evaluation_amount", ascending=False).to_dict("records"):
        amount = float(row.get("evaluation_amount", 0.0) or 0.0)
        rows.append({
            label_name: str(row.get(label_name, "")).strip() or "Unknown",
            "count": int(row.get("count", 0) or 0),
            "evaluation_amount": amount,
            "weight_pct": safe_pct(amount, total_value),
        })
    return rows


def _label_exposure_by(df: pd.DataFrame, column: str, total_value: float, label_name: str) -> List[Dict]:
    if df.empty:
        return []

    grouped = (
        df.groupby(column, dropna=False)
        .agg({"evaluation_amount": "sum", "ticker": "count"})
        .reset_index()
        .rename(columns={column: label_name, "ticker": "count"})
    )

    rows = []
    for row in grouped.sort_values("evaluation_amount", ascending=False).to_dict("records"):
        label = str(row.get(label_name, "")).strip() or "미분류"
        members = df[df[column].fillna("").astype(str) == label].sort_values("evaluation_amount", ascending=False)
        top_items = [str(name).strip() for name in members["ticker"].head(3).tolist() if str(name).strip()]
        amount = float(row.get("evaluation_amount", 0.0) or 0.0)
        rows.append({
            label_name: label,
            "count": int(row.get("count", 0) or 0),
            "evaluation_amount": amount,
            "weight_pct": safe_pct(amount, total_value),
            "top_items": top_items,
        })
    return rows


def _top_positions(positions: pd.DataFrame, total_value: float, limit: int = 5) -> List[Dict]:
    if positions.empty:
        return []

    rows = []
    for row in positions.sort_values("evaluation_amount", ascending=False).head(limit).to_dict("records"):
        amount = float(row.get("evaluation_amount", 0.0) or 0.0)
        rows.append({
            "name": str(row.get("ticker", "")).strip(),
            "asset_type": str(row.get("type", "")).strip(),
            "currency": currency_label(row.get("currency", "")),
            "portfolio_sector": str(row.get("portfolio_sector", "")).strip(),
            "portfolio_role": str(row.get("portfolio_role", "")).strip(),
            "risk_bucket": str(row.get("risk_bucket", "")).strip(),
            "evaluation_amount": amount,
            "weight_pct": safe_pct(amount, total_value),
            "profit_loss": float(row.get("profit_loss", 0.0) or 0.0),
            "profit_rate": float(row.get("profit_rate", 0.0) or 0.0),
        })
    return rows


def _concentration_metrics(positions: pd.DataFrame, total_value: float) -> Dict:
    if positions.empty or total_value == 0:
        return {
            "top1_weight_pct": 0.0,
            "top3_weight_pct": 0.0,
            "top5_weight_pct": 0.0,
            "hhi": 0.0,
            "position_count": 0,
        }

    weights = positions["evaluation_amount"].astype(float).clip(lower=0) / total_value * 100.0
    sorted_weights = weights.sort_values(ascending=False).tolist()
    hhi = sum((weight / 100.0) ** 2 for weight in sorted_weights)

    return {
        "top1_weight_pct": float(sum(sorted_weights[:1])),
        "top3_weight_pct": float(sum(sorted_weights[:3])),
        "top5_weight_pct": float(sum(sorted_weights[:5])),
        "hhi": float(hhi),
        "position_count": int(len(sorted_weights)),
    }


def _account_risk(account_values: pd.DataFrame) -> Dict:
    if account_values.empty or len(account_values) < 2:
        return {
            "daily_volatility_pct": None,
            "max_drawdown_pct": None,
            "latest_7obs_change_pct": None,
            "latest_30obs_change_pct": None,
        }

    df = account_values.copy()
    df["return_pct"] = df["total_value"].pct_change() * 100.0
    recent = df.tail(60)
    daily_vol = recent["return_pct"].dropna().std()

    running_max = df["total_value"].cummax()
    drawdown = (df["total_value"] / running_max - 1.0) * 100.0

    latest = float(df["total_value"].iloc[-1])
    change_7 = None
    change_30 = None
    if len(df) > 7:
        base = float(df["total_value"].iloc[-8])
        change_7 = safe_pct(latest - base, base)
    if len(df) > 30:
        base = float(df["total_value"].iloc[-31])
        change_30 = safe_pct(latest - base, base)

    return {
        "daily_volatility_pct": None if pd.isna(daily_vol) else float(daily_vol),
        "max_drawdown_pct": float(drawdown.min()),
        "latest_7obs_change_pct": change_7,
        "latest_30obs_change_pct": change_30,
    }


@cache.memoize(timeout=60)
def build_risk_summary(period: str = "all", start_date: str | None = None, end_date: str | None = None) -> Dict:
    latest_date, snapshot = latest_snapshot()
    if snapshot.empty:
        return {"ok": False, "error": "no latest snapshot found"}

    df = snapshot.copy()
    df["currency_group"] = df["currency"].apply(currency_label)
    label_map = mapped_portfolio_labels()
    labels = df.apply(
        lambda row: classify_position(row.get("ticker"), row.get("type"), row.get("currency"), label_map),
        axis=1,
        result_type="expand",
    )
    df = pd.concat([df, labels], axis=1)

    total_value = float(df["evaluation_amount"].sum())
    positions = investment_positions(df)
    concentration = _concentration_metrics(positions, total_value)
    top = _top_positions(positions, total_value)
    currency_exposure = _exposure_by(df, "currency_group", total_value, "currency")
    asset_exposure = _exposure_by(df, "type", total_value, "asset_type")
    portfolio_sector_exposure = _label_exposure_by(positions, "portfolio_sector", total_value, "portfolio_sector")
    portfolio_role_exposure = _label_exposure_by(positions, "portfolio_role", total_value, "portfolio_role")
    account_values, period_range = filter_by_period(load_account_values(), "date", period, start_date, end_date)
    account_risk = _account_risk(account_values)

    return {
        "ok": True,
        "asof_date": latest_date,
        "period": period_range.__dict__,
        "summary": {
            "total_value": total_value,
            "position_count": concentration["position_count"],
        },
        "concentration": concentration,
        "top_positions": top,
        "currency_exposure": currency_exposure,
        "asset_type_exposure": asset_exposure,
        "portfolio_sector_exposure": portfolio_sector_exposure,
        "portfolio_role_exposure": portfolio_role_exposure,
        "account_risk": account_risk,
    }
