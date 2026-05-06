# services/anomaly.py
from __future__ import annotations

from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from extensions import cache
from api.kis_api import get_overseas_daily_price
from utils import parse_kis_ohlc


def _safe_float(x: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        if x is None:
            return default
        if isinstance(x, (np.ndarray, list, tuple)):
            if len(x) == 0:
                return default
            x = x[0]
        if hasattr(x, "iloc"):
            if len(x) == 0:
                return default
            x = x.iloc[0]
        v = float(x)
        if not np.isfinite(v):
            return default
        return v
    except Exception:
        return default


def _round_or_none(x: Optional[float], digits: int = 4) -> Optional[float]:
    if x is None:
        return None
    try:
        x = float(x)
        if not np.isfinite(x):
            return None
        return round(x, digits)
    except Exception:
        return None


def _level_from_score(score: float) -> str:
    if score >= 80:
        return "EXTREME"
    if score >= 60:
        return "HIGH"
    if score >= 30:
        return "MEDIUM"
    return "LOW"


def _normalize_ohlc_rows(rows: Any) -> pd.DataFrame:
    """
    parse_kis_ohlc(raw)의 반환값을 이상징후 계산용 DataFrame으로 정규화한다.

    기대 컬럼 후보:
    - date
    - open
    - high
    - low
    - close
    - volume

    일부 컬럼이 없더라도 close/date가 있으면 1차 계산은 가능하게 한다.
    """
    if rows is None:
        return pd.DataFrame()

    if isinstance(rows, pd.DataFrame):
        df = rows.copy()
    elif isinstance(rows, list):
        df = pd.DataFrame(rows)
    else:
        return pd.DataFrame()

    if df.empty:
        return pd.DataFrame()

    # 소문자 통일
    df.columns = [str(c).strip().lower() for c in df.columns]

    # 혹시 parse_kis_ohlc가 다른 이름을 쓸 경우 대비
    rename_map = {
        "stck_bsop_date": "date",
        "xymd": "date",
        "open_price": "open",
        "high_price": "high",
        "low_price": "low",
        "close_price": "close",
        "last": "close",
        "price": "close",
        "vol": "volume",
        "acml_vol": "volume",
    }
    df = df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns})

    if "date" not in df.columns or "close" not in df.columns:
        return pd.DataFrame()

    # 날짜 정규화: 20260421 / 2026-04-21 둘 다 처리
    df["date"] = df["date"].astype(str).str.strip()
    df["date"] = df["date"].apply(
        lambda x: f"{x[:4]}-{x[4:6]}-{x[6:8]}" if len(x) == 8 and x.isdigit() else x
    )
    df["date"] = pd.to_datetime(df["date"], errors="coerce")

    numeric_cols = ["open", "high", "low", "close", "volume"]
    for c in numeric_cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")

    df = df.dropna(subset=["date", "close"]).sort_values("date").reset_index(drop=True)

    # 없는 OHLC는 close로 대체해서 최소 계산 가능하게 함
    if "open" not in df.columns:
        df["open"] = df["close"]
    if "high" not in df.columns:
        df["high"] = df["close"]
    if "low" not in df.columns:
        df["low"] = df["close"]
    if "volume" not in df.columns:
        df["volume"] = np.nan

    return df


