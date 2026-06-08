from __future__ import annotations

from functools import lru_cache
from typing import Dict, List, Optional

import pandas as pd

from extensions import cache
from services.analysis_utils import EPS, is_cash_type, mask_account
from services.periods import resolve_period_range
from services.snapshots import list_snapshot_dates, load_snapshot_frame


def _position_key(row: Dict) -> str:
    return "|".join([
        str(row.get("account_number", "")).strip(),
        str(row.get("ticker", "")).strip(),
        str(row.get("type", "")).strip(),
    ])


def _safe_rate(profit_loss: float, purchase_amount: float) -> float:
    if abs(purchase_amount) <= EPS:
        return 0.0
    return float(profit_loss / purchase_amount * 100.0)


def _safe_float(value, default: float = 0.0) -> float:
    try:
        return float(value or 0.0)
    except Exception:
        return default


def _avg_purchase_price(row: Dict) -> float:
    quantity = _safe_float(row.get("quantity"))
    if abs(quantity) <= EPS:
        return 0.0
    return _safe_float(row.get("purchase_amount")) / quantity


def _evaluation_price(row: Dict) -> float:
    quantity = _safe_float(row.get("quantity"))
    if abs(quantity) <= EPS:
        return 0.0
    return _safe_float(row.get("evaluation_amount")) / quantity


@lru_cache(maxsize=512)
def _positions_for_date(date: str) -> Dict[str, Dict]:
    df = load_snapshot_frame(date)
    if df.empty:
        return {}

    df = df.copy()
    df = df[~df["type"].apply(is_cash_type)]
    df = df[
        (df["ticker"].astype(str).str.strip() != "")
        & ((df["quantity"].abs() > EPS) | (df["evaluation_amount"].abs() > EPS))
    ].copy()

    if df.empty:
        return {}

    grouped = (
        df.groupby(["account_number", "ticker", "type", "currency"], dropna=False)
        .agg({
            "quantity": "sum",
            "purchase_amount": "sum",
            "evaluation_amount": "sum",
            "profit_loss": "sum",
            "evaluation_ratio": "sum",
        })
        .reset_index()
    )
    grouped["profit_rate"] = grouped.apply(
        lambda row: _safe_rate(float(row["profit_loss"]), float(row["purchase_amount"])),
        axis=1,
    )

    out = {}
    for row in grouped.to_dict("records"):
        row["date"] = date
        row["key"] = _position_key(row)
        out[row["key"]] = row
    return out


def _append_diff_events(events: List[Dict], current_date: str, prev_map: Dict[str, Dict], cur_map: Dict[str, Dict]) -> None:
    prev_keys = set(prev_map.keys())
    cur_keys = set(cur_map.keys())

    for key in sorted(cur_keys - prev_keys):
        _append_new_position(events, current_date, cur_map[key])

    for key in sorted(prev_keys - cur_keys):
        _append_full_sell(events, current_date, prev_map[key])

    for key in sorted(prev_keys & cur_keys):
        prev = prev_map[key]
        cur = cur_map[key]
        prev_qty = float(prev.get("quantity", 0.0) or 0.0)
        cur_qty = float(cur.get("quantity", 0.0) or 0.0)

        if cur_qty > prev_qty + EPS:
            _append_add_position(events, current_date, prev, cur)
        elif cur_qty < prev_qty - EPS and cur_qty > EPS:
            _append_partial_sell(events, current_date, prev, cur)


def _base_event(date: str, event_type: str, row: Dict) -> Dict:
    account = str(row.get("account_number", "")).strip()
    key = str(row.get("key") or _position_key(row))
    return {
        "event_id": f"{date}|{event_type}|{key}",
        "date": date,
        "event_type": event_type,
        "event_group": "position",
        "account_label": mask_account(account),
        "name": str(row.get("ticker", "")).strip(),
        "asset_type": str(row.get("type", "")).strip(),
        "currency": str(row.get("currency", "")).strip(),
        "quantity_after": float(row.get("quantity", 0.0) or 0.0),
        "purchase_amount_after": float(row.get("purchase_amount", 0.0) or 0.0),
        "evaluation_amount_after": float(row.get("evaluation_amount", 0.0) or 0.0),
        "profit_loss_after": float(row.get("profit_loss", 0.0) or 0.0),
        "profit_rate_after": float(row.get("profit_rate", 0.0) or 0.0),
        "avg_purchase_price_after": _avg_purchase_price(row),
        "quantity_before": None,
        "purchase_amount_before": None,
        "evaluation_amount_before": None,
        "profit_loss_before": None,
        "avg_purchase_price_before": None,
        "event_unit_price_est": None,
        "cash_flow_est": None,
        "confidence": "high",
        "reason": "",
    }


