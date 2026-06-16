const TIMELINE_LABELS = {
  initial_position: "초기 보유",
  buy_open: "신규 진입",
  buy_add: "추가 매수",
  sell_partial: "일부 매도",
  sell_full: "전량 매도",
};

const TIMELINE_BADGES = {
  initial_position: "secondary",
  buy_open: "primary",
  buy_add: "info",
  sell_partial: "warning",
  sell_full: "danger",
};

const TIMELINE_CONFIDENCE = {
  baseline: "기준점",
  high: "높음",
  medium: "추정",
  low: "낮음",
};

window.loadTimelinePanel = function () {
  window.loadJsonAndRender(window.dashboardApiUrl("/api/timeline/events", { limit: 80, full: 0 }), (data) => {
    window.renderTimelineSummary(data.summary || {});
    window.renderTimelineEvents(data.events || []);
  });
  window.loadJsonAndRender(window.dashboardApiUrl("/api/timeline/review-dataset", { limit: 80 }), (data) => {
    window.renderEventReviewSummary(data.summary || {});
    window.renderEventReviewRows(data.rows || []);
  });
};

window.renderTimelineSummary = function (summary) {
  const root = window.$("timeline-summary");
  if (!root) return;

  const counts = summary.counts || {};
  const total = Number(summary.total || 0);
  const returned = Number(summary.returned || 0);
  const period = summary.period || {};
  const isBoundedPeriod = period.period && period.period !== "all";
  const rangeLabel = summary.partial
    ? "최근 탐색 구간"
    : isBoundedPeriod
      ? (period.label || "조회 구간")
      : "전체 구간";
  const totalLabel = summary.partial ? "최근 이벤트" : (isBoundedPeriod ? "기간 이벤트" : "전체 이벤트");
  const returnedLabel = summary.partial ? "최근 이벤트 우선 표시" : (isBoundedPeriod ? "선택 기간 계산 기준" : "전체 계산 기준");
  const buyCount = (counts.buy_open || 0) + (counts.buy_add || 0);
  const sellCount = (counts.sell_partial || 0) + (counts.sell_full || 0);

  const cards = [
    {
      label: totalLabel,
      value: `${window.toLocaleNum(total)}건`,
      sub: `${rangeLabel}: ${summary.date_start || "-"} ~ ${summary.date_end || "-"}`,
    },
    {
      label: "표시 건수",
      value: `${window.toLocaleNum(returned)}건`,
      sub: returnedLabel,
    },
    {
      label: "매수 / 매도",
      value: `${window.toLocaleNum(buyCount)} / ${window.toLocaleNum(sellCount)}`,
      sub: "표시된 이벤트 기준",
    },
    {
      label: "추정 순현금흐름",
      value: `${window.toLocaleNum(summary.net_cash_flow_est || 0)} KRW`,
      sub: `매수 ${window.toLocaleNum(summary.buy_cash_flow_est || 0)} / 매도 ${window.toLocaleNum(summary.sell_cash_flow_est || 0)}`,
    },
  ];

  root.innerHTML = cards
    .map(
      (card) => `
      <div class="mini-card">
        <div class="mini-card-title">${window.escapeHTML(card.label)}</div>
        <div class="mini-card-value">${window.escapeHTML(card.value)}</div>
        <div class="mini-card-sub">${window.escapeHTML(card.sub)}</div>
      </div>
    `
    )
    .join("");
};

