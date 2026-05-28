window.loadPerformancePanel = function () {
  window.loadJsonAndRender("/api/performance/summary", (data) => {
    window.renderPerformanceSummary(data);
    window.renderPerformanceContributors(data.contributors || {});
    window.renderPerformanceMonthly(data.monthly_changes || []);
    window.renderPerformanceAssets(data.asset_type_summary || []);
  });
};

window.renderPerformanceSummary = function (data) {
  const root = window.$("performance-summary");
  if (!root) return;

  const s = data.summary || {};
  const top = s.top_position || {};

  const cards = [
    {
      label: "평가총액",
      value: `${window.toLocaleNum(s.latest_total_value)} KRW`,
      sub: data.asof_date || "-",
    },
    {
      label: "누적 평가손익",
      value: `${window.toLocaleNum(s.profit_loss)} KRW`,
      sub: `${window.toLocaleNum(s.profit_rate, 2)}%`,
      signed: Number(s.profit_loss || 0),
    },
    {
      label: "최대 비중",
      value: top.name || "-",
      sub: `${window.toLocaleNum(top.weight_pct, 2)}%`,
    },
  ];

  root.innerHTML = cards
    .map((card) => {
      const color =
        card.signed == null ? "" : ` style="color:${Number(card.signed) >= 0 ? "red" : "blue"};"`;
      return `
        <div class="mini-card">
          <div class="mini-card-title">${window.escapeHTML(card.label)}</div>
          <div class="mini-card-value"${color}>${window.escapeHTML(card.value)}</div>
          <div class="mini-card-sub">${window.escapeHTML(card.sub)}</div>
        </div>
      `;
    })
    .join("");
};

window.renderPerformanceContributors = function (contributors) {
  const gainBody = window.$("performance-gainers-body");
  const lossBody = window.$("performance-losers-body");

  const renderRows = (tbody, rows, emptyText) => {
    if (!tbody) return;
    if (!Array.isArray(rows) || rows.length === 0) {
      tbody.innerHTML = `<tr><td colspan="5">${window.escapeHTML(emptyText)}</td></tr>`;
      return;
    }

    tbody.innerHTML = "";
    rows.forEach((row) => {
      const pnl = Number(row.profit_loss || 0);
      const color = pnl >= 0 ? "red" : "blue";
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td>${window.escapeHTML(row.name || "")}</td>
        <td>${window.escapeHTML(row.asset_type || "")}</td>
        <td style="color:${color}; font-weight:600;">${window.toLocaleNum(pnl)} KRW</td>
        <td style="color:${color}; font-weight:600;">${window.toLocaleNum(row.profit_rate, 2)}%</td>
        <td>${window.toLocaleNum(row.value_weight_pct, 2)}%</td>
      `;
      tbody.appendChild(tr);
    });
  };

  renderRows(gainBody, contributors.top_gainers || [], "수익 기여 종목이 없습니다.");
  renderRows(lossBody, contributors.top_losers || [], "손실 기여 종목이 없습니다.");
};

window.renderPerformanceMonthly = function (rows) {
  const tbody = window.$("performance-monthly-body");
  if (!tbody) return;

  if (!Array.isArray(rows) || rows.length === 0) {
    tbody.innerHTML = `<tr><td colspan="4">월별 성과 데이터가 없습니다.</td></tr>`;
    return;
  }

  tbody.innerHTML = "";
  rows.slice().reverse().forEach((row) => {
    const change = row.change == null ? 0 : Number(row.change);
    const color = change >= 0 ? "red" : "blue";
    const changeText = row.change == null ? "-" : `${window.toLocaleNum(change)} KRW`;
    const changePctText = row.change_pct == null ? "-" : `${window.toLocaleNum(row.change_pct, 2)}%`;
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${window.escapeHTML(row.month || "")}</td>
      <td>${window.toLocaleNum(row.total_value)} KRW</td>
      <td style="color:${color}; font-weight:600;">${window.escapeHTML(changeText)}</td>
      <td style="color:${color}; font-weight:600;">${window.escapeHTML(changePctText)}</td>
    `;
    tbody.appendChild(tr);
  });
};

window.renderPerformanceAssets = function (rows) {
  const tbody = window.$("performance-assets-body");
  if (!tbody) return;

  if (!Array.isArray(rows) || rows.length === 0) {
    tbody.innerHTML = `<tr><td colspan="6">자산군 성과 데이터가 없습니다.</td></tr>`;
    return;
  }

  tbody.innerHTML = "";
  rows.forEach((row) => {
    const pnl = Number(row.profit_loss || 0);
    const color = pnl >= 0 ? "red" : "blue";
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${window.escapeHTML(row.asset_type || "")}</td>
      <td>${window.toLocaleNum(row.count)}</td>
      <td>${window.toLocaleNum(row.evaluation_amount)} KRW</td>
      <td>${window.toLocaleNum(row.weight_pct, 2)}%</td>
      <td style="color:${color}; font-weight:600;">${window.toLocaleNum(pnl)} KRW</td>
      <td style="color:${color}; font-weight:600;">${window.toLocaleNum(row.profit_rate, 2)}%</td>
    `;
    tbody.appendChild(tr);
  });
};
