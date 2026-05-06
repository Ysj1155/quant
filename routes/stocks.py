# routes/stocks.py
from flask import Blueprint, jsonify, request

from extensions import cache
from api.finnhub_api import get_quote_raw, get_profile_raw, get_metrics_raw
from api.kis_api import get_overseas_daily_price
from services.anomaly import get_stock_anomaly
from utils import parse_kis_ohlc

stocks_bp = Blueprint("stocks", __name__)


def _pick_metric(metric: dict, key: str, default=None):
    """
    Finnhub metric dict에서 필요한 값만 안전하게 꺼낸다.
    """
    try:
        value = metric.get(key, default)
        return value if value is not None else default
    except Exception:
        return default


def build_metrics_summary(metrics_raw: dict) -> dict:
    """
    Finnhub /stock/metric?metric=all 응답은 매우 크다.
    프론트 상세 패널에서 바로 쓸 만한 핵심 지표만 요약해서 반환한다.

    원본 구조:
    {
        "metric": {...},
        "metricType": "all",
        "series": {
            "annual": {...},
            "quarterly": {...}
        }
    }
    """
    if not isinstance(metrics_raw, dict):
        return {
            "ok": False,
            "error": "metrics unavailable",
            "metricType": None,
            "items": {},
        }

    metric = metrics_raw.get("metric") or {}
    if not isinstance(metric, dict):
        metric = {}

    items = {
        # Valuation
        "marketCapitalization": _pick_metric(metric, "marketCapitalization"),
        "enterpriseValue": _pick_metric(metric, "enterpriseValue"),
        "peTTM": _pick_metric(metric, "peTTM"),
        "forwardPE": _pick_metric(metric, "forwardPE"),
        "pb": _pick_metric(metric, "pb"),
        "psTTM": _pick_metric(metric, "psTTM"),
        "evEbitdaTTM": _pick_metric(metric, "evEbitdaTTM"),
        "evRevenueTTM": _pick_metric(metric, "evRevenueTTM"),
        "pegTTM": _pick_metric(metric, "pegTTM"),

        # Profitability
        "roeTTM": _pick_metric(metric, "roeTTM"),
        "roaTTM": _pick_metric(metric, "roaTTM"),
        "roiTTM": _pick_metric(metric, "roiTTM"),
        "grossMarginTTM": _pick_metric(metric, "grossMarginTTM"),
        "operatingMarginTTM": _pick_metric(metric, "operatingMarginTTM"),
        "netProfitMarginTTM": _pick_metric(metric, "netProfitMarginTTM"),

        # Growth
        "revenueGrowthTTMYoy": _pick_metric(metric, "revenueGrowthTTMYoy"),
        "revenueGrowthQuarterlyYoy": _pick_metric(metric, "revenueGrowthQuarterlyYoy"),
        "epsGrowthTTMYoy": _pick_metric(metric, "epsGrowthTTMYoy"),
        "epsGrowthQuarterlyYoy": _pick_metric(metric, "epsGrowthQuarterlyYoy"),

        # Per-share / dividend
        "epsTTM": _pick_metric(metric, "epsTTM"),
        "bookValuePerShareQuarterly": _pick_metric(metric, "bookValuePerShareQuarterly"),
        "cashFlowPerShareTTM": _pick_metric(metric, "cashFlowPerShareTTM"),
        "currentDividendYieldTTM": _pick_metric(metric, "currentDividendYieldTTM"),
        "dividendPerShareTTM": _pick_metric(metric, "dividendPerShareTTM"),

        # Risk / trading
        "beta": _pick_metric(metric, "beta"),
        "52WeekHigh": _pick_metric(metric, "52WeekHigh"),
        "52WeekLow": _pick_metric(metric, "52WeekLow"),
        "52WeekHighDate": _pick_metric(metric, "52WeekHighDate"),
        "52WeekLowDate": _pick_metric(metric, "52WeekLowDate"),
        "10DayAverageTradingVolume": _pick_metric(metric, "10DayAverageTradingVolume"),
        "3MonthAverageTradingVolume": _pick_metric(metric, "3MonthAverageTradingVolume"),
        "5DayPriceReturnDaily": _pick_metric(metric, "5DayPriceReturnDaily"),
        "13WeekPriceReturnDaily": _pick_metric(metric, "13WeekPriceReturnDaily"),
        "26WeekPriceReturnDaily": _pick_metric(metric, "26WeekPriceReturnDaily"),
        "52WeekPriceReturnDaily": _pick_metric(metric, "52WeekPriceReturnDaily"),
        "yearToDatePriceReturnDaily": _pick_metric(metric, "yearToDatePriceReturnDaily"),

        # Balance sheet
        "currentRatioAnnual": _pick_metric(metric, "currentRatioAnnual"),
        "quickRatioAnnual": _pick_metric(metric, "quickRatioAnnual"),
        "totalDebtToEquityAnnual": _pick_metric(metric, "totalDebt/totalEquityAnnual"),
        "longTermDebtToEquityAnnual": _pick_metric(metric, "longTermDebt/equityAnnual"),
    }

    return {
        "ok": bool(items),
        "metricType": metrics_raw.get("metricType"),
        "items": items,
    }


@stocks_bp.route("/get_stock_detail_finnhub")
@cache.cached(timeout=30, query_string=True)  # ticker/exchange별 캐시
def get_stock_detail_finnhub():
    ticker = request.args.get("ticker", "").upper().strip()
    exchange = request.args.get("exchange", "NAS").upper().strip()

    if not ticker:
        return jsonify({"error": "ticker is required"}), 400

    metrics_raw = get_metrics_raw(ticker)

    return jsonify({
        "ticker": ticker,
        "exchange": exchange,
        "price": get_quote_raw(ticker),
        "profile": get_profile_raw(ticker),

        # ✅ 전체 metrics 대신 요약본만 반환
        "metrics_summary": build_metrics_summary(metrics_raw),

        # ✅ 기존 anomaly 유지
        "anomaly": get_stock_anomaly(ticker, exchange=exchange),
    })


@stocks_bp.route("/get_stock_chart_kis")
@cache.cached(timeout=60 * 5, query_string=True)  # 5분 캐시
def get_stock_chart_kis():
    ticker = request.args.get("ticker", "").upper().strip()
    exchange = request.args.get("exchange", "NAS").upper().strip()

    if not ticker:
        return jsonify({"error": "ticker is required"}), 400

    raw = get_overseas_daily_price(ticker, exchange)
    return jsonify({"ohlc": parse_kis_ohlc(raw)})