def _calc_rsi(close: pd.Series, window: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.rolling(window=window).mean()
    avg_loss = loss.rolling(window=window).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return rsi


def _prepare_kis_price_frame(ticker: str, exchange: str = "NAS") -> pd.DataFrame:
    """
    KIS 해외주식 일봉 데이터를 이용해 anomaly feature 계산용 DataFrame 생성.
    """
    try:
        raw = get_overseas_daily_price(ticker, exchange)
        rows = parse_kis_ohlc(raw)
    except Exception:
        return pd.DataFrame()

    df = _normalize_ohlc_rows(rows)
    if df.empty:
        return pd.DataFrame()

    df["return_pct"] = df["close"].pct_change() * 100.0

    df["MA5"] = df["close"].rolling(window=5).mean()
    df["MA20"] = df["close"].rolling(window=20).mean()

    df["vol_5d"] = df["return_pct"].rolling(window=5).std()
    df["vol_20d"] = df["return_pct"].rolling(window=20).std()

    df["ma20_gap_pct"] = np.where(
        df["MA20"].notna() & (df["MA20"] != 0),
        (df["close"] - df["MA20"]) / df["MA20"] * 100.0,
        np.nan,
    )

    df["RSI"] = _calc_rsi(df["close"], window=14)

    # 고저폭 기반 range feature
    df["daily_range_pct"] = np.where(
        df["close"].notna() & (df["close"] != 0),
        (df["high"] - df["low"]) / df["close"] * 100.0,
        np.nan,
    )
    df["range_5d"] = df["daily_range_pct"].rolling(window=5).mean()
    df["range_20d"] = df["daily_range_pct"].rolling(window=20).mean()

    # 거래량 feature: volume이 있을 때만 의미 있음
    df["volume_ma20"] = df["volume"].rolling(window=20).mean()
    df["volume_ratio"] = np.where(
        df["volume_ma20"].notna() & (df["volume_ma20"] != 0),
        df["volume"] / df["volume_ma20"],
        np.nan,
    )

    return df.dropna(subset=["close"]).reset_index(drop=True)


def _score_return_z(return_z_abs: Optional[float]) -> tuple[int, List[str]]:
    score = 0
    reasons: List[str] = []

    if return_z_abs is None:
        return score, reasons

    if return_z_abs >= 3.0:
        score += 30
        reasons.append(f"최근 일간 수익률이 과거 패턴 대비 매우 크게 벗어났습니다. (z={return_z_abs:.2f})")
    elif return_z_abs >= 2.0:
        score += 20
        reasons.append(f"최근 일간 수익률이 평소보다 크게 벗어났습니다. (z={return_z_abs:.2f})")
    elif return_z_abs >= 1.5:
        score += 10
        reasons.append(f"최근 일간 수익률이 평소보다 다소 크게 움직였습니다. (z={return_z_abs:.2f})")

    return score, reasons


def _score_vol_ratio(vol_ratio: Optional[float]) -> tuple[int, List[str]]:
    score = 0
    reasons: List[str] = []

    if vol_ratio is None:
        return score, reasons

    if vol_ratio >= 2.5:
        score += 25
        reasons.append(f"최근 5일 변동성이 20일 기준 대비 크게 확대되었습니다. ({vol_ratio:.2f}배)")
    elif vol_ratio >= 1.8:
        score += 18
        reasons.append(f"최근 변동성이 평소보다 확대되었습니다. ({vol_ratio:.2f}배)")
    elif vol_ratio >= 1.4:
        score += 10
        reasons.append(f"단기 변동성이 다소 커졌습니다. ({vol_ratio:.2f}배)")

    return score, reasons


def _score_ma_gap(ma20_gap_abs: Optional[float], ma20_gap_pct: Optional[float]) -> tuple[int, List[str]]:
    score = 0
    reasons: List[str] = []

    if ma20_gap_abs is None or ma20_gap_pct is None:
        return score, reasons

    direction = "상방" if ma20_gap_pct > 0 else "하방"

    if ma20_gap_abs >= 15:
        score += 20
        reasons.append(f"20일 이동평균 대비 {direction} 이격이 매우 큽니다. ({ma20_gap_pct:.2f}%)")
    elif ma20_gap_abs >= 10:
        score += 14
        reasons.append(f"20일 이동평균 대비 {direction} 이격이 큽니다. ({ma20_gap_pct:.2f}%)")
    elif ma20_gap_abs >= 6:
        score += 8
        reasons.append(f"20일 이동평균 대비 {direction} 이격이 관찰됩니다. ({ma20_gap_pct:.2f}%)")

    return score, reasons


def _score_rsi(rsi: Optional[float]) -> tuple[int, List[str]]:
    score = 0
    reasons: List[str] = []

    if rsi is None:
        return score, reasons

    if rsi >= 80:
        score += 15
        reasons.append(f"RSI가 강한 과매수 구간입니다. ({rsi:.2f})")
    elif rsi >= 70:
        score += 10
        reasons.append(f"RSI가 과매수권에 진입했습니다. ({rsi:.2f})")
    elif rsi <= 20:
        score += 15
        reasons.append(f"RSI가 강한 과매도 구간입니다. ({rsi:.2f})")
    elif rsi <= 30:
        score += 10
        reasons.append(f"RSI가 과매도권에 진입했습니다. ({rsi:.2f})")

    return score, reasons


def _score_range_ratio(range_ratio: Optional[float]) -> tuple[int, List[str]]:
    score = 0
    reasons: List[str] = []

    if range_ratio is None:
        return score, reasons

    if range_ratio >= 2.2:
        score += 15
        reasons.append(f"최근 고저폭이 평소보다 크게 확대되었습니다. ({range_ratio:.2f}배)")
    elif range_ratio >= 1.6:
        score += 10
        reasons.append(f"최근 장중 변동폭이 다소 커졌습니다. ({range_ratio:.2f}배)")

    return score, reasons


def _score_volume_ratio(volume_ratio: Optional[float]) -> tuple[int, List[str]]:
    score = 0
    reasons: List[str] = []

    if volume_ratio is None:
        return score, reasons

    if volume_ratio >= 3.0:
        score += 20
        reasons.append(f"거래량이 20일 평균 대비 크게 증가했습니다. ({volume_ratio:.2f}배)")
    elif volume_ratio >= 2.0:
        score += 12
        reasons.append(f"거래량이 평소보다 증가했습니다. ({volume_ratio:.2f}배)")
    elif volume_ratio >= 1.5:
        score += 6
        reasons.append(f"거래량 증가가 관찰됩니다. ({volume_ratio:.2f}배)")

    return score, reasons


@cache.memoize(timeout=60 * 5)
def get_stock_anomaly(ticker: str, exchange: str = "NAS") -> Dict[str, Any]:
    """
    종목 단위 이상 징후 탐지기 1차 버전. KIS 일봉 기반.

    판단 요소:
    - 최근 수익률 z-score
    - 단기/중기 변동성 비율
    - 20일 이동평균 이격
    - RSI
    - 고저폭 확대
    - 거래량 비율, KIS 데이터에 volume이 있을 경우
    """
    ticker = (ticker or "").upper().strip()
    exchange = (exchange or "NAS").upper().strip()

    if not ticker:
        return {
            "ok": False,
            "error": "ticker is empty",
            "score": None,
            "level": "UNKNOWN",
            "features": {},
            "reasons": [],
        }

    df = _prepare_kis_price_frame(ticker, exchange=exchange)

    min_rows = 30
    if df.empty or len(df) < min_rows:
        return {
            "ok": False,
            "ticker": ticker,
            "exchange": exchange,
            "error": f"not enough KIS OHLC data: {len(df) if not df.empty else 0} rows",
            "score": None,
            "level": "UNKNOWN",
            "features": {},
            "reasons": [],
            "method": "kis_ohlc_statistical_v1",
        }

    last = df.iloc[-1]

    close = _safe_float(last.get("close"))
    open_price = _safe_float(last.get("open"))
    high = _safe_float(last.get("high"))
    low = _safe_float(last.get("low"))
    volume = _safe_float(last.get("volume"))

    try:
        last_date = pd.to_datetime(last.get("date")).strftime("%Y-%m-%d")
    except Exception:
        last_date = None

    last_return_pct = _safe_float(last.get("return_pct"))
    ma5 = _safe_float(last.get("MA5"))
    ma20 = _safe_float(last.get("MA20"))
    ma20_gap_pct = _safe_float(last.get("ma20_gap_pct"))
    rsi = _safe_float(last.get("RSI"))

    vol_5d = _safe_float(last.get("vol_5d"))
    vol_20d = _safe_float(last.get("vol_20d"))

    daily_range_pct = _safe_float(last.get("daily_range_pct"))
    range_5d = _safe_float(last.get("range_5d"))
    range_20d = _safe_float(last.get("range_20d"))

    volume_ma20 = _safe_float(last.get("volume_ma20"))
    volume_ratio = _safe_float(last.get("volume_ratio"))

    # 최근 60거래일 기준 return z-score
    ret_series = pd.to_numeric(df["return_pct"], errors="coerce").dropna()
    recent_ret = ret_series.tail(60)

    return_z = None
    return_z_abs = None
    if len(recent_ret) >= 20 and last_return_pct is not None:
        mean_ret = float(recent_ret.mean())
        std_ret = float(recent_ret.std())
        if std_ret > 1e-9:
            return_z = (last_return_pct - mean_ret) / std_ret
            return_z_abs = abs(return_z)

    vol_ratio = None
    if vol_5d is not None and vol_20d is not None and vol_20d > 1e-9:
        vol_ratio = vol_5d / vol_20d

    range_ratio = None
    if range_5d is not None and range_20d is not None and range_20d > 1e-9:
        range_ratio = range_5d / range_20d

    ma20_gap_abs = abs(ma20_gap_pct) if ma20_gap_pct is not None else None

    score = 0
    reasons: List[str] = []

    for part_score, part_reasons in [
        _score_return_z(return_z_abs),
        _score_vol_ratio(vol_ratio),
        _score_ma_gap(ma20_gap_abs, ma20_gap_pct),
        _score_rsi(rsi),
        _score_range_ratio(range_ratio),
        _score_volume_ratio(volume_ratio),
    ]:
        score += part_score
        reasons.extend(part_reasons)

    score = int(max(0, min(100, score)))
    level = _level_from_score(score)

    if not reasons:
        reasons.append("최근 가격 흐름은 통계적으로 평소 범위에 가깝습니다.")

    return {
        "ok": True,
        "ticker": ticker,
        "exchange": exchange,
        "last_date": last_date,
        "score": score,
        "level": level,
        "features": {
            "open": _round_or_none(open_price, 4),
            "high": _round_or_none(high, 4),
            "low": _round_or_none(low, 4),
            "close": _round_or_none(close, 4),
            "volume": _round_or_none(volume, 4),
            "last_return_pct": _round_or_none(last_return_pct, 4),
            "return_z": _round_or_none(return_z, 4),
            "return_z_abs": _round_or_none(return_z_abs, 4),
            "vol_5d": _round_or_none(vol_5d, 4),
            "vol_20d": _round_or_none(vol_20d, 4),
            "vol_ratio": _round_or_none(vol_ratio, 4),
            "daily_range_pct": _round_or_none(daily_range_pct, 4),
            "range_5d": _round_or_none(range_5d, 4),
            "range_20d": _round_or_none(range_20d, 4),
            "range_ratio": _round_or_none(range_ratio, 4),
            "ma5": _round_or_none(ma5, 4),
            "ma20": _round_or_none(ma20, 4),
            "ma20_gap_pct": _round_or_none(ma20_gap_pct, 4),
            "rsi": _round_or_none(rsi, 4),
            "volume_ma20": _round_or_none(volume_ma20, 4),
            "volume_ratio": _round_or_none(volume_ratio, 4),
        },
        "reasons": reasons,
        "method": "kis_ohlc_statistical_v1",
    }