# app.py
import os
from html import escape

from data.csv_manager import process_account_value, process_portfolio_data
from extensions import cache
from flask import Flask, render_template
from markupsafe import Markup
from routes.account_forecast import account_forecast_bp
from routes.fx_forecast import fx_forecast_bp
from routes.health import health_bp
from routes.market import market_bp
from routes.portfolio import portfolio_bp
from routes.stocks import stocks_bp
from routes.valuation import valuation_bp
from routes.watchlist import watchlist_bp

try:
    import markdown
except ModuleNotFoundError:
    markdown = None

AUTO_REFRESH_CSV = os.getenv("AUTO_REFRESH_CSV", "false").lower() in ("1", "true", "yes", "y")


def bootstrap_refresh(force: bool = False):
    """1) data/*.csv 원본 → 중간산출물 생성  2) DB 마이그레이션  3) 캐시 무효화"""
    if not force and not AUTO_REFRESH_CSV:
        print("AUTO_REFRESH_CSV=false: CSV refresh skipped")
        return

    try:
        print("CSV regeneration started")
        process_account_value()
        process_portfolio_data()
        print("CSV regeneration completed")
    except Exception as e:
        print(f"CSV regeneration error: {e}")

    try:
        print("DB migration started")
        from db.migration import migrate_account_value, migrate_portfolio

        migrate_portfolio()
        migrate_account_value()
        print("DB migration completed")
    except Exception as e:
        print(f"DB migration error: {e}")

    # 데이터가 바뀌었으니 캐시 무효화
    try:
        cache.clear()
        print("cache cleared")
    except Exception as e:
        print(f"cache clear failed: {e}")


app = Flask(__name__)

# 캐시 설정 (메모리 방식, 기본 5분)
cache.init_app(app, config={
    "CACHE_TYPE": "SimpleCache",
    "CACHE_DEFAULT_TIMEOUT": 300,
})

# 블루프린트 등록
app.register_blueprint(portfolio_bp)
app.register_blueprint(watchlist_bp)
app.register_blueprint(market_bp)
app.register_blueprint(stocks_bp)
app.register_blueprint(health_bp)
app.register_blueprint(valuation_bp)
app.register_blueprint(fx_forecast_bp)
app.register_blueprint(account_forecast_bp)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/readme")
def show_readme():
    with open("readme.md", "r", encoding="utf-8") as f:
        content = f.read()
        html = markdown.markdown(content) if markdown else f"<pre>{escape(content)}</pre>"
        return f"<div style='padding:40px;'>{Markup(html)}</div>"


@app.route("/favicon.ico")
def favicon():
    return "", 204


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Quant dashboard server")
    parser.add_argument("--refresh", action="store_true",
                        help="Regenerate CSVs and migrate DB BEFORE starting the server")
    args = parser.parse_args()

    if args.refresh:
        # debug=True 리로더에서는 자식 프로세스에서만 refresh 실행
        if os.environ.get("WERKZEUG_RUN_MAIN") == "true" or not app.debug:
            bootstrap_refresh(force=True)

    app.run(debug=True)
