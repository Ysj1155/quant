from __future__ import annotations

from pathlib import Path
from typing import Optional

import pandas as pd

from data.csv_manager import ACCOUNT_VALUE_FILE
from services.snapshots import list_snapshot_dates, load_snapshot_frame

EPS = 1e-9
CASH_TYPE_KEYWORD = "\uc608\uc218\uae08"


def safe_pct(num: float, den: float) -> float:
    if abs(float(den or 0.0)) <= EPS:
        return 0.0
    return float(num / den * 100.0)


def mask_account(account: str) -> str:
    account = str(account or "").strip()
    if not account:
        return ""

    parts = account.split("-")
    if len(parts) >= 3:
        return "-".join([parts[0], "***", "***", parts[-1]])

    if len(account) <= 4:
        return "*" * len(account)
    return f"{account[:3]}***{account[-2:]}"


def is_cash_type(value: object) -> bool:
    return CASH_TYPE_KEYWORD in str(value or "")


def currency_label(value: object) -> str:
    raw = str(value or "").strip()
    if raw.upper() == "USD":
        return "USD"
    if raw in ("", "KRW", "\uc6d0\ud654", "\uc608\uc218\uae08"):
        return "KRW"
    return raw


def load_account_values(path: Optional[str | Path] = None) -> pd.DataFrame:
    csv_path = Path(path) if path else ACCOUNT_VALUE_FILE
    if not csv_path.exists():
        return pd.DataFrame(columns=["date", "total_value"])

    df = pd.read_csv(csv_path, encoding="utf-8-sig")
    if df.empty:
        return pd.DataFrame(columns=["date", "total_value"])

    df = df.copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["total_value"] = pd.to_numeric(df["total_value"], errors="coerce")
    df = df.dropna(subset=["date", "total_value"])
    return df.sort_values("date").drop_duplicates(subset=["date"], keep="last")


def latest_snapshot() -> tuple[str, pd.DataFrame]:
    dates = list_snapshot_dates()
    if not dates:
        return "", pd.DataFrame()

    latest_date = dates[-1]
    return latest_date, load_snapshot_frame(latest_date)


def investment_positions(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df.copy()

    out = df.copy()
    return out[
        (out["ticker"].astype(str).str.strip() != "")
        & (~out["type"].apply(is_cash_type))
        & ((out["quantity"].abs() > EPS) | (out["evaluation_amount"].abs() > EPS))
    ].copy()


def latest_investment_positions() -> tuple[str, pd.DataFrame]:
    latest_date, snapshot = latest_snapshot()
    return latest_date, investment_positions(snapshot)
