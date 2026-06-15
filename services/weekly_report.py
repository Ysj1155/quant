from __future__ import annotations

from typing import Dict, List, Optional

from extensions import cache
from services.data_quality import build_data_quality_summary
from services.performance import build_performance_summary
from services.report_files import (
    list_report_files,
    read_report_file,
    save_report_markdown,
    update_report_file,
)
from services.report_markdown import krw as _krw
from services.report_markdown import pct as _pct
from services.report_markdown import render_period_report_markdown
from services.risk import build_risk_summary
from services.timeline import build_investment_timeline

EVENT_LABELS = {
    "initial_position": "초기 보유",
    "buy_open": "신규 진입",
    "buy_add": "추가 매수",
    "sell_partial": "일부 매도",
    "sell_full": "전량 매도",
}


def _signed_direction(value) -> str:
    if value is None:
        return "변화가 계산되지 않았습니다"
    if float(value) > 0:
        return "증가했습니다"
    if float(value) < 0:
        return "감소했습니다"
    return "변화가 없었습니다"


def _top_items(rows: List[Dict], limit: int = 3) -> List[Dict]:
    return rows[:limit] if isinstance(rows, list) else []


def _event_highlights(events: List[Dict], limit: int = 5) -> List[Dict]:
    highlights = []
    for event in events[:limit]:
        event_type = event.get("event_type", "")
        highlights.append({
            "date": event.get("date"),
            "label": EVENT_LABELS.get(event_type, event_type),
            "name": event.get("name"),
            "quantity_delta": event.get("quantity_delta"),
            "cash_flow_est": event.get("cash_flow_est"),
            "confidence": event.get("confidence"),
            "reason": event.get("reason"),
        })
    return highlights


def _quality_highlights(quality: Dict, limit: int = 5) -> List[Dict]:
    checks = quality.get("checks") or []
    issues = [item for item in checks if item.get("severity") in ("high", "warning")]
    if not issues:
        return [{
            "severity": "ok",
            "title": "데이터 품질",
            "message": "이번 리포트 생성에 사용할 주요 품질 점검에서 큰 이슈는 발견되지 않았습니다.",
        }]
    return issues[:limit]


def _build_narrative(period_label: str, performance: Dict, timeline: Dict, risk: Dict, quality: Dict) -> List[str]:
    summary = performance.get("summary") or {}
    advanced = performance.get("advanced_returns") or {}
    events_summary = timeline.get("summary") or {}
    concentration = risk.get("concentration") or {}
    quality_summary = quality.get("summary") or {}

    change = summary.get("period_change")
    change_pct = summary.get("period_change_pct")
    start_value = advanced.get("start_account_value")
    end_value = advanced.get("end_account_value")

    lines = []
    if start_value is not None and end_value is not None:
        lines.append(
            f"{period_label} 동안 계좌 평가액은 {_krw(start_value)}에서 {_krw(end_value)}로 "
            f"{_krw(change)} {_signed_direction(change)} 기간 변화율은 {_pct(change_pct)}입니다."
        )
    else:
        lines.append(f"{period_label} 동안 계좌 평가액 변화 계산에 필요한 관측치가 부족합니다.")

    simple_return = advanced.get("simple_return_pct")
    investment_twr = advanced.get("investment_twr_pct")
    lines.append(
        f"성과 지표로 보면 단순수익률은 {_pct(simple_return)}, "
        f"매수/매도 흐름을 조정한 투자노출 TWR은 {_pct(investment_twr)}입니다."
    )

    counts = events_summary.get("counts") or {}
    buy_count = int(counts.get("buy_open") or 0) + int(counts.get("buy_add") or 0)
    sell_count = int(counts.get("sell_partial") or 0) + int(counts.get("sell_full") or 0)
    total_events = int(events_summary.get("total") or 0)
    lines.append(
        f"이 기간에는 투자 이벤트 {total_events}건이 감지되었습니다. "
        f"추정 매수 {buy_count}건, 추정 매도 {sell_count}건입니다."
    )

    top1 = concentration.get("top1_weight_pct")
    top3 = concentration.get("top3_weight_pct")
    lines.append(
        f"현재 포트폴리오 집중도는 최대 종목 {_pct(top1)}, 상위 3개 종목 {_pct(top3)}입니다."
    )

    score = quality_summary.get("score")
    issue_count = quality_summary.get("issue_count")
    lines.append(
        f"데이터 품질 점수는 {score if score is not None else '-'}점이며, "
        f"확인할 품질 항목은 {issue_count if issue_count is not None else 0}개입니다."
    )

    return lines


