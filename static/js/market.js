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

function getRegimeBadgeClass(regime) {
  switch (regime) {
    case "PANIC":
      return "regime-badge regime-panic";
    case "RISK_OFF":
      return "regime-badge regime-riskoff";
    case "CAUTION":
      return "regime-badge regime-caution";
    case "NORMAL":
    default:
      return "regime-badge regime-normal";
  }
}

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

function renderPanicCard(item) {
  if (!item.ok) {
    return `
      <div class="mini-card">
        <div class="mini-card-title">${item.label}</div>
        <div class="mini-card-value">N/A</div>
        <div class="mini-card-sub">data unavailable</div>
      </div>`;
  }

  const levelText =
    item.level === "panic" ? "🚨 PANIC" :
    item.level === "watch" ? "⚠️ WATCH" :
    "✅ OK";

  return `
    <div class="mini-card">
      <div class="mini-card-title">${item.label}</div>
      <div class="mini-card-value">${levelText}</div>
      <div class="mini-card-sub">${item.window_days}d 중 ${item.threshold}%↓ : ${item.count}회</div>
    </div>`;
}

function renderRegimeCard(regime) {
  if (!regime || !regime.ok) {
    return `
      <div class="mini-card regime-card">
        <div class="mini-card-title">Market Regime</div>
        <div class="mini-card-value">N/A</div>
        <div class="mini-card-sub">regime unavailable</div>
      </div>`;
  }

  const badgeClass = getRegimeBadgeClass(regime.regime);
  const reasons = Array.isArray(regime.reasons) ? regime.reasons.slice(0, 2) : [];
  const reasonText = reasons.length > 0 ? reasons.join(" / ") : (regime.guidance || "-");

  return `
    <div class="mini-card regime-card">
      <div class="mini-card-title">Market Regime</div>
      <div class="mini-card-value">
        <span class="${badgeClass}">${regime.regime}</span>
      </div>
      <div class="mini-card-sub">score: ${regime.score ?? "-"} | ${regime.guidance || ""}</div>
      <div class="mini-card-sub regime-reasons">${reasonText}</div>
    </div>`;
}

window.loadMarketCards = async function () {
  try {
    const [resIdx, resPanic, resRegime] = await Promise.all([
      fetch("/api/market/indices"),
      fetch("/api/market/panic"),
      fetch("/api/market/regime"),
    ]);

    const data = await resIdx.json();
    const panic = await resPanic.json();
    const regime = await resRegime.json();

    data.__panic = panic && panic.ok
      ? {
          ok: true,
          kind: "panic",
          label: "NASDAQ Panic",
          level: panic.level,
          count: panic.count,
          window_days: panic.window_days,
          threshold: panic.threshold_drop_pct,
          updated_at: panic.updated_at,
        }
      : { ok: false, kind: "panic", label: "NASDAQ Panic" };

    data.__regime = regime && regime.ok
      ? {
          ok: true,
          kind: "regime",
          regime: regime.regime,
          score: regime.score,
          guidance: regime.guidance,
          reasons: regime.reasons || [],
          updated_at: regime.updated_at,
        }
      : { ok: false, kind: "regime" };

    const root = window.$("market-cards");
    if (!root) return;

    const preferredOrder = ["SPX", "NDX", "DJI", "RUT", "VIX", "__panic", "__regime"];

    const cards = preferredOrder
      .filter((key) => key in data)
      .map((key) => {
        const item = data[key];

        if (item?.kind === "panic") return renderPanicCard(item);
        if (item?.kind === "regime") return renderRegimeCard(item);
        return renderIndexCard(item);
      })
      .join("");

    root.innerHTML = cards;
  } catch (e) {
    console.error("loadMarketCards failed", e);
  }
};