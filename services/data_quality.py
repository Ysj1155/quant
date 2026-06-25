from __future__ import annotations

from collections import Counter
from datetime import datetime
from typing import Dict, List

import pandas as pd

from data.csv_manager import ACCOUNT_VALUE_FILE, PORTFOLIO_FILE, extract_date_from_filename, get_all_csv_files
from extensions import cache
from services.analysis_utils import latest_snapshot, load_account_values, safe_pct
from services.dashboard_data import load_current_portfolio_rows
from services.kr_security_master import get_kr_security_master_summary
from services.security_resolver import build_security_resolution_summary
from services.snapshots import list_snapshot_dates


def _check(severity: str, title: str, message: str, metric=None, details=None) -> Dict:
    return {
        "severity": severity,
        "title": title,
        "message": message,
        "metric": metric,
        "details": details or [],
    }


def _status_from_checks(checks: List[Dict]) -> str:
    if any(item["severity"] == "high" for item in checks):
        return "high"
    if any(item["severity"] == "warning" for item in checks):
        return "warning"
    return "ok"


def _score_from_checks(checks: List[Dict]) -> int:
    score = 100
    for item in checks:
        if item["severity"] == "high":
            score -= 25
        elif item["severity"] == "warning":
            score -= 10
        elif item["severity"] == "info":
            score -= 2
    return max(0, score)


def _snapshot_file_checks(csv_files: List[str], snapshot_dates: List[str]) -> List[Dict]:
    checks: List[Dict] = []
    if not csv_files:
        return [_check("high", "스냅샷 없음", "날짜가 포함된 원본 CSV 스냅샷을 찾지 못했습니다.")]

    dates = [extract_date_from_filename(name) for name in csv_files]
    dates = [date for date in dates if date]
    duplicates = sorted([date for date, count in Counter(dates).items() if count > 1])

    checks.append(_check(
        "ok",
        "스냅샷 파일",
        f"{len(csv_files)}개 원본 CSV에서 {len(snapshot_dates)}개 날짜를 인식했습니다.",
        len(snapshot_dates),
        [f"{snapshot_dates[0]} ~ {snapshot_dates[-1]}"] if snapshot_dates else [],
    ))

    if duplicates:
        checks.append(_check(
            "warning",
            "중복 날짜 스냅샷",
            f"같은 날짜로 인식되는 CSV가 {len(duplicates)}개 있습니다.",
            len(duplicates),
            duplicates[:10],
        ))
    else:
        checks.append(_check("ok", "중복 날짜", "중복 날짜 스냅샷은 발견되지 않았습니다."))

    return checks


def _account_value_checks(snapshot_dates: List[str], account_values: pd.DataFrame) -> List[Dict]:
    checks: List[Dict] = []
    if not ACCOUNT_VALUE_FILE.exists():
        return [_check("high", "account_value.csv 없음", "날짜별 총자산 파생 CSV가 없습니다.")]

    if account_values.empty:
        return [_check("high", "account_value.csv 비어 있음", "날짜별 총자산 데이터가 비어 있습니다.")]

    account_dates = set(account_values["date"].dt.strftime("%Y-%m-%d").tolist())
    snapshot_date_set = set(snapshot_dates)
    missing_in_account = sorted(snapshot_date_set - account_dates)
    missing_in_snapshots = sorted(account_dates - snapshot_date_set)

    checks.append(_check(
        "ok",
        "총자산 시계열",
        f"account_value.csv에서 {len(account_values)}개 관측치를 읽었습니다.",
        len(account_values),
        [
            f"{account_values['date'].iloc[0].strftime('%Y-%m-%d')} ~ {account_values['date'].iloc[-1].strftime('%Y-%m-%d')}"
        ],
    ))

    if missing_in_account:
        checks.append(_check(
            "warning",
            "총자산 누락 날짜",
            f"스냅샷은 있지만 account_value.csv에 없는 날짜가 {len(missing_in_account)}개 있습니다.",
            len(missing_in_account),
            missing_in_account[:10],
        ))
    else:
        checks.append(_check("ok", "총자산 날짜 일치", "스냅샷 날짜가 account_value.csv에 모두 반영되어 있습니다."))

    if missing_in_snapshots:
        checks.append(_check(
            "warning",
            "원본 없는 총자산 날짜",
            f"account_value.csv에는 있지만 원본 스냅샷이 없는 날짜가 {len(missing_in_snapshots)}개 있습니다.",
            len(missing_in_snapshots),
            missing_in_snapshots[:10],
        ))

    return checks


