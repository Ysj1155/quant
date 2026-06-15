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


def _krw_text(value) -> str:
    if value is None:
        return "-"
    return f"{float(value):,.0f} KRW"


def _pct_text(value) -> str:
    if value is None:
        return "-"
    return f"{float(value):,.2f}%"


def _build_evidence_cards(summary: Dict, advanced: Dict, contributors: Dict, asset_rows: List[Dict], daily_moves: Dict) -> List[Dict]:
    cards: List[Dict] = []
    period = advanced.get("period") or {}
    start_date = period.get("start_date") or "-"
    end_date = period.get("end_date") or "-"

    cards.append({
        "title": "기간 변화 근거",
        "value": _krw_text(summary.get("period_change")),
        "sub": _pct_text(summary.get("period_change_pct")),
        "detail": (
            f"{start_date} {_krw_text(advanced.get('start_account_value'))}에서 "
            f"{end_date} {_krw_text(advanced.get('end_account_value'))}로 이동했습니다."
        ),
        "question": "이 변화가 가격 움직임 때문인지, 현금흐름 때문인지 분리해서 봤는가?",
        "source": "계좌 총액 시계열",
        "signed": summary.get("period_change"),
    })

    cards.append({
        "title": "현금흐름 조정 성과",
        "value": _pct_text(advanced.get("investment_twr_pct")),
        "sub": f"단순수익률 {_pct_text(advanced.get('simple_return_pct'))}",
        "detail": (
            f"기간 중 추정 매수 {_krw_text(advanced.get('buy_cash_flow_est'))}, "
            f"추정 매도 {_krw_text(advanced.get('sell_cash_flow_est'))}를 성과 해석에서 분리했습니다."
        ),
        "question": "추가 매수/매도가 성과를 키운 것인지, 보유 자산 자체가 움직인 것인지 확인했는가?",
        "source": "투자 이벤트 추정 현금흐름",
        "signed": advanced.get("investment_twr_pct"),
    })

    gainers = contributors.get("top_gainers") or []
    losers = contributors.get("top_losers") or []
    top_gain = gainers[0] if gainers else None
    top_loss = losers[0] if losers else None
    if top_gain or top_loss:
        main = top_gain or top_loss
        detail_parts = []
        if top_gain:
            detail_parts.append(f"최대 이익 기여: {top_gain.get('name')} {_krw_text(top_gain.get('profit_loss'))}")
        if top_loss:
            detail_parts.append(f"최대 손실 기여: {top_loss.get('name')} {_krw_text(top_loss.get('profit_loss'))}")
        cards.append({
            "title": "종목 기여 집중",
            "value": str(main.get("name") or "-"),
            "sub": _krw_text(main.get("profit_loss")),
            "detail": " / ".join(detail_parts),
            "question": "이번 성과를 설명하는 종목이 실제 판단의 핵심 종목이었는가?",
            "source": "보유 종목 평가손익",
            "signed": main.get("profit_loss"),
        })

    if asset_rows:
        top_asset = asset_rows[0]
        cards.append({
            "title": "자산군 기여",
            "value": str(top_asset.get("asset_type") or "-"),
            "sub": f"비중 {_pct_text(top_asset.get('weight_pct'))}",
            "detail": (
                f"{top_asset.get('asset_type') or '-'} 평가금액은 {_krw_text(top_asset.get('evaluation_amount'))}, "
                f"평가손익은 {_krw_text(top_asset.get('profit_loss'))}입니다."
            ),
            "question": "자산군 비중은 의도한 배분인가, 성과 때문에 커진 결과인가?",
            "source": "자산군별 보유 평가",
            "signed": top_asset.get("profit_loss"),
        })

    best_days = daily_moves.get("best_days") or []
    worst_days = daily_moves.get("worst_days") or []
    if best_days or worst_days:
        best = best_days[0] if best_days else None
        worst = worst_days[0] if worst_days else None
        main_day = worst or best
        detail_parts = []
        if best:
            detail_parts.append(f"최대 상승일 {best.get('date')} {_krw_text(best.get('change'))} ({_pct_text(best.get('change_pct'))})")
        if worst:
            detail_parts.append(f"최대 하락일 {worst.get('date')} {_krw_text(worst.get('change'))} ({_pct_text(worst.get('change_pct'))})")
        cards.append({
            "title": "일별 변동 증거",
            "value": str(main_day.get("date") or "-"),
            "sub": _krw_text(main_day.get("change")),
            "detail": " / ".join(detail_parts),
            "question": "큰 변동일에 포지션을 바꾸었는지, 그냥 통과했는지 기록할 만한가?",
            "source": "일별 계좌 변화",
            "signed": main_day.get("change"),
        })

    return cards


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

    contributors = _build_contributors(positions, total_eval=total_eval)
    asset_type_summary = _build_asset_type_summary(positions, total_eval=total_eval)
    monthly_changes = _build_monthly_changes(account_values)
    daily_moves = _build_daily_moves(account_values)
    advanced_returns = _build_advanced_returns(account_values, period, start_date, end_date)
    summary = {
        "latest_total_value": latest_total_value,
        "invested_evaluation_amount": invested_eval,
        "purchase_amount": purchase_amount,
        "profit_loss": profit_loss,
        "profit_rate": safe_pct(profit_loss, purchase_amount),
        "period_change": period_change,
        "period_change_pct": period_change_pct,
        "position_count": int(len(positions)),
        "top_position": top_position,
    }

    return {
        "ok": True,
        "asof_date": latest_date,
        "period": period_range.__dict__,
        "summary": summary,
        "contributors": contributors,
        "asset_type_summary": asset_type_summary,
        "monthly_changes": monthly_changes,
        "daily_moves": daily_moves,
        "advanced_returns": advanced_returns,
        "evidence_cards": _build_evidence_cards(summary, advanced_returns, contributors, asset_type_summary, daily_moves),
    }
