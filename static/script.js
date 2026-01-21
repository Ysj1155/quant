document.addEventListener("DOMContentLoaded", () => {
  window.showTab = showTab; // HTML onclick에서 사용
  initApp();
});

// -------------------- State --------------------
let dataTabLoaded = false;

// Plotly 이벤트 중복 바인딩 방지용
const _bound = {
  profitChartClick: false,
};

// -------------------- Small Utils --------------------
function $(id) {
  return document.getElementById(id);
}

function safeText(el, text) {
  if (!el) return;
  el.textContent = text;
}

function safeHTML(el, html) {
  if (!el) return;
  el.innerHTML = html;
}

function normalizeDate(x) {
  // Plotly가 Date 객체/문자열 둘 다 줄 수 있으니 문자열로 강제
  return String(x).slice(0, 10); // "YYYY-MM-DD"
}

function formatMarketCap(value) {
  if (value == null || value === "" || Number.isNaN(Number(value))) return "N/A";
  const v = Number(value);
  const billion = 1_000_000_000;
  const million = 1_000_000;
  if (v >= billion) return (v / billion).toFixed(1) + "B";
  if (v >= million) return (v / million).toFixed(1) + "M";
  return v.toLocaleString();
}

function toLocaleNum(x, digits = 0) {
  const n = Number(x);
  if (!isFinite(n)) return "N/A";
  return n.toLocaleString(undefined, { maximumFractionDigits: digits });
}

// 공통 fetch 래퍼
function loadJsonAndRender(url, onSuccess, onError) {
  fetchJsonCached(url, 15000)
    .then((data) => {
      if (data?.error) {
        console.error(`❌ Error from ${url}:`, data.error);
        onError && onError(data.error);
      } else {
        onSuccess(data);
      }
    })
    .catch((err) => {
      console.error(`❌ Fetch failed from ${url}:`, err);
      onError && onError(err);
    });
}

// -------------------- Plotly Layout Helpers --------------------
function forceRelayout(id) {
  const el = $(id);
  if (!el) return;

  const parent = el.closest(".chart-card") || el.parentElement || el;
  const cs = getComputedStyle(parent);
  const padX = (parseFloat(cs.paddingLeft) || 0) + (parseFloat(cs.paddingRight) || 0);
  const contentW = Math.max(320, Math.floor(parent.clientWidth - padX));

  const isSquare = el.classList.contains("square-plot");
  const aspectAttr = el.dataset.aspect ? parseFloat(el.dataset.aspect) : null;
  const aspect = isSquare ? 1 : (aspectAttr || 0.56);

  const h = Math.max(240, Math.round(contentW * aspect));

  const mTop = parseInt(el.dataset.marginT || 10);
  const mRight = parseInt(el.dataset.marginR || 10);
  const mLeft = parseInt(el.dataset.marginL || 40);
  const mBottom = parseInt(el.dataset.marginB || 60);

  try {
    Plotly.relayout(el, {
      width: contentW,
      height: h,
      margin: { t: mTop, r: mRight, l: mLeft, b: mBottom },
      xaxis: { automargin: true },
      yaxis: { automargin: true },
    });
  } catch (e) {
    // plot이 아직 생성 전일 수도 있음
  }
}

function safePlotlyResize(id) {
  const el = $(id);
  if (!el) return;
  try {
    Plotly.Plots.resize(el);
  } catch (e) {}
}

// -------------------- App Init --------------------
function initApp() {
  loadPortfolioTable();
  loadPieChart();
  loadAccountChart();

  loadWatchlist();
  setupWatchlistForm();

  setupPrivacyToggle();

  loadMarketCards();
  setInterval(loadMarketCards, 60_000);

  // PnL panel (전체 스냅샷 기반 라인 + 이벤트 테이블)
  loadPnlPanel();
}

window.addEventListener("resize", () => {
  ["sp500-treemap", "portfolio-treemap", "exchange-rate-chart", "profit-chart", "pie-chart", "pnl-chart"]
    .forEach((id) => safePlotlyResize(id));
});

