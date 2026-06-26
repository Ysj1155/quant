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


def ensure_portfolio_history_table(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS portfolio_history (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            snapshot_date DATE NOT NULL,
            account_number VARCHAR(32) NOT NULL,
            ticker VARCHAR(255) NOT NULL,
            quantity INT NOT NULL DEFAULT 0,
            purchase_amount BIGINT NOT NULL DEFAULT 0,
            evaluation_amount BIGINT NOT NULL DEFAULT 0,
            profit_loss BIGINT NOT NULL DEFAULT 0,
            profit_rate DOUBLE NOT NULL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            UNIQUE KEY uq_portfolio_history_snapshot_account_ticker (
                snapshot_date, account_number, ticker
            ),
            INDEX idx_portfolio_history_snapshot_date (snapshot_date),
            INDEX idx_portfolio_history_ticker (ticker)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)


def migrate_portfolio(csv_path: str = "data/portfolio_data.csv"):
    df = pd.read_csv(csv_path, encoding="utf-8-sig")

    # 1. 오늘 날짜 생성 (과거 P&L 조회를 위해 필수)
    today = datetime.now().strftime('%Y-%m-%d')

    rows_current = []
    rows_history = []

    for _, r in df.iterrows():
        ticker = r.get("ticker")
        if ticker is None or pd.isna(ticker) or str(ticker).strip() == "":
            continue

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
        rows_history.append((today,) + data[:7])  # date, account, ticker, qty, pur, eval, pnl, rate

    conn = get_connection()
    try:
        _begin(conn)
        with conn.cursor() as cur:
            if not rows_current:
                raise ValueError("portfolio_data.csv 에 유효한 행이 없습니다. portfolio 테이블 삭제를 중단합니다.")

            ensure_portfolio_history_table(cur)

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
                    snapshot_date, account_number, ticker, quantity,
                    purchase_amount, evaluation_amount,
                    profit_loss, profit_rate
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    quantity = VALUES(quantity),
                    purchase_amount = VALUES(purchase_amount),
                    evaluation_amount = VALUES(evaluation_amount),
                    profit_loss = VALUES(profit_loss),
                    profit_rate = VALUES(profit_rate)
            """, rows_history)

        conn.commit()
        print(f"portfolio migration completed: {today} (current + history)")
    except Exception as e:
        conn.rollback()
        print(f"migration error: {e}")
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
