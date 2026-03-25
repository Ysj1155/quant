import os
import pandas as pd
import re

# 경로 설정
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = BASE_DIR
PORTFOLIO_FILE = os.path.join(DATA_DIR, "portfolio_data.csv")
ACCOUNT_VALUE_FILE = os.path.join(DATA_DIR, "account_value.csv")

COLUMN_MAP = {
    "구분": "type", "계좌번호": "account_number", "종목명": "ticker",
    "평가손익": "profit_loss", "손익률": "profit_rate", "잔고수량": "quantity",
    "매입단가": "purchase_price", "매입금액": "purchase_amount",
    "평가금액": "evaluation_amount", "평가비중": "evaluation_ratio"
}


def extract_date_from_filename(filename):
    match = re.search(r"(\d{4}-\d{2}-\d{2})", filename)
    return match.group(1) if match else None


def get_all_csv_files():
    csv_files = [f for f in os.listdir(DATA_DIR) if f.endswith(".csv") and extract_date_from_filename(f)]
    return sorted(csv_files, key=extract_date_from_filename)


def get_latest_csv():
    files = get_all_csv_files()
    return os.path.join(DATA_DIR, files[-1]) if files else None


# --- 기존 app.py와 호환성을 위해 이름을 유지한 개선 함수들 ---

def process_account_value():
    """모든 원본 CSV를 읽어 account_value.csv 생성"""
    csv_files = get_all_csv_files()
    if not csv_files:
        print("⚠️ account_value용 CSV 파일이 없습니다.")
        return

    records = []
    for csv_file in csv_files:
        file_date = extract_date_from_filename(csv_file)
        file_path = os.path.join(DATA_DIR, csv_file)

        try:
            df = pd.read_csv(file_path, encoding="utf-8-sig")
            total_val = df["평가금액"].replace({',': ''}, regex=True).astype(float).sum()
            records.append({
                "date": file_date,
                "total_value": int(total_val)
            })
        except Exception as e:
            print(f"⚠️ {csv_file} 파싱 실패: {e}")

    if not records:
        print("⚠️ account_value.csv로 저장할 데이터가 없습니다.")
        return

    account_value_df = pd.DataFrame(records)
    account_value_df = account_value_df.sort_values("date").drop_duplicates(subset=["date"], keep="last")

    account_value_df.to_csv(ACCOUNT_VALUE_FILE, index=False, encoding="utf-8-sig")
    print(f"✅ account_value.csv 생성 완료 ({len(account_value_df)}건)")


def process_portfolio_data():
    """최신 CSV를 가공하여 portfolio_data.csv 생성"""
    latest_csv = get_latest_csv()
    if not latest_csv:
        return

    df = pd.read_csv(latest_csv, encoding="utf-8-sig")
    if len(df) > 3 and "구분" in df.iloc[3].values:
        df.drop(index=3, inplace=True)

    df.columns = df.columns.str.strip()
    df.rename(columns={k: v for k, v in COLUMN_MAP.items() if k in df.columns}, inplace=True)

    # UI 호환용 컬럼 추출 (매입단가 포함)
    target_cols = ["type", "account_number", "ticker", "profit_loss", "profit_rate",
                   "quantity", "purchase_price", "purchase_amount", "evaluation_amount", "evaluation_ratio"]

    portfolio_df = df[[c for c in target_cols if c in df.columns]].copy()

    # CSV 저장 (기존 방식 유지)
    portfolio_df.to_csv(PORTFOLIO_FILE, index=False, encoding="utf-8-sig")
    print(f"✅ 최신 포트폴리오 갱신 완료: {os.path.basename(latest_csv)}")