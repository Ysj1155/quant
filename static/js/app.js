window.initApp = function () {
  [
    "loadPortfolioTable",
    "loadPieChart",
    "loadAccountChart",
    "loadWatchlist",
    "setupWatchlistForm",
    "setupPrivacyToggle",
    "loadMarketCards",
    "loadDataQualityPanel",
    "loadPnlPanel",
    "loadTimelinePanel",
    "loadPerformancePanel",
    "loadRiskPanel",
    "loadSignalsPanel",
  ].forEach((name) => {
    if (typeof window[name] === "function") {
      window[name]();
    }
  });

  if (typeof window.loadMarketCards === "function" && !window.AppState.intervals.marketCards) {
    window.AppState.intervals.marketCards = setInterval(window.loadMarketCards, 60_000);
  }
};

window.showTab = function (tabId) {
  document.querySelectorAll(".tab-content").forEach((tab) => {
    tab.style.display = "none";
  });

  const target = window.$(tabId);
  if (target) target.style.display = "block";

  document.querySelectorAll(".nav-link").forEach((link) => {
    link.classList.remove("active");
  });

  const tabBtn = window.$(`tab-${tabId}`);
  if (tabBtn) tabBtn.classList.add("active");

  if (tabId === "data") {
    if (!window.AppState.dataTabLoaded) {
      window.loadTreemaps();
      window.loadExchangeRateChart();
      window.AppState.dataTabLoaded = true;

      setTimeout(() => {
        ["sp500-treemap", "portfolio-treemap", "exchange-rate-chart"].forEach((id) => {
          window.forceRelayout(id);
        });
      }, 0);
    } else {
      ["sp500-treemap", "portfolio-treemap", "exchange-rate-chart"].forEach((id) => {
        window.safePlotlyResize(id);
        window.forceRelayout(id);
      });
    }
  }
};

window.showDashboardSection = function (sectionId) {
  document.querySelectorAll(".dashboard-section").forEach((section) => {
    section.classList.remove("active");
  });

  document.querySelectorAll(".dashboard-subtab").forEach((button) => {
    button.classList.remove("active");
  });

  const target = window.$(`dashboard-section-${sectionId}`);
  if (target) target.classList.add("active");

  const button = window.$(`dashboard-subtab-${sectionId}`);
  if (button) button.classList.add("active");

  const chartIdsBySection = {
    overview: ["profit-chart", "pie-chart"],
    timeline: ["pnl-chart"],
    forecast: ["account-forecast-chart"],
  };

  setTimeout(() => {
    (chartIdsBySection[sectionId] || []).forEach((id) => {
      window.safePlotlyResize(id);
      window.forceRelayout(id);
    });
  }, 0);
};

window.addEventListener("resize", () => {
  [
    "sp500-treemap",
    "portfolio-treemap",
    "exchange-rate-chart",
    "profit-chart",
    "pie-chart",
    "pnl-chart",
    "account-forecast-chart",
  ].forEach((id) => {
    window.safePlotlyResize(id);
  });
});

document.addEventListener("DOMContentLoaded", () => {
  window.initApp();
});
