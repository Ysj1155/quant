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
