#routes/stocks.py
from flask import Blueprint, jsonify, request
from extensions import cache
from api.finnhub_api import get_quote_raw, get_profile_raw, get_metrics_raw
from api.kis_api import get_overseas_daily_price
from utils import parse_kis_ohlc

stocks_bp = Blueprint("stocks", __name__)

@stocks_bp.route("/get_stock_detail_finnhub")
@cache.cached(timeout=30, query_string=True)  # ticker별 캐시
def get_stock_detail_finnhub():
    ticker = request.args.get("ticker", "").upper().strip()
    return jsonify({
        "ticker": ticker,
        "price": get_quote_raw(ticker),
        "profile": get_profile_raw(ticker),
        "metrics": get_metrics_raw(ticker)
    })

@stocks_bp.route("/get_stock_chart_kis")
@cache.cached(timeout=60 * 5, query_string=True)  # 5분 캐시
def get_stock_chart_kis():
    ticker = request.args.get("ticker")
    exchange = request.args.get("exchange", "NAS")
    raw = get_overseas_daily_price(ticker, exchange)
    return jsonify({"ohlc": parse_kis_ohlc(raw)})
