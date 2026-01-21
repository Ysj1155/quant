# services/portfolio.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

import pandas as pd

from extensions import cache
from services.snapshots import list_snapshot_dates, load_snapshot


def _holdings_df_from_snapshot(date: str) -> pd.DataFrame:
    snap = load_snapshot(date)
    if "error" in snap:
        return pd.DataFrame(columns=["account", "name", "qty", "buy_amount", "eval_amount", "pnl", "pnl_pct"])

    rows = snap.get("holdings", []) or []
    if not rows:
        return pd.DataFrame(columns=["account", "name", "qty", "buy_amount", "eval_amount", "pnl", "pnl_pct"])

    df = pd.DataFrame(rows)

    # key 생성에 필요한 최소 컬럼 보장
    for c in ["account", "name", "qty", "buy_amount", "eval_amount", "pnl", "pnl_pct"]:
        if c not in df.columns:
            df[c] = 0

    return df


@dataclass
class PositionState:
    buy_date: str
    last_date: str
    last_qty: float
    last_buy_amount: float
    last_eval_amount: float
    last_pnl: float
    last_pnl_pct: float


@cache.memoize(timeout=60)
def build_pnl_from_snapshots(asof_date: Optional[str] = None) -> Dict:
    """
    - open_positions: asof_date 기준 보유중
    - realized: 스냅샷에서 '사라진' 종목을 전량매도로 간주(마지막 pnl을 realized로 기록)
    """
    dates = list_snapshot_dates()
    if not dates:
        return {"error": "no snapshot dates"}

    if asof_date is None:
        asof_date = dates[-1]

    dates = [d for d in dates if d <= asof_date]
    if not dates:
        return {"error": f"no snapshot up to date={asof_date}"}

    states: Dict[str, PositionState] = {}
    realized: List[Dict] = []
    prev_keys = set()

    for d in dates:
        df = _holdings_df_from_snapshot(d)
        df["account"] = df.get("account", "").fillna("").astype(str)
        df["name"] = df.get("name", "").fillna("").astype(str)
        df["key"] = df["account"] + "|" + df["name"]

        cur_keys = set(df["key"].tolist())

        # 신규/갱신
        for _, r in df.iterrows():
            k = r["key"]
            qty = float(r.get("qty", 0) or 0)
            buy_amount = float(r.get("buy_amount", 0) or 0)
            eval_amount = float(r.get("eval_amount", 0) or 0)
            pnl = float(r.get("pnl", 0) or 0)
            pnl_pct = float(r.get("pnl_pct", 0) or 0)

            if k not in states:
                states[k] = PositionState(
                    buy_date=d, last_date=d,
                    last_qty=qty, last_buy_amount=buy_amount,
                    last_eval_amount=eval_amount, last_pnl=pnl, last_pnl_pct=pnl_pct
                )
            else:
                st = states[k]
                st.last_date = d
                st.last_qty = qty
                st.last_buy_amount = buy_amount
                st.last_eval_amount = eval_amount
                st.last_pnl = pnl
                st.last_pnl_pct = pnl_pct

        # 전량 매도(사라짐)
        sold = prev_keys - cur_keys
        for k in sold:
            st = states.get(k)
            if not st:
                continue
            account, name = k.split("|", 1)
            realized.append({
                "account": account,
                "name": name,
                "buy_date": st.buy_date,
                "sell_date": d,              # 이 날짜 스냅샷부터 안 보임
                "last_hold_date": st.last_date,
                "realized_pnl": st.last_pnl,
                "realized_pnl_pct": st.last_pnl_pct,
                "last_buy_amount": st.last_buy_amount,
                "last_eval_amount": st.last_eval_amount,
            })
            states.pop(k, None)

        prev_keys = cur_keys

    open_positions = []
    for k, st in states.items():
        account, name = k.split("|", 1)
        open_positions.append({
            "account": account,
            "name": name,
            "buy_date": st.buy_date,
            "asof_date": st.last_date,
            "qty": st.last_qty,
            "buy_amount": st.last_buy_amount,
            "eval_amount": st.last_eval_amount,
            "pnl": st.last_pnl,
            "pnl_pct": st.last_pnl_pct,
        })

    return {
        "ok": True,
        "asof_date": asof_date,
        "open_positions": open_positions,
        "realized": realized,
    }


@cache.memoize(timeout=60)
def build_pnl_series() -> Dict:
    """
    이벤트용(간단 버전):
    - 종목이 사라짐: full sell
    - 수량 감소: partial sell (이전 pnl/qty 비례로 realized 추정)
    """
    dates = list_snapshot_dates()
    if len(dates) < 2:
        return {"ok": True, "events": []}

    prev_df = _holdings_df_from_snapshot(dates[0])
    prev_df["key"] = prev_df.get("account", "").fillna("").astype(str) + "|" + prev_df.get("name", "").fillna("").astype(str)
    prev_map = {r["key"]: r for r in prev_df.to_dict("records")}

    events: List[Dict] = []

    for d in dates[1:]:
        cur_df = _holdings_df_from_snapshot(d)
        cur_df["key"] = cur_df.get("account", "").fillna("").astype(str) + "|" + cur_df.get("name", "").fillna("").astype(str)
        cur_map = {r["key"]: r for r in cur_df.to_dict("records")}

        prev_keys = set(prev_map.keys())
        cur_keys = set(cur_map.keys())

        # full sell
        for k in (prev_keys - cur_keys):
            r = prev_map[k]
            events.append({
                "date": d,
                "type": "sell_full",
                "account": (r.get("account") or ""),
                "name": (r.get("name") or ""),
                "qty_sold": float(r.get("qty", 0) or 0),
                "realized_pnl_est": float(r.get("pnl", 0) or 0),
            })

        # partial sell
        for k in (prev_keys & cur_keys):
            pr = prev_map[k]
            pq = float(pr.get("qty", 0) or 0)
            cq = float(cur_map[k].get("qty", 0) or 0)
            if pq > cq and pq > 0:
                sold = pq - cq
                pnl = float(pr.get("pnl", 0) or 0)
                pnl_per_share = pnl / pq
                events.append({
                    "date": d,
                    "type": "sell_partial",
                    "account": (pr.get("account") or ""),
                    "name": (pr.get("name") or ""),
                    "qty_sold": sold,
                    "realized_pnl_est": pnl_per_share * sold,
                })

        prev_map = cur_map

    return {"ok": True, "events": events}