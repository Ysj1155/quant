from flask import Blueprint, jsonify, request
from extensions import cache

from services.account_forecast_service import (
    build_account_value_forecast,
    build_account_value_plot_payload,
    save_account_value_forecast_snapshot,
    update_account_forecast_actuals,
    get_account_forecast_history,
)

account_forecast_bp = Blueprint("account_forecast", __name__)


def _parse_models_arg(value):
    if not value:
        return None
    if isinstance(value, list):
        return value
    return [m.strip() for m in str(value).split(",") if m.strip()]


@account_forecast_bp.route("/api/forecast/account", methods=["GET"])
@cache.cached(timeout=60, query_string=True)
def get_account_forecast():
    try:
        horizon = int(request.args.get("horizon", 7))
        backtest_days = int(request.args.get("backtest_days", 30))
        models = _parse_models_arg(request.args.get("models"))
        csv_path = request.args.get("csv_path")

        data = build_account_value_forecast(
            horizon=horizon,
            backtest_days=backtest_days,
            models=models,
            csv_path=csv_path,
        )

        return jsonify(data), (200 if data.get("ok") else 400)

    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@account_forecast_bp.route("/api/forecast/account/plot", methods=["GET"])
@cache.cached(timeout=60, query_string=True)
def get_account_forecast_plot():
    try:
        horizon = int(request.args.get("horizon", 7))
        backtest_days = int(request.args.get("backtest_days", 30))
        models = _parse_models_arg(request.args.get("models"))
        csv_path = request.args.get("csv_path")

        data = build_account_value_plot_payload(
            horizon=horizon,
            backtest_days=backtest_days,
            models=models,
            csv_path=csv_path,
        )

        return jsonify(data), (200 if data.get("ok") else 400)

    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@account_forecast_bp.route("/api/forecast/account/save", methods=["POST"])
def save_account_forecast():
    try:
        body = request.get_json(silent=True) or {}

        horizon = int(body.get("horizon", 7))
        backtest_days = int(body.get("backtest_days", 30))
        models = _parse_models_arg(body.get("models"))
        csv_path = body.get("csv_path")

        data = save_account_value_forecast_snapshot(
            horizon=horizon,
            backtest_days=backtest_days,
            models=models,
            csv_path=csv_path,
        )

        return jsonify(data), (200 if data.get("ok") else 400)

    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@account_forecast_bp.route("/api/forecast/account/update-actuals", methods=["POST"])
def update_account_actuals():
    try:
        body = request.get_json(silent=True) or {}
        csv_path = body.get("csv_path")

        data = update_account_forecast_actuals(csv_path=csv_path)

        return jsonify(data), (200 if data.get("ok") else 400)

    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@account_forecast_bp.route("/api/forecast/account/history", methods=["GET"])
def get_account_history():
    try:
        limit = int(request.args.get("limit", 100))
        model_name = request.args.get("model_name")
        run_date = request.args.get("run_date")

        data = get_account_forecast_history(
            limit=limit,
            model_name=model_name,
            run_date=run_date,
        )

        return jsonify(data), (200 if data.get("ok") else 400)

    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@account_forecast_bp.route("/api/forecast/account/health", methods=["GET"])
def account_forecast_health():
    return jsonify({
        "ok": True,
        "service": "account_forecast",
        "message": "Account forecast API is running",
    })