def _append_new_position(events: List[Dict], date: str, row: Dict, initial: bool = False) -> None:
    event = _base_event(date, "initial_position" if initial else "buy_open", row)
    qty = _safe_float(row.get("quantity"))
    purchase_delta = _safe_float(row.get("purchase_amount"))
    event.update({
        "event_group": "initial" if initial else "buy",
        "quantity_before": 0.0,
        "purchase_amount_before": 0.0,
        "evaluation_amount_before": 0.0,
        "profit_loss_before": 0.0,
        "avg_purchase_price_before": 0.0,
        "quantity_delta": qty,
        "purchase_amount_delta": purchase_delta,
        "evaluation_amount_delta": _safe_float(row.get("evaluation_amount")),
        "realized_pnl_est": None,
        "event_unit_price_est": purchase_delta / qty if abs(qty) > EPS else 0.0,
        "cash_flow_est": None if initial else -purchase_delta,
        "confidence": "baseline" if initial else "high",
        "reason": "첫 스냅샷의 기존 보유분입니다." if initial else "직전 스냅샷에는 없고 현재 스냅샷에 새로 나타난 보유 종목입니다.",
    })
    events.append(event)


def _append_add_position(events: List[Dict], date: str, prev: Dict, cur: Dict) -> None:
    event = _base_event(date, "buy_add", cur)
    quantity_delta = _safe_float(cur.get("quantity")) - _safe_float(prev.get("quantity"))
    purchase_delta = _safe_float(cur.get("purchase_amount")) - _safe_float(prev.get("purchase_amount"))
    event.update({
        "event_group": "buy",
        "quantity_before": _safe_float(prev.get("quantity")),
        "purchase_amount_before": _safe_float(prev.get("purchase_amount")),
        "evaluation_amount_before": _safe_float(prev.get("evaluation_amount")),
        "profit_loss_before": _safe_float(prev.get("profit_loss")),
        "avg_purchase_price_before": _avg_purchase_price(prev),
        "quantity_delta": quantity_delta,
        "purchase_amount_delta": purchase_delta,
        "evaluation_amount_delta": _safe_float(cur.get("evaluation_amount")) - _safe_float(prev.get("evaluation_amount")),
        "realized_pnl_est": None,
        "event_unit_price_est": purchase_delta / quantity_delta if abs(quantity_delta) > EPS else 0.0,
        "cash_flow_est": -purchase_delta,
        "confidence": "high",
        "reason": "동일 계좌/종목의 보유 수량이 직전 스냅샷보다 증가했습니다.",
    })
    events.append(event)


def _append_partial_sell(events: List[Dict], date: str, prev: Dict, cur: Dict) -> None:
    prev_qty = _safe_float(prev.get("quantity"))
    cur_qty = _safe_float(cur.get("quantity"))
    qty_sold = max(0.0, prev_qty - cur_qty)
    prev_pnl = _safe_float(prev.get("profit_loss"))
    realized = (prev_pnl / prev_qty * qty_sold) if prev_qty > EPS else 0.0
    sale_price_est = _evaluation_price(prev)
    proceeds_est = sale_price_est * qty_sold

    event = _base_event(date, "sell_partial", cur)
    event.update({
        "event_group": "sell",
        "quantity_before": prev_qty,
        "purchase_amount_before": _safe_float(prev.get("purchase_amount")),
        "evaluation_amount_before": _safe_float(prev.get("evaluation_amount")),
        "profit_loss_before": _safe_float(prev.get("profit_loss")),
        "avg_purchase_price_before": _avg_purchase_price(prev),
        "quantity_delta": -qty_sold,
        "purchase_amount_delta": _safe_float(cur.get("purchase_amount")) - _safe_float(prev.get("purchase_amount")),
        "evaluation_amount_delta": _safe_float(cur.get("evaluation_amount")) - _safe_float(prev.get("evaluation_amount")),
        "realized_pnl_est": float(realized),
        "event_unit_price_est": sale_price_est,
        "cash_flow_est": proceeds_est,
        "confidence": "medium",
        "reason": "보유 수량이 감소했지만 종목은 남아 있어 일부 매도로 추정했습니다. 매도금액과 실현손익은 직전 평가금액 기준 추정치입니다.",
    })
    events.append(event)


