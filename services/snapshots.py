# services/snapshots.py
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from data.csv_manager import normalize_snapshot_csv, normalize_snapshot_df, to_float
from extensions import cache

DATE_PATTERNS = [
    re.compile(r"(?P<date>\d{4}-\d{2}-\d{2})"),
    re.compile(r"(?P<date>\d{4}\.\d{2}\.\d{2})"),
    re.compile(r"(?P<date>\d{8})"),
]


def _norm_date(s: str) -> Optional[str]:
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
    for pattern in DATE_PATTERNS:
        match = pattern.search(name)
        if match:
            return _norm_date(match.group("date"))
    return None


def _snapshot_dirs() -> List[Path]:
    candidates: List[Path] = []
    env = os.getenv("SNAPSHOT_DIR")
    if env:
        candidates.append(Path(env))
    candidates.append(Path("data") / "snapshots")
    candidates.append(Path("data"))
    return [p for p in candidates if p.exists() and p.is_dir()]


@cache.memoize(timeout=60 * 5)
def _snapshot_file_index() -> Dict[str, str]:
    files: Dict[str, Tuple[float, Path]] = {}
    for base in _snapshot_dirs():
        for path in base.glob("*.csv"):
            date = _extract_date_from_name(path.name)
            if not date:
                continue

            current = files.get(date)
            modified = path.stat().st_mtime
            if current is None or modified > current[0]:
                files[date] = (modified, path)

    return {date: str(path) for date, (_, path) in files.items()}


def _to_int(x: Any) -> int:
    return int(to_float(x))


def _find_snapshot_file(date_yyyy_mm_dd: str) -> Optional[Path]:
    date_yyyy_mm_dd = _norm_date(date_yyyy_mm_dd) or date_yyyy_mm_dd
    if not date_yyyy_mm_dd:
        return None

    path = _snapshot_file_index().get(date_yyyy_mm_dd)
    return Path(path) if path else None


@cache.memoize(timeout=60 * 5)
def list_snapshot_dates() -> List[str]:
    return sorted(_snapshot_file_index().keys())


def normalize_holdings_df(df: pd.DataFrame) -> pd.DataFrame:
    normalized = normalize_snapshot_df(df)
    out = pd.DataFrame()
    out["account"] = normalized["account_number"]
    out["name"] = normalized["ticker"]
    out["qty"] = normalized["quantity"]
    out["buy_amount"] = normalized["purchase_amount"]
    out["eval_amount"] = normalized["evaluation_amount"]
    out["pnl"] = normalized["profit_loss"]
    out["pnl_pct"] = normalized["profit_rate"]
    out["type"] = normalized["type"]

    out = out[~out["type"].str.contains("\uc608\uc218\uae08", na=False)].copy()
    out = out[out["qty"] > 0].copy()
    return out


@cache.memoize(timeout=60 * 5)
def load_snapshot(date: str) -> Dict[str, Any]:
    date = _norm_date(date) or date
    path = _find_snapshot_file(date)
    if not path:
        return {"error": f"snapshot file not found for date={date}"}

    try:
        df = normalize_snapshot_csv(path)
    except Exception as exc:
        return {"error": f"failed to load snapshot {path.name}: {exc}"}

    stock_mask = df["type"].astype(str).str.contains("\uc8fc\uc2dd", na=False)
    stocks = df[stock_mask].copy()

    def holding_row(row) -> Dict[str, Any]:
        return {
            "account": str(row.get("account_number", "")).strip(),
            "name": str(row.get("ticker", "")).strip(),
            "currency": str(row.get("currency", "")).strip(),
            "qty": to_float(row.get("quantity")),
            "avg_price": to_float(row.get("purchase_price")),
            "buy_amount": _to_int(row.get("purchase_amount")),
            "eval_amount": _to_int(row.get("evaluation_amount")),
            "pnl": _to_int(row.get("profit_loss")),
            "pnl_pct": to_float(row.get("profit_rate")),
            "weight": f"{to_float(row.get('evaluation_ratio')):.2f}%",
        }

    holdings = [holding_row(row) for _, row in stocks.iterrows()]
    stock_eval_sum = sum(item.get("eval_amount", 0) for item in holdings)

    cash_items = []
    cash_rows = df[df["type"].astype(str).str.contains("\uc608\uc218\uae08", na=False)]
    for _, row in cash_rows.iterrows():
        cash_items.append({
            "type": str(row.get("type", "")).strip(),
            "account": str(row.get("account_number", "")).strip(),
            "currency": str(row.get("currency", "")).strip(),
            "qty": to_float(row.get("quantity")),
            "eval_amount": _to_int(row.get("evaluation_amount")),
            "weight": f"{to_float(row.get('evaluation_ratio')):.2f}%",
        })

    return {
        "date": date,
        "source_file": path.name,
        "summary": {"stock_eval_sum": stock_eval_sum, "cash": cash_items},
        "holdings": holdings,
    }


@cache.memoize(timeout=60 * 5)
def load_snapshot_frame(date: str) -> pd.DataFrame:
    date = _norm_date(date) or date
    path = _find_snapshot_file(date)
    if not path:
        return pd.DataFrame()
    return normalize_snapshot_csv(path)
