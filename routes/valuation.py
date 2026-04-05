#routes/valuation.py
from flask import Blueprint, jsonify, request
from extensions import cache
from api.finnhub_api import get_metrics_raw, get_quote_raw, get_price_target_raw
from services.valuation import fair_price_from_ev_shares

valuation_bp = Blueprint("valuation", __name__)

@valuation_bp.route("/api/valuation")
@cache.cached(timeout=120, query_string=True)  # ticker별 2분 캐시
def valuation():
    ticker = request.args.get("ticker", "").upper().strip()
    if not ticker:
        return jsonify({"error": "ticker is required"}), 400

    quote = get_quote_raw(ticker) or {}
    metrics = get_metrics_raw(ticker) or {}
    metric = metrics.get("metric", {}) if isinstance(metrics, dict) else {}

    price = quote.get("c")
    hi52 = metric.get("52WeekHigh") or metric.get("52WeekHighAdjusted")
    lo52 = metric.get("52WeekLow") or metric.get("52WeekLowAdjusted")

    per = metric.get("peTTM")
    beta = metric.get("beta")

    ev = metric.get("enterpriseValue") or metric.get("enterpriseValueTTM") or None
    shares = metric.get("sharesOutstanding") or metric.get("shareOutstanding") or None
    my = fair_price_from_ev_shares(ev, shares)

    target = get_price_target_raw(ticker) or {}

    pos = None
    try:
        if price is not None and hi52 is not None and lo52 is not None:
            price = float(price); hi52 = float(hi52); lo52 = float(lo52)
            if hi52 > lo52:
                pos = (price - lo52) / (hi52 - lo52)
    except Exception:
        pos = None

    return jsonify({
        "ticker": ticker,
        "price": price,
        "my_model": my,
        "finnhub_target": {
            "targetHigh": target.get("targetHigh"),
            "targetLow": target.get("targetLow"),
            "targetMean": target.get("targetMean"),
            "targetMedian": target.get("targetMedian"),
        },
        "signals": {
            "per_ttm": per,
            "beta": beta,
            "week52_high": hi52,
            "week52_low": lo52,
            "week52_pos": pos,
        }
    })