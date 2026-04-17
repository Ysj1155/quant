async function fetchFxForecastPlotData() {
  const horizonEl = document.getElementById("fx-horizon");
  const backtestEl = document.getElementById("fx-backtest-days");
  const modelEls = document.querySelectorAll(".fx-model-check:checked");

  const horizon = horizonEl ? horizonEl.value : "7";
  const backtestDays = backtestEl ? backtestEl.value : "30";
  const models = Array.from(modelEls).map(el => el.value);

  const params = new URLSearchParams({
    horizon,
    backtest_days: backtestDays,
  });

  if (models.length > 0) {
    params.set("models", models.join(","));
  }

  const res = await fetch(`/api/forecast/fx/plot?${params.toString()}`);
  if (!res.ok) {
    throw new Error(`FX forecast API failed: ${res.status}`);
  }

  return await res.json();
}

function buildFxForecastTraces(data) {
  const traces = [];

  traces.push({
    x: data.history_dates,
    y: data.actual,
    type: "scatter",
    mode: "lines",
    name: "Actual USD/KRW",
    line: { width: 4 },
    connectgaps: false,
  });

  const modelNames = Object.keys(data.models || {});
  for (const modelName of modelNames) {
    const model = data.models[modelName];
    if (!model.ok) continue;

    traces.push({
      x: model.full_dates,
      y: model.full_fitted_plus_forecast,
      type: "scatter",
      mode: "lines",
      name: modelName.toUpperCase(),
      line: { width: 1.5, dash: "solid" },
      opacity: 0.8,
      connectgaps: false,
    });
  }

  if (data.ensemble && Array.isArray(data.ensemble.full_path)) {
    traces.push({
      x: data.ensemble.full_dates,
      y: data.ensemble.full_path,
      type: "scatter",
      mode: "lines",
      name: "ENSEMBLE",
      line: { width: 3, dash: "dot" },
      opacity: 0.95,
      connectgaps: false,
    });
  }

  return traces;
}

function renderFxForecastMetrics(data) {
  const container = document.getElementById("fx-forecast-metrics");
  if (!container) return;

  const models = data.models || {};
  const weights = data.ensemble?.weights || {};

  const rows = Object.entries(models)
    .filter(([_, model]) => model.ok)
    .map(([name, model]) => {
      const m = model.metrics || {};
      const weight = weights[name] ?? null;

      return `
        <tr>
          <td>${name.toUpperCase()}</td>
          <td>${m.mae != null ? m.mae.toFixed(4) : "-"}</td>
          <td>${m.rmse != null ? m.rmse.toFixed(4) : "-"}</td>
          <td>${m.mape != null ? m.mape.toFixed(4) + "%" : "-"}</td>
          <td>${m.directional_accuracy != null ? m.directional_accuracy.toFixed(2) + "%" : "-"}</td>
          <td>${weight != null ? weight.toFixed(4) : "-"}</td>
        </tr>
      `;
    })
    .join("");

  container.innerHTML = `
    <div style="overflow:auto;">
      <table class="table table-bordered table-sm">
        <thead>
          <tr>
            <th>Model</th>
            <th>MAE</th>
            <th>RMSE</th>
            <th>MAPE</th>
            <th>Direction Acc.</th>
            <th>Ensemble Weight</th>
          </tr>
        </thead>
        <tbody>
          ${rows || `<tr><td colspan="6">표시할 모델이 없습니다.</td></tr>`}
        </tbody>
      </table>
    </div>
  `;
}

async function renderFxForecastChart() {
  const chartEl = document.getElementById("exchange-rate-chart");
  if (!chartEl) return;

  try {
    chartEl.innerHTML = "";
    const data = await fetchFxForecastPlotData();

    if (!data.ok) {
      throw new Error(data.error || "unknown error");
    }

    const traces = buildFxForecastTraces(data);

    const layout = {
      title: "USD/KRW Actual vs Forecast Models",
      hovermode: "x unified",
      margin: { t: 50, r: 20, b: 50, l: 60 },
      xaxis: { title: "Date" },
      yaxis: { title: "Exchange Rate" },
      legend: { orientation: "h", y: -0.2 },
    };

    const config = {
      responsive: true,
      displayModeBar: true,
    };

    Plotly.newPlot(chartEl, traces, layout, config);
    renderFxForecastMetrics(data);

  } catch (err) {
    chartEl.innerHTML = `<div class="alert alert-danger">환율 예측 차트 로드 실패: ${err.message}</div>`;
  }
}

function getFxSelectedParams() {
  const horizonEl = document.getElementById("fx-horizon");
  const backtestEl = document.getElementById("fx-backtest-days");
  const modelEls = document.querySelectorAll(".fx-model-check:checked");

  return {
    horizon: horizonEl ? parseInt(horizonEl.value, 10) : 7,
    backtest_days: backtestEl ? parseInt(backtestEl.value, 10) : 30,
    models: Array.from(modelEls).map(el => el.value),
  };
}

