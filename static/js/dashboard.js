window.loadPortfolioTable = function () {
  window.loadJsonAndRender("/get_portfolio_data", (data) => {
    const tbody = window.$("portfolio-table-body");
    if (!tbody) return;

    tbody.innerHTML = "";

    data.forEach((row) => {
      const tr = document.createElement("tr");

      const profitRate = Number(row.profit_rate || 0);
      const profitRateColor = profitRate >= 0 ? "red" : "blue";

      tr.innerHTML = `
        <td>${row.account_number ?? ""}</td>
        <td>${row.ticker ?? ""}</td>
        <td>${window.toLocaleNum(row.quantity)}</td>
        <td>${window.toLocaleNum(row.purchase_amount)} KRW</td>
        <td>${window.toLocaleNum(row.evaluation_amount)} KRW</td>
        <td>${window.toLocaleNum(row.profit_loss)} KRW</td>
        <td style="color:${profitRateColor}; font-weight:bold;">
          ${profitRate.toFixed(2)}%
        </td>
      `;

      tbody.appendChild(tr);
    });
  });
};

window.loadPieChart = function () {
  window.loadJsonAndRender("/get_pie_chart_data", (data) => {
    if (!window.$("pie-chart")) return;

    Plotly.newPlot(
      "pie-chart",
      [
        {
          labels: data.labels || [],
          values: data.values || [],
          type: "pie",
        },
      ],
      {
        margin: { t: 10, l: 10, r: 10, b: 10 },
      },
      {
        responsive: true,
      }
    );
  });
};

window.onDateSelected = function (dateStr) {
  window.loadSnapshotDetail(dateStr);

  if (typeof window.loadPnlForDate === "function") {
    window.loadPnlForDate(dateStr);
  }
};

window.loadAccountChart = function () {
  window.loadJsonAndRender("/get_account_value_data", (data) => {
    if (!window.$("profit-chart")) return;

    const latestValue = window.toLocaleNum(data.latest_value);
    const latestProfit = Number(data.latest_profit || 0);
    const latestProfitColor = latestProfit >= 0 ? "red" : "blue";

    const totalValueEl = window.$("total-value");
    if (totalValueEl) {
      totalValueEl.innerHTML = `
        Total Value: ${latestValue} KRW
        <span style="color:${latestProfitColor}; font-weight:bold;">
          (${latestProfit.toFixed(2)}%)
        </span>
      `;
    }

    const totalValueTrace = {
      x: data.dates || [],
      y: data.total_values || [],
      type: "scatter",
      mode: "lines+markers",
      name: "Total Account Value",
      yaxis: "y1",
    };

    const profitTrace = {
      x: data.dates || [],
      y: data.profits || [],
      type: "scatter",
      mode: "lines",
      name: "Account Profit (%)",
      yaxis: "y2",
      line: { dash: "dot" },
    };

    const layout = {
      title: "Portfolio Total Value & Profit",
      xaxis: { title: "Date" },
      yaxis: {
        title: "Total Value (KRW)",
        side: "left",
        showgrid: false,
      },
      yaxis2: {
        title: "Profit (%)",
        overlaying: "y",
        side: "right",
        showgrid: false,
      },
      margin: { t: 40, r: 10, l: 50, b: 40 },
    };

    Plotly.newPlot("profit-chart", [totalValueTrace, profitTrace], layout, {
      responsive: true,
    }).then(() => {
      const latestDate = data.dates?.[data.dates.length - 1];
      if (latestDate) {
        window.onDateSelected(window.normalizeDate(latestDate));
      }

      const chartEl = window.$("profit-chart");
      if (chartEl && !window.AppBound.profitChartClick) {
        chartEl.on("plotly_click", (ev) => {
          const x = ev?.points?.[0]?.x;
          if (!x) return;
          window.onDateSelected(window.normalizeDate(x));
        });

        window.AppBound.profitChartClick = true;
      }
    });
  });
};