// -------------------- Tab UI --------------------
function showTab(tabId) {
  document.querySelectorAll(".tab-content").forEach((tab) => (tab.style.display = "none"));
  const target = $(tabId);
  if (target) target.style.display = "block";

  document.querySelectorAll(".nav-link").forEach((link) => link.classList.remove("active"));
  const tabBtn = $(`tab-${tabId}`);
  if (tabBtn) tabBtn.classList.add("active");

  if (tabId === "data") {
    if (!dataTabLoaded) {
      loadTreemaps();
      loadExchangeRateChart();
      dataTabLoaded = true;
      setTimeout(() => {
        ["sp500-treemap", "portfolio-treemap", "exchange-rate-chart"].forEach(forceRelayout);
      }, 0);
    } else {
      ["sp500-treemap", "portfolio-treemap", "exchange-rate-chart"].forEach((id) => {
        safePlotlyResize(id);
        forceRelayout(id);
      });
    }
  }
}

// ---- client cache + inflight dedupe ----
const _clientCache = new Map();   // url -> { exp, data }
const _inflight = new Map();      // url -> Promise

function fetchJsonCached(url, ttlMs = 15000) {
  const now = Date.now();
  const hit = _clientCache.get(url);
  if (hit && hit.exp > now) return Promise.resolve(hit.data);

  const inflight = _inflight.get(url);
  if (inflight) return inflight;

  const p = fetch(url)
    .then((r) => r.json())
    .then((data) => {
      _clientCache.set(url, { exp: now + ttlMs, data });
      return data;
    })
    .finally(() => _inflight.delete(url));

  _inflight.set(url, p);
  return p;
}

