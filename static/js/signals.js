const SIGNAL_LABELS = {
  high: "큼",
  medium: "주의",
  low: "평온",
};

const SIGNAL_BADGES = {
  high: "danger",
  medium: "warning",
  low: "success",
};

window.loadSignalsPanel = function () {
  window.loadJsonAndRender("/api/signals/account", (data) => {
    window.renderSignalsSummary(data);
    window.renderSignalsTrends(data.recent_trends || []);
    window.renderSignalsMoves(data.unusual_moves || []);
  });
};

window.renderSignalsSummary = function (data) {
  const root = window.$("signals-summary");
  if (!root) return;

  const s = data.summary || {};
  const latest = data.latest_signal || {};
  const level = s.latest_level || "low";
  const badge = SIGNAL_BADGES[level] || "secondary";

  const cards = [
    {
      label: "최근 변화 신호",
      value: SIGNAL_LABELS[level] || level,
      sub: `${window.toLocaleNum(latest.change_pct, 2)}% / z ${window.toLocaleNum(latest.z_score, 2)}`,
      badge,
    },
    {
      label: "평균 일변화",
      value: `${window.toLocaleNum(s.daily_change_mean_pct, 2)}%`,
      sub: `표준편차 ${window.toLocaleNum(s.daily_change_std_pct, 2)}%`,
    },
    {
      label: "이상 변동일",
      value: `${window.toLocaleNum(s.unusual_count)}일`,
      sub: `${window.toLocaleNum(s.observation_count)}개 관측`,
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

window.renderSignalsTrends = function (trends) {
  const tbody = window.$("signals-trends-body");
  if (!tbody) return;

  if (!Array.isArray(trends) || trends.length === 0) {
    tbody.innerHTML = `<tr><td colspan="3">추세 데이터가 없습니다.</td></tr>`;
    return;
  }

  tbody.innerHTML = "";
  trends.forEach((row) => {
    const change = Number(row.change || 0);
    const color = change >= 0 ? "red" : "blue";
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>최근 ${window.toLocaleNum(row.window)}개 관측</td>
      <td style="color:${color}; font-weight:600;">${row.change == null ? "-" : `${window.toLocaleNum(row.change)} KRW`}</td>
      <td style="color:${color}; font-weight:600;">${row.change_pct == null ? "-" : `${window.toLocaleNum(row.change_pct, 2)}%`}</td>
    `;
    tbody.appendChild(tr);
  });
};

window.renderSignalsMoves = function (moves) {
  const tbody = window.$("signals-moves-body");
  if (!tbody) return;

  if (!Array.isArray(moves) || moves.length === 0) {
    tbody.innerHTML = `<tr><td colspan="5">평소 범위를 벗어난 변동일이 없습니다.</td></tr>`;
    return;
  }

  tbody.innerHTML = "";
  moves.slice(0, 12).forEach((row) => {
    const change = Number(row.change || 0);
    const color = change >= 0 ? "red" : "blue";
    const badge = SIGNAL_BADGES[row.level] || "secondary";
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${window.escapeHTML(row.date || "")}</td>
      <td><span class="badge text-bg-${badge}">${window.escapeHTML(SIGNAL_LABELS[row.level] || row.level)}</span></td>
      <td style="color:${color}; font-weight:600;">${window.toLocaleNum(change)} KRW</td>
      <td style="color:${color}; font-weight:600;">${window.toLocaleNum(row.change_pct, 2)}%</td>
      <td>${window.toLocaleNum(row.z_score, 2)}</td>
    `;
    tbody.appendChild(tr);
  });
};
