from __future__ import annotations

from datetime import datetime
from html import escape
from pathlib import Path
from typing import Dict, List, Optional

from extensions import cache
from services.data_quality import build_data_quality_summary
from services.performance import build_performance_summary
from services.risk import build_risk_summary
from services.timeline import build_investment_timeline

EVENT_LABELS = {
    "initial_position": "초기 보유",
    "buy_open": "신규 진입",
    "buy_add": "추가 매수",
    "sell_partial": "일부 매도",
    "sell_full": "전량 매도",
}

REPORT_DIR = Path("reports") / "weekly"
AUTO_START = "<!-- portfolio-blackbox:auto:start -->"
AUTO_END = "<!-- portfolio-blackbox:auto:end -->"
TAGS_PREFIX = "- 태그:"


def _krw(value) -> str:
    if value is None:
        return "-"
    return f"{float(value):,.0f} KRW"


def _pct(value, digits: int = 2) -> str:
    if value is None:
        return "-"
    return f"{float(value):,.{digits}f}%"


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


def _markdown_escape(value) -> str:
    return str(value if value is not None else "-").replace("|", "\\|").replace("\n", " ")


def _markdown_table(headers: List[str], rows: List[List[str]]) -> str:
    if not rows:
        rows = [["-" for _ in headers]]
    header = "| " + " | ".join(_markdown_escape(item) for item in headers) + " |"
    sep = "| " + " | ".join("---" for _ in headers) + " |"
    body = ["| " + " | ".join(_markdown_escape(item) for item in row) + " |" for row in rows]
    return "\n".join([header, sep, *body])


def _safe_report_path(name: str) -> Path:
    raw = Path(str(name or "").strip())
    if raw.name != str(name or "").strip() or raw.suffix.lower() != ".md":
        raise ValueError("invalid report name")
    path = (REPORT_DIR / raw.name).resolve()
    root = REPORT_DIR.resolve()
    if root not in path.parents:
        raise ValueError("invalid report path")
    return path


def _normalize_tags(tags: List[str]) -> List[str]:
    out = []
    seen = set()
    for tag in tags or []:
        clean = str(tag).strip().lstrip("#").replace(",", " ")
        clean = " ".join(clean.split())
        if not clean:
            continue
        key = clean.lower()
        if key not in seen:
            seen.add(key)
            out.append(clean)
    return out[:12]


def _extract_tags(content: str) -> List[str]:
    for line in content.splitlines():
        if line.strip().startswith(TAGS_PREFIX):
            raw = line.split(":", 1)[1]
            return _normalize_tags([part.strip().lstrip("#") for part in raw.replace(",", " ").split()])
    return []


def _format_tags_line(tags: List[str]) -> str:
    clean = _normalize_tags(tags)
    if not clean:
        return f"{TAGS_PREFIX} -"
    return f"{TAGS_PREFIX} " + " ".join(f"#{tag}" for tag in clean)


def _upsert_tags_line(content: str, tags: List[str]) -> str:
    lines = content.splitlines()
    tag_line = _format_tags_line(tags)
    for idx, line in enumerate(lines):
        if line.strip().startswith(TAGS_PREFIX):
            lines[idx] = tag_line
            return "\n".join(lines).rstrip() + "\n"

    insert_at = 1
    for idx, line in enumerate(lines):
        if line.startswith("- 기간:"):
            insert_at = idx + 1
            break
    lines.insert(insert_at, tag_line)
    return "\n".join(lines).rstrip() + "\n"


def _manual_body(content: str) -> str:
    if AUTO_END not in content:
        return ""
    return content.split(AUTO_END, 1)[1].lstrip()


def _replace_manual_body(content: str, manual_markdown: str) -> str:
    manual = str(manual_markdown or "").strip()
    if not manual:
        manual = _manual_markdown().strip()
    if AUTO_END not in content:
        return content.rstrip() + "\n\n" + manual + "\n"
    before, _ = content.split(AUTO_END, 1)
    return before.rstrip() + "\n" + AUTO_END + "\n\n" + manual + "\n"