// -------------------- Data: Portfolio Table --------------------
function loadPortfolioTable() {
  loadJsonAndRender("/get_portfolio_data", (data) => {
    const tbody = $("portfolio-table-body");
    if (!tbody) return;

    tbody.innerHTML = "";
    data.forEach((row) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td>${row.account_number ?? ""}</td>
        <td>${row.ticker ?? ""}</td>
        <td>${row.quantity ?? ""}</td>
        <td>${toLocaleNum(row.purchase_amount)} KRW</td>
        <td>${toLocaleNum(row.evaluation_amount)} KRW</td>
        <td>${toLocaleNum(row.profit_loss)} KRW</td>
        <td style="color:${Number(row.profit_rate) >= 0 ? "red" : "blue"}; font-weight:bold;">
          ${Number(row.profit_rate || 0).toFixed(2)}%
        </td>`;
      tbody.appendChild(tr);
    });
  });
}

// -------------------- Chart: Pie --------------------
function loadPieChart() {
  loadJsonAndRender("/get_pie_chart_data", (data) => {
    Plotly.newPlot(
      "pie-chart",
      [
        {
          labels: data.labels,
          values: data.values,
          type: "pie",
        },
      ],
      { margin: { t: 10 } },
      { responsive: true }
    );

    const totalEl = $("total-value");
    if (totalEl) totalEl.innerText = `Total Value: ${data.total_value}`;
  });
}

// -------------------- Date selection (snapshot + pnl detail) --------------------
function onDateSelected(dateStr) {
  // 아래 2개는 “날짜 클릭 시 같이 움직여야 하는 것들”
  loadSnapshotDetail(dateStr);
  loadPnlForDate(dateStr);
}

// -------------------- Chart: Account value & Profit --------------------
function loadAccountChart() {
  loadJsonAndRender("/get_account_value_data", (data) => {
    // Header
    const latestValue = toLocaleNum(data.latest_value);
    const latestProfit = Number(data.latest_profit || 0).toFixed(2);
    const profitColor = Number(data.latest_profit || 0) >= 0 ? "red" : "blue";

    const headEl = $("total-value");
    if (headEl) {
      headEl.innerHTML = `
        Total Value: ${latestValue} KRW
        <span style="color:${profitColor}; font-weight:bold;">(${latestProfit}%)</span>
      `;
    }

    // Traces
    const totalValueTrace = {
      x: data.dates,
      y: data.total_values,
      type: "scatter",
      mode: "lines+markers",
      name: "Total Account Value",
      yaxis: "y1",
    };

    const profitTrace = {
      x: data.dates,
      y: data.profits,
      type: "scatter",
      mode: "lines",
      name: "Account Profit (%)",
      yaxis: "y2",
      line: { dash: "dot" },
    };

    const layout = {
      title: "Portfolio Total Value & Profit",
      xaxis: { title: "Date" },
      yaxis: { title: "Total Value (KRW)", side: "left", showgrid: false },
      yaxis2: { title: "Profit (%)", overlaying: "y", side: "right", showgrid: false },
      margin: { t: 40, r: 10, l: 50, b: 40 },
    };

    Plotly.newPlot("profit-chart", [totalValueTrace, profitTrace], layout, { responsive: true }).then(() => {
      // 1) 기본: 최신 날짜 자동 선택
      const latestDate = data.dates?.[data.dates.length - 1];
      if (latestDate) onDateSelected(normalizeDate(latestDate));

      // 2) 클릭 바인딩 1회만
      const chartEl = $("profit-chart");
      if (chartEl && !_bound.profitChartClick) {
        chartEl.on("plotly_click", (ev) => {
          const x = ev?.points?.[0]?.x;
          if (!x) return;
          onDateSelected(normalizeDate(x));
        });
        _bound.profitChartClick = true;
      }
    });
  });
}

// -------------------- Snapshot Detail --------------------
function renderSnapshotSummary(date, stockSum) {
  const root = $("snapshot-summary");
  const meta = $("snapshot-meta");

  if (meta) meta.innerHTML = `선택 날짜: <strong>${date}</strong>`;
  if (!root) return;

  const cards = [
    { label: "주식 평가금액 합", value: `${toLocaleNum(stockSum)} KRW`, sub: "스냅샷 기준" },
  ];

  root.innerHTML = cards
    .map(
      (c) => `
      <div class="card">
        <div class="card-title">${c.label}</div>
        <div class="card-value">${c.value}</div>
        <div class="card-sub">${c.sub}</div>
      </div>
    `
    )
    .join("");
}

function loadSnapshotDetail(date) {
  const tbody = $("snapshot-table-body");
  const cashBox = $("snapshot-cash");

  if (tbody) tbody.innerHTML = `<tr><td colspan="8">로딩중...</td></tr>`;
  if (cashBox) cashBox.innerHTML = `로딩중...`;

  fetch(`/api/snapshot?date=${encodeURIComponent(date)}`)
    .then((r) => r.json())
    .then((s) => {
      if (s.error) {
        if (tbody) tbody.innerHTML = `<tr><td colspan="8" style="color:red;">❌ ${s.error}</td></tr>`;
        if (cashBox) cashBox.innerHTML = `<span style="color:red;">❌ ${s.error}</span>`;
        return;
      }

      renderSnapshotSummary(s.date, s.summary?.stock_eval_sum ?? 0);

      // holdings table
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
            <td>${toLocaleNum(h.qty)}</td>
            <td>${toLocaleNum(h.buy_amount)}</td>
            <td>${toLocaleNum(h.eval_amount)}</td>
            <td style="color:${pnlColor}; font-weight:600;">${toLocaleNum(pnl)}</td>
            <td style="color:${pnlColor}; font-weight:600;">${pnlPct.toFixed(2)}%</td>
            <td>${h.weight || ""}</td>
          `;
          tbody.appendChild(tr);
        });
      }

      // cash
      const cash = s.summary?.cash || [];
      if (cashBox) {
        if (cash.length === 0) {
          cashBox.innerHTML = "표시할 예수금 데이터가 없습니다.";
        } else {
          cashBox.innerHTML = cash
            .map((c) => {
              const cur = c.currency ? `(${c.currency})` : "";
              return `• ${c.type} ${cur}: ${toLocaleNum(c.eval_amount)} KRW (수량: ${toLocaleNum(c.qty)})`;
            })
            .join("<br>");
        }
      }
    })
    .catch((err) => {
      console.error("snapshot fetch error:", err);
      if (tbody) tbody.innerHTML = `<tr><td colspan="8" style="color:red;">❌ snapshot fetch failed</td></tr>`;
      if (cashBox) cashBox.innerHTML = `<span style="color:red;">❌ snapshot fetch failed</span>`;
    });
}

// -------------------- Treemaps --------------------
function loadTreemaps() {
  // SP500 섹터 treemap
  loadJsonAndRender("/get_treemap_data", (data) => {
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
    ).then(() => forceRelayout("sp500-treemap"));
  });

  // 내 포트폴리오 섹터 분포 treemap
  loadJsonAndRender("/get_portfolio_sector_data", (data) => {
    const sectors = Object.keys(data);
    const values = sectors.map((s) => data[s].total_value);

    const hover = sectors.map((s) => {
      const stocks = (data[s].stocks || [])
        .map((x) => `${x.ticker || "Unknown"}: $${toLocaleNum(x.price)}`)
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
    ).then(() => forceRelayout("portfolio-treemap"));
  });
}