def _append_full_sell(events: List[Dict], date: str, prev: Dict) -> None:
    event = _base_event(date, "sell_full", prev)
    prev_qty = _safe_float(prev.get("quantity"))
    sale_price_est = _evaluation_price(prev)
    event.update({
        "event_group": "sell",
        "quantity_before": prev_qty,
        "purchase_amount_before": _safe_float(prev.get("purchase_amount")),
        "evaluation_amount_before": _safe_float(prev.get("evaluation_amount")),
        "profit_loss_before": _safe_float(prev.get("profit_loss")),
        "avg_purchase_price_before": _avg_purchase_price(prev),
        "quantity_after": 0.0,
        "purchase_amount_after": 0.0,
        "evaluation_amount_after": 0.0,
        "profit_loss_after": 0.0,
        "profit_rate_after": 0.0,
        "avg_purchase_price_after": 0.0,
        "quantity_delta": -prev_qty,
        "purchase_amount_delta": -_safe_float(prev.get("purchase_amount")),
        "evaluation_amount_delta": -_safe_float(prev.get("evaluation_amount")),
        "realized_pnl_est": _safe_float(prev.get("profit_loss")),
        "event_unit_price_est": sale_price_est,
        "cash_flow_est": _safe_float(prev.get("evaluation_amount")),
        "confidence": "medium",
        "reason": "직전 스냅샷에는 있었지만 현재 스냅샷에서 사라져 전량 매도로 추정했습니다. 매도금액과 실현손익은 직전 평가금액 기준 추정치입니다.",
    })
    events.append(event)


def _summarize_events(events: List[Dict], total: Optional[int], dates: List[str], partial: bool, scanned_start: Optional[str] = None) -> Dict:
    counts: Dict[str, int] = {}
    buy_cash = 0.0
    sell_cash = 0.0
    realized = 0.0
    realized_count = 0

    for event in events:
        key = event.get("event_type", "unknown")
        counts[key] = counts.get(key, 0) + 1
        cash_flow = event.get("cash_flow_est")
        if cash_flow is not None:
            if float(cash_flow) < 0:
                buy_cash += abs(float(cash_flow))
            else:
                sell_cash += float(cash_flow)
        if event.get("realized_pnl_est") is not None:
            realized += float(event.get("realized_pnl_est") or 0.0)
            realized_count += 1

    return {
        "total": len(events) if total is None else total,
        "returned": len(events),
        "counts": counts,
        "date_start": scanned_start or (dates[0] if dates else None),
        "date_end": dates[-1] if dates else None,
        "partial": partial,
        "buy_cash_flow_est": buy_cash,
        "sell_cash_flow_est": sell_cash,
        "net_cash_flow_est": sell_cash - buy_cash,
        "realized_pnl_est": realized,
        "realized_count": realized_count,
    }


@cache.memoize(timeout=60)
def build_investment_timeline(
    limit: Optional[int] = 100,
    include_initial: bool = False,
    date: Optional[str] = None,
    event_type: Optional[str] = None,
    full_scan: bool = True,
    period: str = "all",
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> Dict:
    dates = list_snapshot_dates()
    if len(dates) < 1:
        return {"ok": True, "events": [], "summary": {"total": 0}}

    period_range = resolve_period_range(period, start_date, end_date, dates)

    events: List[Dict] = []

    can_fast_scan = (
        not full_scan
        and bool(limit)
        and limit > 0
        and not include_initial
        and date is None
        and event_type is None
        and period_range.period == "all"
        and period_range.start_date is None
    )
    if can_fast_scan:
        scanned_start = dates[-1]
        for idx in range(len(dates) - 1, 0, -1):
            current_date = dates[idx]
            prev_map = _positions_for_date(dates[idx - 1])
            cur_map = _positions_for_date(current_date)
            _append_diff_events(events, current_date, prev_map, cur_map)
            scanned_start = dates[idx - 1]
            if len(events) >= limit:
                break

        events = sorted(events, key=lambda event: event["date"], reverse=True)[:limit]
        return {
            "ok": True,
            "events": events,
            "summary": {
                **_summarize_events(events, len(events), dates, True, scanned_start=scanned_start),
                "period": period_range.__dict__,
            },
        }

    prev_map: Dict[str, Dict] = {}

    for idx, current_date in enumerate(dates):
        cur_map = _positions_for_date(current_date)

        if idx == 0:
            if include_initial:
                for row in cur_map.values():
                    _append_new_position(events, current_date, row, initial=True)
            prev_map = cur_map
            continue

        _append_diff_events(events, current_date, prev_map, cur_map)
        prev_map = cur_map

    if date:
        events = [event for event in events if event.get("date") == date]
    else:
        if period_range.start_date:
            events = [event for event in events if event.get("date") >= period_range.start_date]
        if period_range.end_date:
            events = [event for event in events if event.get("date") <= period_range.end_date]
    if event_type:
        events = [event for event in events if event.get("event_type") == event_type]

    events = sorted(events, key=lambda event: event["date"], reverse=True)
    total = len(events)

    if limit is not None and limit > 0:
        events = events[:limit]

    return {
        "ok": True,
        "events": events,
        "summary": {
            **_summarize_events(events, total, dates, False),
            "period": period_range.__dict__,
            "date_start": period_range.start_date or dates[0],
            "date_end": period_range.end_date or dates[-1],
        },
    }