window.renderTimelineEvents = function (events) {
  const tbody = window.$("timeline-events-body");
  if (!tbody) return;

  if (!Array.isArray(events) || events.length === 0) {
    tbody.innerHTML = `<tr><td colspan="10">표시할 투자 이벤트가 없습니다.</td></tr>`;
    return;
  }

  tbody.innerHTML = "";
  events.forEach((event) => {
    const type = event.event_type || "";
    const label = TIMELINE_LABELS[type] || type;
    const badge = TIMELINE_BADGES[type] || "secondary";
    const realized = event.realized_pnl_est;
    const cashFlow = event.cash_flow_est;
    const realizedText = realized == null ? "-" : `${window.toLocaleNum(realized)} KRW`;
    const cashFlowText = cashFlow == null ? "-" : `${window.toLocaleNum(cashFlow)} KRW`;
    const realizedColor = Number(realized || 0) >= 0 ? "red" : "blue";
    const cashFlowColor = Number(cashFlow || 0) >= 0 ? "red" : "blue";
    const qtyBefore = event.quantity_before == null ? "-" : window.toLocaleNum(event.quantity_before, 4);
    const qtyAfter = event.quantity_after == null ? "-" : window.toLocaleNum(event.quantity_after, 4);
    const confidence = TIMELINE_CONFIDENCE[event.confidence] || event.confidence || "-";

    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${window.escapeHTML(event.date || "")}</td>
      <td><span class="badge text-bg-${badge}">${window.escapeHTML(label)}</span></td>
      <td>${window.escapeHTML(event.name || "")}</td>
      <td>${window.escapeHTML(event.asset_type || "")}</td>
      <td>${window.toLocaleNum(event.quantity_delta, 4)}</td>
      <td>${window.escapeHTML(`${qtyBefore} → ${qtyAfter}`)}</td>
      <td>${window.toLocaleNum(event.event_unit_price_est || 0)} KRW</td>
      <td style="color:${cashFlowColor}; font-weight:600;">${window.escapeHTML(cashFlowText)}</td>
      <td style="color:${realizedColor}; font-weight:600;">${window.escapeHTML(realizedText)}</td>
      <td>
        <div>${window.escapeHTML(confidence)}</div>
        <small>${window.escapeHTML(event.reason || "")}</small>
      </td>
    `;
    tbody.appendChild(tr);
  });
};

window.renderEventReviewSummary = function (summary) {
  const root = window.$("event-review-summary");
  if (!root) return;

  const counts = summary.counts || {};
  const trackable = Number(summary.trackable_30obs || 0);
  const favorable = Number(summary.favorable_30obs || 0);
  const favorablePct = trackable > 0 ? (favorable / trackable) * 100 : 0;
  const cards = [
    {
      label: "복기 표본",
      value: `${window.toLocaleNum(summary.returned || 0)}건`,
      sub: `전체 후보 ${window.toLocaleNum(summary.total_available || summary.total || 0)}건`,
    },
    {
      label: "30관측치 추적",
      value: `${window.toLocaleNum(trackable)}건`,
      sub: `평가 가능 비율 ${window.toLocaleNum(summary.returned ? (trackable / summary.returned) * 100 : 0, 2)}%`,
    },
    {
      label: "유리했던 행동",
      value: `${window.toLocaleNum(favorable)}건`,
      sub: `추적 가능 표본 중 ${window.toLocaleNum(favorablePct, 2)}%`,
    },
    {
      label: "주요 결과",
      value: Object.entries(counts).sort((a, b) => Number(b[1]) - Number(a[1]))[0]?.[0] || "-",
      sub: Object.entries(counts).map(([key, value]) => `${key} ${value}`).join(" / ") || "-",
    },
  ];

  root.innerHTML = cards
    .map(
      (card) => `
      <div class="mini-card">
        <div class="mini-card-title">${window.escapeHTML(card.label)}</div>
        <div class="mini-card-value">${window.escapeHTML(card.value)}</div>
        <div class="mini-card-sub">${window.escapeHTML(card.sub)}</div>
      </div>
    `
    )
    .join("");
};

window.renderEventReviewRows = function (rows) {
  const tbody = window.$("event-review-body");
  if (!tbody) return;

  if (!Array.isArray(rows) || rows.length === 0) {
    tbody.innerHTML = `<tr><td colspan="8">복기할 매매 이벤트가 없습니다.</td></tr>`;
    return;
  }

  tbody.innerHTML = "";
  rows.forEach((row) => {
    const type = row.event_type || "";
    const label = TIMELINE_LABELS[type] || type;
    const badge = TIMELINE_BADGES[type] || "secondary";
    const outcome = row.outcomes?.["30obs"] || {};
    const forward = outcome.forward_return_pct;
    const color = Number(forward || 0) >= 0 ? "red" : "blue";
    const forwardText = forward == null ? "-" : `${window.toLocaleNum(forward, 2)}%`;
    const outcomeText = `${outcome.label || row.label_30obs || "-"} (${forwardText})`;
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${window.escapeHTML(row.date || "")}</td>
      <td><span class="badge text-bg-${badge}">${window.escapeHTML(label)}</span></td>
      <td>${window.escapeHTML(row.name || "")}</td>
      <td>${window.escapeHTML(row.portfolio_sector || "")}</td>
      <td>${window.escapeHTML(row.portfolio_role || "")}</td>
      <td>${window.toLocaleNum(row.event_unit_price_est || 0)} KRW</td>
      <td style="color:${color}; font-weight:600;">${window.escapeHTML(outcomeText)}</td>
      <td>${window.escapeHTML(row.review_prompt || "")}</td>
    `;
    tbody.appendChild(tr);
  });
};