window.renderSnapshotSummary = function (date, stockSum) {
  const root = window.$("snapshot-summary");
  const meta = window.$("snapshot-meta");

  if (meta) {
    meta.innerHTML = `선택 날짜: <strong>${date}</strong>`;
  }

  if (!root) return;

  const cards = [
    {
      label: "주식 평가금액 합",
      value: `${window.toLocaleNum(stockSum)} KRW`,
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

window.loadSnapshotDetail = function (date) {
  const tbody = window.$("snapshot-table-body");
  const cashBox = window.$("snapshot-cash");

  if (tbody) {
    tbody.innerHTML = `<tr><td colspan="8">로딩중...</td></tr>`;
  }

  if (cashBox) {
    cashBox.innerHTML = `로딩중...`;
  }

  fetch(`/api/snapshot?date=${encodeURIComponent(date)}`)
    .then((r) => r.json())
    .then((s) => {
      if (s.error) {
        if (tbody) {
          tbody.innerHTML = `<tr><td colspan="8" style="color:red;">❌ ${s.error}</td></tr>`;
        }
        if (cashBox) {
          cashBox.innerHTML = `<span style="color:red;">❌ ${s.error}</span>`;
        }
        return;
      }

      window.renderSnapshotSummary(s.date, s.summary?.stock_eval_sum ?? 0);

      const rows = s.holdings || [];
      if (!tbody) return;

      if (rows.length === 0) {
        tbody.innerHTML = `<tr><td colspan="8">보유 종목이 없습니다.</td></tr>`;
      } else {
        tbody.innerHTML = "";

        rows.forEach((h) => {
          const pnl = Number(h.pnl || 0);
          const pnlColor = pnl >= 0 ? "red" : "blue";
          const pnlPct = Number(h.pnl_pct || 0);

          const tr = document.createElement("tr");
          tr.innerHTML = `
            <td>${h.name || ""}</td>
            <td>${h.currency || ""}</td>
            <td>${window.toLocaleNum(h.qty)}</td>
            <td>${window.toLocaleNum(h.buy_amount)}</td>
            <td>${window.toLocaleNum(h.eval_amount)}</td>
            <td style="color:${pnlColor}; font-weight:600;">${window.toLocaleNum(pnl)}</td>
            <td style="color:${pnlColor}; font-weight:600;">${pnlPct.toFixed(2)}%</td>
            <td>${h.weight || ""}</td>
          `;
          tbody.appendChild(tr);
        });
      }

      const cash = s.summary?.cash || [];
      if (cashBox) {
        if (cash.length === 0) {
          cashBox.innerHTML = "표시할 예수금 데이터가 없습니다.";
        } else {
          cashBox.innerHTML = cash
            .map((c) => {
              const cur = c.currency ? `(${c.currency})` : "";
              return `• ${c.type} ${cur}: ${window.toLocaleNum(c.eval_amount)} KRW (수량: ${window.toLocaleNum(c.qty)})`;
            })
            .join("<br>");
        }
      }
    })
    .catch((err) => {
      console.error("snapshot fetch error:", err);

      if (tbody) {
        tbody.innerHTML = `<tr><td colspan="8" style="color:red;">❌ snapshot fetch failed</td></tr>`;
      }

      if (cashBox) {
        cashBox.innerHTML = `<span style="color:red;">❌ snapshot fetch failed</span>`;
      }
    });
};

window.setupPrivacyToggle = function () {
  const btn = window.$("toggle-privacy-btn");
  if (!btn || window.AppBound.privacyToggle) return;

  let hidden = false;

  btn.addEventListener("click", () => {
    document.querySelectorAll(".privacy-sensitive").forEach((el) => {
      el.style.visibility = hidden ? "visible" : "hidden";
    });

    btn.textContent = hidden ? "🔒 정보 숨기기" : "🔓 정보 보이기";
    hidden = !hidden;
  });

  window.AppBound.privacyToggle = true;
};