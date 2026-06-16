from __future__ import annotations

from functools import lru_cache
from typing import Dict, List, Optional

from extensions import cache
from services.analysis_utils import EPS, safe_pct
from services.periods import resolve_period_range
from services.portfolio_labels import classify_position, mapped_portfolio_labels
from services.snapshots import list_snapshot_dates
from services.timeline import _evaluation_price, _positions_for_date, build_investment_timeline

HORIZONS = (7, 30)


def _future_date(dates: List[str], event_date: str, horizon: int) -> Optional[str]:
    try:
        idx = dates.index(event_date)
    except ValueError:
        return None
    target_idx = idx + horizon
    if target_idx >= len(dates):
        return None
    return dates[target_idx]


def _future_price(event: Dict, future_date: str | None) -> Optional[float]:
    if not future_date:
        return None
    row = _positions_for_date(future_date).get(event.get("position_key"))
    if not row:
        return None
    price = _evaluation_price(row)
    return price if price > EPS else None


def _outcome_label(event_group: str, forward_return: Optional[float]) -> str:
    if forward_return is None:
        return "추적 불가"
    if event_group == "buy":
        if forward_return >= 5:
            return "매수 후 상승"
        if forward_return <= -5:
            return "매수 후 하락"
        return "매수 후 보합"
    if event_group == "sell":
        if forward_return >= 5:
            return "매도 후 상승"
        if forward_return <= -5:
            return "매도 후 하락 회피"
        return "매도 후 보합"
    return "분류 제외"


def _review_prompt(event: Dict, label_30: str, forward_30: Optional[float]) -> str:
    name = event.get("name") or "해당 종목"
    if label_30 == "추적 불가":
        return f"{name} 이벤트 이후 보유 가격을 추적할 수 없어, 당시 판단 근거를 메모로 남길 만합니다."
    if event.get("event_group") == "buy":
        return f"{name} 매수 뒤 30관측치 수익률은 {forward_30:.2f}%입니다. 진입 근거가 가격 변화로 검증됐는지 복기하세요."
    if event.get("event_group") == "sell":
        return f"{name} 매도 뒤 30관측치 변화는 {forward_30:.2f}%입니다. 매도가 손실 회피였는지, 기회비용이었는지 복기하세요."
    return "복기 대상 이벤트입니다."


@lru_cache(maxsize=512)
def _total_value_for_date(date: str) -> float:
    rows = _positions_for_date(date).values()
    return float(sum(float(row.get("evaluation_amount", 0.0) or 0.0) for row in rows))


def _event_row(event: Dict, dates: List[str], label_map: Dict) -> Dict:
    event_price = float(event.get("event_unit_price_est") or 0.0)
    outcomes: Dict[str, Dict] = {}
    for horizon in HORIZONS:
        date = _future_date(dates, event["date"], horizon)
        price = _future_price(event, date)
        forward_return = safe_pct(price - event_price, event_price) if price is not None and event_price > EPS else None
        outcomes[f"{horizon}obs"] = {
            "date": date,
            "price": price,
            "forward_return_pct": forward_return,
            "label": _outcome_label(event.get("event_group", ""), forward_return),
        }

    labels = classify_position(event.get("name"), event.get("asset_type"), event.get("currency"), label_map)
    total_value = _total_value_for_date(event["date"])
    position_value = float(event.get("evaluation_amount_after") or event.get("evaluation_amount_before") or 0.0)
    label_30 = outcomes["30obs"]["label"]
    forward_30 = outcomes["30obs"]["forward_return_pct"]

    return {
        "event_id": event.get("event_id"),
        "date": event.get("date"),
        "event_type": event.get("event_type"),
        "event_group": event.get("event_group"),
        "name": event.get("name"),
        "asset_type": event.get("asset_type"),
        "currency": event.get("currency"),
        "portfolio_sector": labels.get("portfolio_sector"),
        "portfolio_role": labels.get("portfolio_role"),
        "risk_bucket": labels.get("risk_bucket"),
        "quantity_delta": event.get("quantity_delta"),
        "event_unit_price_est": event_price,
        "cash_flow_est": event.get("cash_flow_est"),
        "realized_pnl_est": event.get("realized_pnl_est"),
        "profit_rate_before": event.get("profit_rate_before"),
        "profit_rate_after": event.get("profit_rate_after"),
        "position_weight_after_pct": safe_pct(position_value, total_value),
        "outcomes": outcomes,
        "label_30obs": label_30,
        "forward_return_30obs_pct": forward_30,
        "review_prompt": _review_prompt(event, label_30, forward_30),
        "confidence": event.get("confidence"),
        "reason": event.get("reason"),
    }


def _summary(rows: List[Dict], period_range) -> Dict:
    counts: Dict[str, int] = {}
    trackable = 0
    favorable = 0
    for row in rows:
        label = row.get("label_30obs") or "Unknown"
        counts[label] = counts.get(label, 0) + 1
        forward = row.get("forward_return_30obs_pct")
        if forward is not None:
            trackable += 1
            if (row.get("event_group") == "buy" and forward >= 0) or (row.get("event_group") == "sell" and forward <= 0):
                favorable += 1

    return {
        "total": len(rows),
        "trackable_30obs": trackable,
        "favorable_30obs": favorable,
        "counts": counts,
        "period": period_range.__dict__,
        "horizons": list(HORIZONS),
    }


@cache.memoize(timeout=60)
def build_event_review_dataset(
    period: str = "all",
    start_date: str | None = None,
    end_date: str | None = None,
    limit: int = 80,
) -> Dict:
    dates = list_snapshot_dates()
    period_range = resolve_period_range(period, start_date, end_date, dates)
    use_fast_recent_scan = period == "all" and not start_date and not end_date
    timeline = build_investment_timeline(
        limit=limit if use_fast_recent_scan else None,
        include_initial=False,
        full_scan=not use_fast_recent_scan,
        period=period,
        start_date=start_date,
        end_date=end_date,
    )
    if not timeline.get("ok"):
        return timeline

    label_map = mapped_portfolio_labels()
    events = [
        event
        for event in timeline.get("events") or []
        if event.get("event_group") in ("buy", "sell")
    ]
    rows = [_event_row(event, dates, label_map) for event in events]
    rows = sorted(rows, key=lambda row: row["date"], reverse=True)
    total = len(rows)
    if limit and limit > 0:
        rows = rows[:limit]

    return {
        "ok": True,
        "rows": rows,
        "summary": {
            **_summary(rows, period_range),
            "total_available": total,
            "returned": len(rows),
        },
    }