def _latest_value_checks(account_values: pd.DataFrame) -> tuple[List[Dict], Dict]:
    checks: List[Dict] = []
    latest_meta: Dict = {
        "latest_snapshot_date": None,
        "latest_account_value_date": None,
        "report_basis_date": None,
        "snapshot_account_lag_days": None,
        "latest_snapshot_total": None,
        "latest_account_value": None,
        "diff": None,
        "diff_pct": None,
    }

    latest_date, latest_df = latest_snapshot()
    if latest_df.empty:
        checks.append(_check("high", "최신 스냅샷 로드 실패", "최신 스냅샷 파일을 정규화해서 읽지 못했습니다."))
        return checks, latest_meta

    snapshot_total = float(latest_df["evaluation_amount"].sum())
    latest_meta["latest_snapshot_date"] = latest_date
    latest_meta["latest_snapshot_total"] = snapshot_total

    if account_values.empty:
        return checks, latest_meta

    latest_account_date = account_values["date"].iloc[-1].strftime("%Y-%m-%d")
    latest_account_value = float(account_values["total_value"].iloc[-1])
    diff = latest_account_value - snapshot_total
    diff_pct = safe_pct(diff, snapshot_total)
    lag_days = (
        datetime.strptime(latest_date, "%Y-%m-%d").date()
        - datetime.strptime(latest_account_date, "%Y-%m-%d").date()
    ).days

    latest_meta.update({
        "latest_account_value_date": latest_account_date,
        "report_basis_date": latest_account_date,
        "snapshot_account_lag_days": lag_days,
        "latest_account_value": latest_account_value,
        "diff": diff,
        "diff_pct": diff_pct,
    })

    severity = "ok"
    if abs(diff_pct) >= 1:
        severity = "high"
    elif abs(diff_pct) >= 0.1:
        severity = "warning"

    checks.append(_check(
        severity,
        "최신 총자산 일치",
        f"최신 스냅샷 합계와 account_value.csv 최신값 차이는 {diff:,.0f} KRW ({diff_pct:.3f}%)입니다.",
        diff_pct,
        [f"snapshot={latest_date}", f"account_value={latest_account_date}"],
    ))

    if lag_days > 0:
        checks.append(_check(
            "warning",
            "계산 기준 지연",
            f"최신 스냅샷은 {latest_date}이지만 성과/회고 계산 기준 총자산은 {latest_account_date}까지 반영되어 있습니다.",
            lag_days,
            [f"{lag_days}일 차이", "python app.py --refresh 실행 필요 가능성"],
        ))
    elif lag_days < 0:
        checks.append(_check(
            "warning",
            "총자산 날짜 초과",
            f"account_value.csv가 최신 스냅샷보다 {-lag_days}일 앞선 날짜까지 들어 있습니다.",
            abs(lag_days),
            ["원본 스냅샷 누락 여부 확인"],
        ))
    else:
        checks.append(_check("ok", "계산 기준 최신화", "최신 스냅샷과 총자산 계산 기준 날짜가 일치합니다."))

    return checks, latest_meta


def _movement_checks(account_values: pd.DataFrame) -> List[Dict]:
    if account_values.empty or len(account_values) < 2:
        return [_check("info", "변동성 검사 부족", "총자산 관측치가 부족해 급격한 변동 검사를 생략했습니다.")]

    df = account_values.copy()
    df["change_pct"] = df["total_value"].pct_change() * 100.0
    moves = df.dropna(subset=["change_pct"]).copy()
    abrupt = moves[moves["change_pct"].abs() >= 10].copy()

    if abrupt.empty:
        return [_check("ok", "급격한 총자산 변동", "일간 10% 이상 총자산 변동은 발견되지 않았습니다.")]

    details = [
        f"{row['date'].strftime('%Y-%m-%d')}: {float(row['change_pct']):.2f}%"
        for _, row in abrupt.sort_values("change_pct", key=lambda col: col.abs(), ascending=False).head(10).iterrows()
    ]
    return [_check(
        "warning",
        "급격한 총자산 변동",
        f"일간 10% 이상 변동한 날짜가 {len(abrupt)}개 있습니다.",
        len(abrupt),
        details,
    )]


