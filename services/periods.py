from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

import pandas as pd


@dataclass(frozen=True)
class PeriodRange:
    period: str
    start_date: Optional[str]
    end_date: Optional[str]
    label: str


PERIOD_LABELS = {
    "all": "전체",
    "1w": "최근 1주",
    "1m": "최근 1개월",
    "3m": "최근 3개월",
    "ytd": "올해",
    "custom": "사용자 지정",
}


def _latest_date_from_values(values: Iterable[str]) -> Optional[pd.Timestamp]:
    parsed = pd.to_datetime(list(values), errors="coerce")
    parsed = parsed.dropna()
    if len(parsed) == 0:
        return None
    return parsed.max().normalize()


def resolve_period_range(
    period: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    available_dates: Optional[Iterable[str]] = None,
) -> PeriodRange:
    period_key = (period or "all").strip().lower()
    if start_date or end_date:
        period_key = "custom"

    latest = _latest_date_from_values(available_dates or [])
    if latest is None:
        latest = pd.Timestamp.today().normalize()

    end = pd.to_datetime(end_date, errors="coerce") if end_date else latest
    if pd.isna(end):
        end = latest
    end = end.normalize()

    start = pd.to_datetime(start_date, errors="coerce") if start_date else None
    if start is not None and pd.isna(start):
        start = None

    if start is None:
        if period_key == "1w":
            start = end - pd.Timedelta(days=7)
        elif period_key == "1m":
            start = end - pd.DateOffset(months=1)
        elif period_key == "3m":
            start = end - pd.DateOffset(months=3)
        elif period_key == "ytd":
            start = pd.Timestamp(year=end.year, month=1, day=1)

    return PeriodRange(
        period=period_key,
        start_date=None if start is None else start.strftime("%Y-%m-%d"),
        end_date=end.strftime("%Y-%m-%d"),
        label=PERIOD_LABELS.get(period_key, period_key),
    )


def filter_by_period(
    df: pd.DataFrame,
    date_column: str,
    period: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> tuple[pd.DataFrame, PeriodRange]:
    if df.empty or date_column not in df.columns:
        return df.copy(), resolve_period_range(period, start_date, end_date, [])

    out = df.copy()
    out[date_column] = pd.to_datetime(out[date_column], errors="coerce")
    out = out.dropna(subset=[date_column])
    available = out[date_column].dt.strftime("%Y-%m-%d").tolist()
    resolved = resolve_period_range(period, start_date, end_date, available)

    if resolved.start_date:
        out = out[out[date_column] >= pd.to_datetime(resolved.start_date)]
    if resolved.end_date:
        out = out[out[date_column] <= pd.to_datetime(resolved.end_date)]

    return out.copy(), resolved


def filter_date_strings(
    dates: list[str],
    period: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> tuple[list[str], PeriodRange]:
    resolved = resolve_period_range(period, start_date, end_date, dates)
    out = dates
    if resolved.start_date:
        out = [date for date in out if date >= resolved.start_date]
    if resolved.end_date:
        out = [date for date in out if date <= resolved.end_date]
    return out, resolved