def _review_questions(performance: Dict, timeline: Dict, risk: Dict, quality: Dict) -> List[str]:
    questions = []
    contributors = performance.get("contributors") or {}
    losers = contributors.get("top_losers") or []
    gainers = contributors.get("top_gainers") or []
    concentration = risk.get("concentration") or {}
    events_summary = timeline.get("summary") or {}
    quality_summary = quality.get("summary") or {}

    if gainers:
        questions.append(f"이번 성과가 {gainers[0].get('name')} 같은 상위 기여 종목에 얼마나 의존했는가?")
    if losers:
        questions.append(f"{losers[0].get('name')}의 손실은 기존 보유 판단과 어떻게 달라졌는가?")
    if float(concentration.get("top3_weight_pct") or 0.0) >= 50:
        questions.append("상위 3개 종목 비중이 커진 이유는 의도한 집중인지, 가격 변화의 결과인지 확인했는가?")
    if int(events_summary.get("total") or 0) > 0:
        questions.append("이번 기간의 매수/매도 이벤트 이후 포트폴리오 구조는 더 설명 가능해졌는가?")
    if int(quality_summary.get("issue_count") or 0) > 0:
        questions.append("이번 리포트에서 확인이 필요한 데이터 품질 항목이 성과 해석에 영향을 주는가?")

    if not questions:
        questions.append("이번 기간의 성과는 반복 가능한 판단에서 나왔는가, 일시적인 가격 변화에서 나왔는가?")
    questions.append("다음 리포트에서 비교하고 싶은 핵심 지표는 무엇인가?")
    return questions[:5]


