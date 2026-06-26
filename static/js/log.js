window.setupReflectionLog = function () {
  if (window.AppBound.reflectionLog) return;

  window.$("reflection-log-save-button")?.addEventListener("click", () => {
    window.saveReflectionLog();
  });

  window.$("reflection-log-memo-save-button")?.addEventListener("click", () => {
    window.saveReflectionLogMemo();
  });

  window.AppBound.reflectionLog = true;
};

window.loadLogPanel = function () {
  window.setupReflectionLog();
  window.loadJsonAndRender("/api/log/current", (data) => {
    window.renderReflectionLog(data);
  });
};

window.saveReflectionLog = function () {
  const button = window.$("reflection-log-save-button");
  const status = window.$("reflection-log-status");
  if (button) button.disabled = true;
  if (status) status.textContent = "자동 요약 갱신 중...";

  fetch("/api/log/current/save", { method: "POST" })
    .then((res) => res.json().then((data) => ({ ok: res.ok, data })))
    .then(({ ok, data }) => {
      if (!ok || !data?.ok) throw new Error(data?.error || "로그 저장에 실패했습니다.");
      window.clearClientCache?.();
      window.renderReflectionLog(data);
      if (status) status.textContent = "자동 요약을 최신 데이터로 갱신했습니다.";
    })
    .catch((err) => {
      console.error("saveReflectionLog failed", err);
      if (status) status.textContent = `자동 요약 갱신 실패: ${err.message || err}`;
    })
    .finally(() => {
      if (button) button.disabled = false;
    });
};

window.saveReflectionLogMemo = function () {
  const button = window.$("reflection-log-memo-save-button");
  const status = window.$("reflection-log-status");
  const editor = window.$("reflection-log-manual-editor");
  const tags = window.$("reflection-log-tags-input");
  if (!editor) return;

  if (button) button.disabled = true;
  if (status) status.textContent = "내 메모 저장 중...";

  fetch("/api/log/current", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      manual_markdown: editor.value,
      tags: (tags?.value || "").split(/[,\s]+/).filter(Boolean),
    }),
  })
    .then((res) => res.json().then((data) => ({ ok: res.ok, data })))
    .then(({ ok, data }) => {
      if (!ok || !data?.ok) throw new Error(data?.error || "메모 저장에 실패했습니다.");
      window.clearClientCache?.();
      window.renderReflectionLog(data);
      if (status) status.textContent = "내 메모를 저장했습니다.";
    })
    .catch((err) => {
      console.error("saveReflectionLogMemo failed", err);
      if (status) status.textContent = `내 메모 저장 실패: ${err.message || err}`;
    })
    .finally(() => {
      if (button) button.disabled = false;
    });
};

window.renderReflectionLog = function (data) {
  const status = window.$("reflection-log-status");
  const current = data.current_week || {};
  const file = data.current_file || {};
  const draft = data.draft || {};

  if (status) {
    const latest = data.latest_data_date || "-";
    const basis = data.report_data_date || latest;
    const state = current.exists ? "저장된 로그 있음" : "이번주 로그 아직 없음";
    status.textContent = `${current.label || "이번주"} · 기준 ${basis} · ${state}`;
  }

  window.renderReflectionLogSummary(draft.summary_cards || []);
  window.renderWeeklyReportList?.("reflection-log-narrative", draft.narrative || []);
  window.renderWeeklyReportList?.("reflection-log-questions", draft.review_questions || []);
  window.renderReflectionLogRecent(data.recent_reports || [], current.filename);
  window.renderReflectionLogMissing(data.missing_weeks || []);

  const title = window.$("reflection-log-editor-title");
  const meta = window.$("reflection-log-editor-meta");
  const tags = window.$("reflection-log-tags-input");
  const editor = window.$("reflection-log-manual-editor");

  if (title) title.textContent = current.exists ? "이번주 내 생각" : "이번주 회고 초안";
  if (meta) meta.textContent = current.filename ? `${current.start_date || "-"} ~ ${current.end_date || "-"} · ${current.filename}` : "-";
  if (tags) tags.value = (file.tags || []).join(" ");
  if (editor) editor.value = file.manual_markdown || data.manual_template || "";
};

window.renderReflectionLogSummary = function (cards) {
  const root = window.$("reflection-log-summary");
  if (!root) return;

  if (!Array.isArray(cards) || cards.length === 0) {
    root.innerHTML = `<div class="mini-card"><div class="mini-card-title">이번주 로그</div><div class="mini-card-value">N/A</div><div class="mini-card-sub">요약할 데이터가 없습니다.</div></div>`;
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

window.renderReflectionLogRecent = function (reports, currentName) {
  const root = window.$("reflection-log-file-list");
  if (!root) return;

  if (!Array.isArray(reports) || reports.length === 0) {
    root.innerHTML = `<div class="muted">아직 저장된 주간 로그가 없습니다.</div>`;
    return;
  }

  root.innerHTML = reports
    .map((report) => `
      <div class="report-file-button ${report.name === currentName ? "active" : ""}">
        <div class="report-file-title">${window.escapeHTML(report.name || "")}</div>
        <div class="report-file-meta">${window.escapeHTML(report.period || "-")} · ${window.escapeHTML(report.updated_at || "-")}</div>
        <div class="report-file-tags">${window.escapeHTML(report.has_manual_notes ? "메모 있음" : "메모 없음")}</div>
      </div>
    `)
    .join("");
};

window.renderReflectionLogMissing = function (weeks) {
  const root = window.$("reflection-log-missing-list");
  if (!root) return;

  if (!Array.isArray(weeks) || weeks.length === 0) {
    root.innerHTML = `<div class="muted">최근 8주 안에 빠진 로그가 없습니다.</div>`;
    return;
  }

  root.innerHTML = weeks
    .map((week) => `
      <div class="report-file-button">
        <div class="report-file-title">${window.escapeHTML(week.label || "")}</div>
        <div class="report-file-meta">${window.escapeHTML(week.start_date || "-")} ~ ${window.escapeHTML(week.end_date || "-")}</div>
        <div class="report-file-tags">${window.escapeHTML(week.status || "미작성")}</div>
      </div>
    `)
    .join("");
};
