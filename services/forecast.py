# services/forecast.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
import math
import warnings
import numpy as np
import pandas as pd
from extensions import cache
from datetime import date
from db.connection import get_connection


# ------------------------------------------------------------
# 선택적 데이터 소스
# 1) FinanceDataReader 우선
# 2) 없으면 yfinance fallback
# ------------------------------------------------------------
try:
    import FinanceDataReader as fdr
except Exception:
    fdr = None

try:
    import yfinance as yf
except Exception:
    yf = None

# statsmodels
from statsmodels.tsa.holtwinters import ExponentialSmoothing
from statsmodels.tsa.arima.model import ARIMA

warnings.filterwarnings("ignore")


# ------------------------------------------------------------
# 설정값
# ------------------------------------------------------------
DEFAULT_START_DATE = "2023-01-01"
DEFAULT_HORIZON = 7
DEFAULT_BACKTEST_DAYS = 30
MIN_SERIES_LENGTH = 40

MODEL_LINEAR = "linear"
MODEL_HOLT = "holt"
MODEL_ARIMA = "arima"

SUPPORTED_MODELS = [MODEL_LINEAR, MODEL_HOLT, MODEL_ARIMA]


@dataclass
class ForecastResult:
    model: str
    fitted: List[Optional[float]]
    forecast_dates: List[str]
    forecast: List[Optional[float]]
    metrics: Dict[str, Optional[float]]
    ok: bool
    error: Optional[str] = None


# ------------------------------------------------------------
# 유틸
# ------------------------------------------------------------
def _safe_float(x) -> Optional[float]:
    try:
        if x is None:
            return None
        if isinstance(x, (np.floating, np.integer)):
            return float(x)
        if pd.isna(x):
            return None
        return float(x)
    except Exception:
        return None


def _series_to_list(s: pd.Series, length: Optional[int] = None) -> List[Optional[float]]:
    vals = [_safe_float(v) for v in s.tolist()]
    if length is not None:
        if len(vals) < length:
            vals = [None] * (length - len(vals)) + vals
        elif len(vals) > length:
            vals = vals[-length:]
    return vals


def _future_bday_dates(last_date: pd.Timestamp, periods: int) -> List[str]:
    if periods <= 0:
        return []
    idx = pd.bdate_range(start=last_date + pd.offsets.BDay(1), periods=periods)
    return idx.strftime("%Y-%m-%d").tolist()


def _mae(y_true: pd.Series, y_pred: pd.Series) -> Optional[float]:
    df = pd.concat([y_true.rename("y"), y_pred.rename("p")], axis=1).dropna()
    if df.empty:
        return None
    return float(np.mean(np.abs(df["y"] - df["p"])))


def _rmse(y_true: pd.Series, y_pred: pd.Series) -> Optional[float]:
    df = pd.concat([y_true.rename("y"), y_pred.rename("p")], axis=1).dropna()
    if df.empty:
        return None
    return float(np.sqrt(np.mean((df["y"] - df["p"]) ** 2)))


def _mape(y_true: pd.Series, y_pred: pd.Series) -> Optional[float]:
    df = pd.concat([y_true.rename("y"), y_pred.rename("p")], axis=1).dropna()
    if df.empty:
        return None
    nonzero = df["y"] != 0
    if not nonzero.any():
        return None
    return float(np.mean(np.abs((df.loc[nonzero, "y"] - df.loc[nonzero, "p"]) / df.loc[nonzero, "y"])) * 100.0)


def _directional_accuracy(y_true: pd.Series, y_pred: pd.Series) -> Optional[float]:
    df = pd.concat([y_true.rename("y"), y_pred.rename("p")], axis=1).dropna()
    if len(df) < 2:
        return None

    dy = np.sign(df["y"].diff())
    dp = np.sign(df["p"].diff())

    valid = pd.concat([dy.rename("dy"), dp.rename("dp")], axis=1).dropna()
    if valid.empty:
        return None

    acc = (valid["dy"] == valid["dp"]).mean() * 100.0
    return float(acc)


