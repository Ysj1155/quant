from flask import Blueprint, jsonify, request
from extensions import cache

from services.forecast import (
    build_exchange_rate_forecast,
    build_exchange_rate_plot_payload,
    save_exchange_rate_forecast_snapshot,
    update_fx_forecast_actuals,
    get_fx_forecast_history,
)

fx_forecast_bp = Blueprint("fx_forecast", __name__)


def _parse_models_arg(value):
    if not value:
        return None
    if isinstance(value, list):
        return value
    return [m.strip() for m in str(value).split(",") if m.strip()]


@fx_forecast_bp.route("/api/forecast/fx", methods=["GET"])
@cache.cached(timeout=60, query_string=True)
def get_fx_forecast():
    try:
        horizon = int(request.args.get("horizon", 7))
        backtest_days = int(request.args.get("backtest_days", 30))
        start_date = request.args.get("start_date", "2023-01-01")
        models = _parse_models_arg(request.args.get("models"))

        data = build_exchange_rate_forecast(
            horizon=horizon,
            start_date=start_date,
            backtest_days=backtest_days,
            models=models,
        )
        return jsonify(data), (200 if data.get("ok") else 400)

    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@fx_forecast_bp.route("/api/forecast/fx/plot", methods=["GET"])
@cache.cached(timeout=60, query_string=True)
def get_fx_forecast_plot():
    try:
        horizon = int(request.args.get("horizon", 7))
        backtest_days = int(request.args.get("backtest_days", 30))
        start_date = request.args.get("start_date", "2023-01-01")
        models = _parse_models_arg(request.args.get("models"))

        data = build_exchange_rate_plot_payload(
            horizon=horizon,
            start_date=start_date,
            backtest_days=backtest_days,
            models=models,
        )
        return jsonify(data), (200 if data.get("ok") else 400)

    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@fx_forecast_bp.route("/api/forecast/fx/health", methods=["GET"])
def fx_forecast_health():
    return jsonify({
        "ok": True,
        "service": "fx_forecast",
        "message": "FX forecast API is running",
    })


@fx_forecast_bp.route("/api/forecast/fx/save", methods=["POST"])
def save_fx_forecast():
    try:
        body = request.get_json(silent=True) or {}

        horizon = int(body.get("horizon", 7))
        backtest_days = int(body.get("backtest_days", 30))
        start_date = body.get("start_date", "2023-01-01")
        models = _parse_models_arg(body.get("models"))

        data = save_exchange_rate_forecast_snapshot(
            horizon=horizon,
            start_date=start_date,
            backtest_days=backtest_days,
            models=models,
        )
        return jsonify(data), (200 if data.get("ok") else 400)

    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@fx_forecast_bp.route("/api/forecast/fx/update-actuals", methods=["POST"])
def update_fx_actuals():
    try:
        body = request.get_json(silent=True) or {}
        start_date = body.get("start_date", "2023-01-01")

        data = update_fx_forecast_actuals(start_date=start_date)
        return jsonify(data), (200 if data.get("ok") else 400)

    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@fx_forecast_bp.route("/api/forecast/fx/history", methods=["GET"])
def get_fx_history():
    try:
        limit = int(request.args.get("limit", 100))
        model_name = request.args.get("model_name")
        run_date = request.args.get("run_date")

        data = get_fx_forecast_history(
            limit=limit,
            model_name=model_name,
            run_date=run_date,
        )
        return jsonify(data), (200 if data.get("ok") else 400)

    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500