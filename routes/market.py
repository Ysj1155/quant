from flask import Blueprint, jsonify
from extensions import cache

import pandas as pd
import FinanceDataReader as fdr

from services.market import (
    get_indices_snapshot,
)

market_bp = Blueprint("market", __name__)

# 주요 지수 스냅샷 (1분 캐시)
@market_bp.route("/api/market/indices")
@cache.cached(timeout=60)
def market_indices():
    return jsonify(get_indices_snapshot())


# 섹터 트리맵 (1시간 캐시)
@market_bp.route("/get_treemap_data")
@cache.cached(timeout=60 * 60)
def get_treemap_data():
    sectors = {
        "Technology": "XLK",
        "Financials": "XLF",
        "Communication": "XLC",
        "Healthcare": "XLV",
        "Consumer Discretionary": "XLY",
        "Consumer Defensive": "XLP",
        "Industrials": "XLI",
        "Real Estate": "XLRE",
        "Energy": "XLE",
        "Utilities": "XLU",
        "Materials": "XLB",
    }

    sector_data = []
    for sector, ticker in sectors.items():
        df = fdr.DataReader(ticker, "2023")
        df["Change"] = ((df["Close"] - df["Close"].shift(1)) / df["Close"].shift(1)) * 100
        latest_change = float(df["Change"].iloc[-1])
        sector_data.append({"Sector": sector, "Change": latest_change})

    df_sectors = pd.DataFrame(sector_data)
    return jsonify({
        "sectors": df_sectors["Sector"].tolist(),
        "changes": df_sectors["Change"].tolist()
    })


# 환율 (6시간 캐시)
@market_bp.route("/get_exchange_rate_data")
@cache.cached(timeout=60 * 60 * 6)
def get_exchange_rate_data():
    df = fdr.DataReader("USD/KRW", "2023")[["Close"]].reset_index()
    df.rename(columns={"Close": "exchange_rate", "index": "date"}, inplace=True)
    df = df.dropna(subset=["exchange_rate"])
    df = df[~df["date"].dt.strftime("%m-%d").eq("01-01")]

    return jsonify({
        "dates": df["date"].astype(str).tolist(),
        "rates": df["exchange_rate"].tolist()
    })
