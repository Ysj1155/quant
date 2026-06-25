window.initApp = function () {
  if (typeof window.setupDashboardPeriodControls === "function") {
    window.setupDashboardPeriodControls();
  }

  [
    "loadPortfolioTable",
    "loadPieChart",
    "loadAccountChart",
    "loadWatchlist",
    "setupWatchlistForm",
    "setupPrivacyToggle",
    "setupExposureModeControls",
    "setupWeeklyReportSave",
    "loadMarketCards",
  ].forEach((name) => {
    if (typeof window[name] === "function") {
      window[name]();
    }
  });

  window.AppState.loadedDashboardSections.overview = true;

  if (typeof window.loadMarketCards === "function" && !window.AppState.intervals.marketCards) {
    window.AppState.intervals.marketCards = setInterval(window.loadMarketCards, 60_000);
  }
};

window.setupDashboardPeriodControls = function () {
  document.querySelectorAll("[data-dashboard-period]").forEach((button) => {
    button.addEventListener("click", () => {
      window.setDashboardPeriod(button.dataset.dashboardPeriod || "all");
    });
  });

  const start = window.$("dashboard-period-start");
  const end = window.$("dashboard-period-end");
  const apply = window.$("dashboard-period-apply");

  if (apply) {
    apply.addEventListener("click", () => {
      window.AppState.dashboardPeriod = {
        period: "custom",
        startDate: start?.value || "",
        endDate: end?.value || "",
      };
      window.updateDashboardPeriodUi();
      window.reloadPeriodSensitivePanels();
    });
  }

  window.updateDashboardPeriodUi();
};

window.setDashboardPeriod = function (period) {
  window.AppState.dashboardPeriod = {
    period,
    startDate: "",
    endDate: "",
  };
  const start = window.$("dashboard-period-start");
  const end = window.$("dashboard-period-end");
  if (start) start.value = "";
  if (end) end.value = "";

  window.updateDashboardPeriodUi();
  window.reloadPeriodSensitivePanels();
};

window.updateDashboardPeriodUi = function () {
  const state = window.AppState.dashboardPeriod || {};
  document.querySelectorAll("[data-dashboard-period]").forEach((button) => {
    button.classList.toggle("active", button.dataset.dashboardPeriod === state.period);
  });

  const label = window.$("dashboard-period-current");
  if (!label) return;
  const labels = {
    all: "전체",
    "1w": "최근 1주",
    "1m": "최근 1개월",
    "3m": "최근 3개월",
    ytd: "올해",
    custom: "사용자 지정",
  };
  if (state.period === "custom") {
    label.textContent = `${state.startDate || "-"} ~ ${state.endDate || "-"}`;
  } else {
    label.textContent = labels[state.period] || state.period || "전체";
  }
};

window.reloadPeriodSensitivePanels = function () {
  if (typeof window.clearClientCache === "function") {
    window.clearClientCache();
  }

  window.loadAccountChart?.();

  const active = document.querySelector(".dashboard-section.active");
  const activeId = active?.id?.replace("dashboard-section-", "") || "overview";
  window.loadDashboardSectionData(activeId, { force: true });
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
      window.loadFxForecastPanel?.();
      window.AppState.dataTabLoaded = true;

      setTimeout(() => {
        ["sp500-treemap", "exchange-rate-chart"].forEach((id) => {
          window.forceRelayout(id);
        });
      }, 0);
    } else {
      ["sp500-treemap", "exchange-rate-chart"].forEach((id) => {
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

  window.loadDashboardSectionData(sectionId);

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

window.loadDashboardSectionData = function (sectionId, options = {}) {
  const force = Boolean(options.force);
  const loaded = window.AppState.loadedDashboardSections || {};
  if (!force && loaded[sectionId]) return;

  const loadersBySection = {
    overview: ["loadPortfolioTable", "loadPieChart", "loadAccountChart", "loadMarketCards"],
    quality: ["loadDataQualityPanel"],
    performance: ["loadPerformancePanel"],
    risk: ["loadRiskPanel"],
    timeline: ["loadPnlPanel", "loadTimelinePanel"],
    log: ["loadLogPanel"],
    report: ["loadWeeklyReportPanel"],
    forecast: ["loadAccountForecastPanel"],
  };

  (loadersBySection[sectionId] || []).forEach((name) => {
    if (typeof window[name] === "function") {
      window[name]();
    }
  });

  loaded[sectionId] = true;
  window.AppState.loadedDashboardSections = loaded;
};

window.addEventListener("resize", () => {
  [
    "sp500-treemap",
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
