window.loadTreemaps = function () {
  window.loadJsonAndRender("/get_treemap_data", (data) => {
    const fig = {
      type: "treemap",
      labels: data.sectors,
      parents: Array(data.sectors.length).fill(""),
      values: data.changes.map((v) => Math.abs(v)),
      textinfo: "label+value",
      marker: { colors: data.changes, colorscale: "RdYlGn", cmin: -3, cmax: 3 },
    };

    Plotly.newPlot(
      "sp500-treemap",
      [fig],
      { margin: { t: 10, l: 10, r: 10, b: 10 }, height: 440, autosize: true },
      { responsive: true }
    ).then(() => window.forceRelayout("sp500-treemap"));
  });

  window.loadJsonAndRender("/get_portfolio_sector_data", (data) => {
    const sectors = Object.keys(data);
    const values = sectors.map((s) => data[s].total_value);

    const hover = sectors.map((s) => {
      const stocks = (data[s].stocks || [])
        .map((x) => `${x.ticker || "Unknown"}: $${window.toLocaleNum(x.price)}`)
        .join("<br>");
      return `${s}<br>${stocks}`;
    });

    Plotly.newPlot(
      "portfolio-treemap",
      [
        {
          type: "treemap",
          labels: sectors,
          parents: Array(sectors.length).fill(""),
          values,
          text: hover,
          hoverinfo: "text",
        },
      ],
      { margin: { t: 10, l: 10, r: 10, b: 10 }, height: 440, autosize: true },
      { responsive: true }
    ).then(() => window.forceRelayout("portfolio-treemap"));
  });
};

window.loadExchangeRateChart = function () {
  window.loadJsonAndRender("/get_exchange_rate_data", (data) => {
    Plotly.newPlot(
      "exchange-rate-chart",
      [
        {
          x: data.dates,
          y: data.rates,
          type: "scatter",
          mode: "lines",
          name: "USD/KRW",
          connectgaps: false,
        },
      ],
      { margin: { t: 10, r: 10, l: 40, b: 40 }, height: 440, autosize: true },
      { responsive: true }
    ).then(() => window.forceRelayout("exchange-rate-chart"));
  });
};

function renderIndexCard(item) {
  if (!item.ok) {
    return `
      <div class="mini-card">
        <div class="mini-card-title">${item.label}</div>
        <div class="mini-card-value">N/A</div>
        <div class="mini-card-sub">data unavailable</div>
      </div>`;
  }

  const sign = Number(item.change_pct || 0) >= 0 ? "+" : "";
  return `
    <div class="mini-card">
      <div class="mini-card-title">${item.label}</div>
      <div class="mini-card-value">${window.toLocaleNum(item.last)}</div>
      <div class="mini-card-sub">${sign}${Number(item.change_pct).toFixed(2)}%</div>
    </div>`;
}

window.loadMarketCards = async function () {
  try {
    const resIdx = await fetch("/api/market/indices");
    const data = await resIdx.json();

    const root = window.$("market-cards");
    if (!root) return;

    const preferredOrder = ["SPX", "NDX", "DJI", "RUT", "VIX"];

    const cards = preferredOrder
      .filter((key) => key in data)
      .map((key) => {
        const item = data[key];

        return renderIndexCard(item);
      })
      .join("");

    root.innerHTML = cards;
  } catch (e) {
    console.error("loadMarketCards failed", e);
  }
};
