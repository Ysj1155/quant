const TIMELINE_LABELS = {
  initial_position: "초기 보유",
  buy_open: "신규 편입",
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

window.loadTimelinePanel = function () {
  window.loadJsonAndRender("/api/timeline/events?limit=60&full=0", (data) => {
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

  const cards = [
    {
      label: "전체 이벤트",
      value: `${window.toLocaleNum(total)}건`,
      sub: `${summary.date_start || "-"} ~ ${summary.date_end || "-"}`,
    },
    {
      label: "최근 표시",
      value: `${window.toLocaleNum(returned)}건`,
      sub: "최근순",
    },
    {
      label: "매수 / 매도",
      value: `${window.toLocaleNum((counts.buy_open || 0) + (counts.buy_add || 0))} / ${window.toLocaleNum(
        (counts.sell_partial || 0) + (counts.sell_full || 0)
      )}`,
      sub: "표시된 이벤트 기준",
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
    tbody.innerHTML = `<tr><td colspan="7">표시할 투자 이벤트가 없습니다.</td></tr>`;
    return;
  }

  tbody.innerHTML = "";
  events.forEach((event) => {
    const type = event.event_type || "";
    const label = TIMELINE_LABELS[type] || type;
    const badge = TIMELINE_BADGES[type] || "secondary";
    const realized = event.realized_pnl_est;
    const realizedText = realized == null ? "-" : `${window.toLocaleNum(realized)} KRW`;
    const realizedColor = Number(realized || 0) >= 0 ? "red" : "blue";

    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${window.escapeHTML(event.date || "")}</td>
      <td><span class="badge text-bg-${badge}">${window.escapeHTML(label)}</span></td>
      <td>${window.escapeHTML(event.name || "")}</td>
      <td>${window.escapeHTML(event.asset_type || "")}</td>
      <td>${window.toLocaleNum(event.quantity_delta, 4)}</td>
      <td>${window.toLocaleNum(event.purchase_amount_delta)} KRW</td>
      <td style="color:${realizedColor}; font-weight:600;">${window.escapeHTML(realizedText)}</td>
    `;
    tbody.appendChild(tr);
  });
};
