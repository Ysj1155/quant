# services/snapshots.py
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from extensions import cache

# 파일명에서 날짜 추출: 2025-12-21 / 2025.12.21 / 20251221 지원
DATE_PATTERNS = [
    re.compile(r"(?P<date>\d{4}-\d{2}-\d{2})"),
    re.compile(r"(?P<date>\d{4}\.\d{2}\.\d{2})"),
    re.compile(r"(?P<date>\d{8})"),
]

# pandas가 중복 헤더를 '구분', '구분.1' 로 만들기 때문에 후보로 처리
COL_CANDIDATES = {
    "asset_type": ["구분"],
    "account": ["계좌번호", "account_number", "account"],
    "name": ["종목명", "ticker", "name"],
    "currency": ["구분.1", "통화", "currency"],
    "pnl": ["평가손익", "profit_loss", "pnl"],
    "pnl_pct": ["손익률", "profit_rate", "pnl_pct"],
    "qty": ["잔고수량", "quantity", "qty"],
    "avg_price": ["매입단가", "avg_price"],
    "buy_amount": ["매입금액", "purchase_amount", "buy_amount"],
    "eval_amount": ["평가금액", "evaluation_amount", "eval_amount"],
    "weight": ["평가비중", "evaluation_ratio", "weight"],
}

def _pick_col(df: pd.DataFrame, keys: List[str]) -> Optional[str]:
    for k in keys:
        if k in df.columns:
            return k
    return None

def _norm_date(s: str) -> Optional[str]:
    """YYYY-MM-DD로 통일"""
    s = (s or "").strip()
    if not s:
        return None
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
        return s
    if re.fullmatch(r"\d{4}\.\d{2}\.\d{2}", s):
        y, m, d = s.split(".")
        return f"{y}-{m}-{d}"
    if re.fullmatch(r"\d{8}", s):
        return f"{s[0:4]}-{s[4:6]}-{s[6:8]}"
    return None

def _extract_date_from_name(name: str) -> Optional[str]:
    for pat in DATE_PATTERNS:
        m = pat.search(name)
        if m:
            return _norm_date(m.group("date"))
    return None

def _snapshot_dirs() -> List[Path]:
    """
    우선순위:
    1) env SNAPSHOT_DIR
    2) ./data/snapshots
    3) ./data
    """
    env = os.getenv("SNAPSHOT_DIR")
    cands = []
    if env:
        cands.append(Path(env))
    cands.append(Path("data") / "snapshots")
    cands.append(Path("data"))
    # 존재하는 것만
    return [p for p in cands if p.exists() and p.is_dir()]

def _read_csv_smart(path: Path) -> pd.DataFrame:
    last_err = None
    for enc in ("utf-8-sig", "cp949", "euc-kr", "utf-8"):
        try:
            return pd.read_csv(path, encoding=enc)
        except Exception as e:
            last_err = e
    raise RuntimeError(f"failed to read csv {path}: {last_err}")

def _to_float(x: Any) -> float:
    if x is None:
        return 0.0
    s = str(x).strip().replace(",", "").replace('"', "")
    if s == "" or s.lower() == "nan":
        return 0.0
    s = s.replace("%", "")
    try:
        return float(s)
    except Exception:
        return 0.0

def _to_int(x: Any) -> int:
    return int(_to_float(x))

def _find_snapshot_file(date_yyyy_mm_dd: str) -> Optional[Path]:
    """해당 날짜를 포함하는 CSV를 찾아 최신 mtime 1개 반환"""
    date_yyyy_mm_dd = _norm_date(date_yyyy_mm_dd) or date_yyyy_mm_dd
    if not date_yyyy_mm_dd:
        return None

    cand: List[Tuple[float, Path]] = []
    for base in _snapshot_dirs():
        for p in base.glob("*.csv"):
            d = _extract_date_from_name(p.name)
            if d == date_yyyy_mm_dd:
                cand.append((p.stat().st_mtime, p))

    if not cand:
        return None
    cand.sort(reverse=True, key=lambda x: x[0])
    return cand[0][1]

@cache.memoize(timeout=60 * 5)
def list_snapshot_dates() -> List[str]:
    dates = set()
    for base in _snapshot_dirs():
        for p in base.glob("*.csv"):
            d = _extract_date_from_name(p.name)
            if d:
                dates.add(d)
    return sorted(dates)

def _map_cols(df: pd.DataFrame) -> Dict[str, Optional[str]]:
    cols = {}
    for k, candidates in COL_CANDIDATES.items():
        cols[k] = _pick_col(df, candidates)
    return cols