def _clean_series(s: pd.Series) -> pd.Series:
    out = s.copy()
    out = pd.to_numeric(out, errors="coerce")
    out = out.dropna()
    out = out[~out.index.duplicated(keep="last")]
    out = out.sort_index()
    return out

# ------------------------------------------------------------
# DB 저장 버튼
# ------------------------------------------------------------
def update_fx_forecast_actuals(start_date: str = DEFAULT_START_DATE) -> Dict:
    """
    저장된 forecast 중 actual_value가 비어 있는 항목에 대해
    실제 USD/KRW 값을 채우고 abs_error 계산
    """
    series = load_exchange_rate_series(start_date=start_date)
    series = _clean_series(series)

    if series.empty:
        return {"ok": False, "error": "actual series is empty"}

    actual_map = {
        d.strftime("%Y-%m-%d"): float(v)
        for d, v in series.items()
    }

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
            if hasattr(fd, "strftime"):
                fd_key = fd.strftime("%Y-%m-%d")
            else:
                fd_key = str(fd)

            actual_val = actual_map.get(fd_key)
            if actual_val is None:
                continue

            pred_val = float(row["predicted_value"])
            abs_error = abs(actual_val - pred_val)

            cur.execute(update_sql, (actual_val, abs_error, row["id"]))
            updated += 1

        conn.commit()

        return {
            "ok": True,
            "updated": updated
        }

    except Exception as e:
        if conn:
            conn.rollback()
        return {
            "ok": False,
            "error": f"failed to update actuals: {e}"
        }
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()

# ------------------------------------------------------------
# 데이터 로더
# ------------------------------------------------------------
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

    # Yahoo의 KRW=X 는 일반적으로 USD/KRW 성격으로 사용 가능
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


@cache.memoize(timeout=60 * 60 * 6)  # 6시간
def load_exchange_rate_series(start_date: str = DEFAULT_START_DATE) -> pd.Series:
    """
    USD/KRW 시계열 로드.
    1) FinanceDataReader 우선
    2) yfinance fallback
    """
    s = _load_exchange_rate_from_fdr(start_date)
    if s is not None and not s.empty:
        return s

    s = _load_exchange_rate_from_yf(start_date)
    if s is not None and not s.empty:
        return s

    raise RuntimeError("failed to load exchange rate series from both FDR and yfinance")


# ------------------------------------------------------------
# 모델 1: 선형 추세
# ------------------------------------------------------------
def fit_linear_trend(series: pd.Series, horizon: int = DEFAULT_HORIZON) -> ForecastResult:
    try:
        n = len(series)
        if n < 2:
            return ForecastResult(
                model=MODEL_LINEAR,
                fitted=[],
                forecast_dates=[],
                forecast=[],
                metrics={},
                ok=False,
                error="not enough data for linear trend",
            )

        x = np.arange(n, dtype=float)
        y = series.values.astype(float)

        coef = np.polyfit(x, y, deg=1)
        fitted = coef[0] * x + coef[1]

        fx = np.arange(n, n + horizon, dtype=float)
        forecast = coef[0] * fx + coef[1]

        return ForecastResult(
            model=MODEL_LINEAR,
            fitted=[float(v) for v in fitted.tolist()],
            forecast_dates=_future_bday_dates(series.index[-1], horizon),
            forecast=[float(v) for v in forecast.tolist()],
            metrics={},
            ok=True,
        )
    except Exception as e:
        return ForecastResult(
            model=MODEL_LINEAR,
            fitted=[],
            forecast_dates=[],
            forecast=[],
            metrics={},
            ok=False,
            error=str(e),
        )