// -------------------- Exchange Rate Chart --------------------
function loadExchangeRateChart() {
  loadJsonAndRender("/get_exchange_rate_data", (data) => {
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
    ).then(() => forceRelayout("exchange-rate-chart"));
  });
}

// -------------------- Watchlist --------------------
function loadWatchlist() {
  loadJsonAndRender("/get_watchlist", (data) => {
    const ul = $("watchlist-items");
    if (!ul) return;

    ul.innerHTML = "";
    (data.watchlist || []).forEach((t) => ul.appendChild(createWatchlistItem(t)));
  });
}

function setupWatchlistForm() {
  const form = $("watchlist-form");
  if (!form) return;

  form.addEventListener("submit", (e) => {
    e.preventDefault();
    const input = $("ticker");
    const ticker = (input?.value || "").trim().toUpperCase();
    if (!ticker) return;

    fetch("/add_watchlist", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ticker }),
    })
      .then((r) => r.json())
      .then((res) => {
        if (res.error) return alert(res.error);
        $("watchlist-items")?.appendChild(createWatchlistItem(ticker));
        if (input) input.value = "";
      });
  });
}

function createWatchlistItem(ticker) {
  const li = document.createElement("li");
  li.className = "list-group-item";
  li.style.display = "flex";
  li.style.justifyContent = "space-between";
  li.style.alignItems = "center";

  const span = document.createElement("span");
  span.textContent = ticker;
  span.style.cursor = "pointer";
  span.title = "클릭하면 분석 정보를 확인합니다";
  span.addEventListener("click", () => openStockDetail(ticker));

  const del = document.createElement("button");
  del.textContent = "❌";
  del.style.border = "none";
  del.style.background = "none";
  del.style.cursor = "pointer";
  del.style.color = "red";
  del.title = "관심 목록에서 제거";
  del.addEventListener("click", () => {
    if (!confirm(`${ticker} 티커를 관심 목록에서 삭제할까요?`)) return;
    fetch("/remove_watchlist", {
      method: "DELETE",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ticker }),
    })
      .then((r) => r.json())
      .then((res) => {
        if (res.error) return alert(res.error);
        li.remove();
      });
  });

  li.appendChild(span);
  li.appendChild(del);
  return li;
}

// -------------------- Stock Detail Panel --------------------
function openStockDetail(ticker) {
  const panel = $("stock-detail-panel");
  const content = $("detail-content");
  if (!panel || !content) return;

  content.innerHTML = `<p>🔄 데이터 로딩중...</p>`;

  fetch(`/get_stock_detail_finnhub?ticker=${encodeURIComponent(ticker)}`)
    .then((r) => r.json())
    .then((data) => {
      if (data.error) {
        content.innerHTML = `<p style="color:red;">❌ ${data.error}</p>`;
        return;
      }

      renderFinnhubBasic(content, ticker, data);
      renderValuationBox(content, ticker, data);
      renderKisCandleChart(content, ticker);
    })
    .catch((err) => {
      console.error("Finnhub fetch error:", err);
      content.innerHTML = `<p style="color:red;">❌ Finnhub 데이터 요청 실패</p>`;
    });

  panel.style.display = "block";
}

function renderFinnhubBasic(root, ticker, data) {
  const price = data.price?.c ?? "N/A";
  const marketCap = data.profile?.marketCapitalization ?? "N/A";
  const per = data.metrics?.metric?.peTTM ?? "N/A";
  const dividendYield = (data.metrics?.metric?.currentDividendYieldTTM ?? 0) * 100;

  root.innerHTML = `
    <h5>${data.profile?.name ?? ""} (${ticker})</h5>
    <p><strong>📈 현재가:</strong> $${price}</p>
    <p><strong>💰 시가총액:</strong> ${formatMarketCap(marketCap)}</p>
    <p><strong>📊 PER:</strong> ${per}</p>
    <p><strong>📤 배당률:</strong> ${Number(dividendYield).toFixed(2)}%</p>
  `;
}