def normalize_holdings_df(df: pd.DataFrame) -> pd.DataFrame:
    """
    스냅샷 CSV → (name, account, qty, buy_amount, eval_amount, pnl, pnl_pct, type) 형태로 정규화
    """
    cols = _map_cols(df)
    name_c = cols["name"]
    qty_c = cols["qty"]
    buy_c = cols["buy_amount"]
    eval_c = cols["eval_amount"]
    pnl_c = cols["pnl"]
    pnlpct_c = cols["pnl_pct"]
    acct_c = cols["account"]
    type_c = cols["asset_type"]

    need = [name_c, qty_c, buy_c, eval_c, pnl_c, pnlpct_c]
    if any(c is None for c in need):
        return pd.DataFrame(columns=["account", "name", "qty", "buy_amount", "eval_amount", "pnl", "pnl_pct", "type"])

    out = pd.DataFrame()
    out["account"] = df[acct_c].fillna("").astype(str) if acct_c else ""
    out["name"] = df[name_c].fillna("").astype(str)
    out["qty"] = df[qty_c].apply(_to_float)
    out["buy_amount"] = df[buy_c].apply(_to_float)
    out["eval_amount"] = df[eval_c].apply(_to_float)
    out["pnl"] = df[pnl_c].apply(_to_float)
    out["pnl_pct"] = df[pnlpct_c].apply(_to_float)
    out["type"] = df[type_c].fillna("").astype(str) if type_c else ""

    # 예수금류/현금류 제외(보유종목만)
    out = out[~out["type"].str.contains("예수금", na=False)].copy()
    out = out[out["qty"] > 0].copy()
    return out

@cache.memoize(timeout=60 * 5)
def load_snapshot(date: str) -> Dict[str, Any]:
    date = _norm_date(date) or date
    path = _find_snapshot_file(date)
    if not path:
        return {"error": f"snapshot file not found for date={date}"}

    df = _read_csv_smart(path)
    cols = _map_cols(df)
    asset_col = cols["asset_type"]
    if not asset_col:
        return {"error": "asset_type column not found (expected '구분')"}

    stock_mask = df[asset_col].astype(str).str.contains("주식", na=False)
    stocks = df[stock_mask].copy()

    def holding_row(r) -> Dict[str, Any]:
        return {
            "account": str(r.get(cols["account"], "")).strip() if cols["account"] else "",
            "name": str(r.get(cols["name"], "")).strip() if cols["name"] else "",
            "currency": str(r.get(cols["currency"], "")).strip() if cols["currency"] else "",
            "qty": _to_float(r.get(cols["qty"])) if cols["qty"] else 0.0,
            "avg_price": _to_float(r.get(cols["avg_price"])) if cols["avg_price"] else 0.0,
            "buy_amount": _to_int(r.get(cols["buy_amount"])) if cols["buy_amount"] else 0,
            "eval_amount": _to_int(r.get(cols["eval_amount"])) if cols["eval_amount"] else 0,
            "pnl": _to_int(r.get(cols["pnl"])) if cols["pnl"] else 0,
            "pnl_pct": _to_float(r.get(cols["pnl_pct"])) if cols["pnl_pct"] else 0.0,
            "weight": str(r.get(cols["weight"], "")).strip() if cols["weight"] else "",
        }

    holdings = [holding_row(r) for _, r in stocks.iterrows()]
    stock_eval_sum = sum(h.get("eval_amount", 0) for h in holdings)

    # 예수금류도 내려줌(프론트에서 카드로 쓰면 좋음)
    cash_rows = df[~stock_mask].copy()
    cash_items = []
    for _, r in cash_rows.iterrows():
        typ = str(r.get(asset_col, "")).strip()
        if typ in ("예수금", "외화예수금"):
            cash_items.append({
                "type": typ,
                "account": str(r.get(cols["account"], "")).strip() if cols["account"] else "",
                "currency": str(r.get(cols["currency"], "")).strip() if cols["currency"] else "",
                "qty": _to_float(r.get(cols["qty"])) if cols["qty"] else 0.0,
                "eval_amount": _to_int(r.get(cols["eval_amount"])) if cols["eval_amount"] else 0,
                "weight": str(r.get(cols["weight"], "")).strip() if cols["weight"] else "",
            })

    return {
        "date": date,
        "source_file": path.name,
        "summary": {"stock_eval_sum": stock_eval_sum, "cash": cash_items},
        "holdings": holdings,
    }
