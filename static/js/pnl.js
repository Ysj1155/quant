window.renderPnlSummary = function (p) {
  const root = window.$("pnl-summary");
  if (!root) return;

  const realizedRows = Array.isArray(p.realized) ? p.realized : [];
  const realizedSum = realizedRows.reduce(
    (acc, row) => acc + Number(row.realized_pnl || 0),
    0
  );

  const win = realizedRows.filter((row) => Number(row.realized_pnl || 0) > 0).length;
  const loss = realizedRows.filter((row) => Number(row.realized_pnl || 0) < 0).length;

  const cards = [
    {
      label: "실현 손익 합",
      value: `${window.toLocaleNum(realizedSum)} KRW`,
      sub: `이벤트 ${realizedRows.length}건`,
    },
    {
      label: "승/패",
      value: `${win} / ${loss}`,
      sub: "전량매도 기준",
    },
    {
      label: "기준 날짜",
      value: `${p.asof_date || "-"}`,
      sub: "스냅샷 기준",
    },
  ];

  root.innerHTML = cards
    .map(
      (c) => `
      <div class="mini-card">
        <div class="mini-card-title">${c.label}</div>
        <div class="mini-card-value">${c.value}</div>
        <div class="mini-card-sub">${c.sub}</div>
      </div>
    `
    )
    .join("");
};

window.loadPnlForDate = function (date) {
  const openBody = window.$("open-pnl-body");
  const realBody = window.$("realized-pnl-body");

  if (openBody) openBody.innerHTML = `<tr><td colspan="8">로딩중...</td></tr>`;
  if (realBody) realBody.innerHTML = `<tr><td colspan="7">로딩중...</td></tr>`;

  fetch(`/api/pnl?date=${encodeURIComponent(date)}`)
    .then((r) => r.json())
    .then((p) => {
      if (p.error) {
        if (openBody) {
          openBody.innerHTML = `<tr><td colspan="8" style="color:red;">❌ ${p.error}</td></tr>`;
        }
        if (realBody) {
          realBody.innerHTML = `<tr><td colspan="7" style="color:red;">❌ ${p.error}</td></tr>`;
        }
        return;
      }

      window.renderPnlSummary(p);

      if (openBody) {
        const rows = Array.isArray(p.open_positions) ? p.open_positions : [];
        if (rows.length === 0) {
          openBody.innerHTML = `<tr><td colspan="8">보유 종목 없음</td></tr>`;
        } else {
          openBody.innerHTML = "";
          rows.forEach((x) => {
            const pnl = Number(x.pnl || 0);
            const color = pnl >= 0 ? "red" : "blue";

            openBody.insertAdjacentHTML(
              "beforeend",
              `
              <tr>
                <td>${x.name || ""}</td>
                <td>${x.account || ""}</td>
                <td>${x.buy_date || ""}</td>
                <td>${window.toLocaleNum(x.qty)}</td>
                <td>${window.toLocaleNum(x.buy_amount)}</td>
                <td>${window.toLocaleNum(x.eval_amount)}</td>
                <td style="color:${color}; font-weight:600;">${window.toLocaleNum(pnl)}</td>
                <td style="color:${color}; font-weight:600;">${Number(x.pnl_pct || 0).toFixed(2)}%</td>
              </tr>
            `
            );
          });
        }
      }

      if (realBody) {
        const rows = Array.isArray(p.realized) ? p.realized : [];
        if (rows.length === 0) {
          realBody.innerHTML = `<tr><td colspan="7">실현 이벤트 없음</td></tr>`;
        } else {
          realBody.innerHTML = "";
          rows.slice(0, 50).forEach((x) => {
            const pnl = Number(x.realized_pnl || 0);
            const color = pnl >= 0 ? "red" : "blue";

            realBody.insertAdjacentHTML(
              "beforeend",
              `
              <tr>
                <td>${x.name || ""}</td>
                <td>${x.account || ""}</td>
                <td>${x.buy_date || ""}</td>
                <td>${x.sell_date || ""}</td>
                <td>${x.last_hold_date || ""}</td>
                <td style="color:${color}; font-weight:600;">${window.toLocaleNum(pnl)}</td>
                <td style="color:${color}; font-weight:600;">${Number(x.realized_pnl_pct || 0).toFixed(2)}%</td>
              </tr>
            `
            );
          });
        }
      }
    })
    .catch((err) => {
      console.error("pnl fetch error:", err);
      if (openBody) {
        openBody.innerHTML = `<tr><td colspan="8" style="color:red;">❌ pnl fetch failed</td></tr>`;
      }
      if (realBody) {
        realBody.innerHTML = `<tr><td colspan="7" style="color:red;">❌ pnl fetch failed</td></tr>`;
      }
    });
};

