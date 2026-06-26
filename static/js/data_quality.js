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

const SECURITY_FILTER_LABELS = {
  all: "전체",
  review: "확인 필요",
  unresolved: "매칭 불가",
  excluded: "별도 자산",
  confirmed: "검산 가능",
};

window.DataQualityState = window.DataQualityState || {
  securityFilter: "all",
  securityRows: [],
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

  const rows = Array.isArray(resolution.rows) ? resolution.rows : [];
  window.DataQualityState.securityRows = rows;

  const coverage = resolution.coverage_pct == null ? 0 : Number(resolution.coverage_pct);
  const cards = [
    {
      label: "검산 커버리지",
      value: `${coverage.toFixed(1)}%`,
      sub: `${window.toLocaleNum(resolution.confirmed_count || 0)} / ${window.toLocaleNum(resolution.priceable_count || 0)}개`,
      filter: "all",
    },
    {
      label: "확인 필요",
      value: `${window.toLocaleNum(resolution.review_count || 0)}개`,
      sub: "후보 검색 또는 사용자 승인 필요",
      filter: "review",
      badge: Number(resolution.review_count || 0) > 0 ? "warning" : null,
    },
    {
      label: "별도 자산",
      value: `${window.toLocaleNum(resolution.excluded_count || 0)}개`,
      sub: "금/예수금처럼 분리 처리",
      filter: "excluded",
    },
    {
      label: "국내 종목 사전",
      value: `${window.toLocaleNum(krMaster.count || 0)}개`,
      sub: krMaster.updated_at ? `갱신 ${krMaster.updated_at}` : "캐시 미생성",
    },
  ];

  summaryRoot.innerHTML = cards
    .map((card) => renderMiniCard({
      ...card,
      active: window.DataQualityState.securityFilter === card.filter,
    }))
    .join("");

  summaryRoot.querySelectorAll("[data-security-filter]").forEach((button) => {
    const activate = () => {
      window.DataQualityState.securityFilter = button.dataset.securityFilter || "all";
      window.renderSecurityResolution(resolution, krMaster);
      window.$("security-resolution-action-panel")?.scrollIntoView({ behavior: "smooth", block: "nearest" });
    };
    button.addEventListener("click", activate);
    button.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        activate();
      }
    });
  });

  window.renderSecurityResolutionRows(rows);
  window.renderSecurityResolutionActionPanel(rows, resolution, krMaster);
};

window.securityFilteredRows = function (rows) {
  const filter = window.DataQualityState.securityFilter || "all";
  if (filter === "all") return rows;
  if (filter === "confirmed") return rows.filter((row) => ["confirmed", "auto"].includes(row.status));
  return rows.filter((row) => row.status === filter);
};

