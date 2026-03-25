#routes/health.py
from flask import Blueprint, jsonify
from utils import get_connection
from extensions import cache

health_bp = Blueprint("health", __name__)

@health_bp.route("/api/health")
def health():
    report = {"warnings": [], "stats": {}}

    try:
        conn = get_connection()
        with conn.cursor(dictionary=True) as cur:
            cur.execute("SELECT COUNT(*) AS n FROM portfolio")
            report["stats"]["portfolio_rows"] = cur.fetchone()["n"]

            cur.execute("SELECT COUNT(*) AS n FROM account_value")
            report["stats"]["account_value_rows"] = cur.fetchone()["n"]

            cur.execute("SELECT COUNT(*) AS n FROM watchlist")
            report["stats"]["watchlist_rows"] = cur.fetchone()["n"]

            cur.execute("SELECT SUM(evaluation_amount) AS s FROM portfolio")
            s = cur.fetchone()["s"] or 0
            report["stats"]["sum_evaluation_amount"] = float(s)

            cur.execute("SELECT date, total_value FROM account_value ORDER BY date DESC LIMIT 1")
            latest = cur.fetchone()
            if latest:
                report["stats"]["latest_account_value_date"] = str(latest["date"])
                report["stats"]["latest_total_value"] = float(latest["total_value"])
            else:
                report["warnings"].append("account_value 테이블이 비어있음")

            # 중복 날짜 체크
            cur.execute("""
                SELECT date, COUNT(*) AS c
                FROM account_value
                GROUP BY date
                HAVING c > 1
                LIMIT 5
            """)
            dup = cur.fetchall()
            if dup:
                report["warnings"].append(
                    f"account_value 날짜 중복 존재(최대 5개): {[str(d['date']) for d in dup]}"
                )

            # 음수 수량 체크
            cur.execute("SELECT ticker, quantity FROM portfolio WHERE quantity < 0 LIMIT 5")
            neg = cur.fetchall()
            if neg:
                report["warnings"].append(
                    f"portfolio에 음수 수량 존재(최대 5개): {[n['ticker'] for n in neg]}"
                )

        conn.close()
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    return jsonify(report)

@health_bp.route("/api/cache/clear", methods=["POST"])
def clear_cache():
    cache.clear()
    return jsonify({"ok": True, "message": "cache cleared"})
