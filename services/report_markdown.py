from __future__ import annotations

from html import escape
from typing import Dict, List

AUTO_START = "<!-- portfolio-blackbox:auto:start -->"
AUTO_END = "<!-- portfolio-blackbox:auto:end -->"
TAGS_PREFIX = "- 태그:"


def krw(value) -> str:
    if value is None:
        return "-"
    return f"{float(value):,.0f} KRW"


def pct(value, digits: int = 2) -> str:
    if value is None:
        return "-"
    return f"{float(value):,.{digits}f}%"


def markdown_escape(value) -> str:
    return str(value if value is not None else "-").replace("|", "\\|").replace("\n", " ")


def markdown_table(headers: List[str], rows: List[List[str]]) -> str:
    if not rows:
        rows = [["-" for _ in headers]]
    header = "| " + " | ".join(markdown_escape(item) for item in headers) + " |"
    sep = "| " + " | ".join("---" for _ in headers) + " |"
    body = ["| " + " | ".join(markdown_escape(item) for item in row) + " |" for row in rows]
    return "\n".join([header, sep, *body])


def normalize_tags(tags: List[str]) -> List[str]:
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


def extract_tags(content: str) -> List[str]:
    for line in content.splitlines():
        if line.strip().startswith(TAGS_PREFIX):
            raw = line.split(":", 1)[1]
            return normalize_tags([part.strip().lstrip("#") for part in raw.replace(",", " ").split()])
    return []


def format_tags_line(tags: List[str]) -> str:
    clean = normalize_tags(tags)
    if not clean:
        return f"{TAGS_PREFIX} -"
    return f"{TAGS_PREFIX} " + " ".join(f"#{tag}" for tag in clean)


def upsert_tags_line(content: str, tags: List[str]) -> str:
    lines = content.splitlines()
    tag_line = format_tags_line(tags)
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


def manual_body(content: str) -> str:
    if AUTO_END not in content:
        return ""
    return content.split(AUTO_END, 1)[1].lstrip()


def manual_markdown() -> str:
    return """## 내가 보는 해석

- 

## 헷갈렸던 것

- 

## 다음에 확인할 것

- 
"""


def replace_manual_body(content: str, manual_markdown_text: str) -> str:
    manual = str(manual_markdown_text or "").strip()
    if not manual:
        manual = manual_markdown().strip()
    if AUTO_END not in content:
        return content.rstrip() + "\n\n" + manual + "\n"
    before, _ = content.split(AUTO_END, 1)
    return before.rstrip() + "\n" + AUTO_END + "\n\n" + manual + "\n"


def has_manual_notes(manual_markdown_text: str) -> bool:
    meaningful = []
    for line in str(manual_markdown_text or "").splitlines():
        text = line.strip()
        if not text or text.startswith("#"):
            continue
        if text in ("-", "- ", "*", "* "):
            continue
        meaningful.append(text)
    return bool(meaningful)


def html_from_markdown(content: str) -> str:
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


def auto_markdown(report: Dict) -> str:
    performance = report.get("performance") or {}
    events = report.get("events") or {}
    risk = report.get("risk") or {}
    data_quality = report.get("data_quality") or {}
    evidence_cards = report.get("evidence_cards") or performance.get("evidence_cards") or []

    lines = [
        AUTO_START,
        "## 자동 요약",
        "",
        *[f"- {item}" for item in report.get("narrative") or []],
        "",
        "## 근거 스냅샷",
        "",
        *[
            f"- **{item.get('title', '-')}**: {item.get('value', '-')} / {item.get('detail', '-')}"
            for item in evidence_cards
        ],
        "",
        "## 성과 지표",
        "",
        markdown_table(
            ["지표", "값"],
            [
                ["시작 평가액", krw(performance.get("start_account_value"))],
                ["종료 평가액", krw(performance.get("end_account_value"))],
                ["기간 변화", krw(performance.get("period_change"))],
                ["기간 변화율", pct(performance.get("period_change_pct"))],
                ["단순수익률", pct(performance.get("simple_return_pct"))],
                ["계좌 TWR", pct(performance.get("account_twr_pct"))],
                ["투자노출 TWR", pct(performance.get("investment_twr_pct"))],
                ["추정 IRR(연율)", pct(performance.get("investment_irr_annual_pct"))],
            ],
        ),
        "",
        f"> {performance.get('method_note') or 'TWR/IRR은 복기용 추정치입니다.'}",
        "",
        "## 성과 기여",
        "",
        "### 이익 기여 상위",
        "",
        markdown_table(
            ["종목", "평가손익", "손익률", "비중"],
            [
                [
                    row.get("name"),
                    krw(row.get("profit_loss")),
                    pct(row.get("profit_rate")),
                    pct(row.get("value_weight_pct")),
                ]
                for row in performance.get("top_gainers") or []
            ],
        ),
        "",
        "### 손실 기여 상위",
        "",
        markdown_table(
            ["종목", "평가손익", "손익률", "비중"],
            [
                [
                    row.get("name"),
                    krw(row.get("profit_loss")),
                    pct(row.get("profit_rate")),
                    pct(row.get("value_weight_pct")),
                ]
                for row in performance.get("top_losers") or []
            ],
        ),
        "",
        "## 투자 이벤트",
        "",
        markdown_table(
            ["일자", "유형", "종목", "추정 현금흐름", "근거"],
            [
                [
                    row.get("date"),
                    row.get("label"),
                    row.get("name"),
                    krw(row.get("cash_flow_est")),
                    row.get("reason"),
                ]
                for row in events.get("highlights") or []
            ],
        ),
        "",
        "## 리스크와 노출",
        "",
        markdown_table(
            ["항목", "값"],
            [
                ["최대 종목 비중", pct((risk.get("concentration") or {}).get("top1_weight_pct"))],
                ["상위 3개 종목 비중", pct((risk.get("concentration") or {}).get("top3_weight_pct"))],
                ["최대 낙폭", pct((risk.get("account_risk") or {}).get("max_drawdown_pct"))],
                ["최근 변동성", pct((risk.get("account_risk") or {}).get("daily_volatility_pct"))],
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


def render_period_report_markdown(report: Dict) -> str:
    period = report.get("period") or {}
    start = period.get("start_date") or "-"
    end = period.get("end_date") or "-"
    title = report.get("title") or "회고 리포트"
    return (
        f"# {title}\n\n"
        f"- 기간: {start} ~ {end}\n"
        f"{format_tags_line([])}\n"
        f"- 생성 기준: CSV 스냅샷, 이벤트 원장, 성과/리스크 요약\n\n"
        f"{auto_markdown(report)}\n"
        f"{manual_markdown()}"
    )


render_weekly_report_markdown = render_period_report_markdown
