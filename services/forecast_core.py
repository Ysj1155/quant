from __future__ import annotations

import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd
from statsmodels.tsa.arima.model import ARIMA
from statsmodels.tsa.holtwinters import ExponentialSmoothing

warnings.filterwarnings("ignore")

# ------------------------------------------------------------
# 공통 설정값
# ------------------------------------------------------------
DEFAULT_START_DATE = "2023-01-01"
DEFAULT_HORIZON = 7
DEFAULT_BACKTEST_DAYS = 30
MIN_SERIES_LENGTH = 40

MODEL_LINEAR = "linear"
MODEL_HOLT = "holt"
MODEL_ARIMA = "arima"

SUPPORTED_MODELS = [MODEL_LINEAR, MODEL_HOLT, MODEL_ARIMA]

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
ACCOUNT_VALUE_CSV = DATA_DIR / "account_value.csv"


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
# 공통 유틸
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
# 공통 모델
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


def fit_arima(series: pd.Series, horizon: int = DEFAULT_HORIZON, order=(1, 1, 1)) -> ForecastResult:
    try:
        model = ARIMA(series.astype(float), order=order)
        fit = model.fit()

        fitted = fit.fittedvalues.copy()
        fitted = fitted.reindex(series.index)

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