def _has_manual_notes(manual_markdown: str) -> bool:
    meaningful = []
    for line in str(manual_markdown or "").splitlines():
        text = line.strip()
        if not text or text.startswith("#"):
            continue
        if text in ("-", "- ", "*", "* "):
            continue
        meaningful.append(text)
    return bool(meaningful)


def _html_from_markdown(content: str) -> str:
    html = []
    in_list = False
    in_table = False

    def close_list():
        nonlocal in_list
        if in_list:
            html.append("</ul>")
            in_list = False

    def close_table():
        nonlocal in_table
        if in_table:
            html.append("</tbody></table>")
            in_table = False

    for raw in content.splitlines():
        line = raw.rstrip()
        stripped = line.strip()

        if not stripped:
            close_list()
            close_table()
            continue

        if stripped.startswith("<!--"):
            continue

        if stripped.startswith("|") and stripped.endswith("|"):
            close_list()
            cells = [escape(cell.strip()) for cell in stripped.strip("|").split("|")]
            if all(set(cell) <= {"-"} for cell in cells):
                continue
            tag = "th" if not in_table else "td"
            if not in_table:
                html.append("<table><thead>")
                html.append("<tr>" + "".join(f"<th>{cell}</th>" for cell in cells) + "</tr>")
                html.append("</thead><tbody>")
                in_table = True
            else:
                html.append("<tr>" + "".join(f"<{tag}>{cell}</{tag}>" for cell in cells) + "</tr>")
            continue

        close_table()

        if stripped.startswith("# "):
            close_list()
            html.append(f"<h1>{escape(stripped[2:].strip())}</h1>")
        elif stripped.startswith("## "):
            close_list()
            html.append(f"<h2>{escape(stripped[3:].strip())}</h2>")
        elif stripped.startswith("### "):
            close_list()
            html.append(f"<h3>{escape(stripped[4:].strip())}</h3>")
        elif stripped.startswith(">"):
            close_list()
            html.append(f"<blockquote>{escape(stripped.lstrip('>').strip())}</blockquote>")
        elif stripped.startswith("- "):
            if not in_list:
                html.append("<ul>")
                in_list = True
            html.append(f"<li>{escape(stripped[2:].strip())}</li>")
        else:
            close_list()
            html.append(f"<p>{escape(stripped)}</p>")

    close_list()
    close_table()
    return "\n".join(html)


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


def _report_filename(report: Dict) -> str:
    period = report.get("period") or {}
    period_key = period.get("period") or "report"
    start = period.get("start_date") or "unknown-start"
    end = period.get("end_date") or "unknown-end"

    if period_key == "1w" and end != "unknown-end":
        try:
            iso = datetime.strptime(end, "%Y-%m-%d").date().isocalendar()
            return f"{iso.year}-W{iso.week:02d}.md"
        except ValueError:
            pass

    safe_period = str(period_key).replace("/", "-")
    return f"{start}_to_{end}_{safe_period}.md"


