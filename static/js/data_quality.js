const DATA_QUALITY_BADGES = {
  ok: "success",
  info: "secondary",
  warning: "warning",
  high: "danger",
};

const DATA_QUALITY_LABELS = {
  ok: "정상",
  info: "참고",
  warning: "주의",
  high: "점검 필요",
};

const SECURITY_STATUS_BADGES = {
  confirmed: "success",
  auto: "primary",
  review: "warning",
  unresolved: "danger",
  excluded: "secondary",
};

window.loadDataQualityPanel = function () {
  window.loadJsonAndRender("/api/data-quality/summary", (data) => {
    window.renderDataQualitySummary(data.summary || {});
    window.renderSecurityResolution(data.security_resolution || {}, data.kr_security_master || {});
    window.renderDataQualityChecks(data.checks || []);
  });
};

window.refreshKrSecurityMaster = function (button) {
  if (button) {
    button.disabled = true;
    button.textContent = "갱신 중...";
  }

  fetch("/api/data-quality/kr-security-master/refresh", { method: "POST" })
    .then((response) => response.json())
    .then((data) => {
      if (!data.ok) throw new Error(data.error || "국내 종목 사전 갱신 실패");
      return fetch(`/api/data-quality/summary?ts=${Date.now()}`);
    })
    .then((response) => response.json())
    .then((data) => {
      window.renderDataQualitySummary(data.summary || {});
      window.renderSecurityResolution(data.security_resolution || {}, data.kr_security_master || {});
      window.renderDataQualityChecks(data.checks || []);
    })
    .catch((error) => {
      const tbody = window.$("security-resolution-body");
      if (tbody) {
        tbody.innerHTML = `<tr><td colspan="6">국내 종목 사전 갱신에 실패했습니다: ${window.escapeHTML(error.message)}</td></tr>`;
      }
    })
    .finally(() => {
      if (button) {
        button.disabled = false;
        button.textContent = "국내 종목 사전 갱신";
      }
    });
};

window.renderDataQualitySummary = function (summary) {
  const root = window.$("data-quality-summary");
  if (!root) return;

  const status = summary.status || "info";
  const badge = DATA_QUALITY_BADGES[status] || "secondary";
  const latestDiffPct = summary.diff_pct == null ? "-" : `${Number(summary.diff_pct).toFixed(3)}%`;
  const lagDays = Number(summary.snapshot_account_lag_days || 0);
  const basisStatus = lagDays === 0 ? "일치" : lagDays > 0 ? `${lagDays}일 지연` : `${Math.abs(lagDays)}일 초과`;

  const cards = [
    {
      label: "품질 상태",
      value: DATA_QUALITY_LABELS[status] || status,
      sub: `점수 ${window.toLocaleNum(summary.score || 0)} / 이슈 ${window.toLocaleNum(summary.issue_count || 0)}개`,
      badge,
    },
    {
      label: "스냅샷 범위",
      value: `${window.toLocaleNum(summary.snapshot_count || 0)}일`,
      sub: `${summary.date_start || "-"} ~ ${summary.date_end || "-"}`,
    },
    {
      label: "계산 기준",
      value: basisStatus,
      sub: `스냅샷 ${summary.latest_snapshot_date || "-"} · 총자산 ${summary.report_basis_date || summary.latest_account_value_date || "-"}`,
    },
    {
      label: "총자산 관측치",
      value: `${window.toLocaleNum(summary.account_value_count || 0)}개`,
      sub: summary.latest_account_value == null ? "-" : `${window.toLocaleNum(summary.latest_account_value)} KRW`,
    },
    {
      label: "최신 총액 차이",
      value: latestDiffPct,
      sub: summary.diff == null ? "-" : `${window.toLocaleNum(summary.diff)} KRW`,
    },
  ];

  root.innerHTML = cards.map(renderMiniCard).join("");
};

window.renderSecurityResolution = function (resolution, krMaster = {}) {
  const summaryRoot = window.$("security-resolution-summary");
  const tbody = window.$("security-resolution-body");
  if (!summaryRoot || !tbody) return;

  const coverage = resolution.coverage_pct == null ? 0 : Number(resolution.coverage_pct);
  const cards = [
    {
      label: "검산 커버리지",
      value: `${coverage.toFixed(1)}%`,
      sub: `${window.toLocaleNum(resolution.confirmed_count || 0)} / ${window.toLocaleNum(resolution.priceable_count || 0)}개`,
    },
    {
      label: "확인 필요",
      value: `${window.toLocaleNum(resolution.review_count || 0)}개`,
      sub: "후보 검색 또는 사용자 승인 필요",
    },
    {
      label: "별도 자산",
      value: `${window.toLocaleNum(resolution.excluded_count || 0)}개`,
      sub: "금/예수금처럼 분리 처리",
    },
    {
      label: "국내 종목 사전",
      value: `${window.toLocaleNum(krMaster.count || 0)}개`,
      sub: krMaster.updated_at ? `갱신 ${krMaster.updated_at}` : "캐시 미생성",
    },
  ];

  summaryRoot.innerHTML = cards.map(renderMiniCard).join("");

  const rows = Array.isArray(resolution.rows) ? resolution.rows : [];
  if (rows.length === 0) {
    tbody.innerHTML = `<tr><td colspan="6">표시할 보유 종목이 없습니다.</td></tr>`;
    return;
  }

  tbody.innerHTML = "";
  rows.forEach((row) => {
    const badge = SECURITY_STATUS_BADGES[row.status] || "secondary";
    const symbol = row.symbol || "-";
    const source = row.price_source || "-";
    const market = row.market ? `${row.market} / ` : "";
    const assetClass = row.asset_class || "-";
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td><span class="badge text-bg-${badge}">${window.escapeHTML(row.status_label || row.status || "")}</span></td>
      <td>${window.escapeHTML(row.name || "")}</td>
      <td>${window.escapeHTML(`${market}${assetClass}`)}</td>
      <td>${window.escapeHTML(symbol)}</td>
      <td>${window.escapeHTML(source)}</td>
      <td>${window.escapeHTML(row.note || "")}</td>
    `;
    tbody.appendChild(tr);
  });
};

window.renderDataQualityChecks = function (checks) {
  const tbody = window.$("data-quality-checks-body");
  if (!tbody) return;

  if (!Array.isArray(checks) || checks.length === 0) {
    tbody.innerHTML = `<tr><td colspan="4">표시할 검사 결과가 없습니다.</td></tr>`;
    return;
  }

  tbody.innerHTML = "";
  checks.forEach((check) => {
    const severity = check.severity || "info";
    const badge = DATA_QUALITY_BADGES[severity] || "secondary";
    const details = Array.isArray(check.details) && check.details.length > 0
      ? check.details.map((item) => window.escapeHTML(item)).join("<br>")
      : "-";

    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td><span class="badge text-bg-${badge}">${window.escapeHTML(DATA_QUALITY_LABELS[severity] || severity)}</span></td>
      <td>${window.escapeHTML(check.title || "")}</td>
      <td>${window.escapeHTML(check.message || "")}</td>
      <td>${details}</td>
    `;
    tbody.appendChild(tr);
  });
};

function renderMiniCard(card) {
  const value = card.badge
    ? `<span class="badge text-bg-${card.badge}">${window.escapeHTML(card.value)}</span>`
    : window.escapeHTML(card.value);
  return `
    <div class="mini-card">
      <div class="mini-card-title">${window.escapeHTML(card.label)}</div>
      <div class="mini-card-value">${value}</div>
      <div class="mini-card-sub">${window.escapeHTML(card.sub)}</div>
    </div>
  `;
}
