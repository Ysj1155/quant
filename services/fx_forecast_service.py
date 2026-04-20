from __future__ import annotations

from datetime import date
from typing import Dict, List, Optional

import pandas as pd

from db.connection import get_connection
from extensions import cache
from services.forecast_core import (
    DEFAULT_BACKTEST_DAYS,
    DEFAULT_HORIZON,
    DEFAULT_START_DATE,
    MIN_SERIES_LENGTH,
    SUPPORTED_MODELS,
    ForecastResult,
    _build_inverse_mae_weights,
    _calc_model_metrics,
    _clean_series,
    _fit_one_model,
    _merge_history_and_forecast,
    _weighted_average_forecast,
)

try:
    import FinanceDataReader as fdr
except Exception:
    fdr = None

try:
    import yfinance as yf
except Exception:
    yf = None


def _load_exchange_rate_from_fdr(start_date: str = DEFAULT_START_DATE) -> Optional[pd.Series]:
    if fdr is None:
        return None

    try:
        df = fdr.DataReader("USD/KRW", start_date)
        if df is None or df.empty or "Close" not in df.columns:
            return None

        s = df["Close"].copy()
        s.index = pd.to_datetime(s.index)
        s = _clean_series(s)
        return s
    except Exception:
        return None


def _load_exchange_rate_from_yf(start_date: str = DEFAULT_START_DATE) -> Optional[pd.Series]:
    if yf is None:
        return None

    try:
        df = yf.download("KRW=X", start=start_date, interval="1d", progress=False, auto_adjust=False)
        if df is None or df.empty:
            return None

        close_col = None
        if "Close" in df.columns:
            close_col = "Close"
        elif isinstance(df.columns, pd.MultiIndex):
            for col in df.columns:
                if col[0] == "Close":
                    close_col = col
                    break

        if close_col is None:
            return None

        s = df[close_col].copy()
        s.index = pd.to_datetime(s.index)
        s = _clean_series(s)
        return s
    except Exception:
        return None


@cache.memoize(timeout=60 * 60 * 6)
def load_exchange_rate_series(start_date: str = DEFAULT_START_DATE) -> pd.Series:
    s = _load_exchange_rate_from_fdr(start_date)
    if s is not None and not s.empty:
        return s

    s = _load_exchange_rate_from_yf(start_date)
    if s is not None and not s.empty:
        return s

    raise RuntimeError("failed to load exchange rate series from both FDR and yfinance")


@cache.memoize(timeout=60 * 30)
def build_exchange_rate_forecast(
    horizon: int = DEFAULT_HORIZON,
    start_date: str = DEFAULT_START_DATE,
    backtest_days: int = DEFAULT_BACKTEST_DAYS,
    models: Optional[List[str]] = None,
) -> Dict:
    if horizon <= 0:
        return {"ok": False, "error": "horizon must be >= 1"}

    if backtest_days <= 0:
        return {"ok": False, "error": "backtest_days must be >= 1"}

    models = models or SUPPORTED_MODELS
    models = [m for m in models if m in SUPPORTED_MODELS]

    if not models:
        return {"ok": False, "error": "no valid models selected"}

    try:
        series = load_exchange_rate_series(start_date=start_date)
    except Exception as e:
        return {"ok": False, "error": f"failed to load exchange rate series: {e}"}

    series = _clean_series(series)

    if len(series) < MIN_SERIES_LENGTH:
        return {"ok": False, "error": f"not enough observations: {len(series)} < {MIN_SERIES_LENGTH}"}

    dates = series.index.strftime("%Y-%m-%d").tolist()
    actual = [float(v) for v in series.values.tolist()]

    model_results: Dict[str, ForecastResult] = {}
    for model_name in models:
        result = _fit_one_model(series, model_name, horizon=horizon)
        if result.ok:
            result.metrics.update(_calc_model_metrics(series, result.fitted, backtest_days))
        else:
            result.metrics.update({
                "mae": None,
                "rmse": None,
                "mape": None,
                "directional_accuracy": None,
            })
        model_results[model_name] = result

    weights = _build_inverse_mae_weights(model_results)
    forecast_dates = pd.bdate_range(start=series.index[-1] + pd.offsets.BDay(1), periods=horizon).strftime("%Y-%m-%d").tolist()
    ensemble_forecast = _weighted_average_forecast(model_results, weights, horizon)

    models_payload = {}
    for name, result in model_results.items():
        models_payload[name] = {
            "ok": result.ok,
            "error": result.error,
            "fitted": result.fitted,
            "forecast_dates": result.forecast_dates,
            "forecast": result.forecast,
            "metrics": result.metrics,
        }

    latest_actual = actual[-1] if actual else None

    return {
        "ok": True,
        "target": "USD/KRW",
        "source_start_date": start_date,
        "history_dates": dates,
        "actual": actual,
        "latest_actual": latest_actual,
        "horizon": horizon,
        "forecast_dates": forecast_dates,
        "models": models_payload,
        "ensemble": {
            "weights": weights,
            "forecast_dates": forecast_dates,
            "forecast": ensemble_forecast,
        },
        "meta": {
            "backtest_days": backtest_days,
            "n_obs": len(series),
            "supported_models": SUPPORTED_MODELS,
        }
    }


