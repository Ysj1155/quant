from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

import numpy as np
import yfinance as yf
import FinanceDataReader as fdr

from extensions import cache

SYMBOLS = {
    "SPX": {"label": "S&P 500", "symbol": "US500"},
    "NDX": {"label": "NASDAQ 100", "symbol": "NASDAQ100"},
    "DJI": {"label": "Dow Jones", "symbol": "DJI"},
    "RUT": {"label": "Russell 2000", "symbol": "RUT"},
    "VIX": {"label": "VIX", "symbol": "VIX"},
}


def _to_scalar(x):
    try:
        if x is None:
            return None
        if hasattr(x, "iloc"):
            x = x.iloc[0]
        if isinstance(x, (np.ndarray, list)):
            x = x[0]
        return float(x)
    except Exception:
        return None


def _safe_float(x, default: Optional[float] = None) -> Optional[float]:
    try:
        if x is None:
            return default
        return float(x)
    except Exception:
        return default


def _last_close_and_change_pct(symbol: str):
    try:
        df = fdr.DataReader(symbol)
        if df is None or df.empty:
            return None

        close = df["Close"].dropna()
        if len(close) < 2:
            return None

        last = float(close.iloc[-1])
        prev = float(close.iloc[-2])
        change_pct = (last - prev) / prev * 100.0 if prev != 0 else 0.0

        return {
            "last": last,
            "change_pct": change_pct,
        }
    except Exception:
        return None


@cache.memoize(timeout=60)  # 1분
def get_indices_snapshot():
    out = {}
    for k, meta in SYMBOLS.items():
        res = _last_close_and_change_pct(meta["symbol"])
        out[k] = {
            "label": meta["label"],
            "symbol": meta["symbol"],
            "ok": res is not None,
            "last": None if res is None else res["last"],
            "change_pct": None if res is None else res["change_pct"],
        }
    return out


