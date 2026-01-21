# routes/watchlist.py
from flask import Blueprint, jsonify, request
from utils import get_connection
from extensions import cache

watchlist_bp = Blueprint("watchlist", __name__)

@watchlist_bp.route("/add_watchlist", methods=["POST"])
def add_watchlist():
    data = request.get_json() or {}
    ticker = (data.get("ticker") or "").upper().strip()
    if not ticker:
        return jsonify({"error": "티커가 유효하지 않습니다"}), 400

    try:
        conn = get_connection()
        with conn.cursor(dictionary=True) as cur:
            cur.execute("SELECT COUNT(*) AS count FROM watchlist WHERE ticker = %s", (ticker,))
            exists = cur.fetchone()["count"]
            if exists:
                conn.close()
                return jsonify({"error": "이미 등록된 티커입니다"}), 400

            cur.execute("INSERT INTO watchlist (ticker) VALUES (%s)", (ticker,))
            conn.commit()
        conn.close()

        # ✅ 변경되었으니 '조회' 캐시만 무효화
        cache.delete_memoized(get_watchlist)

        return jsonify({"message": "추가 완료"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@watchlist_bp.route("/get_watchlist")
@cache.cached(timeout=30)  # 30초 캐시
def get_watchlist():
    try:
        conn = get_connection()
        with conn.cursor(dictionary=True) as cur:
            cur.execute("SELECT ticker FROM watchlist ORDER BY created_at DESC")
            rows = cur.fetchall()
        conn.close()
        tickers = [row["ticker"] for row in rows]
        return jsonify({"watchlist": tickers})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@watchlist_bp.route("/remove_watchlist", methods=["DELETE"])
def remove_watchlist():
    data = request.get_json() or {}
    ticker = (data.get("ticker") or "").upper().strip()
    if not ticker:
        return jsonify({"error": "티커가 유효하지 않습니다"}), 400

    try:
        conn = get_connection()
        with conn.cursor(dictionary=True) as cur:
            cur.execute("DELETE FROM watchlist WHERE ticker = %s", (ticker,))
            conn.commit()
        conn.close()

        # ✅ 변경되었으니 '조회' 캐시만 무효화
        cache.delete_memoized(get_watchlist)

        return jsonify({"message": f"{ticker} 삭제됨"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500