def _portfolio_checks() -> List[Dict]:
    checks: List[Dict] = []
    if not PORTFOLIO_FILE.exists():
        return [_check("high", "portfolio_data.csv 없음", "최신 포트폴리오 파생 CSV가 없습니다.")]

    rows = load_current_portfolio_rows()
    if not rows:
        checks.append(_check("warning", "현재 보유 종목 없음", "예수금 제외 후 표시할 현재 보유 종목이 없습니다."))
    else:
        checks.append(_check("ok", "현재 포트폴리오", f"예수금 제외 후 {len(rows)}개 보유 종목을 표시할 수 있습니다.", len(rows)))

    invalid_names = [row for row in rows if not str(row.get("ticker", "")).strip() or str(row.get("ticker", "")).lower() == "nan"]
    if invalid_names:
        checks.append(_check("warning", "종목명 이상", f"종목명이 비어 있거나 nan인 행이 {len(invalid_names)}개 있습니다.", len(invalid_names)))
    else:
        checks.append(_check("ok", "종목명 정리", "현재 표시 대상에서 빈 종목명/nan 행은 발견되지 않았습니다."))

    return checks


def _security_resolution_checks(security_resolution: Dict) -> List[Dict]:
    total = int(security_resolution.get("total_count") or 0)
    priceable = int(security_resolution.get("priceable_count") or 0)
    confirmed = int(security_resolution.get("confirmed_count") or 0)
    review = int(security_resolution.get("review_count") or 0)
    unresolved = int(security_resolution.get("unresolved_count") or 0)
    excluded = int(security_resolution.get("excluded_count") or 0)
    coverage_pct = float(security_resolution.get("coverage_pct") or 0.0)

    if total == 0:
        return [_check("info", "외부 가격 검산 준비도", "검산할 현재 보유 종목이 없습니다.")]

    details = [
        f"검산 가능 {confirmed}개",
        f"확인 필요 {review}개",
        f"매칭 불가 {unresolved}개",
        f"별도 자산 {excluded}개",
    ]

    if unresolved:
        severity = "warning"
        message = f"외부 가격 검산 대상 {priceable}개 중 {confirmed}개만 매칭되었습니다. 매칭 불가 종목을 확인해야 합니다."
    elif review:
        severity = "warning"
        message = f"외부 가격 검산 대상 {priceable}개 중 {confirmed}개는 바로 검산 가능하고 {review}개는 사용자 확인이 필요합니다."
    else:
        severity = "ok"
        message = f"외부 가격 검산 대상 {priceable}개가 모두 준비되었습니다. 커버리지 {coverage_pct:.1f}%입니다."

    return [_check(severity, "외부 가격 검산 준비도", message, coverage_pct, details)]


def _kr_master_checks(kr_master: Dict) -> List[Dict]:
    count = int(kr_master.get("count") or 0)
    if count <= 0:
        return [_check(
            "warning",
            "국내 종목 사전",
            "국내 종목코드 마스터 캐시가 아직 없습니다. KIS 마스터 파일을 갱신하면 국내 종목명 매칭이 가능합니다.",
        )]

    markets = ", ".join(kr_master.get("markets") or [])
    return [_check(
        "ok",
        "국내 종목 사전",
        f"국내 종목코드 마스터 캐시에 {count:,}개 종목이 저장되어 있습니다.",
        count,
        [markets, f"updated_at={kr_master.get('updated_at') or '-'}"],
    )]


@cache.memoize(timeout=60)
def build_data_quality_summary() -> Dict:
    csv_files = get_all_csv_files()
    snapshot_dates = list_snapshot_dates()
    account_values = load_account_values()

    checks: List[Dict] = []
    checks.extend(_snapshot_file_checks(csv_files, snapshot_dates))
    checks.extend(_account_value_checks(snapshot_dates, account_values))
    latest_checks, latest_meta = _latest_value_checks(account_values)
    checks.extend(latest_checks)
    checks.extend(_movement_checks(account_values))
    checks.extend(_portfolio_checks())
    kr_master = get_kr_security_master_summary()
    checks.extend(_kr_master_checks(kr_master))
    security_resolution = build_security_resolution_summary()
    checks.extend(_security_resolution_checks(security_resolution))

    issue_count = sum(1 for item in checks if item["severity"] in ("high", "warning"))
    status = _status_from_checks(checks)

    return {
        "ok": True,
        "summary": {
            "status": status,
            "score": _score_from_checks(checks),
            "issue_count": issue_count,
            "snapshot_count": len(snapshot_dates),
            "account_value_count": int(len(account_values)),
            "date_start": snapshot_dates[0] if snapshot_dates else None,
            "date_end": snapshot_dates[-1] if snapshot_dates else None,
            **latest_meta,
        },
        "checks": checks,
        "kr_security_master": kr_master,
        "security_resolution": security_resolution,
    }