# ------------------------------------------------------------
# 모델 2: Holt / Exponential Smoothing
# ------------------------------------------------------------
def fit_holt(series: pd.Series, horizon: int = DEFAULT_HORIZON) -> ForecastResult:
    try:
        if len(series) < 8:
            return ForecastResult(
                model=MODEL_HOLT,
                fitted=[],
                forecast_dates=[],
                forecast=[],
                metrics={},
                ok=False,
                error="not enough data for holt",
            )

        model = ExponentialSmoothing(
            series.astype(float),
            trend="add",
            seasonal=None,
            initialization_method="estimated",
        )
        fit = model.fit(optimized=True)
        fitted = fit.fittedvalues
        forecast = fit.forecast(horizon)

        return ForecastResult(
            model=MODEL_HOLT,
            fitted=_series_to_list(fitted, len(series)),
            forecast_dates=_future_bday_dates(series.index[-1], horizon),
            forecast=_series_to_list(forecast),
            metrics={},
            ok=True,
        )
    except Exception as e:
        return ForecastResult(
            model=MODEL_HOLT,
            fitted=[],
            forecast_dates=[],
            forecast=[],
            metrics={},
            ok=False,
            error=str(e),
        )


# ------------------------------------------------------------
# 모델 3: ARIMA
# ------------------------------------------------------------
def fit_arima(series: pd.Series, horizon: int = DEFAULT_HORIZON, order=(1, 1, 1)):
    try:
        model = ARIMA(series.astype(float), order=order)
        fit = model.fit()

        fitted = fit.fittedvalues.copy()
        fitted = fitted.reindex(series.index)

        # d=1 이므로 초기 1개 fitted는 신뢰하지 않고 결측 처리
        d = order[1]
        if d > 0:
            fitted.iloc[:d] = np.nan

        forecast = fit.forecast(steps=horizon)

        return ForecastResult(
            model=MODEL_ARIMA,
            fitted=_series_to_list(fitted, len(series)),
            forecast_dates=_future_bday_dates(series.index[-1], horizon),
            forecast=_series_to_list(forecast),
            metrics={
                "order_p": order[0],
                "order_d": order[1],
                "order_q": order[2],
            },
            ok=True,
        )

    except Exception as e:
        return ForecastResult(
            model=MODEL_ARIMA,
            fitted=[],
            forecast_dates=[],
            forecast=[],
            metrics={},
            ok=False,
            error=str(e),
        )


# ------------------------------------------------------------
# 모델 실행 디스패처
# ------------------------------------------------------------
def _fit_one_model(series: pd.Series, model_name: str, horizon: int) -> ForecastResult:
    if model_name == MODEL_LINEAR:
        return fit_linear_trend(series, horizon=horizon)
    if model_name == MODEL_HOLT:
        return fit_holt(series, horizon=horizon)
    if model_name == MODEL_ARIMA:
        return fit_arima(series, horizon=horizon)
    return ForecastResult(
        model=model_name,
        fitted=[],
        forecast_dates=[],
        forecast=[],
        metrics={},
        ok=False,
        error=f"unsupported model: {model_name}",
    )


# ------------------------------------------------------------
# 간이 백테스트
# 최근 backtest_days 구간에서 fitted 값 기준 오차 측정
# ------------------------------------------------------------
def _calc_model_metrics(actual_series: pd.Series, fitted_values: List[Optional[float]], backtest_days: int) -> Dict[str, Optional[float]]:
    if not fitted_values:
        return {
            "mae": None,
            "rmse": None,
            "mape": None,
            "directional_accuracy": None,
        }

    fitted = pd.Series(fitted_values, index=actual_series.index[-len(fitted_values):])
    if len(fitted) != len(actual_series):
        fitted = fitted.reindex(actual_series.index)

    y_true = actual_series.tail(backtest_days)
    y_pred = fitted.tail(backtest_days)

    return {
        "mae": _mae(y_true, y_pred),
        "rmse": _rmse(y_true, y_pred),
        "mape": _mape(y_true, y_pred),
        "directional_accuracy": _directional_accuracy(y_true, y_pred),
    }


