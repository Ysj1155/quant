# routes/portfolio.py
from flask import Blueprint, jsonify, request
from extensions import cache

# 기존 portfolio 관련 DB/섹터 기능이 이미 프로젝트에 있다면 그대로 사용
from utils import get_connection
from domain.sector import (
    normalize_symbol, is_etf, get_etf_sector_weights,
    get_sector_for_symbol, add_to_bucket
)

from services.portfolio import build_pnl_from_snapshots, build_pnl_series, build_pnl_timeseries
from services.snapshots import list_snapshot_dates, load_snapshot

portfolio_bp = Blueprint("portfolio", __name__)

# -----------------------------
# (A) 기존: 포트폴리오/자산 그래프 API
# -----------------------------
@portfolio_bp.route("/get_portfolio_data")
@cache.cached(timeout=30)
def get_portfolio_data():
    try:
        conn = get_connection()
        with conn.cursor(dictionary=True) as cur:
            cur.execute("""
                SELECT account_number, ticker, quantity,
                       purchase_amount, evaluation_amount,
                       profit_loss, profit_rate, evaluation_ratio
                FROM portfolio
            """)
            rows = cur.fetchall()
        conn.close()
        return jsonify(rows)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@portfolio_bp.route("/get_pie_chart_data")
@cache.cached(timeout=30)
def get_pie_chart_data():
    try:
        conn = get_connection()
        with conn.cursor(dictionary=True) as cur:
            cur.execute("SELECT ticker, evaluation_amount FROM portfolio")
            rows = cur.fetchall()
        conn.close()

        if not rows:
            return jsonify({"labels": [], "values": [], "total_value": "0 KRW"})

        tickers = [row["ticker"] for row in rows]
        amounts = [row["evaluation_amount"] for row in rows]
        total = sum(amounts)
        values = [(amt / total) * 100 if total else 0 for amt in amounts]

        return jsonify({
            "labels": tickers,
            "values": values,
            "total_value": f"{int(total):,} KRW"
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@portfolio_bp.route("/get_account_value_data")
@cache.cached(timeout=60)
def get_account_value_data():
    conn = None
    try:
        conn = get_connection()
        with conn.cursor(dictionary=True) as cur:
            cur.execute("SELECT date, total_value FROM account_value ORDER BY date ASC")
            rows = cur.fetchall()

        if not rows:
            return jsonify({"error": "No account value data found"}), 500

        dates = [str(row["date"]) for row in rows]
        values = [row["total_value"] for row in rows]
        base = values[0]
        profits = [0 for _ in values] if base == 0 else [((v - base) / base) * 100 for v in values]

        return jsonify({
            "dates": dates,
            "total_values": values,
            "profits": profits,
            "latest_value": values[-1],
            "latest_profit": profits[-1]
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        if conn:
            conn.close()


@portfolio_bp.route("/get_portfolio_sector_data")
@cache.cached(timeout=60 * 10)
def get_portfolio_sector_data():
    """개별주식+ETF를 섹터 기준 look-through."""
    try:
        conn = get_connection()
        with conn.cursor(dictionary=True) as cur:
            cur.execute("SELECT ticker, evaluation_amount FROM portfolio")
            rows = cur.fetchall()
        conn.close()

        if not rows:
            return jsonify({})

        bucket = {}
        for r in rows:
            raw = r["ticker"]
            eval_amt = float(r["evaluation_amount"] or 0)

            sym = normalize_symbol(raw)
            if not sym:
                continue

            if is_etf(sym):
                weights = get_etf_sector_weights(sym)
                if weights:
                    for sector, w in weights.items():
                        add_to_bucket(bucket, sector, sym, eval_amt * w)
                else:
                    add_to_bucket(bucket, "Unknown", sym, eval_amt)
            else:
                sector = get_sector_for_symbol(sym)
                add_to_bucket(bucket, sector, sym, eval_amt)

        return jsonify(bucket)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# -----------------------------
# (B) 기존: PnL API (routes/pnl.py 흡수)
# -----------------------------
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
        events = [e for e in events if e.get("date") == date]

    return jsonify({"ok": True, "events": events})

@portfolio_bp.route("/api/pnl/series")
@cache.cached(timeout=60)
def api_pnl_series():
    data = build_pnl_timeseries()
    status = 200 if data.get("ok") else 500
    return jsonify(data), status


# -----------------------------
# (C) 기존: Snapshots API (routes/snapshots.py 흡수)
# -----------------------------
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