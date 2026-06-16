const RISK_LABELS = {
  high: "높음",
  medium: "보통",
  low: "낮음",
};

const RISK_BADGES = {
  high: "danger",
  medium: "warning",
  low: "success",
};

window.loadRiskPanel = function () {
  window.loadJsonAndRender(window.dashboardApiUrl("/api/risk/summary"), (data) => {
    window.renderRiskSummary(data);
    window.renderRiskTopPositions(data.top_positions || []);
    window.renderRiskExposure("risk-currency-body", data.currency_exposure || [], "currency");
    window.renderRiskExposure("risk-asset-body", data.asset_type_exposure || [], "asset_type");
    window.renderRiskLabelExposure("risk-portfolio-sector-body", data.portfolio_sector_exposure || [], "portfolio_sector");
    window.renderRiskLabelExposure("risk-portfolio-role-body", data.portfolio_role_exposure || [], "portfolio_role");
  });
};

window.renderRiskSummary = function (data) {
  const root = window.$("risk-summary");
  if (!root) return;

  const s = data.summary || {};
  const c = data.concentration || {};
  const ar = data.account_risk || {};
  const cards = [
    {
      label: "보유 종목",
      value: `${window.toLocaleNum(s.position_count)}개`,
      sub: data.period?.label || data.asof_date || "-",
    },
    {
      label: "최대 종목 비중",
      value: `${window.toLocaleNum(c.top1_weight_pct, 2)}%`,
      sub: `상위 3개 ${window.toLocaleNum(c.top3_weight_pct, 2)}%`,
    },
    {
      label: "최대 내 분류",
      value: data.portfolio_sector_exposure?.[0]?.portfolio_sector || "-",
      sub: data.portfolio_sector_exposure?.[0]
        ? `${window.toLocaleNum(data.portfolio_sector_exposure[0].weight_pct, 2)}%`
        : "-",
    },
    {
      label: "최대 낙폭",
      value: `${window.toLocaleNum(ar.max_drawdown_pct, 2)}%`,
      sub: `최근 변동성 ${window.toLocaleNum(ar.daily_volatility_pct, 2)}%`,
    },
  ];

  root.innerHTML = cards
    .map((card) => {
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
    })
    .join("");
};

window.renderRiskTopPositions = function (positions) {
  const tbody = window.$("risk-top-positions-body");
  if (!tbody) return;

  if (!Array.isArray(positions) || positions.length === 0) {
    tbody.innerHTML = `<tr><td colspan="7">포지션 데이터가 없습니다.</td></tr>`;
    return;
  }

  tbody.innerHTML = "";
  positions.forEach((row) => {
    const pnl = Number(row.profit_loss || 0);
    const color = pnl >= 0 ? "red" : "blue";
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${window.escapeHTML(row.name || "")}</td>
      <td>${window.escapeHTML(row.asset_type || "")}</td>
      <td>${window.escapeHTML(row.portfolio_sector || "")}</td>
      <td>${window.escapeHTML(row.portfolio_role || "")}</td>
      <td>${window.toLocaleNum(row.evaluation_amount)} KRW</td>
      <td>${window.toLocaleNum(row.weight_pct, 2)}%</td>
      <td style="color:${color}; font-weight:600;">${window.toLocaleNum(row.profit_rate, 2)}%</td>
    `;
    tbody.appendChild(tr);
  });
};

window.renderRiskLabelExposure = function (tbodyId, rows, labelKey) {
  const tbody = window.$(tbodyId);
  if (!tbody) return;

  if (!Array.isArray(rows) || rows.length === 0) {
    tbody.innerHTML = `<tr><td colspan="5">라벨 노출 데이터가 없습니다.</td></tr>`;
    return;
  }

  tbody.innerHTML = "";
  rows.forEach((row) => {
    const tr = document.createElement("tr");
    const topItems = Array.isArray(row.top_items) ? row.top_items.join(", ") : "";
    tr.innerHTML = `
      <td>${window.escapeHTML(row[labelKey] || "")}</td>
      <td>${window.toLocaleNum(row.count)}</td>
      <td>${window.toLocaleNum(row.evaluation_amount)} KRW</td>
      <td>${window.toLocaleNum(row.weight_pct, 2)}%</td>
      <td>${window.escapeHTML(topItems || "-")}</td>
    `;
    tbody.appendChild(tr);
  });
};

window.renderRiskExposure = function (tbodyId, rows, labelKey) {
  const tbody = window.$(tbodyId);
  if (!tbody) return;

  if (!Array.isArray(rows) || rows.length === 0) {
    tbody.innerHTML = `<tr><td colspan="4">노출 데이터가 없습니다.</td></tr>`;
    return;
  }

  tbody.innerHTML = "";
  rows.forEach((row) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${window.escapeHTML(row[labelKey] || "")}</td>
      <td>${window.toLocaleNum(row.count)}</td>
      <td>${window.toLocaleNum(row.evaluation_amount)} KRW</td>
      <td>${window.toLocaleNum(row.weight_pct, 2)}%</td>
    `;
    tbody.appendChild(tr);
  });
};