@cache.memoize(timeout=60)
def build_weekly_report_context(
    period: str = "1w",
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> Dict:
    performance = build_performance_summary(period=period, start_date=start_date, end_date=end_date)
    if not performance.get("ok"):
        return {"ok": False, "error": performance.get("error") or "performance summary unavailable"}

    period_info = performance.get("period") or {}
    resolved_start = period_info.get("start_date") or start_date
    resolved_end = period_info.get("end_date") or end_date
    child_period = "custom" if resolved_start or resolved_end else period

    risk = build_risk_summary(period=child_period, start_date=resolved_start, end_date=resolved_end)
    if not risk.get("ok"):
        return {"ok": False, "error": risk.get("error") or "risk summary unavailable"}

    timeline = build_investment_timeline(
        limit=20,
        include_initial=False,
        full_scan=True,
        period=child_period,
        start_date=resolved_start,
        end_date=resolved_end,
    )
    quality = build_data_quality_summary()

    return {
        "ok": True,
        "period_info": period_info,
        "performance": performance,
        "risk": risk,
        "timeline": timeline,
        "quality": quality,
    }


def _performance_payload(performance: Dict) -> Dict:
    summary = performance.get("summary") or {}
    advanced = performance.get("advanced_returns") or {}
    contributors = performance.get("contributors") or {}
    evidence_cards = performance.get("evidence_cards") or []
    return {
        "simple_return_pct": advanced.get("simple_return_pct"),
        "account_twr_pct": advanced.get("account_twr_pct"),
        "investment_twr_pct": advanced.get("investment_twr_pct"),
        "investment_irr_annual_pct": advanced.get("investment_irr_annual_pct"),
        "start_account_value": advanced.get("start_account_value"),
        "end_account_value": advanced.get("end_account_value"),
        "period_change": summary.get("period_change"),
        "period_change_pct": summary.get("period_change_pct"),
        "top_gainers": _top_items(contributors.get("top_gainers") or []),
        "top_losers": _top_items(contributors.get("top_losers") or []),
        "evidence_cards": _top_items(evidence_cards, 4),
        "method_note": advanced.get("method_note"),
    }


@cache.memoize(timeout=60)
def build_weekly_report(
    period: str = "1w",
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> Dict:
    context = build_weekly_report_context(period=period, start_date=start_date, end_date=end_date)
    if not context.get("ok"):
        return context

    performance = context["performance"]
    risk = context["risk"]
    timeline = context["timeline"]
    quality = context["quality"]
    period_info = context["period_info"]

    period_label = period_info.get("label") or "선택 기간"
    summary = performance.get("summary") or {}
    advanced = performance.get("advanced_returns") or {}
    risk_summary = risk.get("summary") or {}
    account_risk = risk.get("account_risk") or {}
    timeline_summary = timeline.get("summary") or {}
    quality_summary = quality.get("summary") or {}

    return {
        "ok": True,
        "period": period_info,
        "title": f"{period_label} 회고 리포트",
        "generated_from": "csv_snapshot",
        "summary_cards": [
            {
                "label": "기간 변화",
                "value": _krw(summary.get("period_change")),
                "sub": _pct(summary.get("period_change_pct")),
                "signed": summary.get("period_change"),
            },
            {
                "label": "투자노출 TWR",
                "value": _pct(advanced.get("investment_twr_pct")),
                "sub": "매수/매도 흐름 조정",
                "signed": advanced.get("investment_twr_pct"),
            },
            {
                "label": "투자 이벤트",
                "value": f"{int(timeline_summary.get('total') or 0):,}건",
                "sub": f"순현금흐름 {_krw(timeline_summary.get('net_cash_flow_est'))}",
            },
            {
                "label": "데이터 품질",
                "value": f"{quality_summary.get('score', '-')}점",
                "sub": f"확인 항목 {quality_summary.get('issue_count', 0)}개",
            },
        ],
        "narrative": _build_narrative(period_label, performance, timeline, risk, quality),
        "performance": _performance_payload(performance),
        "evidence_cards": _top_items(performance.get("evidence_cards") or [], 4),
        "events": {
            "summary": timeline_summary,
            "highlights": _event_highlights(timeline.get("events") or []),
        },
        "risk": {
            "summary": risk_summary,
            "concentration": risk.get("concentration") or {},
            "account_risk": account_risk,
            "top_positions": _top_items(risk.get("top_positions") or []),
            "currency_exposure": _top_items(risk.get("currency_exposure") or []),
            "asset_type_exposure": _top_items(risk.get("asset_type_exposure") or []),
        },
        "data_quality": {
            "summary": quality_summary,
            "highlights": _quality_highlights(quality),
        },
        "review_questions": _review_questions(performance, timeline, risk, quality),
    }


def save_weekly_report_markdown(
    period: str = "1w",
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> Dict:
    report = build_weekly_report(period=period, start_date=start_date, end_date=end_date)
    if not report.get("ok"):
        return report
    return save_report_markdown(report)


def list_weekly_report_files() -> Dict:
    return list_report_files()


def read_weekly_report_file(name: str) -> Dict:
    return read_report_file(name)


def update_weekly_report_file(name: str, manual_markdown: str, tags: List[str]) -> Dict:
    return update_report_file(name, manual_markdown, tags)


build_period_report_context = build_weekly_report_context
build_period_report = build_weekly_report
save_period_report_markdown = save_weekly_report_markdown
list_period_report_files = list_weekly_report_files
read_period_report_file = read_weekly_report_file
update_period_report_file = update_weekly_report_file
render_weekly_report_markdown = render_period_report_markdown
