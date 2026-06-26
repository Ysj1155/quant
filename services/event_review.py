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
DEFAULT_THRESHOLD_PCT = 5.0
RISK_BUCKET_THRESHOLDS = {
    "고변동": 10.0,
    "중간": 5.0,
    "낮음": 3.0,
    "미분류": DEFAULT_THRESHOLD_PCT,
}
ASSET_TYPE_THRESHOLDS = {
    "금현물": 3.0,
    "현금": None,
    "예수금": None,
    "외화예수금": None,
}


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
    row = _positions_for_date(future_date).get(event.get("_position_key") or event.get("position_key"))
    if not row:
        return None
    price = _evaluation_price(row)
    return price if price > EPS else None


def _threshold_for_event(event: Dict, labels: Dict) -> tuple[Optional[float], str]:
    asset_type = str(event.get("asset_type") or "").strip()
    risk_bucket = str(labels.get("risk_bucket") or "").strip()

    if asset_type in ASSET_TYPE_THRESHOLDS:
        return ASSET_TYPE_THRESHOLDS[asset_type], f"자산군:{asset_type}"
    if risk_bucket in RISK_BUCKET_THRESHOLDS:
        return RISK_BUCKET_THRESHOLDS[risk_bucket], f"리스크:{risk_bucket}"
    return DEFAULT_THRESHOLD_PCT, "기본"


def _outcome_label(event_group: str, forward_return: Optional[float], threshold: Optional[float]) -> str:
    if threshold is None:
        return "가격 검증 제외"
    if forward_return is None:
        return "추적 불가"

    if event_group == "buy":
        if forward_return >= threshold:
            return "매수 후 의미 있는 상승"
        if forward_return <= -threshold:
            return "매수 후 의미 있는 하락"
        return "매수 후 관찰 범위"

    if event_group == "sell":
        if forward_return >= threshold:
            return "매도 후 상승: 기회비용 점검"
        if forward_return <= -threshold:
            return "매도 후 하락: 방어 효과"
        return "매도 후 관찰 범위"

    return "분류 제외"


def _context_label(event_group: str) -> str:
    if event_group == "buy":
        return "진입 근거 검증"
    if event_group == "sell":
        return "매도 맥락 점검"
    return "복기 대상"


def _review_prompt(event: Dict, label_30: str, forward_30: Optional[float], threshold: Optional[float], threshold_basis: str) -> str:
    name = event.get("name") or "해당 종목"
    role = event.get("portfolio_role") or "역할 미분류"
    risk = event.get("risk_bucket") or "리스크 미분류"
    threshold_text = "가격 기준 제외" if threshold is None else f"±{threshold:.0f}% 기준"

    if threshold is None:
        return f"{name}은 가격 사후검증보다 비중/유동성 맥락으로 보는 편이 낫습니다. 당시 보유 목적을 메모하세요."
    if label_30 == "추적 불가":
        return f"{name} 이벤트 이후 보유 가격을 추적할 수 없습니다. 당시 판단 근거와 이후 재진입 여부를 메모하세요."

    if event.get("event_group") == "buy":
        return (
            f"{name} 매수 뒤 30관측치 변화는 {forward_30:.2f}%입니다. "
            f"{role}/{risk} 포지션의 {threshold_text}({threshold_basis})에서 진입 근거가 충분했는지 복기하세요."
        )
    if event.get("event_group") == "sell":
        return (
            f"{name} 매도 뒤 30관측치 변화는 {forward_30:.2f}%입니다. "
            f"가격만으로 판단하지 말고, {role}/{risk} 포지션의 비중 축소·리스크 완화·기회비용을 분리해서 복기하세요."
        )
    return "복기 대상 이벤트입니다."


@lru_cache(maxsize=512)
def _total_value_for_date(date: str) -> float:
    rows = _positions_for_date(date).values()
    return float(sum(float(row.get("evaluation_amount", 0.0) or 0.0) for row in rows))


def _event_row(event: Dict, dates: List[str], label_map: Dict) -> Dict:
    labels = classify_position(event.get("name"), event.get("asset_type"), event.get("currency"), label_map)
    event_with_labels = {**event, **labels}
    threshold, threshold_basis = _threshold_for_event(event, labels)
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
            "threshold_pct": threshold,
            "threshold_basis": threshold_basis,
            "label": _outcome_label(event.get("event_group", ""), forward_return, threshold),
        }

    total_value = _total_value_for_date(event["date"])
    position_value = float(event.get("evaluation_amount_after") or event.get("evaluation_amount_before") or 0.0)
    label_30 = outcomes["30obs"]["label"]
    forward_30 = outcomes["30obs"]["forward_return_pct"]

    return {
        "event_id": event.get("event_id"),
        "date": event.get("date"),
        "event_type": event.get("event_type"),
        "event_group": event.get("event_group"),
        "review_context": _context_label(event.get("event_group", "")),
        "name": event.get("name"),
        "asset_type": event.get("asset_type"),
        "currency": event.get("currency"),
        "portfolio_sector": labels.get("portfolio_sector"),
        "portfolio_role": labels.get("portfolio_role"),
        "risk_bucket": labels.get("risk_bucket"),
        "threshold_pct": threshold,
        "threshold_basis": threshold_basis,
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
        "review_prompt": _review_prompt(event_with_labels, label_30, forward_30, threshold, threshold_basis),
        "confidence": event.get("confidence"),
        "reason": event.get("reason"),
    }


def _summary(rows: List[Dict], period_range) -> Dict:
    counts: Dict[str, int] = {}
    threshold_counts: Dict[str, int] = {}
    buy_total = 0
    sell_total = 0
    trackable = 0
    favorable_buy = 0
    defensive_sell = 0
    opportunity_sell = 0

    for row in rows:
        label = row.get("label_30obs") or "Unknown"
        counts[label] = counts.get(label, 0) + 1

        basis = row.get("threshold_basis") or "기본"
        threshold_counts[basis] = threshold_counts.get(basis, 0) + 1

        event_group = row.get("event_group")
        if event_group == "buy":
            buy_total += 1
        elif event_group == "sell":
            sell_total += 1

        forward = row.get("forward_return_30obs_pct")
        if forward is not None:
            trackable += 1
            threshold = row.get("threshold_pct")
            if threshold is None:
                continue
            threshold = float(threshold)
            if event_group == "buy" and forward >= threshold:
                favorable_buy += 1
            elif event_group == "sell" and forward <= -threshold:
                defensive_sell += 1
            elif event_group == "sell" and forward >= threshold:
                opportunity_sell += 1

    return {
        "total": len(rows),
        "buy_total": buy_total,
        "sell_total": sell_total,
        "trackable_30obs": trackable,
        "favorable_30obs": favorable_buy + defensive_sell,
        "favorable_buy_30obs": favorable_buy,
        "defensive_sell_30obs": defensive_sell,
        "opportunity_sell_30obs": opportunity_sell,
        "counts": counts,
        "threshold_counts": threshold_counts,
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
