function signedColor(value) {
  return Number(value || 0) >= 0 ? "red" : "blue";
}

function accountValueChartStats(data) {
  const values = (data.total_values || []).map((value) => Number(value));
  const profits = (data.profits || []).map((value) => Number(value));
  const latestValue = values[values.length - 1];
  const latestProfit = profits[profits.length - 1] || 0;
  const startValue = values[0];
  const valueDelta = Number.isFinite(latestValue) && Number.isFinite(startValue)
    ? latestValue - startValue
    : 0;
  const peakValue = values.reduce(
    (peak, value) => (Number.isFinite(value) ? Math.max(peak, value) : peak),
    Number.NEGATIVE_INFINITY
  );
  const drawdownFromPeak = Number.isFinite(peakValue) && peakValue > 0 && Number.isFinite(latestValue)
    ? ((latestValue / peakValue) - 1) * 100
    : 0;

  return {
    latestValue,
    latestProfit,
    valueDelta,
    drawdownFromPeak,
  };
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
        <td>${window.escapeHTML(row.account_label ?? "")}</td>
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
  const mode = window.AppState.exposureMode || "asset_type";
  window.loadJsonAndRender(`/api/portfolio/exposure?mode=${encodeURIComponent(mode)}`, (data) => {
    if (!window.$("pie-chart")) return;

    const exposures = Array.isArray(data.exposures) ? data.exposures : [];
    const labels = exposures.map((row) => row.label || "Unknown");
    const values = exposures.map((row) => row.total_value || 0);
    const total = Number(data.total_value || 0);
    const hover = exposures.map((row) => {
      const items = (row.items || [])
        .slice(0, 6)
        .map((item) => `${item.ticker || item.type || "Unknown"}: ${window.toLocaleNum(item.evaluation_amount)} KRW`)
        .join("<br>");
      const more = (row.items || []).length > 6 ? "<br>..." : "";
      return `${row.label}<br>${window.toLocaleNum(row.total_value)} KRW<br>${window.toLocaleNum(row.weight_pct, 2)}%${items ? `<br><br>${items}${more}` : ""}`;
    });

    Plotly.newPlot(
      "pie-chart",
      [{
        labels,
        values,
        type: "pie",
        hole: 0.48,
        sort: false,
        textinfo: "label+percent",
        hoverinfo: "text",
        text: hover,
        marker: {
          line: { color: "#ffffff", width: 2 },
        },
      }],
      {
        margin: { t: 10, l: 10, r: 10, b: 10 },
        showlegend: false,
        annotations: [{
          text: `${window.toLocaleNum(total)}<br>KRW`,
          showarrow: false,
          font: { size: 13, color: "#17201b" },
        }],
      },
      { responsive: true }
    );

    const label = window.$("exposure-mode-label");
    if (label) {
      const modeLabels = {
        asset_type: "자산군 기준",
        holding: "종목 기준",
        currency: "통화 기준",
      };
      label.textContent = modeLabels[mode] || "자산군 기준";
    }
  });
};

window.setupExposureModeControls = function () {
  if (window.AppBound.exposureMode) return;

  document.querySelectorAll("[data-exposure-mode]").forEach((button) => {
    button.addEventListener("click", () => {
      window.AppState.exposureMode = button.dataset.exposureMode || "asset_type";
      document.querySelectorAll("[data-exposure-mode]").forEach((item) => {
        item.classList.toggle("active", item.dataset.exposureMode === window.AppState.exposureMode);
      });
      window.loadPieChart();
    });
  });

  window.AppBound.exposureMode = true;
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

    const stats = accountValueChartStats(data);
    const latestValue = window.toLocaleNum(stats.latestValue);
    const latestProfit = Number(stats.latestProfit || 0);
    const valueDelta = Number(stats.valueDelta || 0);
    const drawdownFromPeak = Number(stats.drawdownFromPeak || 0);
    const periodLabel = data.period?.label || "조회 구간";
    const latestDate = data.dates?.[data.dates.length - 1] || "-";
    const totalValueEl = window.$("total-value");
    if (totalValueEl) {
      totalValueEl.innerHTML = `
        <div class="mini-card-title">차트 기준 총자산</div>
        <div class="mini-card-value">${latestValue} KRW</div>
        <div class="mini-card-sub" style="color:${signedColor(latestProfit)}; font-weight:700;">
          ${window.escapeHTML(periodLabel)} 시작 대비 ${latestProfit.toFixed(2)}%
        </div>
        <div class="mini-card-sub">
          기준일 ${window.escapeHTML(latestDate)} · 변화 ${window.toLocaleNum(valueDelta)} KRW · 고점 대비 ${drawdownFromPeak.toFixed(2)}%
        </div>
      `;
    }

    const totalValueTrace = {
      x: data.dates || [],
      y: data.total_values || [],
      type: "scatter",
      mode: "lines",
      name: "총자산",
      xaxis: "x",
      yaxis: "y",
      line: { color: "#256f5b", width: 3 },
      hovertemplate: "날짜=%{x}<br>총자산=%{y:,.0f} KRW<extra></extra>",
    };

    const profitTrace = {
      x: data.dates || [],
      y: data.profits || [],
      type: "scatter",
      mode: "lines",
      name: "기간 수익률",
      xaxis: "x2",
      yaxis: "y2",
      line: { color: signedColor(latestProfit), width: 2 },
      fill: "tozeroy",
      fillcolor: latestProfit >= 0 ? "rgba(196, 56, 43, 0.10)" : "rgba(21, 91, 212, 0.10)",
      hovertemplate: "날짜=%{x}<br>기간 수익률=%{y:.2f}%<extra></extra>",
    };

    const latestMarkerTrace = {
      x: data.dates?.length ? [data.dates[data.dates.length - 1]] : [],
      y: data.total_values?.length ? [data.total_values[data.total_values.length - 1]] : [],
      type: "scatter",
      mode: "markers",
      name: "현재",
      xaxis: "x",
      yaxis: "y",
      marker: {
        color: "#17201b",
        size: 8,
        line: { color: "#ffffff", width: 2 },
      },
      hovertemplate: "현재=%{y:,.0f} KRW<extra></extra>",
    };

    const layout = {
      title: "",
      hovermode: "x unified",
      xaxis: {
        anchor: "y",
        showticklabels: false,
        matches: "x2",
      },
      yaxis: {
        title: "총자산 (KRW)",
        domain: [0.34, 1],
        tickformat: ",.0f",
        gridcolor: "#edf2ef",
        zeroline: false,
      },
      xaxis2: {
        title: "날짜",
        anchor: "y2",
        tickformat: "%Y-%m-%d",
      },
      yaxis2: {
        title: "기간 수익률 (%)",
        domain: [0, 0.24],
        gridcolor: "#edf2ef",
        zeroline: true,
        zerolinecolor: "#8a9690",
        zerolinewidth: 1,
      },
      legend: { orientation: "h", y: 1.08, x: 0 },
      margin: { t: 36, r: 24, l: 72, b: 64 },
    };

    Plotly.newPlot("profit-chart", [totalValueTrace, latestMarkerTrace, profitTrace], layout, { responsive: true }).then(() => {
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
