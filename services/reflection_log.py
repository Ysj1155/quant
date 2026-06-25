from __future__ import annotations

from datetime import date, datetime, timedelta
import re
from typing import Dict, List, Optional

from services.period_report import (
    build_period_report,
    list_period_report_files,
    read_period_report_file,
    save_period_report_markdown,
    update_period_report_file,
)
from services.report_files import report_filename
from services.report_markdown import manual_markdown
from services.snapshots import list_snapshot_dates

WEEK_FILE_RE = re.compile(r"^(?P<year>\d{4})-W(?P<week>\d{2})\.md$")


def _parse_date(value: Optional[str]) -> Optional[date]:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def _week_range(day: date) -> Dict:
    start = day - timedelta(days=day.weekday())
    end = start + timedelta(days=6)
    iso = day.isocalendar()
    return {
        "iso_year": iso.year,
        "iso_week": iso.week,
        "label": f"{iso.year}-W{iso.week:02d}",
        "filename": f"{iso.year}-W{iso.week:02d}.md",
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
    }


def _latest_data_date() -> Optional[date]:
    dates = [_parse_date(item) for item in list_snapshot_dates()]
    dates = [item for item in dates if item is not None]
    if not dates:
        return None
    return max(dates)


def _saved_week_ids(reports: List[Dict]) -> set[str]:
    out = set()
    for report in reports:
        match = WEEK_FILE_RE.match(str(report.get("name") or ""))
        if match:
            out.add(f"{match.group('year')}-W{match.group('week')}")
    return out


def _recent_weeks(latest: date, count: int = 8) -> List[Dict]:
    start = latest - timedelta(days=latest.weekday())
    return [_week_range(start - timedelta(days=7 * offset)) for offset in range(count)]


def _current_report_filename(report: Dict) -> str:
    try:
        return report_filename(report)
    except Exception:
        latest = _latest_data_date() or date.today()
        return _week_range(latest)["filename"]


def build_current_log() -> Dict:
    report = build_period_report(period="1w")
    if not report.get("ok"):
        return report

    files = list_period_report_files()
    reports = files.get("reports") or []
    saved_ids = _saved_week_ids(reports)

    latest = _latest_data_date()
    report_period = report.get("period") or {}
    report_end = _parse_date(report_period.get("end_date"))
    basis_date = report_end or latest or date.today()
    current_week = _week_range(basis_date)
    filename = _current_report_filename(report)
    current_week["filename"] = filename
    current_week["exists"] = any(item.get("name") == filename for item in reports)

    current_file = read_period_report_file(filename) if current_week["exists"] else None
    missing_weeks = [
        {
            **week,
            "is_current": week["filename"] == filename,
            "status": "이번주 미작성" if week["filename"] == filename else "미작성",
        }
        for week in _recent_weeks(latest or date.today())
        if week["label"] not in saved_ids
    ]

    return {
        "ok": True,
        "latest_data_date": latest.isoformat() if latest else None,
        "report_data_date": basis_date.isoformat(),
        "current_week": current_week,
        "draft": {
            "title": report.get("title"),
            "period": report.get("period"),
            "summary_cards": report.get("summary_cards") or [],
            "narrative": report.get("narrative") or [],
            "review_questions": report.get("review_questions") or [],
        },
        "current_file": current_file if current_file and current_file.get("ok") else None,
        "manual_template": manual_markdown(),
        "missing_weeks": missing_weeks,
        "recent_reports": reports[:8],
    }


def save_current_log() -> Dict:
    saved = save_period_report_markdown(period="1w")
    if not saved.get("ok"):
        return saved
    data = build_current_log()
    data["saved"] = saved
    return data


def update_current_log(manual_markdown_text: str, tags: List[str]) -> Dict:
    saved = save_period_report_markdown(period="1w")
    if not saved.get("ok"):
        return saved

    updated = update_period_report_file(
        name=saved["name"],
        manual_markdown=manual_markdown_text,
        tags=tags,
    )
    if not updated.get("ok"):
        return updated

    data = build_current_log()
    data["current_file"] = updated
    data["saved"] = saved
    return data
