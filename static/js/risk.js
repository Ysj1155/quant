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
  window.loadJsonAndRender("/api/risk/summary", (data) => {
    window.renderRiskSummary(data);
    window.renderRiskAlerts(data.alerts || []);
    window.renderRiskTopPositions(data.top_positions || []);
    window.renderRiskExposure("risk-currency-body", data.currency_exposure || [], "currency");
    window.renderRiskExposure("risk-asset-body", data.asset_type_exposure || [], "asset_type");
  });
};

window.renderRiskSummary = function (data) {
  const root = window.$("risk-summary");
  if (!root) return;

  const s = data.summary || {};
  const c = data.concentration || {};
  const ar = data.account_risk || {};
  const level = s.risk_level || "low";

  const cards = [
    {
      label: "리스크 수준",
      value: RISK_LABELS[level] || level,
      sub: `${window.toLocaleNum(s.alert_count)}개 신호`,
      badge: RISK_BADGES[level] || "secondary",
    },
    {
      label: "최대 종목 비중",
      value: `${window.toLocaleNum(c.top1_weight_pct, 2)}%`,
      sub: `상위 3개 ${window.toLocaleNum(c.top3_weight_pct, 2)}%`,
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

window.renderRiskAlerts = function (alerts) {
  const tbody = window.$("risk-alerts-body");
  if (!tbody) return;

  if (!Array.isArray(alerts) || alerts.length === 0) {
    tbody.innerHTML = `<tr><td colspan="3">현재 표시할 리스크 신호가 없습니다.</td></tr>`;
    return;
  }

  tbody.innerHTML = "";
  alerts.forEach((alert) => {
    const badge = RISK_BADGES[alert.severity] || "secondary";
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td><span class="badge text-bg-${badge}">${window.escapeHTML(RISK_LABELS[alert.severity] || alert.severity)}</span></td>
      <td>${window.escapeHTML(alert.title || "")}</td>
      <td>${window.escapeHTML(alert.message || "")}</td>
    `;
    tbody.appendChild(tr);
  });
};

window.renderRiskTopPositions = function (positions) {
  const tbody = window.$("risk-top-positions-body");
  if (!tbody) return;

  if (!Array.isArray(positions) || positions.length === 0) {
    tbody.innerHTML = `<tr><td colspan="5">포지션 데이터가 없습니다.</td></tr>`;
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
      <td>${window.toLocaleNum(row.evaluation_amount)} KRW</td>
      <td>${window.toLocaleNum(row.weight_pct, 2)}%</td>
      <td style="color:${color}; font-weight:600;">${window.toLocaleNum(row.profit_rate, 2)}%</td>
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