def _auto_markdown(report: Dict) -> str:
    performance = report.get("performance") or {}
    events = report.get("events") or {}
    risk = report.get("risk") or {}
    data_quality = report.get("data_quality") or {}

    lines = [
        AUTO_START,
        "## 자동 요약",
        "",
        *[f"- {item}" for item in report.get("narrative") or []],
        "",
        "## 성과 지표",
        "",
        _markdown_table(
            ["지표", "값"],
            [
                ["시작 평가액", _krw(performance.get("start_account_value"))],
                ["종료 평가액", _krw(performance.get("end_account_value"))],
                ["기간 변화", _krw(performance.get("period_change"))],
                ["기간 변화율", _pct(performance.get("period_change_pct"))],
                ["단순수익률", _pct(performance.get("simple_return_pct"))],
                ["계좌 TWR", _pct(performance.get("account_twr_pct"))],
                ["투자노출 TWR", _pct(performance.get("investment_twr_pct"))],
                ["추정 IRR(연율)", _pct(performance.get("investment_irr_annual_pct"))],
            ],
        ),
        "",
        f"> {performance.get('method_note') or 'TWR/IRR은 복기용 추정치입니다.'}",
        "",
        "## 성과 기여",
        "",
        "### 이익 기여 상위",
        "",
        _markdown_table(
            ["종목", "평가손익", "손익률", "비중"],
            [
                [
                    row.get("name"),
                    _krw(row.get("profit_loss")),
                    _pct(row.get("profit_rate")),
                    _pct(row.get("value_weight_pct")),
                ]
                for row in performance.get("top_gainers") or []
            ],
        ),
        "",
        "### 손실 기여 상위",
        "",
        _markdown_table(
            ["종목", "평가손익", "손익률", "비중"],
            [
                [
                    row.get("name"),
                    _krw(row.get("profit_loss")),
                    _pct(row.get("profit_rate")),
                    _pct(row.get("value_weight_pct")),
                ]
                for row in performance.get("top_losers") or []
            ],
        ),
        "",
        "## 투자 이벤트",
        "",
        _markdown_table(
            ["일자", "유형", "종목", "추정 현금흐름", "근거"],
            [
                [
                    row.get("date"),
                    row.get("label"),
                    row.get("name"),
                    _krw(row.get("cash_flow_est")),
                    row.get("reason"),
                ]
                for row in events.get("highlights") or []
            ],
        ),
        "",
        "## 리스크와 노출",
        "",
        _markdown_table(
            ["항목", "값"],
            [
                ["최대 종목 비중", _pct((risk.get("concentration") or {}).get("top1_weight_pct"))],
                ["상위 3개 종목 비중", _pct((risk.get("concentration") or {}).get("top3_weight_pct"))],
                ["최대 낙폭", _pct((risk.get("account_risk") or {}).get("max_drawdown_pct"))],
                ["최근 변동성", _pct((risk.get("account_risk") or {}).get("daily_volatility_pct"))],
            ],
        ),
        "",
        "## 데이터 품질 메모",
        "",
        *[
            f"- **{item.get('title', '-')}**: {item.get('message', '-')}"
            for item in data_quality.get("highlights") or []
        ],
        "",
        "## 다음 회고 질문",
        "",
        *[f"- {item}" for item in report.get("review_questions") or []],
        AUTO_END,
    ]
    return "\n".join(lines).strip() + "\n"


def _manual_markdown() -> str:
    return """## 내가 보는 해석

- 

## 헷갈렸던 것

- 

## 다음에 확인할 것

- 
"""


def render_weekly_report_markdown(report: Dict) -> str:
    period = report.get("period") or {}
    start = period.get("start_date") or "-"
    end = period.get("end_date") or "-"
    title = report.get("title") or "회고 리포트"
    return (
        f"# {title}\n\n"
        f"- 기간: {start} ~ {end}\n"
        f"{_format_tags_line([])}\n"
        f"- 생성 기준: CSV 스냅샷, 이벤트 원장, 성과/리스크 요약\n\n"
        f"{_auto_markdown(report)}\n"
        f"{_manual_markdown()}"
    )