window.renderSecurityResolutionRows = function (rows) {
  const tbody = window.$("security-resolution-body");
  if (!tbody) return;

  const filteredRows = window.securityFilteredRows(rows);
  const filterLabel = SECURITY_FILTER_LABELS[window.DataQualityState.securityFilter || "all"] || "전체";

  if (filteredRows.length === 0) {
    tbody.innerHTML = `<tr><td colspan="6">${window.escapeHTML(filterLabel)} 상태의 보유 종목이 없습니다.</td></tr>`;
    return;
  }

  tbody.innerHTML = "";
  filteredRows.forEach((row) => {
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

window.renderSecurityResolutionActionPanel = function (rows, resolution, krMaster = {}) {
  const root = window.$("security-resolution-action-panel");
  if (!root) return;

  const filter = window.DataQualityState.securityFilter || "all";
  const filteredRows = window.securityFilteredRows(rows);
  const filterLabel = SECURITY_FILTER_LABELS[filter] || "전체";

  if (filter === "all") {
    root.innerHTML = `
      <div class="quality-action-head">
        <div>
          <h5>외부 검산 점검 큐</h5>
          <p>위 카드를 눌러 확인 필요, 별도 자산, 검산 가능 항목을 따로 볼 수 있습니다.</p>
        </div>
        <span class="badge text-bg-secondary">${window.toLocaleNum(rows.length)}개</span>
      </div>
    `;
    return;
  }

  const actionRows = filteredRows.map(renderSecurityActionItem).join("");
  root.innerHTML = `
    <div class="quality-action-head">
      <div>
        <h5>${window.escapeHTML(filterLabel)} 점검</h5>
        <p>${securityFilterDescription(filter, resolution, krMaster)}</p>
      </div>
      <span class="badge text-bg-${filter === "review" ? "warning" : filter === "unresolved" ? "danger" : "secondary"}">${window.toLocaleNum(filteredRows.length)}개</span>
    </div>
    <div class="quality-action-list">
      ${actionRows || `<div class="muted">해당 상태의 항목이 없습니다.</div>`}
    </div>
  `;
};

function securityFilterDescription(filter, resolution, krMaster) {
  if (filter === "review") return "외부 가격 검산을 하려면 종목 심볼 또는 국내 종목코드 확인이 필요한 항목입니다.";
  if (filter === "unresolved") return "현재 규칙으로 가격 검산 대상인지 판단하지 못한 항목입니다.";
  if (filter === "excluded") return "금, 현금성 자산처럼 주식 가격 API 검산과 분리해서 보는 항목입니다.";
  if (filter === "confirmed") return `현재 바로 검산 가능한 항목입니다. 국내 종목 사전 ${window.toLocaleNum(krMaster.count || 0)}개 기준도 함께 사용합니다.`;
  return "외부 검산 상태를 확인합니다.";
}

function renderSecurityActionItem(row) {
  const badge = SECURITY_STATUS_BADGES[row.status] || "secondary";
  const action = securityActionText(row);
  const symbol = row.symbol || "-";
  const market = row.market || "-";
  const source = row.price_source || "-";

  return `
    <div class="quality-action-item">
      <div class="quality-action-title">
        <span class="badge text-bg-${badge}">${window.escapeHTML(row.status_label || row.status || "")}</span>
        <strong>${window.escapeHTML(row.name || "")}</strong>
      </div>
      <div class="quality-action-meta">
        ${window.escapeHTML(row.asset_type || "-")} · ${window.escapeHTML(row.currency || "-")} · ${window.escapeHTML(market)} · ${window.escapeHTML(source)} · ${window.escapeHTML(symbol)}
      </div>
      <div class="quality-action-note">${window.escapeHTML(row.note || "")}</div>
      <div class="quality-action-next">${window.escapeHTML(action)}</div>
    </div>
  `;
}

function securityActionText(row) {
  if (row.status === "review" && row.market === "US") {
    return "다음 단계: 티커를 확인한 뒤 data/security_map.csv에 symbol과 status=confirmed를 등록하면 검산 대상으로 전환됩니다.";
  }
  if (row.status === "review" && row.market === "KR") {
    return "다음 단계: 후보 종목코드 중 맞는 코드를 골라 data/security_map.csv에 등록하면 자동 검산 대상으로 전환됩니다.";
  }
  if (row.status === "unresolved") {
    return "다음 단계: 가격 검산 대상인지 먼저 결정하고, 검산 대상이면 market/symbol/price_source를 지정합니다.";
  }
  if (row.status === "excluded") {
    return "다음 단계: 이 항목은 주식 가격 API 검산에서 제외하고 별도 자산/현금 흐름으로 관리합니다.";
  }
  return "현재 검산 준비가 된 항목입니다. 추후 외부 가격 비교 단계에서 사용됩니다.";
}

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
  const active = card.active ? " active" : "";
  const attrs = card.filter ? ` role="button" tabindex="0" data-security-filter="${window.escapeHTML(card.filter)}"` : "";
  return `
    <div class="mini-card${active}"${attrs}>
      <div class="mini-card-title">${window.escapeHTML(card.label)}</div>
      <div class="mini-card-value">${value}</div>
      <div class="mini-card-sub">${window.escapeHTML(card.sub)}</div>
    </div>
  `;
}
