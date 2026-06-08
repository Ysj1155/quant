from __future__ import annotations

from typing import Dict, List, Optional

import pandas as pd

from extensions import cache
from services.analysis_utils import (
    latest_investment_positions,
    load_account_values,
    mask_account,
    safe_pct,
)
from services.periods import filter_by_period
from services.periods import filter_date_strings
from services.snapshots import list_snapshot_dates, load_snapshot_frame
from services.analysis_utils import investment_positions
from services.timeline import _append_diff_events, _positions_for_date


def _xnpv(rate: float, cashflows: List[Dict]) -> float:
    if not cashflows:
        return 0.0
    base = pd.to_datetime(cashflows[0]["date"])
    total = 0.0
    for flow in cashflows:
        days = (pd.to_datetime(flow["date"]) - base).days
        total += float(flow["amount"]) / ((1.0 + rate) ** (days / 365.0))
    return total


def _xirr(cashflows: List[Dict]) -> Optional[float]:
    flows = [flow for flow in cashflows if abs(float(flow.get("amount", 0.0))) > 1e-9]
    if not flows:
        return None
    if not any(float(flow["amount"]) > 0 for flow in flows):
        return None
    if not any(float(flow["amount"]) < 0 for flow in flows):
        return None

    low = -0.9999
    high = 10.0
    low_val = _xnpv(low, flows)
    high_val = _xnpv(high, flows)

    tries = 0
    while low_val * high_val > 0 and high < 1_000 and tries < 20:
        high *= 2
        high_val = _xnpv(high, flows)
        tries += 1

    if low_val * high_val > 0:
        return None

    for _ in range(100):
        mid = (low + high) / 2.0
        mid_val = _xnpv(mid, flows)
        if abs(mid_val) < 1e-5:
            return mid * 100.0
        if low_val * mid_val <= 0:
            high = mid
            high_val = mid_val
        else:
            low = mid
            low_val = mid_val
    return ((low + high) / 2.0) * 100.0


def _investment_value(date: str) -> float:
    df = load_snapshot_frame(date)
    if df.empty:
        return 0.0
    return float(investment_positions(df)["evaluation_amount"].sum())


def _window_trade_events(filtered_dates: List[str]) -> List[Dict]:
    all_dates = list_snapshot_dates()
    if len(all_dates) < 2 or not filtered_dates:
        return []

    start_idx = all_dates.index(filtered_dates[0])
    end_idx = all_dates.index(filtered_dates[-1])
    scan_dates = all_dates[max(0, start_idx - 1): end_idx + 1]
    if len(scan_dates) < 2:
        return []

    events: List[Dict] = []
    target_dates = set(filtered_dates)
    prev_map = _positions_for_date(scan_dates[0])
    for current_date in scan_dates[1:]:
        cur_map = _positions_for_date(current_date)
        if current_date in target_dates:
            _append_diff_events(events, current_date, prev_map, cur_map)
        prev_map = cur_map
    return events