function renderValuationBox(root, ticker, finnhubData) {
  const valBox = document.createElement("div");
  valBox.style.marginTop = "12px";
  valBox.innerHTML = `<p>🔄 적정주가/목표가 계산중...</p>`;
  root.appendChild(valBox);

  const cur = finnhubData.price?.c ?? null;
  const curNum = cur == null || cur === "N/A" ? null : Number(cur);

  fetch(`/api/valuation?ticker=${encodeURIComponent(ticker)}`)
    .then((r) => r.json())
    .then((v) => {
      if (v.error) {
        valBox.innerHTML = `<p style="color:red;">❌ valuation error: ${v.error}</p>`;
        return;
      }

      const myOk = v.my_model?.ok;
      const myFair = myOk ? Number(v.my_model.fair_price) : null;

      const tMean = v.finnhub_target?.targetMean != null ? Number(v.finnhub_target.targetMean) : null;
      const tHigh = v.finnhub_target?.targetHigh != null ? Number(v.finnhub_target.targetHigh) : null;
      const tLow = v.finnhub_target?.targetLow != null ? Number(v.finnhub_target.targetLow) : null;

      function upsidePct(target) {
        if (curNum == null || !isFinite(curNum) || target == null || !isFinite(target) || curNum === 0) return null;
        return ((target - curNum) / curNum) * 100.0;
      }

      const upMy = upsidePct(myFair);
      const upMean = upsidePct(tMean);

      const fmt = (x) => (x == null || !isFinite(x) ? "N/A" : x.toLocaleString(undefined, { maximumFractionDigits: 2 }));
      const fmtPct = (x) => (x == null || !isFinite(x) ? "N/A" : `${x >= 0 ? "+" : ""}${x.toFixed(1)}%`);

      valBox.innerHTML = `
        <hr>
        <h5>🧠 적정주가/목표가 비교</h5>
        <div style="display:grid; grid-template-columns: 1fr 1fr; gap: 10px;">
          <div class="card">
            <div class="card-title">내 모델 적정주가 (EV/발행주식수)</div>
            <div class="card-value">$${fmt(myFair)}</div>
            <div class="card-sub">현재가 대비: ${fmtPct(upMy)}</div>
          </div>
          <div class="card">
            <div class="card-title">Finnhub 목표가(평균)</div>
            <div class="card-value">$${fmt(tMean)}</div>
            <div class="card-sub">현재가 대비: ${fmtPct(upMean)}</div>
          </div>
        </div>
        <div style="margin-top:8px; font-size:12px; opacity:0.8;">
          Finnhub 범위: low $${fmt(tLow)} / high $${fmt(tHigh)}
        </div>
      `;
    })
    .catch((err) => {
      console.error("valuation fetch error:", err);
      valBox.innerHTML = `<p style="color:red;">❌ valuation fetch failed</p>`;
    });
}

function renderKisCandleChart(root, ticker) {
  const chartDiv = document.createElement("div");
  chartDiv.id = "kis-candle-chart";
  chartDiv.style.height = "500px";
  chartDiv.style.marginTop = "20px";
  chartDiv.innerHTML = `<span id="kis-loading-text">🔄 KIS 캔들차트 로딩중...</span>`;
  root.appendChild(chartDiv);

  fetch(`/get_stock_chart_kis?ticker=${encodeURIComponent(ticker)}&exchange=NAS`)
    .then((r) => r.json())
    .then((kis) => {
      if (kis.error) {
        chartDiv.innerHTML = `<p style="color:red;">KIS 데이터 불러오기 실패: ${kis.error}</p>`;
        return;
      }

      const ohlc = kis.ohlc || [];
      const dates = ohlc.map((x) => `${x.date.slice(0, 4)}-${x.date.slice(4, 6)}-${x.date.slice(6, 8)}`);
      const opens = ohlc.map((x) => x.open);
      const highs = ohlc.map((x) => x.high);
      const lows = ohlc.map((x) => x.low);
      const closes = ohlc.map((x) => x.close);
      const vols = ohlc.map((x) => x.volume);

      Plotly.newPlot(
        "kis-candle-chart",
        [
          { x: dates, open: opens, high: highs, low: lows, close: closes, type: "candlestick", name: "Price", xaxis: "x", yaxis: "y" },
          { x: dates, y: vols, type: "bar", name: "Volume", xaxis: "x", yaxis: "y2", marker: { color: "rgba(128,128,128,0.4)" } },
        ],
        {
          title: `${ticker} 캔들차트 (KIS API)`,
          xaxis: { title: "날짜", rangeslider: { visible: false } },
          yaxis: { title: "가격", domain: [0.3, 1] },
          yaxis2: { title: "거래량", domain: [0, 0.2], showticklabels: true },
          height: 500,
          margin: { t: 40, b: 50 },
          showlegend: false,
        },
        { responsive: true }
      ).then(() => {
        $("kis-loading-text")?.remove();
      });
    })
    .catch((err) => {
      console.error("KIS fetch error:", err);
      chartDiv.innerHTML = `<p style="color:red;">KIS 캔들차트 로드 실패</p>`;
    });
}

