window.setupWeeklyReportSave = function () {
  if (window.AppBound.weeklyReportSave) return;
  const button = window.$("weekly-report-save-button");

  button?.addEventListener("click", () => {
    window.saveWeeklyReportMarkdown();
  });

  window.$("weekly-report-edit-toggle")?.addEventListener("click", () => {
    const panel = window.$("weekly-report-editor");
    window.toggleWeeklyReportEditor(panel?.hidden !== false);
  });

  window.$("weekly-report-editor-save")?.addEventListener("click", () => {
    window.saveWeeklyReportEdit();
  });

  window.$("weekly-report-editor-cancel")?.addEventListener("click", () => {
    window.toggleWeeklyReportEditor(false);
    if (window.AppState.selectedWeeklyReport) {
      window.selectWeeklyReportFile(window.AppState.selectedWeeklyReport);
    }
  });

  window.AppBound.weeklyReportSave = true;
};

window.saveWeeklyReportMarkdown = function () {
  const button = window.$("weekly-report-save-button");
  const status = window.$("weekly-report-save-status");
  const url = window.dashboardApiUrl("/api/reports/weekly/save");

  if (button) button.disabled = true;
  if (status) status.textContent = "마크다운 저장 중...";

  fetch(url, { method: "POST" })
    .then((res) => res.json().then((data) => ({ ok: res.ok, data })))
    .then(({ ok, data }) => {
      if (!ok || !data?.ok) {
        throw new Error(data?.error || "저장에 실패했습니다.");
      }
      const action = data.action === "created" ? "생성" : data.action === "updated" ? "갱신" : "저장";
      if (status) status.textContent = `${action} 완료: ${data.path || "-"}`;
      window.loadWeeklyReportArchive(data.name);
    })
    .catch((err) => {
      console.error("saveWeeklyReportMarkdown failed", err);
      if (status) status.textContent = `저장 실패: ${err.message || err}`;
    })
    .finally(() => {
      if (button) button.disabled = false;
    });
};

window.loadWeeklyReportArchive = function (selectedName) {
  window.loadJsonAndRender("/api/reports/weekly/files", (data) => {
    window.renderWeeklyReportArchive(data.reports || [], selectedName);
  });
};

