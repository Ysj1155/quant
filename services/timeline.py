from __future__ import annotations

from functools import lru_cache
from typing import Dict, List, Optional

import pandas as pd

from extensions import cache
from services.analysis_utils import EPS, is_cash_type, mask_account
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
    return {
        "date": date,
        "event_type": event_type,
        "account_label": mask_account(account),
        "name": str(row.get("ticker", "")).strip(),
        "asset_type": str(row.get("type", "")).strip(),
        "currency": str(row.get("currency", "")).strip(),
        "quantity_after": float(row.get("quantity", 0.0) or 0.0),
        "purchase_amount_after": float(row.get("purchase_amount", 0.0) or 0.0),
        "evaluation_amount_after": float(row.get("evaluation_amount", 0.0) or 0.0),
        "profit_loss_after": float(row.get("profit_loss", 0.0) or 0.0),
        "profit_rate_after": float(row.get("profit_rate", 0.0) or 0.0),
    }


def _append_new_position(events: List[Dict], date: str, row: Dict, initial: bool = False) -> None:
    event = _base_event(date, "initial_position" if initial else "buy_open", row)
    event.update({
        "quantity_delta": float(row.get("quantity", 0.0) or 0.0),
        "purchase_amount_delta": float(row.get("purchase_amount", 0.0) or 0.0),
        "evaluation_amount_delta": float(row.get("evaluation_amount", 0.0) or 0.0),
        "realized_pnl_est": None,
    })
    events.append(event)


def _append_add_position(events: List[Dict], date: str, prev: Dict, cur: Dict) -> None:
    event = _base_event(date, "buy_add", cur)
    event.update({
        "quantity_delta": float(cur.get("quantity", 0.0) or 0.0) - float(prev.get("quantity", 0.0) or 0.0),
        "purchase_amount_delta": float(cur.get("purchase_amount", 0.0) or 0.0) - float(prev.get("purchase_amount", 0.0) or 0.0),
        "evaluation_amount_delta": float(cur.get("evaluation_amount", 0.0) or 0.0) - float(prev.get("evaluation_amount", 0.0) or 0.0),
        "realized_pnl_est": None,
    })
    events.append(event)


def _append_partial_sell(events: List[Dict], date: str, prev: Dict, cur: Dict) -> None:
    prev_qty = float(prev.get("quantity", 0.0) or 0.0)
    cur_qty = float(cur.get("quantity", 0.0) or 0.0)
    qty_sold = max(0.0, prev_qty - cur_qty)
    prev_pnl = float(prev.get("profit_loss", 0.0) or 0.0)
    realized = (prev_pnl / prev_qty * qty_sold) if prev_qty > EPS else 0.0

    event = _base_event(date, "sell_partial", cur)
    event.update({
        "quantity_delta": -qty_sold,
        "purchase_amount_delta": float(cur.get("purchase_amount", 0.0) or 0.0) - float(prev.get("purchase_amount", 0.0) or 0.0),
        "evaluation_amount_delta": float(cur.get("evaluation_amount", 0.0) or 0.0) - float(prev.get("evaluation_amount", 0.0) or 0.0),
        "realized_pnl_est": float(realized),
    })
    events.append(event)


def _append_full_sell(events: List[Dict], date: str, prev: Dict) -> None:
    event = _base_event(date, "sell_full", prev)
    event.update({
        "quantity_after": 0.0,
        "purchase_amount_after": 0.0,
        "evaluation_amount_after": 0.0,
        "profit_loss_after": 0.0,
        "profit_rate_after": 0.0,
        "quantity_delta": -float(prev.get("quantity", 0.0) or 0.0),
        "purchase_amount_delta": -float(prev.get("purchase_amount", 0.0) or 0.0),
        "evaluation_amount_delta": -float(prev.get("evaluation_amount", 0.0) or 0.0),
        "realized_pnl_est": float(prev.get("profit_loss", 0.0) or 0.0),
    })
    events.append(event)


@cache.memoize(timeout=60)
def build_investment_timeline(
    limit: Optional[int] = 100,
    include_initial: bool = False,
    date: Optional[str] = None,
    event_type: Optional[str] = None,
    full_scan: bool = True,
) -> Dict:
    dates = list_snapshot_dates()
    if len(dates) < 1:
        return {"ok": True, "events": [], "summary": {"total": 0}}

    events: List[Dict] = []

    can_fast_scan = (
        not full_scan
        and bool(limit)
        and limit > 0
        and not include_initial
        and date is None
        and event_type is None
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
        counts: Dict[str, int] = {}
        for event in events:
            key = event.get("event_type", "unknown")
            counts[key] = counts.get(key, 0) + 1

        return {
            "ok": True,
            "events": events,
            "summary": {
                "total": len(events),
                "returned": len(events),
                "counts": counts,
                "date_start": scanned_start,
                "date_end": dates[-1],
                "partial": True,
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
    if event_type:
        events = [event for event in events if event.get("event_type") == event_type]

    events = sorted(events, key=lambda event: event["date"], reverse=True)
    total = len(events)

    if limit is not None and limit > 0:
        events = events[:limit]

    counts: Dict[str, int] = {}
    for event in events:
        key = event.get("event_type", "unknown")
        counts[key] = counts.get(key, 0) + 1

    return {
        "ok": True,
        "events": events,
        "summary": {
            "total": total,
            "returned": len(events),
            "counts": counts,
            "date_start": dates[0],
            "date_end": dates[-1],
            "partial": False,
        },
    }