// -------------------- Privacy Toggle --------------------
function setupPrivacyToggle() {
  const btn = $("toggle-privacy-btn");
  if (!btn) return;

  let hidden = false;
  btn.addEventListener("click", () => {
    document.querySelectorAll(".privacy-sensitive").forEach((el) => {
      el.style.visibility = hidden ? "visible" : "hidden";
    });
    btn.textContent = hidden ? "🔒 정보 숨기기" : "🔓 정보 보이기";
    hidden = !hidden;
  });
}

// -------------------- Market Cards --------------------
async function loadMarketCards() {
  try {
    const [resIdx, resPanic] = await Promise.all([fetch("/api/market/indices"), fetch("/api/market/panic")]);

    const data = await resIdx.json();
    const panic = await resPanic.json();

    // panic 카드 합치기
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

    const root = $("market-cards");
    if (!root) return;

    const cards = Object.values(data)
      .map((item) => {
        if (item?.kind === "panic") {
          if (!item.ok) {
            return `
              <div class="card">
                <div class="card-title">${item.label}</div>
                <div class="card-value">N/A</div>
                <div class="card-sub">data unavailable</div>
              </div>`;
          }

          const levelText =
            item.level === "panic" ? "🚨 PANIC" : item.level === "watch" ? "⚠️ WATCH" : "✅ OK";

          return `
            <div class="card">
              <div class="card-title">${item.label}</div>
              <div class="card-value">${levelText}</div>
              <div class="card-sub">${item.window_days}d 중 ${item.threshold}%↓ : ${item.count}회</div>
            </div>`;
        }

        if (!item.ok) {
          return `
            <div class="card">
              <div class="card-title">${item.label}</div>
              <div class="card-value">N/A</div>
              <div class="card-sub">data unavailable</div>
            </div>`;
        }

        const sign = item.change_pct >= 0 ? "+" : "";
        return `
          <div class="card">
            <div class="card-title">${item.label}</div>
            <div class="card-value">${toLocaleNum(item.last)}</div>
            <div class="card-sub">${sign}${Number(item.change_pct).toFixed(2)}%</div>
          </div>`;
      })
      .join("");

    root.innerHTML = cards;
  } catch (e) {
    console.error("loadMarketCards failed", e);
  }
}

// -------------------- PnL (date detail) --------------------
function renderPnlSummary(p) {
  const root = $("pnl-summary");
  if (!root) return;

  const sum = p.summary?.realized_sum ?? 0;
  const cnt = p.summary?.realized_count ?? 0;
  const win = p.summary?.win ?? 0;
  const loss = p.summary?.loss ?? 0;

  const cards = [
    { label: "실현 손익 합", value: `${toLocaleNum(sum)} KRW`, sub: `이벤트 ${cnt}건` },
    { label: "승/패", value: `${win} / ${loss}`, sub: "전량매도 기준" },
    { label: "기준 날짜", value: `${p.asof_date}`, sub: "스냅샷 기준" },
  ];

  root.innerHTML = cards
    .map(
      (c) => `
      <div class="card">
        <div class="card-title">${c.label}</div>
        <div class="card-value">${c.value}</div>
        <div class="card-sub">${c.sub}</div>
      </div>
    `
    )
    .join("");
}