window.renderWeeklyReportArchive = function (reports, selectedName) {
  const root = window.$("weekly-report-file-list");
  const status = window.$("weekly-report-archive-status");
  if (!root) return;

  if (!Array.isArray(reports) || reports.length === 0) {
    root.innerHTML = `<div class="muted">저장된 리포트가 없습니다.</div>`;
    if (status) status.textContent = "먼저 마크다운 저장을 눌러 리포트를 누적하세요.";
    return;
  }

  root.innerHTML = "";
  reports.forEach((report) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "report-file-button";
    button.dataset.reportName = report.name;
    button.innerHTML = `
      <div class="report-file-title">${window.escapeHTML(report.title || report.name)}</div>
      <div class="report-file-meta">${window.escapeHTML(report.period || "-")} · ${window.escapeHTML(report.updated_at || "-")}</div>
      <div class="report-file-tags">${window.escapeHTML((report.tags || []).map((tag) => `#${tag}`).join(" ") || "태그 없음")}</div>
    `;
    button.addEventListener("click", () => {
      window.selectWeeklyReportFile(report.name);
    });
    root.appendChild(button);
  });

  const next = selectedName || reports[0].name;
  window.selectWeeklyReportFile(next);
};

window.selectWeeklyReportFile = function (name) {
  if (!name) return;
  document.querySelectorAll(".report-file-button").forEach((button) => {
    button.classList.toggle("active", button.dataset.reportName === name);
  });

  const url = `/api/reports/weekly/file?name=${encodeURIComponent(name)}`;
  window.loadJsonAndRender(url, (data) => {
    window.AppState.selectedWeeklyReport = data.name;
    window.renderWeeklyReportFile(data);
  });
};

window.renderWeeklyReportFile = function (data) {
  const title = window.$("weekly-report-viewer-title");
  const meta = window.$("weekly-report-viewer-meta");
  const tags = window.$("weekly-report-tags-input");
  const view = window.$("weekly-report-markdown-view");
  const editor = window.$("weekly-report-manual-editor");
  const editPanel = window.$("weekly-report-editor");
  const archiveStatus = window.$("weekly-report-archive-status");

  if (title) title.textContent = data.title || data.name || "리포트";
  if (meta) meta.textContent = `${data.name || "-"} · ${data.updated_at || "-"}`;
  if (tags) {
    tags.value = (data.tags || []).join(" ");
    tags.disabled = true;
  }
  if (view) view.innerHTML = data.html || "";
  if (editor) editor.value = data.manual_markdown || "";
  if (editPanel) editPanel.hidden = true;
  if (archiveStatus) {
    archiveStatus.textContent = data.has_manual_notes ? "수동 회고 메모가 있는 리포트입니다." : "아직 수동 회고 메모가 비어 있습니다.";
  }
};

window.toggleWeeklyReportEditor = function (enabled) {
  const panel = window.$("weekly-report-editor");
  const tags = window.$("weekly-report-tags-input");
  const button = window.$("weekly-report-edit-toggle");
  if (panel) panel.hidden = !enabled;
  if (tags) tags.disabled = !enabled;
  if (button) button.textContent = enabled ? "편집 중" : "편집";
};

window.saveWeeklyReportEdit = function () {
  const name = window.AppState.selectedWeeklyReport;
  const tags = window.$("weekly-report-tags-input");
  const editor = window.$("weekly-report-manual-editor");
  const status = window.$("weekly-report-archive-status");
  if (!name || !editor) return;

  if (status) status.textContent = "리포트 편집 저장 중...";

  fetch("/api/reports/weekly/file", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      name,
      tags: (tags?.value || "").split(/[,\s]+/).filter(Boolean),
      manual_markdown: editor.value,
    }),
  })
    .then((res) => res.json().then((data) => ({ ok: res.ok, data })))
    .then(({ ok, data }) => {
      if (!ok || !data?.ok) {
        throw new Error(data?.error || "편집 저장에 실패했습니다.");
      }
      window.renderWeeklyReportFile(data);
      window.loadWeeklyReportArchive(data.name);
      if (status) status.textContent = "편집 저장 완료";
    })
    .catch((err) => {
      console.error("saveWeeklyReportEdit failed", err);
      if (status) status.textContent = `편집 저장 실패: ${err.message || err}`;
    });
};

window.loadWeeklyReportPanel = function () {
  window.loadJsonAndRender(window.dashboardApiUrl("/api/reports/weekly"), (data) => {
    window.renderWeeklyReport(data);
  });
  window.loadWeeklyReportArchive();
};

window.renderWeeklyReport = function (data) {
  window.renderWeeklyReportTitle(data);
  window.renderWeeklyReportSummary(data.summary_cards || []);
  window.renderWeeklyReportList("weekly-report-narrative", data.narrative || []);
  window.renderWeeklyReportContributors("weekly-report-gainers-body", data.performance?.top_gainers || [], "수익 기여 종목이 없습니다.");
  window.renderWeeklyReportContributors("weekly-report-losers-body", data.performance?.top_losers || [], "손실 기여 종목이 없습니다.");
  window.renderWeeklyReportEvents(data.events?.highlights || []);
  window.renderWeeklyReportRisk(data.risk || {});
  window.renderWeeklyReportQuality(data.data_quality?.highlights || []);
  window.renderWeeklyReportList("weekly-report-questions", data.review_questions || []);
};

window.renderWeeklyReportTitle = function (data) {
  const title = window.$("weekly-report-title");
  if (title) title.textContent = data.title || "선택 기간 회고 리포트";
};

window.renderWeeklyReportSummary = function (cards) {
  const root = window.$("weekly-report-summary");
  if (!root) return;

  if (!Array.isArray(cards) || cards.length === 0) {
    root.innerHTML = `<div class="mini-card"><div class="mini-card-title">리포트</div><div class="mini-card-value">N/A</div><div class="mini-card-sub">데이터가 없습니다.</div></div>`;
    return;
  }

  root.innerHTML = cards
    .map((card) => {
      const color = card.signed == null ? "" : ` style="color:${Number(card.signed) >= 0 ? "red" : "blue"};"`;
      return `
        <div class="mini-card">
          <div class="mini-card-title">${window.escapeHTML(card.label || "")}</div>
          <div class="mini-card-value"${color}>${window.escapeHTML(card.value || "-")}</div>
          <div class="mini-card-sub">${window.escapeHTML(card.sub || "")}</div>
        </div>
      `;
    })
    .join("");
};

window.renderWeeklyReportList = function (id, rows) {
  const root = window.$(id);
  if (!root) return;

  if (!Array.isArray(rows) || rows.length === 0) {
    root.innerHTML = `<li>표시할 내용이 없습니다.</li>`;
    return;
  }

  root.innerHTML = rows.map((item) => `<li>${window.escapeHTML(item)}</li>`).join("");
};

window.renderWeeklyReportContributors = function (tbodyId, rows, emptyText) {
  const tbody = window.$(tbodyId);
  if (!tbody) return;

  if (!Array.isArray(rows) || rows.length === 0) {
    tbody.innerHTML = `<tr><td colspan="4">${window.escapeHTML(emptyText)}</td></tr>`;
    return;
  }

  tbody.innerHTML = "";
  rows.forEach((row) => {
    const pnl = Number(row.profit_loss || 0);
    const color = pnl >= 0 ? "red" : "blue";
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${window.escapeHTML(row.name || "")}</td>
      <td style="color:${color}; font-weight:600;">${window.toLocaleNum(pnl)} KRW</td>
      <td style="color:${color}; font-weight:600;">${window.toLocaleNum(row.profit_rate, 2)}%</td>
      <td>${window.toLocaleNum(row.value_weight_pct, 2)}%</td>
    `;
    tbody.appendChild(tr);
  });
};

