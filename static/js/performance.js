window.loadPerformancePanel = function () {
  window.loadJsonAndRender(window.dashboardApiUrl("/api/performance/summary"), (data) => {
    window.renderPerformanceSummary(data);
    window.renderPerformanceAdvanced(data.advanced_returns || {});
    window.renderPerformanceContributors(data.contributors || {});
    window.renderPerformanceMonthly(data.monthly_changes || []);
    window.renderPerformanceAssets(data.asset_type_summary || []);
  });
};

window.renderPerformanceAdvanced = function (advanced) {
  const root = window.$("performance-advanced-summary");
  const note = window.$("performance-advanced-note");
  if (!root) return;

  const pct = (value) => value == null ? "-" : `${window.toLocaleNum(value, 2)}%`;
  const cards = [
    {
      label: "단순수익률",
      value: pct(advanced.simple_return_pct),
      sub: "계좌 총액 시작/종료 기준",
      signed: advanced.simple_return_pct,
    },
    {
      label: "계좌 TWR",
      value: pct(advanced.account_twr_pct),
      sub: "일별 계좌 변화율 연결",
      signed: advanced.account_twr_pct,
    },
    {
      label: "투자노출 TWR",
      value: pct(advanced.investment_twr_pct),
      sub: "매수/매도 흐름 조정",
      signed: advanced.investment_twr_pct,
    },
    {
      label: "추정 IRR",
      value: pct(advanced.investment_irr_annual_pct),
      sub: `연율 / 현금흐름 ${window.toLocaleNum(advanced.flow_count || 0)}건`,
      signed: advanced.investment_irr_annual_pct,
    },
  ];

  root.innerHTML = cards
    .map((card) => {
      const color = card.signed == null ? "" : ` style="color:${Number(card.signed) >= 0 ? "red" : "blue"};"`;
      return `
        <div class="mini-card">
          <div class="mini-card-title">${window.escapeHTML(card.label)}</div>
          <div class="mini-card-value"${color}>${window.escapeHTML(card.value)}</div>
          <div class="mini-card-sub">${window.escapeHTML(card.sub)}</div>
        </div>
      `;
    })
    .join("");

  if (note) {
    note.textContent = advanced.method_note || "";
  }
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
      label: "기간 변화",
      value: s.period_change == null ? "-" : `${window.toLocaleNum(s.period_change)} KRW`,
      sub: s.period_change_pct == null ? data.period?.label || "-" : `${window.toLocaleNum(s.period_change_pct, 2)}% / ${data.period?.label || "-"}`,
      signed: s.period_change,
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
