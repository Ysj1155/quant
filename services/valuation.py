#services/valuation.py
from __future__ import annotations

def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))

def fair_price_from_ev_shares(ev: float | None, shares_outstanding: float | None) -> dict:
    """
    네가 말한 방식: 적정주가 = 기업가치(EV 또는 기업가치에 준하는 값) / 발행주식수
    - 단위는 입력 데이터 단위에 따라 달라짐(보통 USD)
    """
    if ev is None or shares_outstanding is None:
        return {"ok": False, "fair_price": None, "reason": "missing ev or shares"}

    try:
        ev = float(ev)
        shares_outstanding = float(shares_outstanding)
        if shares_outstanding <= 0:
            return {"ok": False, "fair_price": None, "reason": "shares_outstanding<=0"}
        fair = ev / shares_outstanding
        # 비정상 값 방지(너무 크거나 음수 등)
        fair = clamp(fair, 0.0, 1e7)
        return {"ok": True, "fair_price": fair, "reason": None}
    except Exception:
        return {"ok": False, "fair_price": None, "reason": "parse error"}
