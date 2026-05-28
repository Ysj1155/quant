from flask import Blueprint, jsonify, request

from domain.sector import (
    add_to_bucket,
    get_etf_sector_weights,
    get_sector_for_symbol,
    is_etf,
    normalize_symbol,
)
from extensions import cache
from services.dashboard_data import load_account_value_rows, load_current_portfolio_rows
from services.performance import build_performance_summary
from services.portfolio import build_pnl_from_snapshots, build_pnl_series, build_pnl_timeseries
from services.risk import build_risk_summary
from services.signals import build_account_signals
from services.snapshots import list_snapshot_dates, load_snapshot
from services.timeline import build_investment_timeline

portfolio_bp = Blueprint("portfolio", __name__)


@portfolio_bp.route("/get_portfolio_data")
@cache.cached(timeout=30)
def get_portfolio_data():
    try:
        return jsonify(load_current_portfolio_rows())
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@portfolio_bp.route("/get_pie_chart_data")
@cache.cached(timeout=30)
def get_pie_chart_data():
    try:
        rows = load_current_portfolio_rows()
        if not rows:
            return jsonify({"labels": [], "values": [], "total_value": "0 KRW"})

        tickers = [row["ticker"] for row in rows]
        amounts = [row["evaluation_amount"] for row in rows]
        total = sum(amounts)
        values = [(amount / total) * 100 if total else 0 for amount in amounts]

        return jsonify({
            "labels": tickers,
            "values": values,
            "total_value": f"{int(total):,} KRW",
        })
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@portfolio_bp.route("/get_account_value_data")
@cache.cached(timeout=60)
def get_account_value_data():
    try:
        df = load_account_value_rows()
        if df.empty:
            return jsonify({"error": "No account value data found"}), 500

        dates = df["date"].dt.strftime("%Y-%m-%d").tolist()
        values = df["total_value"].astype(float).tolist()
        base = values[0]
        profits = [0 for _ in values] if base == 0 else [((value - base) / base) * 100 for value in values]

        return jsonify({
            "dates": dates,
            "total_values": values,
            "profits": profits,
            "latest_value": values[-1],
            "latest_profit": profits[-1],
        })
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@portfolio_bp.route("/get_portfolio_sector_data")
@cache.cached(timeout=60 * 10)
def get_portfolio_sector_data():
    """Build sector exposure from current stock and ETF holdings."""
    try:
        rows = load_current_portfolio_rows()
        if not rows:
            return jsonify({})

        bucket = {}
        for row in rows:
            raw = row["ticker"]
            eval_amount = float(row["evaluation_amount"] or 0)
            symbol = normalize_symbol(raw)
            if not symbol:
                continue

            if is_etf(symbol):
                weights = get_etf_sector_weights(symbol)
                if weights:
                    for sector, weight in weights.items():
                        add_to_bucket(bucket, sector, symbol, eval_amount * weight)
                else:
                    add_to_bucket(bucket, "Unknown", symbol, eval_amount)
            else:
                sector = get_sector_for_symbol(symbol)
                add_to_bucket(bucket, sector, symbol, eval_amount)

        return jsonify(bucket)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@portfolio_bp.route("/api/pnl")
@cache.cached(timeout=60, query_string=True)
def api_pnl():
    date = (request.args.get("date") or "").strip() or None
    data = build_pnl_from_snapshots(asof_date=date)
    status = 200 if "error" not in data else 400
    return jsonify(data), status


@portfolio_bp.route("/api/pnl/events")
@cache.cached(timeout=60, query_string=True)
def api_pnl_events():
    data = build_pnl_series()
    if not data.get("ok"):
        return jsonify(data), 500

    date = (request.args.get("date") or "").strip()
    events = data.get("events", [])
    if date:
        events = [event for event in events if event.get("date") == date]

    return jsonify({"ok": True, "events": events})


@portfolio_bp.route("/api/pnl/series")
@cache.cached(timeout=60)
def api_pnl_series():
    data = build_pnl_timeseries()
    status = 200 if data.get("ok") else 500
    return jsonify(data), status


@portfolio_bp.route("/api/timeline/events")
@cache.cached(timeout=60, query_string=True)
def api_timeline_events():
    limit = int(request.args.get("limit", 100))
    include_initial = (request.args.get("include_initial") or "").lower() in ("1", "true", "yes", "y")
    full_scan = (request.args.get("full") or "1").lower() in ("1", "true", "yes", "y")
    date = (request.args.get("date") or "").strip() or None
    event_type = (request.args.get("event_type") or "").strip() or None

    data = build_investment_timeline(
        limit=limit,
        include_initial=include_initial,
        date=date,
        event_type=event_type,
        full_scan=full_scan,
    )
    return jsonify(data), (200 if data.get("ok") else 500)


@portfolio_bp.route("/api/performance/summary")
@cache.cached(timeout=60)
def api_performance_summary():
    data = build_performance_summary()
    return jsonify(data), (200 if data.get("ok") else 500)


@portfolio_bp.route("/api/risk/summary")
@cache.cached(timeout=60)
def api_risk_summary():
    data = build_risk_summary()
    return jsonify(data), (200 if data.get("ok") else 500)


@portfolio_bp.route("/api/signals/account")
@cache.cached(timeout=60)
def api_account_signals():
    data = build_account_signals()
    return jsonify(data), (200 if data.get("ok") else 500)


@portfolio_bp.route("/api/snapshots/dates")
@cache.cached(timeout=60 * 5)
def snapshot_dates():
    return jsonify({"dates": list_snapshot_dates()})


@portfolio_bp.route("/api/snapshot")
@cache.cached(timeout=60 * 5, query_string=True)
def snapshot_one():
    date = (request.args.get("date") or "").strip()
    if not date:
        return jsonify({"error": "date is required (YYYY-MM-DD)"}), 400

    data = load_snapshot(date)
    if "error" in data:
        return jsonify(data), 404
    return jsonify(data)