window.renderWeeklyReportEvents = function (events) {
  const tbody = window.$("weekly-report-events-body");
  if (!tbody) return;

  if (!Array.isArray(events) || events.length === 0) {
    tbody.innerHTML = `<tr><td colspan="4">선택 기간에 표시할 투자 이벤트가 없습니다.</td></tr>`;
    return;
  }

  tbody.innerHTML = "";
  events.forEach((event) => {
    const cashFlow = event.cash_flow_est;
    const color = Number(cashFlow || 0) >= 0 ? "red" : "blue";
    const cashFlowText = cashFlow == null ? "-" : `${window.toLocaleNum(cashFlow)} KRW`;
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${window.escapeHTML(event.date || "")}</td>
      <td>${window.escapeHTML(event.label || "")}</td>
      <td>${window.escapeHTML(event.name || "")}</td>
      <td style="color:${color}; font-weight:600;">${window.escapeHTML(cashFlowText)}</td>
    `;
    tbody.appendChild(tr);
  });
};

window.renderWeeklyReportRisk = function (risk) {
  const rows = [];
  const concentration = risk.concentration || {};
  const accountRisk = risk.account_risk || {};
  const topPosition = Array.isArray(risk.top_positions) ? risk.top_positions[0] : null;
  const currency = Array.isArray(risk.currency_exposure) ? risk.currency_exposure[0] : null;
  const asset = Array.isArray(risk.asset_type_exposure) ? risk.asset_type_exposure[0] : null;

  rows.push(`최대 종목 비중 ${window.toLocaleNum(concentration.top1_weight_pct, 2)}%, 상위 3개 ${window.toLocaleNum(concentration.top3_weight_pct, 2)}%`);
  if (topPosition) rows.push(`최대 보유 종목은 ${topPosition.name}이며 비중은 ${window.toLocaleNum(topPosition.weight_pct, 2)}%입니다.`);
  if (currency) rows.push(`가장 큰 통화 노출은 ${currency.currency} ${window.toLocaleNum(currency.weight_pct, 2)}%입니다.`);
  if (asset) rows.push(`가장 큰 자산군 노출은 ${asset.asset_type} ${window.toLocaleNum(asset.weight_pct, 2)}%입니다.`);
  rows.push(`선택 기간 최대 낙폭은 ${window.toLocaleNum(accountRisk.max_drawdown_pct, 2)}%, 최근 변동성은 ${window.toLocaleNum(accountRisk.daily_volatility_pct, 2)}%입니다.`);

  window.renderWeeklyReportList("weekly-report-risk-list", rows);
};

window.renderWeeklyReportQuality = function (rows) {
  const root = window.$("weekly-report-quality-list");
  if (!root) return;

  if (!Array.isArray(rows) || rows.length === 0) {
    root.innerHTML = `<li>데이터 품질 메모가 없습니다.</li>`;
    return;
  }

  root.innerHTML = rows
    .map((row) => `<li><strong>${window.escapeHTML(row.title || "")}</strong>: ${window.escapeHTML(row.message || "")}</li>`)
    .join("");
};
