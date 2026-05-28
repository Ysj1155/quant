from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

import pandas as pd

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR
PORTFOLIO_FILE = DATA_DIR / "portfolio_data.csv"
ACCOUNT_VALUE_FILE = DATA_DIR / "account_value.csv"

KO = {
    "type": "\uad6c\ubd84",
    "account_number": "\uacc4\uc88c\ubc88\ud638",
    "ticker": "\uc885\ubaa9\uba85",
    "profit_loss": "\ud3c9\uac00\uc190\uc775",
    "profit_rate": "\uc190\uc775\ub960",
    "quantity": "\uc794\uace0\uc218\ub7c9",
    "purchase_price": "\ub9e4\uc785\ub2e8\uac00",
    "purchase_amount": "\ub9e4\uc785\uae08\uc561",
    "evaluation_amount": "\ud3c9\uac00\uae08\uc561",
    "evaluation_ratio": "\ud3c9\uac00\ube44\uc911",
    "currency": "\ud1b5\ud654",
}

CANONICAL_COLUMNS = [
    "type",
    "account_number",
    "ticker",
    "currency",
    "profit_loss",
    "profit_rate",
    "quantity",
    "purchase_price",
    "purchase_amount",
    "evaluation_amount",
    "evaluation_ratio",
]

COLUMN_CANDIDATES: Dict[str, Iterable[str]] = {
    "type": [KO["type"], "type", "asset_type"],
    "account_number": [KO["account_number"], "account_number", "account"],
    "ticker": [KO["ticker"], "ticker", "name"],
    "currency": [f'{KO["type"]}.1', KO["currency"], "currency"],
    "profit_loss": [KO["profit_loss"], "profit_loss", "pnl"],
    "profit_rate": [KO["profit_rate"], "profit_rate", "pnl_pct"],
    "quantity": [KO["quantity"], "quantity", "qty"],
    "purchase_price": [KO["purchase_price"], "purchase_price", "avg_price"],
    "purchase_amount": [KO["purchase_amount"], "purchase_amount", "buy_amount"],
    "evaluation_amount": [KO["evaluation_amount"], "evaluation_amount", "eval_amount"],
    "evaluation_ratio": [KO["evaluation_ratio"], "evaluation_ratio", "weight"],
}

DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")
ENCODINGS = ("utf-8-sig", "cp949", "euc-kr", "utf-8")


def extract_date_from_filename(filename: str) -> Optional[str]:
    match = DATE_RE.search(filename)
    return match.group(1) if match else None


def get_all_csv_files() -> list[str]:
    csv_files = [
        p.name
        for p in DATA_DIR.glob("*.csv")
        if extract_date_from_filename(p.name)
    ]
    return sorted(csv_files, key=lambda name: extract_date_from_filename(name) or name)


def get_latest_csv() -> Optional[str]:
    files = get_all_csv_files()
    return str(DATA_DIR / files[-1]) if files else None


def read_csv_smart(path: str | Path) -> pd.DataFrame:
    last_error: Optional[Exception] = None
    for encoding in ENCODINGS:
        try:
            return pd.read_csv(path, encoding=encoding)
        except Exception as exc:
            last_error = exc
    raise RuntimeError(f"failed to read csv {path}: {last_error}")


def _pick_col(df: pd.DataFrame, canonical_name: str) -> Optional[str]:
    for candidate in COLUMN_CANDIDATES[canonical_name]:
        if candidate in df.columns:
            return candidate
    return None


def to_float(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default
    try:
        if pd.isna(value):
            return default
    except Exception:
        pass

    text = str(value).strip().replace(",", "").replace('"', "").replace("%", "")
    if not text or text.lower() == "nan":
        return default

    try:
        return float(text)
    except Exception:
        return default


def normalize_snapshot_df(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]

    out = pd.DataFrame(index=df.index)
    for canonical_name in CANONICAL_COLUMNS:
        source_col = _pick_col(df, canonical_name)
        if source_col is None:
            out[canonical_name] = ""
        else:
            out[canonical_name] = df[source_col]

    text_cols = ["type", "account_number", "ticker", "currency"]
    for col in text_cols:
        out[col] = out[col].fillna("").astype(str).str.strip()

    numeric_cols = [
        "profit_loss",
        "profit_rate",
        "quantity",
        "purchase_price",
        "purchase_amount",
        "evaluation_amount",
        "evaluation_ratio",
    ]
    for col in numeric_cols:
        out[col] = out[col].apply(to_float)

    out = out[out["type"].astype(str).str.strip() != ""].copy()
    out = out[
        (out["ticker"].astype(str).str.strip() != "")
        | (out["evaluation_amount"].abs() > 0)
        | (out["quantity"].abs() > 0)
    ].copy()

    return out[CANONICAL_COLUMNS]


def normalize_snapshot_csv(path: str | Path) -> pd.DataFrame:
    return normalize_snapshot_df(read_csv_smart(path))


def process_account_value() -> None:
    csv_files = get_all_csv_files()
    if not csv_files:
        print("No snapshot CSV files found for account_value.csv")
        return

    records = []
    failed = []

    for csv_file in csv_files:
        file_date = extract_date_from_filename(csv_file)
        if not file_date:
            continue

        file_path = DATA_DIR / csv_file
        try:
            df = normalize_snapshot_csv(file_path)
            total_value = int(round(df["evaluation_amount"].sum()))
            records.append({"date": file_date, "total_value": total_value})
        except Exception as exc:
            failed.append((csv_file, str(exc)))

    if not records:
        print("No valid account value rows were generated.")
        if failed:
            print(f"Failed snapshots: {len(failed)}")
        return

    account_value_df = pd.DataFrame(records)
    account_value_df = (
        account_value_df.sort_values("date")
        .drop_duplicates(subset=["date"], keep="last")
        .reset_index(drop=True)
    )
    account_value_df.to_csv(ACCOUNT_VALUE_FILE, index=False, encoding="utf-8-sig")

    print(
        "account_value.csv generated "
        f"({len(account_value_df)} rows, {account_value_df['date'].iloc[0]}..{account_value_df['date'].iloc[-1]})"
    )
    if failed:
        print(f"Skipped {len(failed)} snapshot files.")


def process_portfolio_data() -> None:
    latest_csv = get_latest_csv()
    if not latest_csv:
        print("No snapshot CSV files found for portfolio_data.csv")
        return

    portfolio_df = normalize_snapshot_csv(latest_csv)
    portfolio_df.to_csv(PORTFOLIO_FILE, index=False, encoding="utf-8-sig")
    print(f"portfolio_data.csv generated from {Path(latest_csv).name}")
