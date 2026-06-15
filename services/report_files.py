from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Dict, List

from services.report_markdown import (
    AUTO_END,
    AUTO_START,
    auto_markdown,
    extract_tags,
    has_manual_notes,
    html_from_markdown,
    manual_body,
    render_period_report_markdown,
    replace_manual_body,
    upsert_tags_line,
)

PERIOD_REPORT_DIR = Path("reports") / "weekly"
REPORT_DIR = PERIOD_REPORT_DIR


def safe_report_path(name: str) -> Path:
    raw = Path(str(name or "").strip())
    if raw.name != str(name or "").strip() or raw.suffix.lower() != ".md":
        raise ValueError("invalid report name")
    path = (REPORT_DIR / raw.name).resolve()
    root = REPORT_DIR.resolve()
    if root not in path.parents:
        raise ValueError("invalid report path")
    return path


def report_filename(report: Dict) -> str:
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


def save_report_markdown(report: Dict) -> Dict:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    path = REPORT_DIR / report_filename(report)
    auto = auto_markdown(report)

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
        content = render_period_report_markdown(report)
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


def list_report_files() -> Dict:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    rows = []
    for path in sorted(REPORT_DIR.glob("*.md"), reverse=True):
        content = path.read_text(encoding="utf-8")
        lines = content.splitlines()
        title = path.stem
        if lines and lines[0].startswith("# "):
            title = lines[0].lstrip("#").strip()
        period = next((line.split(":", 1)[1].strip() for line in lines if line.startswith("- 기간:")), "-")
        manual = manual_body(content)
        rows.append({
            "name": path.name,
            "title": title,
            "period": period,
            "tags": extract_tags(content),
            "has_manual_notes": has_manual_notes(manual),
            "updated_at": datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
            "size": path.stat().st_size,
        })
    return {"ok": True, "reports": rows}


def read_report_file(name: str) -> Dict:
    path = safe_report_path(name)
    if not path.exists():
        return {"ok": False, "error": "report not found"}

    content = path.read_text(encoding="utf-8")
    manual = manual_body(content)
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
        "tags": extract_tags(content),
        "manual_markdown": manual,
        "auto_markdown": auto,
        "content": content,
        "html": html_from_markdown(content),
        "updated_at": datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
        "has_manual_notes": has_manual_notes(manual),
    }


def update_report_file(name: str, manual_markdown: str, tags: List[str]) -> Dict:
    path = safe_report_path(name)
    if not path.exists():
        return {"ok": False, "error": "report not found"}

    content = path.read_text(encoding="utf-8")
    content = replace_manual_body(content, manual_markdown)
    content = upsert_tags_line(content, tags)
    path.write_text(content, encoding="utf-8", newline="\n")
    return read_report_file(path.name)
