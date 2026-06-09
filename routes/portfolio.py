from flask import Blueprint, jsonify, request

from domain.sector import (
    add_to_bucket,
    get_etf_sector_weights,
    get_sector_for_symbol,
    is_etf,
    normalize_symbol,
)
from extensions import cache
from services.data_quality import build_data_quality_summary
from services.dashboard_data import load_account_value_rows, load_current_portfolio_rows
from services.kr_security_master import get_kr_security_master_summary, refresh_kr_security_master
from services.performance import build_performance_summary
from services.portfolio import build_pnl_from_snapshots, build_pnl_series, build_pnl_timeseries
from services.risk import build_risk_summary
from services.security_resolver import build_security_resolution_summary
from services.snapshots import list_snapshot_dates, load_snapshot
from services.timeline import build_investment_timeline
from services.weekly_report import (
    build_weekly_report,
    list_weekly_report_files,
    read_weekly_report_file,
    save_weekly_report_markdown,
    update_weekly_report_file,
)

portfolio_bp = Blueprint("portfolio", __name__)


def _period_args():
    return {
        "period": (request.args.get("period") or "all").strip() or "all",
        "start_date": (request.args.get("start_date") or "").strip() or None,
        "end_date": (request.args.get("end_date") or "").strip() or None,
    }


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
@cache.cached(timeout=60, query_string=True)
def get_account_value_data():
    try:
        df = load_account_value_rows()
        if df.empty:
            return jsonify({"error": "No account value data found"}), 500

        from services.periods import filter_by_period

        df, period_range = filter_by_period(df, "date", **_period_args())
        if df.empty:
            return jsonify({
                "dates": [],
                "total_values": [],
                "profits": [],
                "latest_value": None,
                "latest_profit": 0,
                "period": period_range.__dict__,
            })

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
            "period": period_range.__dict__,
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
@cache.cached(timeout=60, query_string=True)
def api_pnl_series():
    data = build_pnl_timeseries(**_period_args())
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
        **_period_args(),
    )
    return jsonify(data), (200 if data.get("ok") else 500)


@portfolio_bp.route("/api/performance/summary")
@cache.cached(timeout=60, query_string=True)
def api_performance_summary():
    data = build_performance_summary(**_period_args())
    return jsonify(data), (200 if data.get("ok") else 500)


@portfolio_bp.route("/api/risk/summary")
@cache.cached(timeout=60, query_string=True)
def api_risk_summary():
    data = build_risk_summary(**_period_args())
    return jsonify(data), (200 if data.get("ok") else 500)


@portfolio_bp.route("/api/reports/weekly")
@cache.cached(timeout=60, query_string=True)
def api_weekly_report():
    args = _period_args()
    if args["period"] == "all" and not args["start_date"] and not args["end_date"]:
        args["period"] = "1w"
    data = build_weekly_report(**args)
    return jsonify(data), (200 if data.get("ok") else 500)


@portfolio_bp.route("/api/reports/weekly/save", methods=["POST"])
def api_save_weekly_report():
    args = _period_args()
    if args["period"] == "all" and not args["start_date"] and not args["end_date"]:
        args["period"] = "1w"
    data = save_weekly_report_markdown(**args)
    cache.clear()
    return jsonify(data), (200 if data.get("ok") else 500)


@portfolio_bp.route("/api/reports/weekly/files")
@cache.cached(timeout=10)
def api_weekly_report_files():
    data = list_weekly_report_files()
    return jsonify(data), (200 if data.get("ok") else 500)


@portfolio_bp.route("/api/reports/weekly/file")
def api_weekly_report_file():
    name = (request.args.get("name") or "").strip()
    if not name:
        return jsonify({"ok": False, "error": "name is required"}), 400
    try:
        data = read_weekly_report_file(name)
        return jsonify(data), (200 if data.get("ok") else 404)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@portfolio_bp.route("/api/reports/weekly/file", methods=["POST"])
def api_update_weekly_report_file():
    payload = request.get_json(silent=True) or {}
    name = str(payload.get("name") or "").strip()
    if not name:
        return jsonify({"ok": False, "error": "name is required"}), 400
    try:
        data = update_weekly_report_file(
            name=name,
            manual_markdown=str(payload.get("manual_markdown") or ""),
            tags=payload.get("tags") or [],
        )
        cache.clear()
        return jsonify(data), (200 if data.get("ok") else 404)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@portfolio_bp.route("/api/data-quality/summary")
@cache.cached(timeout=60)
def api_data_quality_summary():
    data = build_data_quality_summary()
    return jsonify(data), (200 if data.get("ok") else 500)


@portfolio_bp.route("/api/data-quality/security-resolution")
@cache.cached(timeout=60)
def api_security_resolution():
    data = build_security_resolution_summary()
    return jsonify({"ok": True, "security_resolution": data})


@portfolio_bp.route("/api/data-quality/kr-security-master")
@cache.cached(timeout=60)
def api_kr_security_master():
    return jsonify({"ok": True, "kr_security_master": get_kr_security_master_summary()})


@portfolio_bp.route("/api/data-quality/kr-security-master/refresh", methods=["POST"])
def api_refresh_kr_security_master():
    try:
        data = refresh_kr_security_master()
        cache.clear()
        return jsonify({"ok": True, "kr_security_master": data})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


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