def _build_advanced_returns(account_values: pd.DataFrame, period: str, start_date: Optional[str], end_date: Optional[str]) -> Dict:
    all_dates = list_snapshot_dates()
    filtered_dates, period_range = filter_date_strings(all_dates, period, start_date, end_date)
    if len(filtered_dates) < 2 or account_values.empty or len(account_values) < 2:
        return {
            "period": period_range.__dict__,
            "simple_return_pct": None,
            "account_twr_pct": None,
            "investment_twr_pct": None,
            "investment_irr_annual_pct": None,
            "flow_count": 0,
            "buy_cash_flow_est": 0.0,
            "sell_cash_flow_est": 0.0,
            "method_note": "기간 내 성과 계산에 필요한 관측치가 부족합니다.",
        }

    start_account = float(account_values["total_value"].iloc[0])
    end_account = float(account_values["total_value"].iloc[-1])
    simple_return = safe_pct(end_account - start_account, start_account)

    account_returns = account_values["total_value"].pct_change().dropna()
    account_twr = float(((account_returns + 1.0).prod() - 1.0) * 100.0) if len(account_returns) else None

    investment_values = {date: _investment_value(date) for date in filtered_dates}
    events = _window_trade_events(filtered_dates)
    flow_by_date: Dict[str, float] = {date: 0.0 for date in filtered_dates}
    buy_cash = 0.0
    sell_cash = 0.0
    for event in events:
        cash_flow = event.get("cash_flow_est")
        if cash_flow is None:
            continue
        date = event["date"]
        investor_cash_flow = float(cash_flow)
        contribution_to_investments = -investor_cash_flow
        flow_by_date[date] = flow_by_date.get(date, 0.0) + contribution_to_investments
        if investor_cash_flow < 0:
            buy_cash += abs(investor_cash_flow)
        else:
            sell_cash += investor_cash_flow

    twr_factor = 1.0
    for prev_date, cur_date in zip(filtered_dates, filtered_dates[1:]):
        prev_value = investment_values.get(prev_date, 0.0)
        cur_value = investment_values.get(cur_date, 0.0)
        flow = flow_by_date.get(cur_date, 0.0)
        if abs(prev_value) <= 1e-9:
            continue
        twr_factor *= 1.0 + ((cur_value - prev_value - flow) / prev_value)
    investment_twr = float((twr_factor - 1.0) * 100.0)

    irr_flows = [{"date": filtered_dates[0], "amount": -investment_values[filtered_dates[0]]}]
    for event in events:
        cash_flow = event.get("cash_flow_est")
        if cash_flow is not None:
            irr_flows.append({"date": event["date"], "amount": float(cash_flow)})
    irr_flows.append({"date": filtered_dates[-1], "amount": investment_values[filtered_dates[-1]]})

    return {
        "period": period_range.__dict__,
        "simple_return_pct": simple_return,
        "account_twr_pct": account_twr,
        "investment_twr_pct": investment_twr,
        "investment_irr_annual_pct": _xirr(irr_flows),
        "flow_count": len([event for event in events if event.get("cash_flow_est") is not None]),
        "buy_cash_flow_est": buy_cash,
        "sell_cash_flow_est": sell_cash,
        "start_account_value": start_account,
        "end_account_value": end_account,
        "start_investment_value": investment_values[filtered_dates[0]],
        "end_investment_value": investment_values[filtered_dates[-1]],
        "method_note": "TWR/IRR은 스냅샷과 추정 이벤트 원장을 기반으로 한 복기용 추정치입니다.",
    }


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
def build_performance_summary(period: str = "all", start_date: str | None = None, end_date: str | None = None) -> Dict:
    latest_date, positions = latest_investment_positions()
    account_values_all = load_account_values()
    account_values, period_range = filter_by_period(account_values_all, "date", period, start_date, end_date)

    if positions.empty:
        return {"ok": False, "error": "no latest positions found"}

    latest_total_value = None
    if not account_values_all.empty:
        latest_total_value = float(account_values_all["total_value"].iloc[-1])

    period_change = None
    period_change_pct = None
    if len(account_values) >= 2:
        first_value = float(account_values["total_value"].iloc[0])
        last_value = float(account_values["total_value"].iloc[-1])
        period_change = last_value - first_value
        period_change_pct = safe_pct(period_change, first_value)

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
        "period": period_range.__dict__,
        "summary": {
            "latest_total_value": latest_total_value,
            "invested_evaluation_amount": invested_eval,
            "purchase_amount": purchase_amount,
            "profit_loss": profit_loss,
            "profit_rate": safe_pct(profit_loss, purchase_amount),
            "period_change": period_change,
            "period_change_pct": period_change_pct,
            "position_count": int(len(positions)),
            "top_position": top_position,
        },
        "contributors": _build_contributors(positions, total_eval=total_eval),
        "asset_type_summary": _build_asset_type_summary(positions, total_eval=total_eval),
        "monthly_changes": _build_monthly_changes(account_values),
        "daily_moves": _build_daily_moves(account_values),
        "advanced_returns": _build_advanced_returns(account_values, period, start_date, end_date),
    }