async function saveFxForecastSnapshot() {
  const statusEl = document.getElementById("fx-save-status");
  if (statusEl) {
    statusEl.innerHTML = `<span class="text-muted">저장 중...</span>`;
  }

  try {
    const payload = getFxSelectedParams();

    const res = await fetch("/api/forecast/fx/save", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    });

    const data = await res.json();

    if (!res.ok || !data.ok) {
      throw new Error(data.error || `save failed: ${res.status}`);
    }

    if (statusEl) {
      statusEl.innerHTML = `
        <span class="text-success">
          저장 완료. run_date=${data.run_date}, inserted=${data.inserted}, skipped=${data.skipped}
        </span>
      `;
    }

    await loadFxForecastHistory();

  } catch (err) {
    if (statusEl) {
      statusEl.innerHTML = `<span class="text-danger">저장 실패: ${err.message}</span>`;
    }
  }
}

async function updateFxActuals() {
  const statusEl = document.getElementById("fx-actuals-status");
  if (statusEl) {
    statusEl.innerHTML = `<span class="text-muted">실제값 반영 중...</span>`;
  }

  try {
    const res = await fetch("/api/forecast/fx/update-actuals", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({}),
    });

    const data = await res.json();

    if (!res.ok || !data.ok) {
      throw new Error(data.error || `update actuals failed: ${res.status}`);
    }

    if (statusEl) {
      statusEl.innerHTML = `
        <span class="text-success">
          실제값 반영 완료. updated=${data.updated}
        </span>
      `;
    }

    await loadFxForecastHistory();

  } catch (err) {
    if (statusEl) {
      statusEl.innerHTML = `<span class="text-danger">실제값 반영 실패: ${err.message}</span>`;
    }
  }
}

async function fetchFxForecastHistory(limit = 100) {
  const params = new URLSearchParams({
    limit: String(limit),
  });

  const res = await fetch(`/api/forecast/fx/history?${params.toString()}`);
  if (!res.ok) {
    throw new Error(`FX history API failed: ${res.status}`);
  }

  return await res.json();
}

function renderFxForecastHistoryTable(data) {
  const container = document.getElementById("fx-history-table");
  if (!container) return;

  const rows = (data.rows || []).map(row => `
    <tr>
      <td>${row.run_date ?? "-"}</td>
      <td>${row.model_name ?? "-"}</td>
      <td>${row.forecast_date ?? "-"}</td>
      <td>${row.predicted_value != null ? row.predicted_value.toFixed(4) : "-"}</td>
      <td>${row.actual_value != null ? row.actual_value.toFixed(4) : "-"}</td>
      <td>${row.abs_error != null ? row.abs_error.toFixed(4) : "-"}</td>
      <td>${row.horizon ?? "-"}</td>
      <td>${row.backtest_days ?? "-"}</td>
    </tr>
  `).join("");

  container.innerHTML = `
    <div style="overflow:auto;">
      <table class="table table-bordered table-sm">
        <thead>
          <tr>
            <th>Run Date</th>
            <th>Model</th>
            <th>Forecast Date</th>
            <th>Predicted</th>
            <th>Actual</th>
            <th>Abs Error</th>
            <th>Horizon</th>
            <th>Backtest</th>
          </tr>
        </thead>
        <tbody>
          ${rows || `<tr><td colspan="8">저장된 예측 이력이 없습니다.</td></tr>`}
        </tbody>
      </table>
    </div>
  `;
}

async function loadFxForecastHistory() {
  const container = document.getElementById("fx-history-table");
  if (container) {
    container.innerHTML = `<div class="text-muted">이력 불러오는 중...</div>`;
  }

  try {
    const data = await fetchFxForecastHistory(100);
    if (!data.ok) {
      throw new Error(data.error || "failed to load history");
    }

    renderFxForecastHistoryTable(data);

  } catch (err) {
    if (container) {
      container.innerHTML = `<div class="alert alert-danger">이력 로드 실패: ${err.message}</div>`;
    }
  }
}

function bindFxForecastControls() {
  const refreshBtn = document.getElementById("fx-refresh-btn");
  if (refreshBtn) {
    refreshBtn.addEventListener("click", renderFxForecastChart);
  }

  const saveBtn = document.getElementById("fx-save-btn");
  if (saveBtn) {
    saveBtn.addEventListener("click", saveFxForecastSnapshot);
  }

  const updateActualsBtn = document.getElementById("fx-update-actuals-btn");
  if (updateActualsBtn) {
    updateActualsBtn.addEventListener("click", updateFxActuals);
  }

  const historyRefreshBtn = document.getElementById("fx-history-refresh-btn");
  if (historyRefreshBtn) {
    historyRefreshBtn.addEventListener("click", loadFxForecastHistory);
  }

  const horizonEl = document.getElementById("fx-horizon");
  const backtestEl = document.getElementById("fx-backtest-days");
  const modelEls = document.querySelectorAll(".fx-model-check");

  if (horizonEl) horizonEl.addEventListener("change", renderFxForecastChart);
  if (backtestEl) backtestEl.addEventListener("change", renderFxForecastChart);
  modelEls.forEach(el => el.addEventListener("change", renderFxForecastChart));
}

document.addEventListener("DOMContentLoaded", async () => {
  bindFxForecastControls();
  await renderFxForecastChart();
  await loadFxForecastHistory();
});