window.loadPnlPanel = function () {
  window.loadJsonAndRender("/api/pnl/series", (data) => {
    if (data?.error) {
      console.error("pnl series api error", data.error);
      return;
    }
    if (!data?.ok) {
      console.error("pnl series api not ok", data);
      return;
    }

    const dates = Array.isArray(data.dates) ? data.dates : [];
    if (dates.length === 0) {
      console.warn("pnl dates empty");
      try {
        Plotly.purge("pnl-chart");
      } catch (e) {}
      window.renderPnlEvents([]);
      return;
    }

    const toNumArr = (arr) =>
      (Array.isArray(arr) ? arr : []).map((v) => {
        const n = Number(v);
        return Number.isFinite(n) ? n : 0;
      });

    const unreal = toNumArr(data.unrealized_pnl);
    const realCum = toNumArr(data.realized_pnl_cum);

    const n = dates.length;
    const u = unreal.slice(0, n);
    const rc = realCum.slice(0, n);
    const realDaily = rc.map((val, i) => (i === 0 ? val : val - rc[i - 1]));

    const traceUnrealBar = {
      x: dates,
      y: u,
      type: "bar",
      name: "Unrealized PnL (snapshot)",
      hovertemplate: "Date=%{x}<br>Unrealized=%{y:,.0f} KRW<extra></extra>",
    };

    const traceRealDailyBar = {
      x: dates,
      y: realDaily,
      type: "bar",
      name: "Realized PnL (daily, estimated)",
      hovertemplate: "Date=%{x}<br>Realized(daily)=%{y:,.0f} KRW<extra></extra>",
    };

    const traceRealCumLine = {
      x: dates,
      y: rc,
      type: "scatter",
      mode: "lines",
      name: "Realized PnL (cum)",
      yaxis: "y2",
      line: { dash: "dot" },
      hovertemplate: "Date=%{x}<br>Realized(cum)=%{y:,.0f} KRW<extra></extra>",
    };

    const layout = {
      title: "PnL (Stacked: Unrealized + Realized Daily)",
      barmode: "relative",
      xaxis: { title: "Date", automargin: true },
      yaxis: { title: "KRW", automargin: true, zeroline: true },
      yaxis2: {
        title: "Realized Cum (KRW)",
        overlaying: "y",
        side: "right",
        showgrid: false,
      },
      margin: { t: 40, r: 50, l: 50, b: 40 },
      legend: { orientation: "h" },
    };

    Plotly.newPlot(
      "pnl-chart",
      [traceUnrealBar, traceRealDailyBar, traceRealCumLine],
      layout,
      { responsive: true }
    );

    window.renderPnlEvents(data.events || []);
  });
};

window.renderPnlEvents = function (events) {
  const tbody = window.$("pnl-events-body");
  if (!tbody) return;

  const list = (events || []).slice().reverse().slice(0, 30);

  if (list.length === 0) {
    tbody.innerHTML = `<tr><td colspan="5">매도 이벤트(추정)가 아직 없습니다.</td></tr>`;
    return;
  }

  tbody.innerHTML = "";
  list.forEach((e) => {
    const pnl = Number(e.realized_pnl_est || 0);
    const color = pnl >= 0 ? "red" : "blue";
    const kindLabel =
      e.type === "sell_full"
        ? "전량매도(추정)"
        : e.type === "sell_partial"
        ? "부분매도(추정)"
        : (e.type || "");

    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${e.date || ""}</td>
      <td>${e.name || ""}</td>
      <td>${kindLabel}</td>
      <td>${window.toLocaleNum(e.qty_sold)}</td>
      <td style="color:${color}; font-weight:600;">${window.toLocaleNum(pnl)}</td>
    `;
    tbody.appendChild(tr);
  });
};