@cache.memoize(timeout=60 * 30)
def build_exchange_rate_plot_payload(
    horizon: int = DEFAULT_HORIZON,
    start_date: str = DEFAULT_START_DATE,
    backtest_days: int = DEFAULT_BACKTEST_DAYS,
    models: Optional[List[str]] = None,
) -> Dict:
    data = build_exchange_rate_forecast(
        horizon=horizon,
        start_date=start_date,
        backtest_days=backtest_days,
        models=models,
    )
    if not data.get("ok"):
        return data

    history_dates = data["history_dates"]
    forecast_dates = data["forecast_dates"]

    plot_models = {}
    for name, info in data["models"].items():
        plot_models[name] = {
            **info,
            **_merge_history_and_forecast(
                history_dates=history_dates,
                fitted=info.get("fitted", []),
                forecast_dates=forecast_dates,
                forecast=info.get("forecast", []),
            )
        }

    ensemble_fc = data.get("ensemble", {}).get("forecast", [])
    ensemble_path = [None] * len(history_dates) + ensemble_fc

    return {
        "ok": True,
        "target": data["target"],
        "history_dates": history_dates,
        "actual": data["actual"],
        "forecast_dates": forecast_dates,
        "models": plot_models,
        "ensemble": {
            **data["ensemble"],
            "full_dates": history_dates + forecast_dates,
            "full_path": ensemble_path,
        },
        "meta": data["meta"],
        "latest_actual": data["latest_actual"],
    }


def save_exchange_rate_forecast_snapshot(
    horizon: Optional[int] = None,
    start_date: Optional[str] = None,
    backtest_days: Optional[int] = None,
    models: Optional[List[str]] = None,
) -> Dict:
    horizon = DEFAULT_HORIZON if horizon is None else horizon
    start_date = DEFAULT_START_DATE if start_date is None else start_date
    backtest_days = DEFAULT_BACKTEST_DAYS if backtest_days is None else backtest_days

    payload = build_exchange_rate_forecast(
        horizon=horizon,
        start_date=start_date,
        backtest_days=backtest_days,
        models=models,
    )

    if not payload.get("ok"):
        return payload

    run_date = date.today()
    target = payload.get("target", "USD/KRW")
    forecast_dates = payload.get("forecast_dates", [])
    rows_to_insert = []

    for model_name, model_info in payload.get("models", {}).items():
        if not model_info.get("ok"):
            continue
        forecasts = model_info.get("forecast", [])
        for fd, pred in zip(forecast_dates, forecasts):
            if pred is None:
                continue
            rows_to_insert.append((run_date, target, horizon, backtest_days, model_name, fd, float(pred)))

    ensemble_fc = payload.get("ensemble", {}).get("forecast", [])
    for fd, pred in zip(forecast_dates, ensemble_fc):
        if pred is None:
            continue
        rows_to_insert.append((run_date, target, horizon, backtest_days, "ensemble", fd, float(pred)))

    if not rows_to_insert:
        return {"ok": False, "error": "no forecast rows to save"}

    conn = None
    cur = None
    inserted = 0
    skipped = 0

    try:
        conn = get_connection()
        cur = conn.cursor()

        sql = """
        INSERT INTO fx_forecast_snapshots
            (run_date, target, horizon, backtest_days, model_name, forecast_date, predicted_value)
        VALUES
            (%s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            updated_at = CURRENT_TIMESTAMP
        """

        for row in rows_to_insert:
            cur.execute(sql, row)
            if cur.rowcount == 1:
                inserted += 1
            else:
                skipped += 1

        conn.commit()

        return {
            "ok": True,
            "message": "forecast snapshot saved",
            "run_date": run_date.isoformat(),
            "target": target,
            "horizon": horizon,
            "inserted": inserted,
            "skipped": skipped,
            "total_attempted": len(rows_to_insert),
        }

    except Exception as e:
        if conn:
            conn.rollback()
        return {"ok": False, "error": f"failed to save forecast snapshot: {e}"}
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


