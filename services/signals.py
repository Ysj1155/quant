from __future__ import annotations

from typing import Dict

import pandas as pd

from extensions import cache
from services.analysis_utils import load_account_values, safe_pct


def _level_from_z(abs_z: float) -> str:
    if abs_z >= 2.5:
        return "high"
    if abs_z >= 1.5:
        return "medium"
    return "low"


def _serialize_move(row) -> Dict:
    return {
        "date": row["date"].strftime("%Y-%m-%d"),
        "total_value": float(row["total_value"]),
        "change": float(row["change"]),
        "change_pct": float(row["change_pct"]),
        "z_score": None if pd.isna(row["z_score"]) else float(row["z_score"]),
        "level": _level_from_z(abs(float(row["z_score"]))) if not pd.isna(row["z_score"]) else "low",
    }


def _recent_trend(df: pd.DataFrame, window: int) -> Dict:
    if len(df) <= window:
        return {"window": window, "change": None, "change_pct": None}

    latest = float(df["total_value"].iloc[-1])
    base = float(df["total_value"].iloc[-(window + 1)])
    change = latest - base
    return {
        "window": window,
        "change": change,
        "change_pct": safe_pct(change, base),
    }


@cache.memoize(timeout=60)
def build_account_signals() -> Dict:
    df = load_account_values()
    if len(df) < 20:
        return {"ok": False, "error": "not enough account value observations"}

    df = df.copy()
    df["change"] = df["total_value"].diff()
    df["change_pct"] = df["total_value"].pct_change() * 100.0

    baseline = df["change_pct"].dropna()
    mean = float(baseline.mean())
    std = float(baseline.std()) if float(baseline.std()) != 0 else 0.0
    if std == 0:
        df["z_score"] = 0.0
    else:
        df["z_score"] = (df["change_pct"] - mean) / std

    moves = df.dropna(subset=["change", "change_pct"]).copy()
    latest = moves.iloc[-1]

    unusual = moves[moves["z_score"].abs() >= 1.5].copy()
    unusual = unusual.sort_values("date", ascending=False).head(20)

    biggest_abs = moves.reindex(moves["change"].abs().sort_values(ascending=False).index).head(10)

    latest_signal = _serialize_move(latest)
    latest_abs_z = abs(latest_signal["z_score"] or 0.0)
    latest_signal["message"] = (
        f"최근 계좌 변화율은 {latest_signal['change_pct']:.2f}%이고, "
        f"평소 변동 대비 z-score는 {latest_signal['z_score']:.2f}입니다."
    )

    return {
        "ok": True,
        "asof_date": df["date"].iloc[-1].strftime("%Y-%m-%d"),
        "summary": {
            "latest_total_value": float(df["total_value"].iloc[-1]),
            "latest_level": _level_from_z(latest_abs_z),
            "daily_change_mean_pct": mean,
            "daily_change_std_pct": std,
            "observation_count": int(len(df)),
            "unusual_count": int(len(moves[moves["z_score"].abs() >= 1.5])),
        },
        "latest_signal": latest_signal,
        "recent_trends": [
            _recent_trend(df, 7),
            _recent_trend(df, 30),
            _recent_trend(df, 90),
        ],
        "unusual_moves": [_serialize_move(row) for _, row in unusual.iterrows()],
        "biggest_moves": [_serialize_move(row) for _, row in biggest_abs.iterrows()],
    }
