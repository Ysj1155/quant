async function fetchAccountForecastPlotData() {
  const horizonEl = document.getElementById("account-horizon");
  const backtestEl = document.getElementById("account-backtest-days");
  const modelEls = document.querySelectorAll(".account-model-check:checked");

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

  const res = await fetch(`/api/forecast/account/plot?${params.toString()}`);
  if (!res.ok) {
    throw new Error(`Account forecast API failed: ${res.status}`);
  }

  return await res.json();
}

function buildAccountForecastTraces(data) {
  const traces = [];

  traces.push({
    x: data.history_dates,
    y: data.actual,
    type: "scatter",
    mode: "lines",
    name: "Actual Account Value",
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

function renderAccountForecastMetrics(data) {
  const container = document.getElementById("account-forecast-metrics");
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
          <td>${m.mae != null ? m.mae.toFixed(2) : "-"}</td>
          <td>${m.rmse != null ? m.rmse.toFixed(2) : "-"}</td>
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

async function renderAccountForecastChart() {
  const chartEl = document.getElementById("account-forecast-chart");
  if (!chartEl) return;

  try {
    chartEl.innerHTML = "";

    const data = await fetchAccountForecastPlotData();
    if (!data.ok) {
      throw new Error(data.error || "unknown error");
    }

    const traces = buildAccountForecastTraces(data);

    const layout = {
      title: "Account Value Actual vs Forecast Models",
      hovermode: "x unified",
      margin: { t: 50, r: 20, b: 50, l: 70 },
      xaxis: { title: "Date" },
      yaxis: { title: "Account Value" },
      legend: { orientation: "h", y: -0.2 },
    };

    const config = {
      responsive: true,
      displayModeBar: true,
    };

    Plotly.newPlot(chartEl, traces, layout, config);
    renderAccountForecastMetrics(data);

  } catch (err) {
    chartEl.innerHTML = `<div class="alert alert-danger">계좌 예측 차트 로드 실패: ${err.message}</div>`;
  }
}

function getAccountSelectedParams() {
  const horizonEl = document.getElementById("account-horizon");
  const backtestEl = document.getElementById("account-backtest-days");
  const modelEls = document.querySelectorAll(".account-model-check:checked");

  return {
    horizon: horizonEl ? parseInt(horizonEl.value, 10) : 7,
    backtest_days: backtestEl ? parseInt(backtestEl.value, 10) : 30,
    models: Array.from(modelEls).map(el => el.value),
  };
}

async function saveAccountForecastSnapshot() {
  const statusEl = document.getElementById("account-save-status");
  if (statusEl) {
    statusEl.innerHTML = `<span class="text-muted">저장 중...</span>`;
  }

  try {
    const payload = getAccountSelectedParams();

    const res = await fetch("/api/forecast/account/save", {
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

    await loadAccountForecastHistory();

  } catch (err) {
    if (statusEl) {
      statusEl.innerHTML = `<span class="text-danger">저장 실패: ${err.message}</span>`;
    }
  }
}

async function updateAccountActuals() {
  const statusEl = document.getElementById("account-actuals-status");
  if (statusEl) {
    statusEl.innerHTML = `<span class="text-muted">실제값 반영 중...</span>`;
  }

  try {
    const res = await fetch("/api/forecast/account/update-actuals", {
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

    await loadAccountForecastHistory();

  } catch (err) {
    if (statusEl) {
      statusEl.innerHTML = `<span class="text-danger">실제값 반영 실패: ${err.message}</span>`;
    }
  }
}

async function fetchAccountForecastHistory(limit = 100) {
  const params = new URLSearchParams({
    limit: String(limit),
  });

  const res = await fetch(`/api/forecast/account/history?${params.toString()}`);
  if (!res.ok) {
    throw new Error(`Account history API failed: ${res.status}`);
  }

  return await res.json();
}

function renderAccountForecastHistoryTable(data) {
  const container = document.getElementById("account-history-table");
  if (!container) return;

  const rows = (data.rows || []).map(row => `
    <tr>
      <td>${row.run_date ?? "-"}</td>
      <td>${row.model_name ?? "-"}</td>
      <td>${row.forecast_date ?? "-"}</td>
      <td>${row.predicted_value != null ? row.predicted_value.toFixed(2) : "-"}</td>
      <td>${row.actual_value != null ? row.actual_value.toFixed(2) : "-"}</td>
      <td>${row.abs_error != null ? row.abs_error.toFixed(2) : "-"}</td>
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
          ${rows || `<tr><td colspan="8">저장된 계좌 예측 이력이 없습니다.</td></tr>`}
        </tbody>
      </table>
    </div>
  `;
}

async function loadAccountForecastHistory() {
  const container = document.getElementById("account-history-table");
  if (container) {
    container.innerHTML = `<div class="text-muted">이력 불러오는 중...</div>`;
  }

  try {
    const data = await fetchAccountForecastHistory(100);
    if (!data.ok) {
      throw new Error(data.error || "failed to load account history");
    }

    renderAccountForecastHistoryTable(data);

  } catch (err) {
    if (container) {
      container.innerHTML = `<div class="alert alert-danger">계좌 이력 로드 실패: ${err.message}</div>`;
    }
  }
}

function bindAccountForecastControls() {
  const refreshBtn = document.getElementById("account-refresh-btn");
  if (refreshBtn) {
    refreshBtn.addEventListener("click", renderAccountForecastChart);
  }

  const saveBtn = document.getElementById("account-save-btn");
  if (saveBtn) {
    saveBtn.addEventListener("click", saveAccountForecastSnapshot);
  }

  const updateActualsBtn = document.getElementById("account-update-actuals-btn");
  if (updateActualsBtn) {
    updateActualsBtn.addEventListener("click", updateAccountActuals);
  }

  const historyRefreshBtn = document.getElementById("account-history-refresh-btn");
  if (historyRefreshBtn) {
    historyRefreshBtn.addEventListener("click", loadAccountForecastHistory);
  }

  const horizonEl = document.getElementById("account-horizon");
  const backtestEl = document.getElementById("account-backtest-days");
  const modelEls = document.querySelectorAll(".account-model-check");

  if (horizonEl) horizonEl.addEventListener("change", renderAccountForecastChart);
  if (backtestEl) backtestEl.addEventListener("change", renderAccountForecastChart);
  modelEls.forEach(el => el.addEventListener("change", renderAccountForecastChart));
}

document.addEventListener("DOMContentLoaded", async () => {
  bindAccountForecastControls();
  await renderAccountForecastChart();
  await loadAccountForecastHistory();
});