@cache.memoize(timeout=60 * 10)  # 10분
def get_nasdaq_panic(
    window_days: int = 21,
    drop_pct: float = -3.3,
    lookback_days: int = 120,
) -> dict:
    df = yf.download(
        "^IXIC",
        period=f"{lookback_days}d",
        interval="1d",
        progress=False,
        auto_adjust=False,
    )

    if df is None or df.empty:
        return {"ok": False, "error": "no data from yfinance (^IXIC)"}

    # yfinance 반환 형태 방어:
    # 1) 일반 단일 컬럼 DataFrame
    # 2) MultiIndex 컬럼
    # 3) Close가 1열 DataFrame으로 나오는 경우
    try:
        close = df["Close"]
    except Exception:
        return {"ok": False, "error": "Close column not found from yfinance (^IXIC)"}

    # DataFrame이면 1열 Series로 축소
    if hasattr(close, "ndim") and close.ndim == 2:
        if close.shape[1] == 0:
            return {"ok": False, "error": "Close data is empty"}
        close = close.iloc[:, 0]

    close = close.dropna()

    if close is None or len(close) < window_days + 2:
        return {"ok": False, "error": f"not enough data: {0 if close is None else len(close)} rows"}

    ret = close.pct_change() * 100.0
    recent = ret.dropna().tail(window_days)

    # Series 기준으로 조건 만족 개수 계산
    drops = recent[recent <= drop_pct]
    count = int(drops.count())

    level = "panic" if count >= 4 else ("watch" if count >= 3 else "ok")
    drop_dates = [d.strftime("%Y-%m-%d") for d in drops.index.to_pydatetime()]

    last_close = float(close.iloc[-1]) if len(close) >= 1 else None
    last_daily_return_pct = float(recent.iloc[-1]) if len(recent) >= 1 else None

    return {
        "ok": True,
        "label": "NASDAQ Panic",
        "symbol": "^IXIC",
        "window_days": window_days,
        "threshold_drop_pct": drop_pct,
        "count": count,
        "level": level,
        "drop_dates": drop_dates,
        "last_date": close.index[-1].to_pydatetime().strftime("%Y-%m-%d"),
        "last_close": last_close,
        "last_daily_return_pct": last_daily_return_pct,
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


def _classify_regime(score: int) -> str:
    if score >= 65:
        return "PANIC"
    if score >= 40:
        return "RISK_OFF"
    if score >= 20:
        return "CAUTION"
    return "NORMAL"


def _append_reason(reasons: List[str], condition: bool, message: str):
    if condition:
        reasons.append(message)


@cache.memoize(timeout=60 * 5)  # 5분
def get_market_regime() -> Dict[str, Any]:
    """
    1차 룰 기반 시장 상태 분류기
    반환 예시:
    {
        "ok": True,
        "regime": "CAUTION",
        "score": 35,
        "components": {...},
        "reasons": [...],
        "updated_at": "..."
    }
    """
    snapshot = get_indices_snapshot()
    panic = get_nasdaq_panic(window_days=21, drop_pct=-3.3, lookback_days=120)

    if not snapshot:
        return {
            "ok": False,
            "error": "indices snapshot unavailable",
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

    spx = snapshot.get("SPX", {})
    ndx = snapshot.get("NDX", {})
    dji = snapshot.get("DJI", {})
    rut = snapshot.get("RUT", {})
    vix = snapshot.get("VIX", {})

    spx_chg = _safe_float(spx.get("change_pct"))
    ndx_chg = _safe_float(ndx.get("change_pct"))
    dji_chg = _safe_float(dji.get("change_pct"))
    rut_chg = _safe_float(rut.get("change_pct"))
    vix_last = _safe_float(vix.get("last"))
    vix_chg = _safe_float(vix.get("change_pct"))

    panic_count = int(panic.get("count", 0)) if panic.get("ok") else 0
    panic_level = str(panic.get("level", "unknown")) if panic else "unknown"

    score = 0
    reasons: List[str] = []

    # 1) VIX 수준
    if vix_last is not None:
        if vix_last >= 30:
            score += 35
            reasons.append(f"VIX가 매우 높은 수준입니다. ({vix_last:.2f})")
        elif vix_last >= 22:
            score += 20
            reasons.append(f"VIX가 위험 선호 둔화 구간입니다. ({vix_last:.2f})")
        elif vix_last >= 18:
            score += 10
            reasons.append(f"VIX가 경계 구간입니다. ({vix_last:.2f})")

    # 2) VIX 일간 변화
    if vix_chg is not None:
        if vix_chg >= 8:
            score += 10
            reasons.append(f"VIX가 하루 기준 크게 상승했습니다. ({vix_chg:.2f}%)")
        elif vix_chg >= 3:
            score += 5
            reasons.append(f"VIX가 상승 중입니다. ({vix_chg:.2f}%)")

    # 3) 최근 21거래일 내 나스닥 급락 횟수
    if panic.get("ok"):
        if panic_count >= 4:
            score += 30
            reasons.append(
                f"최근 {panic.get('window_days', 21)}거래일 내 나스닥 -3.3% 이하 급락이 "
                f"{panic_count}회 발생했습니다."
            )
        elif panic_count == 3:
            score += 18
            reasons.append(
                f"최근 {panic.get('window_days', 21)}거래일 내 나스닥 급락 횟수가 경계 수준입니다. "
                f"({panic_count}회)"
            )
        elif panic_count >= 1:
            score += 8
            reasons.append(
                f"최근 {panic.get('window_days', 21)}거래일 내 나스닥 급락이 누적되었습니다. "
                f"({panic_count}회)"
            )

    # 4) 주요 지수 약세 개수
    equity_changes = {
        "SPX": spx_chg,
        "NDX": ndx_chg,
        "DJI": dji_chg,
        "RUT": rut_chg,
    }
    valid_changes = {k: v for k, v in equity_changes.items() if v is not None}
    negative_count = sum(1 for v in valid_changes.values() if v < 0)
    strong_negative_count = sum(1 for v in valid_changes.values() if v <= -1.0)

    if negative_count >= 3:
        score += 15
        reasons.append("주요 지수 전반이 약세입니다.")
    elif negative_count == 2:
        score += 8
        reasons.append("주요 지수 중 절반 이상이 하락 중입니다.")

    if strong_negative_count >= 2:
        score += 12
        reasons.append("주요 지수에서 1% 이상 하락이 복수 발생했습니다.")

    # 5) 나스닥/러셀 추가 약세 가중치
    if ndx_chg is not None and ndx_chg <= -1.5:
        score += 10
        reasons.append(f"NASDAQ 100 낙폭이 큽니다. ({ndx_chg:.2f}%)")

    if rut_chg is not None and rut_chg <= -1.5:
        score += 10
        reasons.append(f"Russell 2000 약세가 큽니다. ({rut_chg:.2f}%)")

    # 6) 아주 양호한 경우 점수 일부 상쇄
    if (
        vix_last is not None and vix_last < 16
        and ndx_chg is not None and ndx_chg > 0
        and spx_chg is not None and spx_chg > 0
        and panic_count == 0
    ):
        score = max(0, score - 10)
        reasons.append("VIX가 낮고 주요 지수가 견조해 위험 점수를 일부 낮췄습니다.")

    regime = _classify_regime(score)

    # 보조 메시지
    guidance_map = {
        "NORMAL": "위험 신호가 제한적입니다.",
        "CAUTION": "공격적 신규 진입보다 변동성 확대 가능성을 점검할 구간입니다.",
        "RISK_OFF": "위험 회피 성향이 강해질 수 있어 포지션 관리가 중요합니다.",
        "PANIC": "스트레스 구간입니다. 현금 비중, 손절 기준, 변동성 노출을 우선 점검하는 편이 좋습니다.",
    }

    components = {
        "vix_last": vix_last,
        "vix_change_pct": vix_chg,
        "spx_change_pct": spx_chg,
        "ndx_change_pct": ndx_chg,
        "dji_change_pct": dji_chg,
        "rut_change_pct": rut_chg,
        "negative_index_count": negative_count,
        "strong_negative_index_count": strong_negative_count,
        "nasdaq_panic_count_21d": panic_count,
        "nasdaq_panic_level": panic_level,
    }

    return {
        "ok": True,
        "regime": regime,
        "score": score,
        "guidance": guidance_map.get(regime, ""),
        "components": components,
        "reasons": reasons,
        "raw": {
            "indices": snapshot,
            "panic": panic,
        },
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }