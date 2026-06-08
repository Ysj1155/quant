function signedColor(value) {
  return Number(value || 0) >= 0 ? "red" : "blue";
}

window.loadPortfolioTable = function () {
  window.loadJsonAndRender("/get_portfolio_data", (data) => {
    const tbody = window.$("portfolio-table-body");
    if (!tbody) return;

    const rows = Array.isArray(data) ? data : [];
    if (rows.length === 0) {
      tbody.innerHTML = `<tr><td colspan="7">표시할 보유 종목이 없습니다.</td></tr>`;
      return;
    }

    tbody.innerHTML = "";
    rows.forEach((row) => {
      const profitRate = Number(row.profit_rate || 0);
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td>${window.escapeHTML(row.account_number ?? "")}</td>
        <td>${window.escapeHTML(row.ticker ?? "")}</td>
        <td>${window.toLocaleNum(row.quantity)}</td>
        <td>${window.toLocaleNum(row.purchase_amount)} KRW</td>
        <td>${window.toLocaleNum(row.evaluation_amount)} KRW</td>
        <td style="color:${signedColor(row.profit_loss)}; font-weight:600;">${window.toLocaleNum(row.profit_loss)} KRW</td>
        <td style="color:${signedColor(profitRate)}; font-weight:700;">${profitRate.toFixed(2)}%</td>
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
      [{
        labels: data.labels || [],
        values: data.values || [],
        type: "pie",
        textinfo: "label+percent",
        hoverinfo: "label+value+percent",
      }],
      {
        margin: { t: 10, l: 10, r: 10, b: 10 },
        showlegend: false,
      },
      { responsive: true }
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
  window.loadJsonAndRender(window.dashboardApiUrl("/get_account_value_data"), (data) => {
    if (!window.$("profit-chart")) return;

    const latestValue = window.toLocaleNum(data.latest_value);
    const latestProfit = Number(data.latest_profit || 0);
    const totalValueEl = window.$("total-value");
    if (totalValueEl) {
      totalValueEl.innerHTML = `
        <div class="mini-card-title">현재 총자산</div>
        <div class="mini-card-value">${latestValue} KRW</div>
        <div class="mini-card-sub" style="color:${signedColor(latestProfit)}; font-weight:700;">
          시작 대비 ${latestProfit.toFixed(2)}%
        </div>
      `;
    }

    const totalValueTrace = {
      x: data.dates || [],
      y: data.total_values || [],
      type: "scatter",
      mode: "lines+markers",
      name: "총자산",
      yaxis: "y1",
      line: { color: "#256f5b", width: 3 },
      marker: { size: 5 },
    };

    const profitTrace = {
      x: data.dates || [],
      y: data.profits || [],
      type: "scatter",
      mode: "lines",
      name: "수익률",
      yaxis: "y2",
      line: { color: "#2f5f98", dash: "dot", width: 2 },
    };

    const layout = {
      title: "",
      hovermode: "x unified",
      xaxis: { title: "날짜" },
      yaxis: {
        title: "총자산 (KRW)",
        side: "left",
        showgrid: false,
      },
      yaxis2: {
        title: "수익률 (%)",
        overlaying: "y",
        side: "right",
        showgrid: false,
      },
      legend: { orientation: "h", y: -0.18 },
      margin: { t: 18, r: 50, l: 68, b: 64 },
    };

    Plotly.newPlot("profit-chart", [totalValueTrace, profitTrace], layout, { responsive: true }).then(() => {
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
    meta.innerHTML = `선택 날짜: <strong>${window.escapeHTML(date)}</strong>`;
  }

  if (!root) return;

  root.innerHTML = `
    <div class="mini-card">
      <div class="mini-card-title">주식 평가금액</div>
      <div class="mini-card-value">${window.toLocaleNum(stockSum)} KRW</div>
      <div class="mini-card-sub">스냅샷 기준</div>
    </div>
  `;
};

window.loadSnapshotDetail = function (date) {
  const tbody = window.$("snapshot-table-body");
  const cashBox = window.$("snapshot-cash");

  if (tbody) {
    tbody.innerHTML = `<tr><td colspan="8">불러오는 중...</td></tr>`;
  }

  if (cashBox) {
    cashBox.innerHTML = `불러오는 중...`;
  }

  fetch(`/api/snapshot?date=${encodeURIComponent(date)}`)
    .then((response) => response.json())
    .then((snapshot) => {
      if (snapshot.error) {
        const message = window.escapeHTML(snapshot.error);
        if (tbody) {
          tbody.innerHTML = `<tr><td colspan="8" style="color:red;">${message}</td></tr>`;
        }
        if (cashBox) {
          cashBox.innerHTML = `<span style="color:red;">${message}</span>`;
        }
        return;
      }

      window.renderSnapshotSummary(snapshot.date, snapshot.summary?.stock_eval_sum ?? 0);

      const rows = snapshot.holdings || [];
      if (!tbody) return;

      if (rows.length === 0) {
        tbody.innerHTML = `<tr><td colspan="8">보유 종목이 없습니다.</td></tr>`;
      } else {
        tbody.innerHTML = "";
        rows.forEach((holding) => {
          const pnl = Number(holding.pnl || 0);
          const pnlPct = Number(holding.pnl_pct || 0);
          const tr = document.createElement("tr");
          tr.innerHTML = `
            <td>${window.escapeHTML(holding.name || "")}</td>
            <td>${window.escapeHTML(holding.currency || "")}</td>
            <td>${window.toLocaleNum(holding.qty)}</td>
            <td>${window.toLocaleNum(holding.buy_amount)}</td>
            <td>${window.toLocaleNum(holding.eval_amount)}</td>
            <td style="color:${signedColor(pnl)}; font-weight:600;">${window.toLocaleNum(pnl)}</td>
            <td style="color:${signedColor(pnlPct)}; font-weight:600;">${pnlPct.toFixed(2)}%</td>
            <td>${window.escapeHTML(holding.weight || "")}</td>
          `;
          tbody.appendChild(tr);
        });
      }

      const cash = snapshot.summary?.cash || [];
      if (cashBox) {
        if (cash.length === 0) {
          cashBox.innerHTML = "표시할 예수금 데이터가 없습니다.";
        } else {
          cashBox.innerHTML = cash
            .map((item) => {
              const currency = item.currency ? `(${window.escapeHTML(item.currency)})` : "";
              return `${window.escapeHTML(item.type)} ${currency}: ${window.toLocaleNum(item.eval_amount)} KRW (수량: ${window.toLocaleNum(item.qty)})`;
            })
            .join("<br>");
        }
      }
    })
    .catch((err) => {
      console.error("snapshot fetch error:", err);

      if (tbody) {
        tbody.innerHTML = `<tr><td colspan="8" style="color:red;">스냅샷을 불러오지 못했습니다.</td></tr>`;
      }

      if (cashBox) {
        cashBox.innerHTML = `<span style="color:red;">스냅샷을 불러오지 못했습니다.</span>`;
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

    btn.textContent = hidden ? "정보 숨기기" : "정보 보이기";
    hidden = !hidden;
  });

  window.AppBound.privacyToggle = true;
};
