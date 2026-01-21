#db/migration.py
import pandas as pd
from datetime import datetime
from utils import get_connection


def _begin(conn):
    """mysql-connector / pymysql 둘 다 대응"""
    try:
        conn.start_transaction()
    except Exception:
        try:
            conn.begin()
        except Exception:
            # 일부 드라이버는 autocommit=False로만 트랜잭션이 잡힘
            pass


def clean_int(val, default=0) -> int:
    """'1,234', '12.3%', NaN, '' 등을 안전하게 int로."""
    if val is None or (isinstance(val, float) and pd.isna(val)) or (isinstance(val, str) and val.strip() == ""):
        return default
    s = str(val).replace(",", "").replace("%", "").strip()
    if s == "" or s.lower() == "nan":
        return default
    try:
        return int(float(s))
    except Exception:
        return default


def clean_float(val, default=0.0) -> float:
    """'12.3%', NaN, '' 등을 안전하게 float로."""
    if val is None or (isinstance(val, float) and pd.isna(val)) or (isinstance(val, str) and val.strip() == ""):
        return default
    s = str(val).replace(",", "").replace("%", "").strip()
    if s == "" or s.lower() == "nan":
        return default
    try:
        return float(s)
    except Exception:
        return default


def migrate_portfolio(csv_path: str = "data/portfolio_data.csv"):
    df = pd.read_csv(csv_path, encoding="utf-8-sig")

    # 1. 오늘 날짜 생성 (과거 P&L 조회를 위해 필수)
    today = datetime.now().strftime('%Y-%m-%d')

    rows_current = []
    rows_history = []

    for _, r in df.iterrows():
        ticker = r.get("ticker")
        if not ticker: continue

        data = (
            r.get("account_number"),
            ticker,
            clean_int(r.get("quantity")),
            clean_int(r.get("purchase_amount")),
            clean_int(r.get("evaluation_amount")),
            clean_int(r.get("profit_loss")),
            clean_float(r.get("profit_rate")),
            clean_float(r.get("evaluation_ratio")),
        )
        rows_current.append(data)

        # 히스토리용 데이터 (날짜 추가)
        rows_history.append((today,) + data[1:7])  # date, ticker, qty, pur, eval, pnl, rate

    conn = get_connection()
    try:
        _begin(conn)
        with conn.cursor() as cur:
            # [성능 개선 1] 현재 잔고는 기존처럼 유지하되 트랜잭션 보장
            cur.execute("DELETE FROM portfolio")
            cur.executemany("""
                INSERT INTO portfolio (
                    account_number, ticker, quantity,
                    purchase_amount, evaluation_amount,
                    profit_loss, profit_rate, evaluation_ratio
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, rows_current)

            # [성능 개선 2] 히스토리 테이블에 누적 (Upsert 로직)
            # 오늘 이미 마이그레이션 했다면 덮어쓰기
            cur.executemany("""
                INSERT INTO portfolio_history (
                    snapshot_date, ticker, quantity, 
                    purchase_amount, evaluation_amount, 
                    profit_loss, profit_rate
                ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    quantity = VALUES(quantity),
                    evaluation_amount = VALUES(evaluation_amount),
                    profit_loss = VALUES(profit_loss),
                    profit_rate = VALUES(profit_rate)
            """, rows_history)

        conn.commit()
        print(f"✅ {today} 포트폴리오 마이그레이션 완료 (현재 + 히스토리)")
    except Exception as e:
        conn.rollback()
        print(f"❌ 오류 발생: {e}")
        raise
    finally:
        conn.close()


def migrate_account_value(csv_path: str = "data/account_value.csv"):
    """계좌 총액 히스토리는 중요하므로 DELETE 대신 Upsert 사용"""
    df = pd.read_csv(csv_path, encoding="utf-8-sig")
    rows = [(r.get("date"), clean_int(r.get("total_value"))) for _, r in df.iterrows()]

    conn = get_connection()
    try:
        _begin(conn)
        with conn.cursor() as cur:
            # 날짜가 겹치면 업데이트, 없으면 삽입 (데이터 누적)
            cur.executemany("""
                INSERT INTO account_value (date, total_value) 
                VALUES (%s, %s)
                ON DUPLICATE KEY UPDATE total_value = VALUES(total_value)
            """, rows)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()