from __future__ import annotations

import io
import re
import zipfile
from datetime import datetime
from typing import Dict, Iterable, List, Optional

import pandas as pd
import requests

from data.csv_manager import DATA_DIR, read_csv_smart, to_float

KR_SECURITY_MASTER_FILE = DATA_DIR / "kr_security_master.csv"

MASTER_SOURCES = {
    "KOSPI": {
        "url": "https://new.real.download.dws.co.kr/common/master/kospi_code.mst.zip",
        "filename": "kospi_code.mst",
        "tail_width": 228,
        "name_column": "한글명",
        "base_price_column": "기준가",
        "listed_date_column": "상장일자",
        "market_cap_column": "시가총액",
        "tail_widths": [
            2, 1, 4, 4, 4, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1,
            1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 9, 5, 5, 1, 1, 1, 2, 1, 1,
            1, 2, 2, 2, 3, 1, 3, 12, 12, 8, 15, 21, 2, 7, 1, 1, 1, 1, 1,
            9, 9, 9, 5, 9, 8, 9, 3, 1, 1, 1,
        ],
        "tail_columns": [
            "그룹코드", "시가총액규모", "지수업종대분류", "지수업종중분류", "지수업종소분류", "제조업",
            "저유동성", "지배구조지수종목", "KOSPI200섹터업종", "KOSPI100", "KOSPI50", "KRX",
            "ETP", "ELW발행", "KRX100", "KRX자동차", "KRX반도체", "KRX바이오", "KRX은행", "SPAC",
            "KRX에너지화학", "KRX철강", "단기과열", "KRX미디어통신", "KRX건설", "Non1", "KRX증권",
            "KRX선박", "KRX섹터_보험", "KRX섹터_운송", "SRI", "기준가", "매매수량단위", "시간외수량단위",
            "거래정지", "정리매매", "관리종목", "시장경고", "경고예고", "불성실공시", "우회상장",
            "락구분", "액면변경", "증자구분", "증거금비율", "신용가능", "신용기간", "전일거래량",
            "액면가", "상장일자", "상장주수", "자본금", "결산월", "공모가", "우선주", "공매도과열",
            "이상급등", "KRX300", "KOSPI", "매출액", "영업이익", "경상이익", "당기순이익", "ROE",
            "기준년월", "시가총액", "그룹사코드", "회사신용한도초과", "담보대출가능", "대주가능",
        ],
    },
    "KOSDAQ": {
        "url": "https://new.real.download.dws.co.kr/common/master/kosdaq_code.mst.zip",
        "filename": "kosdaq_code.mst",
        "tail_width": 222,
        "name_column": "한글종목명",
        "base_price_column": "주식 기준가",
        "listed_date_column": "주식 상장 일자",
        "market_cap_column": "전일기준 시가총액 (억)",
        "tail_widths": [
            2, 1, 4, 4, 4, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1,
            1, 1, 1, 1, 1, 1, 9, 5, 5, 1, 1, 1, 2, 1, 1, 1, 2, 2, 2, 3,
            1, 3, 12, 12, 8, 15, 21, 2, 7, 1, 1, 1, 1, 9, 9, 9, 5, 9, 8,
            9, 3, 1, 1, 1,
        ],
        "tail_columns": [
            "증권그룹구분코드", "시가총액 규모 구분 코드 유가", "지수업종 대분류 코드", "지수 업종 중분류 코드",
            "지수업종 소분류 코드", "벤처기업 여부 (Y/N)", "저유동성종목 여부", "KRX 종목 여부",
            "ETP 상품구분코드", "KRX100 종목 여부 (Y/N)", "KRX 자동차 여부", "KRX 반도체 여부",
            "KRX 바이오 여부", "KRX 은행 여부", "기업인수목적회사여부", "KRX 에너지 화학 여부",
            "KRX 철강 여부", "단기과열종목구분코드", "KRX 미디어 통신 여부", "KRX 건설 여부",
            "(코스닥)투자주의환기종목여부", "KRX 증권 구분", "KRX 선박 구분", "KRX섹터지수 보험여부",
            "KRX섹터지수 운송여부", "KOSDAQ150지수여부 (Y,N)", "주식 기준가", "정규 시장 매매 수량 단위",
            "시간외 시장 매매 수량 단위", "거래정지 여부", "정리매매 여부", "관리 종목 여부",
            "시장 경고 구분 코드", "시장 경고위험 예고 여부", "불성실 공시 여부", "우회 상장 여부",
            "락구분 코드", "액면가 변경 구분 코드", "증자 구분 코드", "증거금 비율", "신용주문 가능 여부",
            "신용기간", "전일 거래량", "주식 액면가", "주식 상장 일자", "상장 주수(천)", "자본금",
            "결산 월", "공모 가격", "우선주 구분 코드", "공매도과열종목여부", "이상급등종목여부",
            "KRX300 종목 여부 (Y/N)", "매출액", "영업이익", "경상이익", "단기순이익", "ROE(자기자본이익률)",
            "기준년월", "전일기준 시가총액 (억)", "그룹사 코드", "회사신용한도초과여부", "담보대출가능여부",
            "대주가능여부",
        ],
    },
    "KONEX": {
        "url": "https://new.real.download.dws.co.kr/common/master/konex_code.mst.zip",
        "filename": "konex_code.mst",
        "tail_width": 184,
    },
}

MASTER_COLUMNS = [
    "market",
    "code",
    "standard_code",
    "name",
    "normalized_name",
    "base_price",
    "listed_date",
    "market_cap",
    "source",
    "updated_at",
]