def update_fx_forecast_actuals(start_date: str = DEFAULT_START_DATE) -> Dict:
    series = load_exchange_rate_series(start_date=start_date)
    series = _clean_series(series)

    if series.empty:
        return {"ok": False, "error": "actual series is empty"}

    actual_map = {d.strftime("%Y-%m-%d"): float(v) for d, v in series.items()}

    conn = None
    cur = None
    updated = 0

    try:
        conn = get_connection()
        cur = conn.cursor()

        cur.execute("""
            SELECT id, forecast_date, predicted_value
            FROM fx_forecast_snapshots
            WHERE actual_value IS NULL
        """)
        rows = cur.fetchall()

        update_sql = """
            UPDATE fx_forecast_snapshots
            SET actual_value = %s,
                abs_error = %s,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
        """

        for row in rows:
            fd = row["forecast_date"]
            fd_key = fd.strftime("%Y-%m-%d") if hasattr(fd, "strftime") else str(fd)

            actual_val = actual_map.get(fd_key)
            if actual_val is None:
                continue

            pred_val = float(row["predicted_value"])
            abs_error = abs(actual_val - pred_val)

            cur.execute(update_sql, (actual_val, abs_error, row["id"]))
            updated += 1

        conn.commit()
        return {"ok": True, "updated": updated}

    except Exception as e:
        if conn:
            conn.rollback()
        return {"ok": False, "error": f"failed to update actuals: {e}"}
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


def get_fx_forecast_history(
    limit: int = 100,
    model_name: Optional[str] = None,
    run_date: Optional[str] = None,
) -> Dict:
    conn = None
    cur = None

    try:
        conn = get_connection()
        cur = conn.cursor()

        sql = """
            SELECT
                id,
                run_date,
                target,
                horizon,
                backtest_days,
                model_name,
                forecast_date,
                predicted_value,
                actual_value,
                abs_error,
                created_at,
                updated_at
            FROM fx_forecast_snapshots
            WHERE 1=1
        """
        params = []

        if model_name:
            sql += " AND model_name = %s"
            params.append(model_name)

        if run_date:
            sql += " AND run_date = %s"
            params.append(run_date)

        sql += """
            ORDER BY run_date DESC, forecast_date ASC, model_name ASC
            LIMIT %s
        """
        params.append(int(limit))

        cur.execute(sql, params)
        rows = cur.fetchall()

        def _serialize_row(row):
            out = dict(row)
            for key in ["run_date", "forecast_date", "created_at", "updated_at"]:
                val = out.get(key)
                if hasattr(val, "isoformat"):
                    out[key] = val.isoformat()
                elif val is not None:
                    out[key] = str(val)
            for key in ["predicted_value", "actual_value", "abs_error"]:
                if out.get(key) is not None:
                    out[key] = float(out[key])
            return out

        rows = [_serialize_row(r) for r in rows]
        return {"ok": True, "count": len(rows), "rows": rows}

    except Exception as e:
        return {"ok": False, "error": f"failed to load forecast history: {e}"}
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()