def save_weekly_report_markdown(
    period: str = "1w",
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> Dict:
    report = build_weekly_report(period=period, start_date=start_date, end_date=end_date)
    if not report.get("ok"):
        return report

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    path = REPORT_DIR / _report_filename(report)
    auto = _auto_markdown(report)

    if path.exists():
        old = path.read_text(encoding="utf-8")
        if AUTO_START in old and AUTO_END in old:
            before, rest = old.split(AUTO_START, 1)
            _, after = rest.split(AUTO_END, 1)
            content = before.rstrip() + "\n\n" + auto + "\n" + after.lstrip()
            action = "updated"
        else:
            content = old.rstrip() + "\n\n" + auto + "\n"
            action = "appended"
    else:
        content = render_weekly_report_markdown(report)
        action = "created"

    path.write_text(content, encoding="utf-8", newline="\n")
    return {
        "ok": True,
        "action": action,
        "path": str(path),
        "name": path.name,
        "title": report.get("title"),
        "period": report.get("period"),
    }


def list_weekly_report_files() -> Dict:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    rows = []
    for path in sorted(REPORT_DIR.glob("*.md"), reverse=True):
        content = path.read_text(encoding="utf-8")
        lines = content.splitlines()
        title = path.stem
        if lines and lines[0].startswith("# "):
            title = lines[0].lstrip("#").strip()
        period = next((line.split(":", 1)[1].strip() for line in lines if line.startswith("- 기간:")), "-")
        manual = _manual_body(content)
        rows.append({
            "name": path.name,
            "title": title,
            "period": period,
            "tags": _extract_tags(content),
            "has_manual_notes": _has_manual_notes(manual),
            "updated_at": datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
            "size": path.stat().st_size,
        })
    return {"ok": True, "reports": rows}


def read_weekly_report_file(name: str) -> Dict:
    path = _safe_report_path(name)
    if not path.exists():
        return {"ok": False, "error": "report not found"}

    content = path.read_text(encoding="utf-8")
    manual = _manual_body(content)
    auto = ""
    if AUTO_START in content and AUTO_END in content:
        auto = content.split(AUTO_START, 1)[1].split(AUTO_END, 1)[0].strip()

    title = path.stem
    lines = content.splitlines()
    if lines and lines[0].startswith("# "):
        title = lines[0].lstrip("#").strip()

    return {
        "ok": True,
        "name": path.name,
        "title": title,
        "tags": _extract_tags(content),
        "manual_markdown": manual,
        "auto_markdown": auto,
        "content": content,
        "html": _html_from_markdown(content),
        "updated_at": datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
        "has_manual_notes": _has_manual_notes(manual),
    }


def update_weekly_report_file(name: str, manual_markdown: str, tags: List[str]) -> Dict:
    path = _safe_report_path(name)
    if not path.exists():
        return {"ok": False, "error": "report not found"}

    content = path.read_text(encoding="utf-8")
    content = _replace_manual_body(content, manual_markdown)
    content = _upsert_tags_line(content, tags)
    path.write_text(content, encoding="utf-8", newline="\n")
    return read_weekly_report_file(path.name)


@cache.memoize(timeout=60)
def build_weekly_report(
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
    timeline = build_investment_timeline(
        limit=20,
        include_initial=False,
        full_scan=True,
        period=child_period,
        start_date=resolved_start,
        end_date=resolved_end,
    )
    quality = build_data_quality_summary()

    if not risk.get("ok"):
        return {"ok": False, "error": risk.get("error") or "risk summary unavailable"}

    period_label = period_info.get("label") or "선택 기간"
    summary = performance.get("summary") or {}
    advanced = performance.get("advanced_returns") or {}
    contributors = performance.get("contributors") or {}
    risk_summary = risk.get("summary") or {}
    account_risk = risk.get("account_risk") or {}

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
                "value": f"{int((timeline.get('summary') or {}).get('total') or 0):,}건",
                "sub": f"순현금흐름 {_krw((timeline.get('summary') or {}).get('net_cash_flow_est'))}",
            },
            {
                "label": "데이터 품질",
                "value": f"{(quality.get('summary') or {}).get('score', '-')}점",
                "sub": f"확인 항목 {(quality.get('summary') or {}).get('issue_count', 0)}개",
            },
        ],
        "narrative": _build_narrative(period_label, performance, timeline, risk, quality),
        "performance": {
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
            "method_note": advanced.get("method_note"),
        },
        "events": {
            "summary": timeline.get("summary") or {},
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
            "summary": quality.get("summary") or {},
            "highlights": _quality_highlights(quality),
        },
        "review_questions": _review_questions(performance, timeline, risk, quality),
    }
