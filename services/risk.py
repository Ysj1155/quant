from __future__ import annotations

from typing import Dict, List, Optional

import pandas as pd

from extensions import cache
from services.analysis_utils import (
    currency_label,
    investment_positions,
    is_cash_type,
    latest_snapshot,
    load_account_values,
    safe_pct,
)


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


def _alert(severity: str, title: str, message: str, metric: Optional[float] = None) -> Dict:
    return {
        "severity": severity,
        "title": title,
        "message": message,
        "metric": metric,
    }


def _build_alerts(
    concentration: Dict,
    currency_exposure: List[Dict],
    asset_exposure: List[Dict],
    top_positions: List[Dict],
    snapshot: pd.DataFrame,
    total_value: float,
) -> List[Dict]:
    alerts: List[Dict] = []
    top1 = concentration.get("top1_weight_pct", 0.0)
    top3 = concentration.get("top3_weight_pct", 0.0)

    if top1 >= 30:
        name = top_positions[0]["name"] if top_positions else "상위 종목"
        alerts.append(_alert("high", "단일 종목 집중", f"{name} 비중이 {top1:.2f}%입니다.", top1))
    elif top1 >= 20:
        name = top_positions[0]["name"] if top_positions else "상위 종목"
        alerts.append(_alert("medium", "단일 종목 비중 상승", f"{name} 비중이 {top1:.2f}%입니다.", top1))

    if top3 >= 60:
        alerts.append(_alert("medium", "상위 3개 종목 집중", f"상위 3개 종목 비중이 {top3:.2f}%입니다.", top3))

    for row in currency_exposure:
        if row["weight_pct"] >= 70:
            alerts.append(_alert("medium", "통화 노출 집중", f"{row['currency']} 노출이 {row['weight_pct']:.2f}%입니다.", row["weight_pct"]))

    for row in asset_exposure:
        if row["weight_pct"] >= 75 and not is_cash_type(row["asset_type"]):
            alerts.append(_alert("medium", "자산군 집중", f"{row['asset_type']} 비중이 {row['weight_pct']:.2f}%입니다.", row["weight_pct"]))

    cash_value = float(snapshot[snapshot["type"].apply(is_cash_type)]["evaluation_amount"].sum())
    cash_pct = safe_pct(cash_value, total_value)
    if cash_pct < 3:
        alerts.append(_alert("low", "현금 비중 낮음", f"현금성 자산 비중이 {cash_pct:.2f}%입니다.", cash_pct))

    losing = investment_positions(snapshot)
    losing = losing[losing["profit_rate"].astype(float) <= -20].copy()
    for row in losing.sort_values("profit_rate").head(3).to_dict("records"):
        profit_rate = float(row["profit_rate"])
        alerts.append(_alert(
            "medium",
            "손실 포지션 점검",
            f"{row['ticker']} 수익률이 {profit_rate:.2f}%입니다.",
            profit_rate,
        ))

    return alerts


@cache.memoize(timeout=60)
def build_risk_summary() -> Dict:
    latest_date, snapshot = latest_snapshot()
    if snapshot.empty:
        return {"ok": False, "error": "no latest snapshot found"}

    df = snapshot.copy()
    df["currency_group"] = df["currency"].apply(currency_label)

    total_value = float(df["evaluation_amount"].sum())
    positions = investment_positions(df)
    concentration = _concentration_metrics(positions, total_value)
    top = _top_positions(positions, total_value)
    currency_exposure = _exposure_by(df, "currency_group", total_value, "currency")
    asset_exposure = _exposure_by(df, "type", total_value, "asset_type")
    account_risk = _account_risk(load_account_values())
    alerts = _build_alerts(
        concentration=concentration,
        currency_exposure=currency_exposure,
        asset_exposure=asset_exposure,
        top_positions=top,
        snapshot=df,
        total_value=total_value,
    )

    severity_rank = {"high": 3, "medium": 2, "low": 1}
    max_severity = "low"
    if alerts:
        max_severity = max(alerts, key=lambda item: severity_rank.get(item["severity"], 0))["severity"]

    return {
        "ok": True,
        "asof_date": latest_date,
        "summary": {
            "total_value": total_value,
            "risk_level": max_severity,
            "alert_count": len(alerts),
            "position_count": concentration["position_count"],
        },
        "concentration": concentration,
        "top_positions": top,
        "currency_exposure": currency_exposure,
        "asset_type_exposure": asset_exposure,
        "account_risk": account_risk,
        "alerts": alerts,
    }