# ------------------------------------------------------------
# 앙상블
# 최근 MAE의 역수 기반 자동 가중치
# ------------------------------------------------------------
def _build_inverse_mae_weights(model_results: Dict[str, ForecastResult]) -> Dict[str, float]:
    raw = {}
    for name, result in model_results.items():
        if not result.ok:
            continue
        mae = result.metrics.get("mae")
        if mae is None or mae <= 0:
            continue
        raw[name] = 1.0 / mae

    if not raw:
        ok_models = [name for name, result in model_results.items() if result.ok and result.forecast]
        if not ok_models:
            return {}
        w = 1.0 / len(ok_models)
        return {name: w for name in ok_models}

    total = sum(raw.values())
    return {name: float(v / total) for name, v in raw.items()}


def _weighted_average_forecast(
    model_results: Dict[str, ForecastResult],
    weights: Dict[str, float],
    horizon: int,
) -> List[Optional[float]]:
    if not weights:
        return [None] * horizon

    out: List[Optional[float]] = []
    for i in range(horizon):
        num = 0.0
        den = 0.0
        for name, weight in weights.items():
            result = model_results.get(name)
            if not result or not result.ok:
                continue
            if i >= len(result.forecast):
                continue
            val = result.forecast[i]
            if val is None:
                continue
            num += weight * float(val)
            den += weight

        out.append(float(num / den) if den > 0 else None)
    return out


# ------------------------------------------------------------
# 메인 빌더
# ------------------------------------------------------------
@cache.memoize(timeout=60 * 30)  # 30분
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
        return {
            "ok": False,
            "error": f"not enough observations: {len(series)} < {MIN_SERIES_LENGTH}",
        }

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
    forecast_dates = _future_bday_dates(series.index[-1], horizon)
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


# ------------------------------------------------------------
# 프론트 표시용 단순화 버전
# 실제선은 history_dates에만 있고,
# 각 모델 forecast는 history 끝에 이어붙인 full path도 함께 제공
# ------------------------------------------------------------
def _merge_history_and_forecast(
    history_dates: List[str],
    fitted: List[Optional[float]],
    forecast_dates: List[str],
    forecast: List[Optional[float]],
) -> Dict[str, List]:
    return {
        "full_dates": history_dates + forecast_dates,
        "full_fitted_plus_forecast": fitted + forecast,
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

# ------------------------------------------------------------
# 환율 예상값 DB에 저장용
# ------------------------------------------------------------

def save_exchange_rate_forecast_snapshot(
    horizon: Optional[int] = None,
    start_date: Optional[str] = None,
    backtest_days: Optional[int] = None,
    models: Optional[List[str]] = None,
) -> Dict:
    """
    현재 환율 forecast 결과를 DB에 저장.
    하루 1회 제한:
      run_date + target + horizon + model_name + forecast_date unique
    """
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
            rows_to_insert.append(
                (
                    run_date,
                    target,
                    horizon,
                    backtest_days,
                    model_name,
                    fd,
                    float(pred),
                )
            )

    ensemble_fc = payload.get("ensemble", {}).get("forecast", [])
    for fd, pred in zip(forecast_dates, ensemble_fc):
        if pred is None:
            continue
        rows_to_insert.append(
            (
                run_date,
                target,
                horizon,
                backtest_days,
                "ensemble",
                fd,
                float(pred),
            )
        )

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

# ------------------------------------------------------------
# 이력 조회
# ------------------------------------------------------------
def get_fx_forecast_history(
    limit: int = 100,
    model_name: Optional[str] = None,
    run_date: Optional[str] = None,
) -> Dict:
    """
    저장된 환율 forecast 이력 조회
    """
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

        return {
            "ok": True,
            "count": len(rows),
            "rows": rows,
        }

    except Exception as e:
        return {
            "ok": False,
            "error": f"failed to load forecast history: {e}"
        }
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()