def normalize_kr_name(value: object) -> str:
    text = str(value or "").strip().casefold()
    text = re.sub(r"\s+", "", text)
    text = re.sub(r"\(.*?\)", "", text)
    return text


def _slice_fixed_width(text: str, widths: Iterable[int], columns: Iterable[str]) -> Dict[str, str]:
    values: Dict[str, str] = {}
    pos = 0
    for width, column in zip(widths, columns):
        values[column] = text[pos:pos + width].strip()
        pos += width
    return values


def _download_master_text(source: Dict) -> str:
    response = requests.get(source["url"], timeout=20)
    response.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(response.content)) as zipped:
        with zipped.open(source["filename"]) as handle:
            return handle.read().decode("cp949", errors="replace")


def _parse_kis_market(market: str, source: Dict, text: str, updated_at: str) -> pd.DataFrame:
    rows: List[Dict] = []
    for raw_line in text.splitlines():
        row = raw_line.rstrip("\n\r")
        if not row:
            continue

        if market == "KONEX":
            code = row[0:9].strip()
            standard_code = row[9:21].strip()
            name = row[21:-184].strip()
            base_price = row[-182:-173].strip()
            listed_date = row[-118:-110].strip()
            market_cap = row[-12:-3].strip()
        else:
            tail_width = sum(source["tail_widths"])
            head = row[:len(row) - tail_width]
            tail = row[-tail_width:]
            code = head[0:9].strip()
            standard_code = head[9:21].strip()
            name = head[21:].strip()
            tail_values = _slice_fixed_width(tail, source["tail_widths"], source["tail_columns"])
            base_price = tail_values.get(source["base_price_column"], "")
            listed_date = tail_values.get(source["listed_date_column"], "")
            market_cap = tail_values.get(source["market_cap_column"], "")

        if not code or not name:
            continue

        rows.append({
            "market": market,
            "code": code,
            "standard_code": standard_code,
            "name": name,
            "normalized_name": normalize_kr_name(name),
            "base_price": to_float(base_price),
            "listed_date": listed_date,
            "market_cap": to_float(market_cap),
            "source": "kis_master",
            "updated_at": updated_at,
        })

    return pd.DataFrame(rows, columns=MASTER_COLUMNS)


def refresh_kr_security_master() -> Dict:
    updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    frames = []
    errors = []

    for market, source in MASTER_SOURCES.items():
        try:
            text = _download_master_text(source)
            frames.append(_parse_kis_market(market, source, text, updated_at))
        except Exception as exc:
            errors.append({"market": market, "error": str(exc)})

    if not frames:
        raise RuntimeError(f"failed to refresh Korean security master: {errors}")

    master = pd.concat(frames, ignore_index=True)
    master = master.drop_duplicates(subset=["market", "code"], keep="last")
    master = master.sort_values(["market", "code"]).reset_index(drop=True)
    master.to_csv(KR_SECURITY_MASTER_FILE, index=False, encoding="utf-8-sig")

    return {
        "ok": len(errors) == 0,
        "path": str(KR_SECURITY_MASTER_FILE),
        "count": int(len(master)),
        "markets": sorted(master["market"].unique().tolist()),
        "updated_at": updated_at,
        "errors": errors,
    }


def load_kr_security_master() -> pd.DataFrame:
    if not KR_SECURITY_MASTER_FILE.exists():
        return pd.DataFrame(columns=MASTER_COLUMNS)

    df = read_csv_smart(KR_SECURITY_MASTER_FILE)
    if df.empty:
        return pd.DataFrame(columns=MASTER_COLUMNS)

    out = df.copy()
    for column in MASTER_COLUMNS:
        if column not in out.columns:
            out[column] = ""

    text_columns = ["market", "code", "standard_code", "name", "normalized_name", "source", "updated_at"]
    for column in text_columns:
        out[column] = out[column].fillna("").astype(str).str.strip()

    if "normalized_name" in out.columns:
        missing_norm = out["normalized_name"].astype(str).str.strip() == ""
        out.loc[missing_norm, "normalized_name"] = out.loc[missing_norm, "name"].apply(normalize_kr_name)

    out["base_price"] = out["base_price"].apply(to_float)
    out["market_cap"] = out["market_cap"].apply(to_float)
    return out[MASTER_COLUMNS]


def get_kr_security_master_summary() -> Dict:
    df = load_kr_security_master()
    if df.empty:
        return {
            "exists": KR_SECURITY_MASTER_FILE.exists(),
            "path": str(KR_SECURITY_MASTER_FILE),
            "count": 0,
            "markets": [],
            "updated_at": None,
        }

    updated_at = df["updated_at"].dropna().astype(str).max() if "updated_at" in df.columns else None
    return {
        "exists": True,
        "path": str(KR_SECURITY_MASTER_FILE),
        "count": int(len(df)),
        "markets": sorted(df["market"].dropna().unique().tolist()),
        "updated_at": updated_at,
    }


def find_kr_security_candidates(name: str, limit: int = 5) -> List[Dict]:
    df = load_kr_security_master()
    if df.empty:
        return []

    normalized = normalize_kr_name(name)
    if not normalized:
        return []

    exact = df[df["normalized_name"] == normalized].copy()
    if exact.empty:
        contains = df[df["normalized_name"].str.contains(re.escape(normalized), na=False)].copy()
        if contains.empty:
            contains = df[df["name"].astype(str).str.contains(str(name).strip(), case=False, na=False, regex=False)].copy()
        matches = contains
    else:
        matches = exact

    if matches.empty:
        return []

    matches = matches.sort_values(["market", "code"]).head(limit)
    return matches.to_dict("records")