function loadPnlForDate(date) {
  const openBody = $("open-pnl-body");
  const realBody = $("realized-pnl-body");

  if (openBody) openBody.innerHTML = `<tr><td colspan="8">로딩중...</td></tr>`;
  if (realBody) realBody.innerHTML = `<tr><td colspan="7">로딩중...</td></tr>`;

  fetch(`/api/pnl?date=${encodeURIComponent(date)}`)
    .then((r) => r.json())
    .then((p) => {
      if (p.error) {
        if (openBody) openBody.innerHTML = `<tr><td colspan="8" style="color:red;">❌ ${p.error}</td></tr>`;
        if (realBody) realBody.innerHTML = `<tr><td colspan="7" style="color:red;">❌ ${p.error}</td></tr>`;
        return;
      }

      renderPnlSummary(p);

      // open positions
      if (openBody) {
        const rows = p.open_positions || [];
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
                <td>${toLocaleNum(x.qty)}</td>
                <td>${toLocaleNum(x.buy_amount)}</td>
                <td>${toLocaleNum(x.eval_amount)}</td>
                <td style="color:${color}; font-weight:600;">${toLocaleNum(pnl)}</td>
                <td style="color:${color}; font-weight:600;">${Number(x.pnl_pct || 0).toFixed(2)}%</td>
              </tr>
            `
            );
          });
        }
      }

      // realized
      if (realBody) {
        const rows = p.realized || [];
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
                <td style="color:${color}; font-weight:600;">${toLocaleNum(pnl)}</td>
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
      if (openBody) openBody.innerHTML = `<tr><td colspan="8" style="color:red;">❌ pnl fetch failed</td></tr>`;
      if (realBody) realBody.innerHTML = `<tr><td colspan="7" style="color:red;">❌ pnl fetch failed</td></tr>`;
    });
}

// -------------------- PnL Panel (overall chart + events list) --------------------
function loadPnlPanel() {
  loadJsonAndRender("/api/pnl", (data) => {
    if (data?.error) {
      console.error("pnl api error", data.error);
      return;
    }
    if (!data?.ok) {
      console.error("pnl api not ok", data);
      return;
    }

    const dates = Array.isArray(data.dates) ? data.dates : [];
    if (dates.length === 0) {
      console.warn("pnl dates empty");
      Plotly.purge("pnl-chart");
      return;
    }

    // 숫자 배열로 안전 변환 (문자열/undefined 대비)
    const toNumArr = (arr) =>
      (Array.isArray(arr) ? arr : []).map(v => {
        const n = Number(v);
        return Number.isFinite(n) ? n : 0;
      });

    const unreal = toNumArr(data.unrealized_pnl);
    const realCum = toNumArr(data.realized_pnl_cum);

    // 길이 맞추기(안 맞으면 잘라서 맞춤)
    const n = dates.length;
    const u = unreal.slice(0, n);
    const rc = realCum.slice(0, n);

    // ✅ 누적(realCum) → 일별(realDaily)로 변환(스택바용)
    const realDaily = rc.map((val, i) => (i === 0 ? val : (val - rc[i - 1])));

    // ✅ 스택바(Realized daily + Unrealized)
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

    // (선택) 누적 실현손익 라인도 같이 보고 싶으면 켜기
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
      barmode: "relative", // ✅ 양/음수도 자연스럽게 위아래로 스택
      xaxis: { title: "Date", automargin: true },
      yaxis: { title: "KRW", automargin: true, zeroline: true },
      // (선택) 누적 실현손익 라인 같이 보기용 우측축
      yaxis2: { title: "Realized Cum (KRW)", overlaying: "y", side: "right", showgrid: false },
      margin: { t: 40, r: 50, l: 50, b: 40 },
      legend: { orientation: "h" },
    };

    // ✅ 라인까지 같이 그릴지 결정:
    const traces = [traceUnrealBar, traceRealDailyBar, traceRealCumLine]; // 라인 포함
    // const traces = [traceUnrealBar, traceRealDailyBar]; // 라인 빼고 “스택바만” 원하면 이걸로

    Plotly.newPlot("pnl-chart", traces, layout, { responsive: true });

    // ---- Events table ----
    renderPnlEvents(data.events || []);
  });
}

function renderPnlEvents(events) {
  const tbody = $("pnl-events-body");
  if (!tbody) return;

  const list = (events || []).slice().reverse().slice(0, 30);

  if (list.length === 0) {
    tbody.innerHTML = `<tr><td colspan="5">매도 이벤트(추정)가 아직 없습니다.</td></tr>`;
    return;
  }

  tbody.innerHTML = "";
  list.forEach((e) => {
    const pnl = Number(e.approx_realized_pnl || 0);
    const color = pnl >= 0 ? "red" : "blue";
    const kindLabel = e.kind === "sell_all" ? "전량매도(추정)" : "부분매도(추정)";

    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${e.date || ""}</td>
      <td>${e.name || ""}</td>
      <td>${kindLabel}</td>
      <td>${toLocaleNum(e.sold_qty)}</td>
      <td style="color:${color}; font-weight:600;">${toLocaleNum(pnl)}</td>
    `;
    tbody.appendChild(tr);
  });
}